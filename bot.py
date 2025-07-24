#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Standard library imports
import asyncio
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone, timedelta, time as dt_time
from functools import wraps
from typing import Any, Callable, Optional

# Third-party imports
import discord
import keyboard
from discord.ext import commands, tasks
from discord.ui import View, Button
from dotenv import load_dotenv
from loguru import logger

# Local application imports
import config
from omegle import OmegleHandler
from helper import BotHelper
from tools import (
    BotConfig,
    BotState,
    build_embed,
    build_role_update_embed,
    handle_errors,
    record_command_usage,
    record_command_usage_by_user,
)

# Load environment variables from the .env file
load_dotenv()

# --- INITIALIZATION ---
# Load configuration from the config.py module into a structured dataclass
bot_config = BotConfig.from_config_module(config)
# Initialize the bot's state management object
state = BotState(config=bot_config)
# Initialize the handler for Selenium-based browser automation
omegle_handler = OmegleHandler(bot_config)

# Initialize the Discord bot instance with required intents
intents = discord.Intents.default()
intents.message_content = True  # Required for reading message content
intents.members = True          # Required for tracking member updates (joins, roles, etc.)
bot = commands.Bot(command_prefix="!", help_command=None, intents=intents)
bot.state = state # Attach the state object to the bot instance for global access in cogs/decorators

# --- CONSTANTS ---
STATE_FILE = "data.json" # File name for saving and loading the bot's state

#########################################
# Persistence Functions
#########################################

@tasks.loop(minutes=59)
async def periodic_cleanup():
    """
    A background task that runs periodically to clean up old data from the bot's state.
    This includes trimming old event histories and expired cooldowns to manage memory usage.
    """
    try:
        await state.clean_old_entries()
        logger.info("Unified cleanup completed (7-day history/entry limits)")
    except Exception as e:
        logger.error(f"Cleanup error: {e}", exc_info=True)

def _save_state_sync(file_path: str, data: dict) -> None:
    """
    A synchronous helper function to write the bot's state data to a JSON file.
    This is designed to be run in a separate thread to avoid blocking the bot's event loop.
    """
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def _load_state_sync(file_path: str) -> dict:
    """
    A synchronous helper function to read the bot's state data from a JSON file.
    This is designed to be run in a separate thread to avoid blocking the bot's event loop.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

async def save_state_async() -> None:
    """
    Asynchronously saves the current bot state to disk.
    It gathers all necessary data, serializes it, and writes to a file
    using a non-blocking thread for the file I/O operation.
    """
    serializable_state = {}
    current_time = time.time()

    # Acquire all necessary locks before reading state data to ensure thread safety and prevent race conditions.
    async with state.vc_lock, state.analytics_lock, state.moderation_lock:
        active_vc_sessions_copy = state.active_vc_sessions.copy()
        
        # The complex serialization logic is encapsulated within the BotState class's `to_dict` method.
        serializable_state = state.to_dict(
            guild=bot.get_guild(bot_config.GUILD_ID),
            active_vc_sessions_to_save=active_vc_sessions_copy,
            current_time=current_time
        )

    try:
        # Run the blocking file I/O in a separate thread to avoid halting the async event loop.
        if serializable_state:
            await asyncio.to_thread(_save_state_sync, STATE_FILE, serializable_state)
            logger.info("Bot state saved, including active VC sessions.")
    except Exception as e:
        logger.error(f"Failed to save bot state: {e}", exc_info=True)

async def load_state_async() -> None:
    """
    Asynchronously loads the bot state from the JSON file if it exists.
    If loading fails or the file doesn't exist, it initializes a fresh state.
    """
    global state
    if os.path.exists(STATE_FILE):
        try:
            # Run the blocking file I/O in a separate thread.
            data = await asyncio.to_thread(_load_state_sync, STATE_FILE)
            # Deserialize the data into a BotState object.
            state = BotState.from_dict(data, bot_config)
            bot.state = state # Re-attach the newly loaded state to the bot.
            helper.state = state # Ensure the helper also gets the newly loaded state object.
            logger.info("Bot state loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load bot state: {e}", exc_info=True)
            # If loading fails, start with a fresh state to ensure bot functionality.
            state = BotState(config=bot_config)
            bot.state = state
    else:
        logger.info("No saved state file found, starting with a fresh state.")
        state = BotState(config=bot_config)
        bot.state = state
        helper.state = state # Ensure helper state is also updated on a fresh start.

# Initialize the helper class AFTER the initial state object is created but BEFORE it might be replaced by `load_state_async`.
helper = BotHelper(bot, state, bot_config, save_state_async)

@tasks.loop(minutes=14)
async def periodic_state_save() -> None:
    """A background task that periodically saves the bot's state to ensure data is not lost on crash."""
    await save_state_async()

#########################################
# Voice Connection Functions
#########################################

def is_user_in_streaming_vc_with_camera(user: discord.Member) -> bool:
    """Checks if a given user is in the designated streaming voice channel with their camera enabled."""
    streaming_vc = user.guild.get_channel(bot_config.STREAMING_VC_ID)
    # Returns True only if the user is in the VC and their self_video attribute is True.
    return bool(streaming_vc and user in streaming_vc.members and user.voice and user.voice.self_video)

async def global_skip() -> None:
    """
    Executes a skip command triggered by a global hotkey press on the host machine.
    This allows for control of the Omegle stream without needing to be in the Discord window.
    """
    guild = bot.get_guild(bot_config.GUILD_ID)
    if guild:
        await omegle_handler.custom_skip()
        logger.info("Executed global skip command via hotkey.")
    else:
        logger.error("Guild not found for global skip.")

#########################################
# Decorators
#########################################

def omegle_command_cooldown(func: Callable) -> Callable:
    """A decorator to apply a global 5-second cooldown to Omegle commands."""
    @wraps(func)
    async def wrapper(ctx, *args, **kwargs):
        current_time = time.time()
        # Use a lock to ensure thread-safe access to the shared cooldown timestamp
        async with state.cooldown_lock:
            time_since_last_cmd = current_time - state.last_omegle_command_time
            # Using 5.0 to make it a float operation
            if time_since_last_cmd < 5.0:
                # Attempt to delete the message that triggered the command
                try:
                    await ctx.message.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass  # Ignore if we can't delete it (e.g., missing permissions)

                # Send a cooldown message that self-deletes
                await ctx.send(
                    f"{ctx.author.mention}, please wait {5.0 - time_since_last_cmd:.1f} more seconds before using this command again.",
                    delete_after=5
                )
                return
            # Update the timestamp if the command is allowed to proceed
            state.last_omegle_command_time = current_time
        
        # If cooldown check passes, execute the original command function
        return await func(ctx, *args, **kwargs)
    return wrapper

def require_command_channel(func: Callable) -> Callable:
    """
    A decorator that restricts command usage to a specific channel for non-admin users.
    This helps keep the general chat clean.
    """
    @wraps(func)
    async def wrapper(ctx, *args, **kwargs):
        # Admins (ALLOWED_USERS) can use commands anywhere.
        if ctx.author.id not in bot_config.ALLOWED_USERS and ctx.channel.id != bot_config.COMMAND_CHANNEL_ID:
            await ctx.send(f"All commands (including !{func.__name__}) should be used in <#{bot_config.COMMAND_CHANNEL_ID}>")
            return # Stop command execution.
        return await func(ctx, *args, **kwargs)
    return wrapper

def require_camera_or_allowed_user():
    """
    A decorator factory for commands. It creates a check that ensures the user
    is either an admin or is in the streaming VC with their camera on.
    This is used for commands that control the Omegle stream.
    """
    async def predicate(ctx):
        if ctx.author.id in bot_config.ALLOWED_USERS or is_user_in_streaming_vc_with_camera(ctx.author):
            return True # User meets requirements.
        # User does not meet requirements, send an error message.
        await ctx.send("You must be in the Streaming VC with your camera on to use this command.")
        return False
    return commands.check(predicate)

def require_admin_or_allowed():
    """
    A decorator factory for commands. It creates a check that ensures the user
    is either in the ALLOWED_USERS list or has a configured admin role.
    This is used for sensitive or moderation-related commands.
    """
    async def predicate(ctx):
        # Check if user ID is in the explicit list of allowed users.
        if ctx.author.id in bot_config.ALLOWED_USERS:
            return True
        # Check if the user has any of the designated admin roles.
        if isinstance(ctx.author, discord.Member) and any(role.name in bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles):
            return True
        
        # If neither check passes, deny permission.
        await ctx.send("⛔ You do not have permission to use this command.")
        return False
    return commands.check(predicate)

#########################################
# Background Task Helpers
#########################################

async def _handle_stream_vc_join(member: discord.Member):
    """
    A helper function to handle the logic when a user joins the streaming VC.
    It attempts to send them the server rules via DM.
    Decoupled from the main event handler to allow it to run as a separate task.
    """
    # Check if we have already sent rules, if their DMs are closed, or if a DM has failed before to avoid spam/errors.
    async with state.moderation_lock:
        if (member.id in state.users_received_rules or
            member.id in state.users_with_dms_disabled or
            member.id in state.failed_dm_users):
            return

    # Attempt to send the rules message.
    try:
        await member.send(bot_config.RULES_MESSAGE)
        async with state.moderation_lock:
            state.users_received_rules.add(member.id)
        logger.info(f"Sent rules to {member.display_name}")
    except discord.Forbidden: # This error means the user has DMs disabled or has blocked the bot.
        async with state.moderation_lock:
            state.users_with_dms_disabled.add(member.id)
            state.failed_dm_users.add(member.id)
        logger.warning(f"Could not DM {member.display_name} (DMs disabled or blocked).")
    except Exception as e: # Catch any other potential errors.
        async with state.moderation_lock:
            state.failed_dm_users.add(member.id)
        logger.error(f"Generic error sending DM to {member.name}: {e}", exc_info=True)


async def _check_for_auto_pause(vc: discord.VoiceChannel, reason: str):
    """

    Checks if the conditions for an automatic stream refresh (pause) are met.
    This is typically triggered when the last user with a camera leaves or turns it off.
    """
    if not vc: return

    # Find all non-admin users in the VC who currently have their camera on.
    users_with_camera = [m for m in vc.members if m.voice and m.voice.self_video and m.id not in bot_config.ALLOWED_USERS and not m.bot]

    async with state.vc_lock:
        # If there are no users with cameras on and a cooldown has passed since the last auto-action.
        if not users_with_camera and (time.time() - state.last_auto_pause_time >= 1):
            state.last_auto_pause_time = time.time() # Update the timestamp to prevent rapid-fire triggers.
            should_refresh = True
        else:
            should_refresh = False

    if should_refresh:
        await omegle_handler.refresh()
        logger.info(reason)
        # Notify the command channel that an automatic action was taken.
        if (command_channel := vc.guild.get_channel(bot_config.COMMAND_CHANNEL_ID)):
            try:
                await command_channel.send("Stream automatically paused")
            except Exception as e:
                logger.error(f"Failed to send auto-refresh notification: {e}")

#########################################
# Bot Event Handlers
#########################################

@bot.event
async def on_ready() -> None:
    """
    The primary event handler that runs once the bot successfully connects to Discord.
    It initializes all background tasks, loads saved state, and sets up systems like hotkeys.
    """
    logger.info(f"Bot is online as {bot.user}")

    # Send an "online" message to a designated channel.
    try:
        channel = bot.get_channel(bot_config.CHAT_CHANNEL_ID)
        if channel:
            await channel.send("✅ Bot is online and ready!")
    except Exception as e:
        logger.error(f"Failed to send online message: {e}")

    # Load the previously saved bot state.
    try:
        await load_state_async()
        logger.info("State loaded successfully")
    except Exception as e:
        logger.error(f"Error loading state: {e}", exc_info=True)

    try:
        # Start all periodic background tasks if they are not already running.
        if not periodic_state_save.is_running(): periodic_state_save.start()
        if not periodic_cleanup.is_running(): periodic_cleanup.start()
        if not periodic_help_menu.is_running(): periodic_help_menu.start()
        if not timeout_unauthorized_users_task.is_running(): timeout_unauthorized_users_task.start()
        if not daily_auto_stats_clear.is_running():
            daily_auto_stats_clear.start()
            logger.info("Daily auto-stats task started")

        # Initialize the Selenium browser controller.
        if not await omegle_handler.initialize():
            logger.critical("Selenium initialization failed. Browser commands will not work until bot restart.")

        async def init_vc_moderation():
            """A sub-function to set up initial VC moderation state for users already present at startup."""
            async with state.vc_lock:
                is_active = state.vc_moderation_active
            
            if not is_active:
                logger.warning("VC Moderation is disabled on startup.")
                return

            guild = bot.get_guild(bot_config.GUILD_ID)
            if not guild: return
            streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
            if not streaming_vc: return

            async with state.vc_lock:
                for member in streaming_vc.members:
                    # Start tracking VC time for members who were already in the channel when the bot started.
                    if not member.bot and member.id not in state.active_vc_sessions:
                        state.active_vc_sessions[member.id] = time.time()
                        logger.info(f"Started tracking VC time for existing member: {member.name} (ID: {member.id})")

                    # Apply initial mute/deafen to non-admins who are in the VC without a camera on.
                    if (not member.bot and member.id not in bot_config.ALLOWED_USERS and member.id != bot_config.MUSIC_BOT and not (member.voice and member.voice.self_video)):
                        try:
                            await asyncio.sleep(1) # Add delay before muting
                            await member.edit(mute=True, deafen=True)
                            logger.info(f"Auto-muted/deafened {member.name} for camera off.")
                        except Exception as e:
                            logger.error(f"Failed to auto mute/deafen {member.name}: {e}")
                        # Start the camera-off timer for them.
                        state.camera_off_timers[member.id] = time.time()

        # Run the VC moderation setup as a separate task.
        asyncio.create_task(init_vc_moderation())

        # Set up the global hotkey if enabled in the config.
        if bot_config.ENABLE_GLOBAL_HOTKEY:
            try:
                # FIX: Run blocking keyboard calls in a separate thread
                await asyncio.to_thread(keyboard.remove_hotkey, bot_config.GLOBAL_HOTKEY_COMBINATION)
            except (KeyError, ValueError): pass # Ignore errors if hotkey wasn't registered before.

            def hotkey_callback() -> None:
                """The function that gets called when the hotkey is pressed."""
                logger.info("Global hotkey pressed, triggering skip command.")
                # Since this callback runs in a separate thread, we must use `call_soon_threadsafe`
                # to safely schedule the async `global_skip` function on the bot's event loop.
                bot.loop.call_soon_threadsafe(lambda: asyncio.create_task(global_skip()))

            try:
                # FIX: Run blocking keyboard calls in a separate thread
                await asyncio.to_thread(keyboard.add_hotkey, bot_config.GLOBAL_HOTKEY_COMBINATION, hotkey_callback)
                logger.info(f"Registered global hotkey: {bot_config.GLOBAL_HOTKEY_COMBINATION}")
            except Exception as e:
                logger.error(f"Failed to register hotkey: {e}")
                bot_config.ENABLE_GLOBAL_HOTKEY = False
                logger.warning("Global hotkey functionality disabled due to registration failure")

        logger.info("Initialization complete")

    except Exception as e:
        logger.error(f"Error during on_ready: {e}", exc_info=True)

# --- Member Event Handlers ---
# These events are delegated to the BotHelper class to keep this file cleaner.

@bot.event
@handle_errors
async def on_member_join(member: discord.Member) -> None:
    """Handles new members joining the server."""
    await helper.handle_member_join(member)

@bot.event
@handle_errors
async def on_member_ban(guild: discord.Guild, user: discord.User) -> None:
    """Handles a user being banned from the server."""
    await helper.handle_member_ban(guild, user)

@bot.event
@handle_errors
async def on_member_unban(guild: discord.Guild, user: discord.User) -> None:
    """Handles a user being unbanned from the server."""
    await helper.handle_member_unban(guild, user)

@bot.event
@handle_errors
async def on_member_remove(member: discord.Member) -> None:
    """Handles a member leaving or being kicked/banned from the server."""
    await helper.handle_member_remove(member)

@bot.event
@handle_errors # Custom decorator for logging errors
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
    """
    Handles all updates to a member's voice state.
    This is a critical event for tracking VC time, enforcing camera rules, and auto-pausing the stream.
    """
    if member.bot: # Ignore bots
        return

    # --- Determine which moderated VC (if any) the user was in and is now in ---
    is_in_moderated_vc = lambda ch: ch and ch.id in (bot_config.STREAMING_VC_ID, bot_config.ALT_VC_ID)
    was_in_mod_vc = is_in_moderated_vc(before.channel)
    is_now_in_mod_vc = is_in_moderated_vc(after.channel)

    # --- Fast Operations: VC Time Tracking for Stats (Main Streaming VC only) ---
    was_in_streaming_vc = before.channel and before.channel.id == bot_config.STREAMING_VC_ID
    is_now_in_streaming_vc = after.channel and after.channel.id == bot_config.STREAMING_VC_ID

    async with state.vc_lock:
        # User joined the streaming VC
        if is_now_in_streaming_vc and not was_in_streaming_vc:
            if member.id not in state.active_vc_sessions:
                state.active_vc_sessions[member.id] = time.time()
                # Initialize user's time data if they are new.
                if member.id not in state.vc_time_data:
                    state.vc_time_data[member.id] = {"total_time": 0, "sessions": [], "username": member.name, "display_name": member.display_name}
                logger.info(f"VC Time Tracking: {member.display_name} started session.")
        
        # User left the streaming VC
        elif was_in_streaming_vc and not is_now_in_streaming_vc:
            if member.id in state.active_vc_sessions:
                start_time = state.active_vc_sessions.pop(member.id)
                duration = time.time() - start_time
                if member.id in state.vc_time_data:
                    # Add the completed session's duration to their total time.
                    state.vc_time_data[member.id]["total_time"] += duration
                    state.vc_time_data[member.id]["sessions"].append({"start": start_time, "end": time.time(), "duration": duration, "vc_name": before.channel.name})
                    logger.info(f"VC Time Tracking: {member.display_name} ended session, adding {duration:.1f}s.")

    # --- Moderation and Other Logic (Slower Operations Decoupled via asyncio.create_task) ---
    async with state.vc_lock:
        is_mod_active = state.vc_moderation_active
        is_hush_active = state.hush_override_active
        
    if is_mod_active:
        # Case 1: User joined a moderated VC from no VC or another VC.
        if is_now_in_mod_vc and not was_in_mod_vc:
            if after.channel.id == bot_config.STREAMING_VC_ID:
                asyncio.create_task(_handle_stream_vc_join(member))

            # For non-admins, handle the join with a grace period for soundboards.
            if member.id not in bot_config.ALLOWED_USERS:
                # --- START FIX ---
                # 1. Immediately start the camera-off timer upon join.
                #    This timer acts as the grace period. If the camera turns on,
                #    the existing 'camera_turned_on' logic will correctly remove it.
                async with state.vc_lock:
                    state.camera_off_timers[member.id] = time.time()
                    logger.info(f"Started camera grace period timer for {member.name}.")

                # 2. Spawn a SEPARATE task that ONLY handles the temporary unmute for soundboards.
                #    This task will no longer touch any punishment timers.
                async def soundboard_grace_protocol(m: discord.Member):
                    try:
                        # Unmute to allow soundboard
                        if m.voice and (m.voice.mute or m.voice.deaf):
                            await m.edit(mute=False, deafen=False)
                    except Exception:
                        pass # Ignore if user leaves quickly

                    await asyncio.sleep(2.0) # Slightly longer grace period

                    # Re-check state after grace period
                    # We need to re-acquire the member object to get the latest voice state
                    guild = m.guild
                    if not guild: return
                    member_after_sleep = guild.get_member(m.id)

                    if (member_after_sleep and member_after_sleep.voice and
                            member_after_sleep.voice.channel and is_in_moderated_vc(member_after_sleep.voice.channel)
                            and not member_after_sleep.voice.self_video):
                        try:
                            # If camera is still off, re-apply mute/deafen.
                            await member_after_sleep.edit(mute=True, deafen=True)
                            logger.info(f"Re-applied mute/deafen for {m.name} after soundboard grace period.")
                        except Exception as e:
                            logger.error(f"Failed to re-mute {m.name} after grace period: {e}")

                asyncio.create_task(soundboard_grace_protocol(member))
                # --- END FIX ---


        # Case 2: User left a moderated VC for a non-moderated one.
        elif was_in_mod_vc and not is_now_in_mod_vc:
            # Clean up their camera-off timer.
            async with state.vc_lock:
                state.camera_off_timers.pop(member.id, None)
            if before.channel.id == bot_config.STREAMING_VC_ID:
                 # Check if the stream should be auto-paused now that they've left.
                 asyncio.create_task(_check_for_auto_pause(before.channel, "Auto Refreshed - User with camera left"))

        # Case 3: User changed state (e.g., toggled camera or moved between moderated VCs).
        elif was_in_mod_vc and is_now_in_mod_vc:
            camera_turned_on = not before.self_video and after.self_video
            camera_turned_off = before.self_video and not after.self_video

            if member.id not in bot_config.ALLOWED_USERS:
                if camera_turned_off:
                    # Start penalty timer and mute/deafen.
                    async with state.vc_lock:
                        state.camera_off_timers[member.id] = time.time()
                    try:
                        # NO DELAY when turning camera off
                        await member.edit(mute=True, deafen=True)
                        logger.info(f"Auto-muted/deafened {member.name} for turning camera off.")
                    except Exception as e:
                        logger.error(f"Failed to auto-mute {member.name}: {e}")
                    # Check for auto-pause.
                    if after.channel.id == bot_config.STREAMING_VC_ID:
                        asyncio.create_task(_check_for_auto_pause(after.channel, "Auto Refreshed - Camera Turned Off"))

                elif camera_turned_on:
                    # Stop penalty timer and unmute/undeafen.
                    async with state.vc_lock:
                        state.camera_off_timers.pop(member.id, None)
                    # The `hush` command can override this unmute.
                    if not is_hush_active:
                        try:
                            await member.edit(mute=False, deafen=False)
                            logger.info(f"Auto-unmuted {member.name} after turning camera on.")
                        except Exception as e:
                            logger.error(f"Failed to auto-unmute {member.name}: {e}")
            
            # **FIX:** Check for auto-pause if the user moved OUT of the streaming VC into another moderated VC
            if before.channel.id == bot_config.STREAMING_VC_ID and after.channel.id != bot_config.STREAMING_VC_ID:
                asyncio.create_task(_check_for_auto_pause(before.channel, f"Auto Refreshed - {member.display_name} moved from streaming VC"))


    # --- Other VC Logic ---
    # Revert server mutes/deafens on admin users to prevent them from being accidentally silenced.
    if is_now_in_mod_vc and member.id in bot_config.ALLOWED_USERS:
        if member.voice and ((member.voice.mute and not member.voice.self_mute) or (member.voice.deaf and not member.voice.self_deaf)):
            try:
                await member.edit(mute=False, deafen=False)
                logger.info(f"Reverted server mute/deafen for allowed user {member.display_name}")
            except Exception as e:
                logger.error(f"Failed to revert mute/deafen for {member.name}: {e}")

    # Automatically unmute users who are moved to the designated punishment VC.
    if after.channel and after.channel.id == bot_config.PUNISHMENT_VC_ID:
        if member.voice and (member.voice.mute or member.voice.deaf):
            try:
                await member.edit(mute=False, deafen=False)
                logger.info(f"Automatically unmuted/undeafened {member.name} in Punishment VC.")
            except Exception as e:
                logger.error(f"Failed to unmute/undeafen {member.name} in Punishment VC: {e}")

@bot.event
@handle_errors
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    """Handles member updates, specifically for role changes and timeouts."""
    # --- Role change notifications ---
    if before.roles != after.roles:
        roles_gained = [role for role in after.roles if role not in before.roles and role.name != "@everyone"]
        roles_lost = [role for role in before.roles if role not in after.roles and role.name != "@everyone"]
        
        if roles_gained or roles_lost:
            # Log the event for the !whois command
            async with state.moderation_lock:
                state.recent_role_changes.append((
                    after.id,
                    after.name,
                    [r.name for r in roles_gained],
                    [r.name for r in roles_lost],
                    datetime.now(timezone.utc)
                ))
            
            # Send a public notification
            channel = after.guild.get_channel(bot_config.CHAT_CHANNEL_ID)
            if channel:
                embed = await build_role_update_embed(after, roles_gained, roles_lost)
                await channel.send(embed=embed)

    # --- Timeout added/removed notifications ---
    if before.is_timed_out() != after.is_timed_out():
        if after.is_timed_out():
            # User was timed out. We need to check the audit log to see who did it and for how long.
            async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                # Find the specific log entry for this timeout event.
                if entry.target.id == after.id and hasattr(entry.after, "timed_out_until") and entry.after.timed_out_until is not None:
                    duration = (entry.after.timed_out_until - datetime.now(timezone.utc)).total_seconds()
                    reason = entry.reason or "No reason provided"
                    moderator = entry.user

                    # Send a public notification and log the timeout in the bot's state.
                    await helper.send_timeout_notification(after, moderator, int(duration), reason)
                    await helper._log_timeout_in_state(after, int(duration), reason, moderator.name, moderator.id)
                    break
        else:
            # User's timeout was removed.
            async with state.moderation_lock:
                # Use a pending removal flag to prevent duplicate notifications from race conditions.
                if after.id in state.pending_timeout_removals:
                    return
                state.pending_timeout_removals[after.id] = True

            try:
                moderator_name = "System"
                moderator_id = None
                reason = "Timeout Expired Naturally"
                found_log = False

                # Poll the audit log for a few seconds to see if a moderator manually removed the timeout.
                for _ in range(5): # Poll for up to 5 seconds
                    try:
                        async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update, after=datetime.now(timezone.utc) - timedelta(seconds=15)):
                            # This checks for the specific change from being timed out to not being timed out.
                            if (entry.target.id == after.id and
                                getattr(entry.before, "timed_out_until") is not None and
                                getattr(entry.after, "timed_out_until") is None):
                                moderator_name = entry.user.name
                                moderator_id = entry.user.id
                                reason = f"Manually removed by 🛡️ {moderator_name}"
                                found_log = True
                                break
                        if found_log:
                            break
                    except discord.Forbidden:
                        logger.warning("Cannot check audit logs for un-timeout (Missing Permissions).")
                        break
                    except Exception as e:
                        logger.error(f"Error checking audit logs for un-timeout: {e}")
                    await asyncio.sleep(1) # Wait before polling again.

                # Update the state with the un-timeout information.
                async with state.moderation_lock:
                    start_timestamp = state.active_timeouts.get(after.id, {}).get("start_timestamp", time.time())
                    duration = int(time.time() - start_timestamp)

                    state.recent_untimeouts.append((after.id, after.name, after.display_name, datetime.now(timezone.utc), reason, moderator_name, moderator_id))
                    if len(state.recent_untimeouts) > 100:
                        state.recent_untimeouts.pop(0)

                    state.active_timeouts.pop(after.id, None)

                # Send a public notification about the removal.
                await helper.send_timeout_removal_notification(after, duration, reason)

            finally:
                # Clean up the pending removal flag.
                async with state.moderation_lock:
                    state.pending_timeout_removals.pop(after.id, None)

# --- Discord UI Classes (Buttons and Views) ---

class HelpButton(Button):
    """
    A custom Discord UI Button subclass. When clicked, it simulates a user
    typing and running a specific bot command.
    """
    def __init__(self, label: str, emoji: str, command: str) -> None:
        # Initialize the parent Button with style and text.
        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.primary)
        self.command = command # The command string to execute (e.g., "!skip").

    async def callback(self, interaction: discord.Interaction) -> None:
        """
        This function is executed when a user clicks the button.
        It handles permission checks, cooldowns, and command invocation.
        """
        try:
            user_id = interaction.user.id
            # Enforce that buttons must be used in the designated command channel for non-admins.
            if user_id not in bot_config.ALLOWED_USERS and interaction.channel.id != bot_config.COMMAND_CHANNEL_ID:
                await interaction.response.send_message(f"All commands should be used in <#{bot_config.COMMAND_CHANNEL_ID}>", ephemeral=True)
                return

            # Check and enforce a cooldown to prevent button spam.
            current_time = time.time()
            async with state.cooldown_lock:
                if user_id in state.button_cooldowns:
                    last_used, warned = state.button_cooldowns[user_id]
                    time_left = bot_config.COMMAND_COOLDOWN - (current_time - last_used)
                    if time_left > 0:
                        if not warned: # Only warn the user once per cooldown period.
                            await interaction.response.send_message(f"{interaction.user.mention}, wait {int(time_left)}s before using another button.", ephemeral=True)
                            state.button_cooldowns[user_id] = (last_used, True)
                        else: # If already warned, just ignore the click silently.
                            await interaction.response.defer(ephemeral=True)
                        return
                # If not on cooldown, update the timestamp.
                state.button_cooldowns[user_id] = (current_time, False)

            await interaction.response.defer() # Acknowledge the interaction to prevent it from failing.
            cmd_name = self.command.lstrip("!")
            command_obj = bot.get_command(cmd_name)
            if command_obj:
                # To invoke the command, we create a "fake" message object that mimics a real user message.
                # This allows us to reuse the existing command processing logic.
                fake_message = await interaction.channel.send(f"{interaction.user.mention} used {self.command}")
                fake_message.content = self.command
                fake_message.author = interaction.user
                ctx = await bot.get_context(fake_message)
                await bot.invoke(ctx) # Invoke the command with the created context.
            else:
                logger.warning(f"Button tried to invoke non-existent command: {cmd_name}")
                await interaction.followup.send("Could not process that command.", ephemeral=True)

        except Exception as e:
            logger.error(f"Error in HelpButton callback: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("An error occurred while processing this button.", ephemeral=True)
            else:
                await interaction.followup.send("An error occurred while processing this button.", ephemeral=True)

class HelpView(View):
    """
    A Discord UI View that contains a collection of HelpButtons.
    This creates the interactive menu for controlling the bot.
    """
    def __init__(self) -> None:
        super().__init__(timeout=None) # `timeout=None` makes the view persistent across bot restarts.
        # Define the buttons to be added to the view.
        commands_list = [
            ("⏭️", "Skip", "!skip"),
            ("⏸️", "Pause", "!refresh"),
            ("ℹ️", "Info", "!info"),
            ("⏱️", "Top 10", "!times")
        ]
        # Create and add each button from the list.
        for emoji, label, command in commands_list:
            self.add_item(HelpButton(label=label, emoji=emoji, command=command))

@bot.event
@handle_errors
async def on_message(message: discord.Message) -> None:
    """
    The event handler for every message the bot can see.
    It handles command processing and media-only channel moderation.
    """
    # Ignore messages from the bot itself, DMs, or from other servers.
    if message.author == bot.user or not message.guild or message.guild.id != bot_config.GUILD_ID:
        return

    # --- Media-only channel moderation ---
    if bot_config.MEDIA_ONLY_CHANNEL_ID and message.channel.id == bot_config.MEDIA_ONLY_CHANNEL_ID:
        # Admins are exempt from this rule.
        if message.author.id not in bot_config.ALLOWED_USERS:
            is_media_present = False
            # Check for file attachments.
            if message.attachments:
                is_media_present = True

            # Check for embeds (like links from Twitter/Tenor that become GIFs).
            if not is_media_present and message.embeds:
                for embed in message.embeds:
                    if embed.type in ['image', 'gifv', 'video']:
                        is_media_present = True
                        break

            # If no media is found, delete the message and notify the user.
            if not is_media_present:
                try:
                    await message.delete()
                    logger.info(f"Deleted message from {message.author} in media-only channel #{message.channel.name} because it contained no media.")
                    await message.channel.send(
                        f"{message.author.mention}, this channel only allows photos and other media.",
                        delete_after=10 # The notification will self-delete after 10 seconds.
                    )
                except discord.Forbidden:
                    logger.warning(f"Missing permissions to delete message in media-only channel #{message.channel.name}.")
                except discord.NotFound:
                    pass # Message was already deleted.
                except Exception as e:
                    logger.error(f"Error deleting message in media-only channel: {e}")
                return # Stop further processing of this message.

    # Process the message to check for and execute any commands it contains.
    await bot.process_commands(message)

# --- Help Menu Functions ---

async def send_help_menu(target: Any) -> None:
    """
    Sends the main interactive help menu embed with buttons to a specified target.
    The target can be a channel, context, or message object.
    This version is restored from your working original to support VoiceChannel targets.
    """
    try:
        help_description = """
**Skip** ----------- Skip/Start Omegle
**Pause** --------- Pause/Refresh Omegle
**Info** ----------- Server Info/Rules
**Top 10** -------- Top 10 VC Times
**!commands** --- List All Commands
"""
        embed = build_embed("Omegle Controls", help_description, discord.Color.blue())

        # This logic correctly handles that VoiceChannel objects can be messaged in discord.py v2.0+
        destination = None
        if isinstance(target, (discord.TextChannel, discord.VoiceChannel, discord.Thread)):
            destination = target
        elif hasattr(target, 'channel'): # Covers Context and Message objects
            destination = target.channel

        if destination and hasattr(destination, 'send'):
            await destination.send(embed=embed, view=HelpView())
        else:
            logger.warning(f"Unsupported target type for help menu: {type(target)}")

    except Exception as e:
        logger.error(f"Error in send_help_menu: {e}", exc_info=True)


@tasks.loop(minutes=2)
async def periodic_help_menu() -> None:
    """
    A background task that periodically purges the command channel and reposts
    the interactive help menu to keep it clean and visible.
    """
    try:
        guild = bot.get_guild(bot_config.GUILD_ID)
        if not guild: return
        channel = guild.get_channel(bot_config.COMMAND_CHANNEL_ID)
        if not channel:
            logger.warning(f"Help menu channel with ID {bot_config.COMMAND_CHANNEL_ID} not found.")
            return

        try:
            # Safely purge messages and then send a new menu.
            await safe_purge(channel, limit=50)
            await send_help_menu(channel)
        except discord.HTTPException as e:
            # Handle Discord API rate limiting gracefully.
            if e.status == 429:
                wait = e.retry_after + 5
                logger.warning(f"Rate limited during help menu update. Retrying in {wait}s")
                await asyncio.sleep(wait)
    except Exception as e:
        logger.error(f"Help menu update failed: {e}", exc_info=True)
        await asyncio.sleep(300) # Wait longer on other failures to avoid spamming errors.

async def safe_purge(channel: Any, limit: int = 50) -> None:
    """
    A helper function to safely purge messages from a channel, with built-in
    handling for Discord's rate-limiting. Now accepts any channel type that has .purge
    """
    if not hasattr(channel, 'purge'):
        logger.warning(f"Attempted to purge channel '{channel.name}' which is not a messageable channel.")
        return
        
    try:
        deleted = await channel.purge(limit=min(limit, 50))
        if deleted:
            logger.info(f"Purged {len(deleted)} messages in {channel.name}")
            await asyncio.sleep(1) # Small sleep to avoid hitting other rate limits.
    except discord.HTTPException as e:
        if e.status == 429: # Specifically handle rate limit errors.
            wait = max(e.retry_after, 10) # Get the required wait time from Discord's response.
            logger.warning(f"Purge rate limited in {channel.name}. Waiting {wait}s")
            await asyncio.sleep(wait)
        else: raise # Re-raise other HTTP errors.
    except Exception as e:
        logger.error(f"An error occurred during purge: {e}", exc_info=True)


@tasks.loop(time=dt_time(bot_config.AUTO_STATS_HOUR_UTC, bot_config.AUTO_STATS_MINUTE_UTC))
async def daily_auto_stats_clear() -> None:
    """
    A daily background task that automatically posts the VC time leaderboard,
    then clears all statistics for the next day's contest.
    """
    channel = bot.get_channel(bot_config.AUTO_STATS_CHAN)
    if not channel:
        logger.error("AUTO_STATS_CHAN channel not found! Cannot run daily stats clear.")
        return

    report_sent_successfully = False
    try:
        # First, post the final report for the day.
        await helper.show_times_report(channel)
        report_sent_successfully = True
    except Exception as e:
        logger.error(f"Daily auto-stats failed during 'show_times_report': {e}", exc_info=True)
        # If the report fails, do NOT clear the stats, as the data would be lost.
        try:
            await channel.send("⚠️ **Critical Error:** Failed to generate the daily stats report. **Statistics will NOT be cleared.** Please check the logs.")
        except Exception as e_inner:
            logger.error(f"Failed to send the critical error message to the channel: {e_inner}")

    # Only clear the stats if the report was sent successfully.
    if report_sent_successfully:
        try:
            # Get a list of all members currently in the moderated VCs.
            streaming_vc = channel.guild.get_channel(bot_config.STREAMING_VC_ID)
            alt_vc = channel.guild.get_channel(bot_config.ALT_VC_ID)
            current_members = []
            if streaming_vc: current_members.extend([m for m in streaming_vc.members if not m.bot])
            if alt_vc: current_members.extend([m for m in alt_vc.members if not m.bot])

            # Lock the state and reset all statistical data.
            async with state.vc_lock, state.analytics_lock, state.moderation_lock:
                state.vc_time_data = {}
                state.active_vc_sessions = {}
                state.analytics = {"command_usage": {}, "command_usage_by_user": {}, "violation_events": 0}
                state.user_violations = {}
                state.camera_off_timers = {}

                # After clearing, immediately re-initialize sessions for members who are still in the VC.
                # This ensures their time for the *new* day starts counting immediately.
                if current_members:
                    current_time = time.time()
                    for member in current_members:
                        state.active_vc_sessions[member.id] = current_time
                        state.vc_time_data[member.id] = {"total_time": 0, "sessions": [], "username": member.name, "display_name": member.display_name}
                    logger.info(f"Restarted VC tracking for {len(current_members)} members after auto-clear")

            await channel.send("✅ Statistics automatically cleared and tracking restarted!")

        except Exception as e:
            logger.error(f"Daily auto-stats failed during state clearing: {e}", exc_info=True)

@tasks.loop(seconds=15)
@handle_errors
async def timeout_unauthorized_users_task() -> None:
    """
    The core moderation task. It runs every 15 seconds to check for users
    who have had their camera off for too long and applies punishments accordingly.
    """
    async with state.vc_lock:
        is_active = state.vc_moderation_active
    if not is_active:
        return

    guild = bot.get_guild(bot_config.GUILD_ID)
    if not guild: return
    
    punishment_vc = guild.get_channel(bot_config.PUNISHMENT_VC_ID)
    if not punishment_vc: 
        logger.warning("Punishment VC not found, moderation task cannot run.")
        return

    # --- Build list of VCs to moderate ---
    moderated_vcs = []
    if streaming_vc := guild.get_channel(bot_config.STREAMING_VC_ID):
        moderated_vcs.append(streaming_vc)
    if bot_config.ALT_VC_ID and (alt_vc := guild.get_channel(bot_config.ALT_VC_ID)):
        if alt_vc not in moderated_vcs: # Avoid duplicates
            moderated_vcs.append(alt_vc)

    if not moderated_vcs:
        logger.warning("No valid moderated VCs found.")
        return

    # --- Identify users whose timers might have expired ---
    users_to_check = []
    current_time = time.time()
    async with state.vc_lock:
        for member_id, start_time in state.camera_off_timers.items():
            if current_time - start_time >= bot_config.CAMERA_OFF_ALLOWED_TIME:
                users_to_check.append(member_id)

    # --- Process candidates one by one, re-validating state before punishment ---
    for member_id in users_to_check:
        member = guild.get_member(member_id)
        if not member or not member.voice or not member.voice.channel:
            continue

        vc = member.voice.channel
        
        # Re-validate the condition and update state atomically
        async with state.vc_lock:
            timer_start_time = state.camera_off_timers.get(member_id)
            if not timer_start_time or (time.time() - timer_start_time < bot_config.CAMERA_OFF_ALLOWED_TIME):
                continue
            
            # Condition confirmed, remove timer to prevent re-punishment
            state.camera_off_timers.pop(member_id, None)

        # Increment violation counts
        violation_count = 0
        async with state.moderation_lock:
            state.analytics["violation_events"] += 1
            state.user_violations[member_id] = state.user_violations.get(member_id, 0) + 1
            violation_count = state.user_violations[member_id]

        # Apply the actual punishment (slow API calls) AFTER releasing locks
        try:
            punishment_applied = ""
            if violation_count == 1: # First offense
                await member.move_to(punishment_vc, reason=f"No camera detected in {vc.name}.")
                punishment_applied = "moved"
                logger.info(f"Moved {member.name} to PUNISHMENT VC (from {vc.name}).")
            elif violation_count == 2: # Second offense
                timeout_duration = bot_config.TIMEOUT_DURATION_SECOND_VIOLATION
                reason = f"2nd camera violation in {vc.name}."
                await member.timeout(timedelta(seconds=timeout_duration), reason=reason)
                punishment_applied = "timed out"
                await helper._log_timeout_in_state(member, timeout_duration, reason, "AutoMod")
                logger.info(f"Timed out {member.name} for {timeout_duration}s (from {vc.name}).")
            else:  # Third offense or more
                timeout_duration = bot_config.TIMEOUT_DURATION_THIRD_VIOLATION
                reason = f"Repeated camera violations in {vc.name}."
                await member.timeout(timedelta(seconds=timeout_duration), reason=reason)
                punishment_applied = "timed out"
                await helper._log_timeout_in_state(member, timeout_duration, reason, "AutoMod")
                logger.info(f"Timed out {member.name} for {timeout_duration}s (from {vc.name}).")

            # Send DM notification to the user
            is_dm_disabled = False
            async with state.moderation_lock:
                is_dm_disabled = member_id in state.users_with_dms_disabled

            if not is_dm_disabled:
                try:
                    await member.send(f"You've been {punishment_applied} for not having a camera on in the VC.")
                except discord.Forbidden: # User has DMs closed.
                    async with state.moderation_lock:
                        state.users_with_dms_disabled.add(member_id)
                except Exception as e:
                    logger.error(f"Failed to send violation DM to {member.name}: {e}")

        except discord.Forbidden:
            logger.warning(f"Missing permissions to punish {member.name} in {vc.name}.")
        except discord.HTTPException as e:
            logger.error(f"Failed to punish {member.name} in {vc.name}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during punishment for {member.name}: {e}")

#########################################
# Bot Commands
#########################################

@bot.command(name='help')
@require_command_channel
@require_admin_or_allowed()
@handle_errors
async def help_command(ctx):
    """(Admin/Allowed) Sends the interactive help menu with buttons."""
    await send_help_menu(ctx)

@bot.command(name='skip', aliases=['start'])
@require_command_channel
@require_camera_or_allowed_user()
@omegle_command_cooldown
@handle_errors
async def skip(ctx):
    """(Camera On/Allowed) Skips the current Omegle user or starts a new chat."""
    command_name = f"!{ctx.invoked_with}"
    # Record command usage for analytics.
    record_command_usage(state.analytics, command_name)
    record_command_usage_by_user(state.analytics, ctx.author.id, command_name)
    await omegle_handler.custom_skip(ctx)

@bot.command(name='refresh', aliases=['pause'])
@require_command_channel
@require_camera_or_allowed_user()
@omegle_command_cooldown
@handle_errors
async def refresh(ctx):
    """(Camera On/Allowed) Refreshes the Omegle page to fix potential stream issues."""
    command_name = f"!{ctx.invoked_with}"
    record_command_usage(state.analytics, command_name)
    record_command_usage_by_user(state.analytics, ctx.author.id, command_name)
    await omegle_handler.refresh(ctx)

@bot.command(name='purge')
@require_admin_or_allowed()
@handle_errors
async def purge(ctx, count: int) -> None:
    """(Admin/Allowed) Purges a specified number of messages from the current channel."""
    logger.info(f"Purge command received with count: {count}")
    deleted = await ctx.channel.purge(limit=count)
    logger.info(f"Purged {len(deleted)} messages.")

@purge.error
async def purge_error(ctx, error: Exception) -> None:
    """Error handler specifically for the !purge command."""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: !purge <number>")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("⛔ You do not have permission to use this command.")
    else:
        await ctx.send("An error occurred in the purge command.")
        logger.error(f"Error in purge command: {error}", exc_info=True)

@bot.command(name='shutdown')
@require_admin_or_allowed()
@handle_errors
async def shutdown(ctx) -> None:
    """(Admin/Allowed) Safely shuts down the bot, saving state first."""
    if getattr(bot, "_is_shutting_down", False):
        await ctx.send("🛑 Shutdown already in progress")
        return

    # Confirmation prompt to prevent accidental shutdowns.
    confirm_msg = await ctx.send("⚠️ **Are you sure you want to shut down the bot?**\nReact with ✅ to confirm or ❌ to cancel.")
    for emoji in ("✅", "❌"): await confirm_msg.add_reaction(emoji)

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in {"✅", "❌"} and reaction.message.id == confirm_msg.id

    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=30.0, check=check)
        if str(reaction.emoji) == "❌":
            await confirm_msg.edit(content="🟢 Shutdown cancelled")
            return
    except asyncio.TimeoutError:
        await confirm_msg.edit(content="🟢 Shutdown timed out")
        return
    finally:
        try: await confirm_msg.clear_reactions()
        except discord.HTTPException: pass

    # Call the internal shutdown logic
    await _initiate_shutdown(ctx)


async def _initiate_shutdown(ctx: Optional[commands.Context] = None):
    """Internal shutdown logic, can be called by command or signal handler."""
    if getattr(bot, "_is_shutting_down", False):
        return
    bot._is_shutting_down = True

    author_name = ctx.author.name if ctx else "the system"
    author_id = ctx.author.id if ctx else "N/A"
    logger.critical(f"Shutdown initiated by {author_name} (ID: {author_id})")

    if ctx:
        await ctx.send("🛑 **Bot is shutting down...**")

    # Clean up resources like the global hotkey.
    if bot_config.ENABLE_GLOBAL_HOTKEY:
        try:
            # Run blocking keyboard calls in a separate thread
            await asyncio.to_thread(keyboard.remove_hotkey, bot_config.GLOBAL_HOTKEY_COMBINATION)
            logger.info("Unregistered global hotkey during shutdown")
        except Exception: pass

    # Close the bot's connection to Discord. This will eventually lead to the script ending.
    await bot.close()

@bot.command(name='hush')
@require_admin_or_allowed()
@handle_errors
async def hush(ctx) -> None:
    """(Admin/Allowed) Server-mutes all non-admin users in the Streaming VC."""
    async with state.vc_lock:
        state.hush_override_active = True

    streaming_vc = ctx.guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        impacted = []
        for member in streaming_vc.members:
            if not member.bot and member.id not in bot_config.ALLOWED_USERS:
                try:
                    await member.edit(mute=True)
                    impacted.append(member.name)
                except Exception as e:
                    logger.error(f"Error muting {member.name}: {e}")
        msg = "Muted: " + ", ".join(impacted) if impacted else "No users muted."
        await ctx.send(msg)
    else:
        await ctx.send("Streaming VC not found.")

@bot.command(name='secret')
@require_admin_or_allowed()
@handle_errors
async def secret(ctx) -> None:
    """(Admin/Allowed) Server-mutes and deafens all non-admin users in the Streaming VC."""
    async with state.vc_lock:
        state.hush_override_active = True

    streaming_vc = ctx.guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        impacted = []
        for member in streaming_vc.members:
            if not member.bot and member.id not in bot_config.ALLOWED_USERS:
                try:
                    await member.edit(mute=True, deafen=True)
                    impacted.append(member.name)
                except Exception as e:
                    logger.error(f"Error muting/deafening {member.name}: {e}")
        msg = "Muted & Deafened: " + ", ".join(impacted) if impacted else "No users to mute/deafen."
        await ctx.send(msg)
    else:
        await ctx.send("Streaming VC not found.")

@bot.command(name='rhush', aliases=['removehush'])
@require_admin_or_allowed()
@handle_errors
async def rhush(ctx) -> None:
    """(Admin/Allowed) Removes server-mutes from all users in the Streaming VC."""
    async with state.vc_lock:
        state.hush_override_active = False

    streaming_vc = ctx.guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        impacted = []
        for member in streaming_vc.members:
            if not member.bot:
                try:
                    # Only unmute if they have their camera on (or are an admin)
                    if is_user_in_streaming_vc_with_camera(member) or member.id in bot_config.ALLOWED_USERS:
                       await member.edit(mute=False)
                       impacted.append(member.name)
                except Exception as e:
                    logger.error(f"Error unmuting {member.name}: {e}")
        msg = "Unmuted: " + ", ".join(impacted) if impacted else "No users to unmute."
        await ctx.send(msg)
    else:
        await ctx.send("Streaming VC not found.")

@bot.command(name='rsecret', aliases=['removesecret'])
@require_admin_or_allowed()
@handle_errors
async def rsecret(ctx) -> None:
    """(Admin/Allowed) Removes mute and deafen from all users in the Streaming VC."""
    async with state.vc_lock:
        state.hush_override_active = False

    streaming_vc = ctx.guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        impacted = []
        for member in streaming_vc.members:
            if not member.bot:
                try:
                    # Only unmute/undeafen if they have their camera on (or are an admin)
                    if is_user_in_streaming_vc_with_camera(member) or member.id in bot_config.ALLOWED_USERS:
                        await member.edit(mute=False, deafen=False)
                        impacted.append(member.name)
                except Exception as e:
                    logger.error(f"Error removing mute/deafen from {member.name}: {e}")
        msg = "Unmuted & Undeafened: " + ", ".join(impacted) if impacted else "No users to unmute/undeafen."
        await ctx.send(msg)
    else:
        await ctx.send("Streaming VC not found.")

@bot.command(name='modoff')
@require_admin_or_allowed()
@handle_errors
async def modoff(ctx):
    """(Admin/Allowed) Temporarily disables all automated VC moderation features."""
    async with state.vc_lock:
        state.vc_moderation_active = False
    logger.warning(f"VC Moderation DISABLED by {ctx.author.name}")
    await ctx.send("🛡️ VC Moderation has been temporarily **DISABLED**.")

@bot.command(name='modon')
@require_admin_or_allowed()
@handle_errors
async def modon(ctx):
    """(Admin/Allowed) Re-enables automated VC moderation features."""
    async with state.vc_lock:
        state.vc_moderation_active = True
    logger.warning(f"VC Moderation ENABLED by {ctx.author.name}")
    await ctx.send("🛡️ VC Moderation has been **ENABLED**.")

# --- Commands Delegated to BotHelper ---
# These commands simply call their corresponding methods in the helper class.
# This keeps the main bot file focused on event handling and core logic.

@bot.command(name='bans', aliases=['banned'])
@require_command_channel
@require_admin_or_allowed()
@handle_errors
async def bans(ctx) -> None:
    """(Admin/Allowed) Lists all banned users."""
    await helper.show_bans(ctx)

@bot.command(name='top')
@require_command_channel
@require_admin_or_allowed()
@handle_errors
async def top_members(ctx) -> None:
    """(Admin/Allowed) Lists the top 10 oldest accounts in the server."""
    await helper.show_top_members(ctx)

@bot.command(name='info', aliases=['about'])
@require_command_channel
@require_camera_or_allowed_user()
@handle_errors
async def info(ctx) -> None:
    """(Camera On/Allowed) Shows server information and rules."""
    await helper.show_info(ctx)

@bot.command(name='roles')
@require_command_channel
@require_admin_or_allowed()
@handle_errors
async def roles(ctx) -> None:
    """(Admin/Allowed) Lists all server roles and their members."""
    await helper.list_roles(ctx)

@bot.command(name='admin', aliases=['owner', 'admins', 'owners'])
@require_command_channel
@require_admin_or_allowed()
@handle_errors
async def admin(ctx) -> None:
    """(Admin/Allowed) Lists all configured admins and owners."""
    await helper.show_admin_list(ctx)

@bot.command(name='commands')
@require_command_channel
@require_admin_or_allowed()
@handle_errors
async def commands_list(ctx) -> None:
    """(Admin/Allowed) Shows a complete list of available bot commands."""
    await helper.show_commands_list(ctx)

@bot.command(name='whois')
@require_command_channel
@require_admin_or_allowed()
@handle_errors
async def whois(ctx) -> None:
    """(Admin/Allowed) Shows a report of recent user activities (joins, leaves, bans, etc.)."""
    await helper.show_whois(ctx)

@bot.command(name='rtimeouts')
@require_command_channel
@require_admin_or_allowed()
@handle_errors
async def remove_timeouts(ctx) -> None:
    """(Admin/Allowed) Removes all active timeouts from members."""
    await helper.remove_timeouts(ctx)

@bot.command(name='rules')
@require_command_channel
@require_camera_or_allowed_user()
@handle_errors
async def rules(ctx) -> None:
    """(Camera On/Allowed) Displays the server rules."""
    await helper.show_rules(ctx)

@bot.command(name='timeouts')
@require_command_channel
@require_admin_or_allowed()
@handle_errors
async def timeouts(ctx) -> None:
    """(Admin/Allowed) Shows currently timed out members and recent timeout removals."""
    await helper.show_timeouts(ctx)

@bot.command(name='times')
@require_command_channel
@require_camera_or_allowed_user()
@handle_errors
async def time_report(ctx) -> None:
    """(Camera On/Allowed) Shows the top 10 VC time leaderboard."""
    await helper.show_times_report(ctx)

@bot.command(name='stats')
@require_command_channel
@require_admin_or_allowed()
@handle_errors
async def analytics_report(ctx) -> None:
    """(Admin/Allowed) Shows a detailed report of command usage and other analytics."""
    await helper.show_analytics_report(ctx)

@bot.command(name='join')
@require_admin_or_allowed()
@handle_errors
async def join(ctx) -> None:
    """(Admin/Allowed) Sends a join invite DM to all admin-role members."""
    await helper.send_join_invites(ctx)

@bot.command(name='clear')
@require_admin_or_allowed()
@handle_errors
async def clear_stats(ctx) -> None:
    """(Admin/Allowed) Resets all statistical data."""
    await helper.clear_stats(ctx)

#########################################
# Main Execution
#########################################
if __name__ == "__main__":
    # Ensure necessary environment variables (like the bot token) are set.
    required_vars = ["BOT_TOKEN"]
    if missing := [var for var in required_vars if not os.getenv(var)]:
        logger.critical(f"Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    def handle_shutdown(signum, _frame):
        """
        A signal handler for gracefully shutting down the bot on signals like Ctrl+C (SIGINT).
        """
        logger.info("Graceful shutdown initiated by signal")
        # Call the async shutdown function safely from a synchronous context.
        if not getattr(bot, "_is_shutting_down", False):
            bot.loop.create_task(_initiate_shutdown(None))

    # Register the signal handler for interrupt and termination signals.
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        # Start the bot. This is a blocking call that runs the bot's event loop.
        bot.run(os.getenv("BOT_TOKEN"))
    except discord.LoginFailure as e:
        logger.critical(f"Invalid token: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Fatal error during bot run: {e}", exc_info=True)
        raise
    finally:
        # This block runs after the bot has fully shut down.
        logger.info("Starting final shutdown process...")
        # Clean up resources like the hotkey and Selenium driver.
        try:
            if 'bot_config' in globals() and getattr(bot_config, 'ENABLE_GLOBAL_HOTKEY', False):
                try:
                    # Run blocking keyboard calls in a separate thread
                    asyncio.run(asyncio.to_thread(keyboard.remove_hotkey, bot_config.GLOBAL_HOTKEY_COMBINATION))
                    logger.info("Unregistered global hotkey in finally block")
                except Exception: pass
        except NameError: pass

        if 'omegle_handler' in globals() and omegle_handler.driver:
            asyncio.run(omegle_handler.close())

        # Perform one final state save to capture any last-minute changes.
        if 'state' in globals():
            logger.info("Performing final state save...")
            asyncio.run(save_state_async())

        logger.info("Shutdown complete")
