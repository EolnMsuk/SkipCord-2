# bot.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Standard library imports
import asyncio
import json
import os
import random
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta, time as dt_time
from functools import wraps
from typing import Any, Callable, Optional

# Third-party imports
import discord
import keyboard
from discord.ext import commands, tasks
from dotenv import load_dotenv
from loguru import logger


# Local application imports
try:
    import config
except ImportError:
    logger.critical("CRITICAL: config.py not found. Please create it based on the example.")
    sys.exit(1)
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

# --- VALIDATION AND INITIALIZATION ---
# Load configuration from the config.py module into a structured dataclass
bot_config = BotConfig.from_config_module(config)

# Validate that all essential configuration variables have been set
required_settings = [
    'GUILD_ID', 'COMMAND_CHANNEL_ID', 'CHAT_CHANNEL_ID', 'STREAMING_VC_ID',
    'PUNISHMENT_VC_ID', 'OMEGLE_VIDEO_URL', 'EDGE_USER_DATA_DIR'
]
missing_settings = [
    setting for setting in required_settings if not getattr(bot_config, setting)
]

if missing_settings:
    logger.critical(f"FATAL: The following required settings are missing in config.py: {', '.join(missing_settings)}")
    logger.critical("Please fill them out before starting the bot.")
    sys.exit(1)


# Initialize the bot's state management object
state = BotState(config=bot_config)
# Initialize the handler for Selenium-based browser automation
omegle_handler = OmegleHandler(bot_config)
omegle_handler.state = state

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
            omegle_handler.state = state
            logger.info("Bot state loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load bot state: {e}", exc_info=True)
            # If loading fails, start with a fresh state to ensure bot functionality.
            state = BotState(config=bot_config)
            bot.state = state
            omegle_handler.state = state
    else:
        logger.info("No saved state file found, starting with a fresh state.")
        state = BotState(config=bot_config)
        bot.state = state
        helper.state = state # Ensure helper state is also updated on a fresh start.
        omegle_handler.state = state

# Initialize the helper class AFTER the initial state object is created but BEFORE it might be replaced by `load_state_async`.
helper = BotHelper(bot, state, bot_config, save_state_async)


@tasks.loop(minutes=14)
async def periodic_state_save() -> None:
    """A background task that periodically saves the bot's state to ensure data is not lost on crash."""
    await save_state_async()

@tasks.loop(minutes=1)
async def periodic_geometry_save():
    """Periodically saves the browser window's size and position."""
    if omegle_handler:
        geometry = await omegle_handler.get_window_geometry()
        if geometry:
            size, position = geometry
            # This check prevents saving geometry when the window is minimized.
            # Minimized windows can return negative positions like (-32000, -32000).
            if position.get('x', -1) >= 0 and position.get('y', -1) >= 0:
                # Use a lock to prevent race conditions during state updates
                async with state.cooldown_lock:
                    # Only update if the values have changed to reduce write overhead
                    if state.window_size != size or state.window_position != position:
                        state.window_size = size
                        state.window_position = position

#########################################
# Voice Connection & Hotkey Functions
#########################################

def is_user_in_streaming_vc_with_camera(user: discord.Member) -> bool:
    """Checks if a given user is in the designated streaming voice channel with their camera enabled."""
    streaming_vc = user.guild.get_channel(bot_config.STREAMING_VC_ID)
    # Returns True only if the user is in the VC and their self_video attribute is True.
    return bool(streaming_vc and user in streaming_vc.members and user.voice and user.voice.self_video)

async def global_skip() -> None:
    """Executes a skip command triggered by a global hotkey press on the host machine."""
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
        async with state.cooldown_lock:
            time_since_last_cmd = current_time - state.last_omegle_command_time
            if time_since_last_cmd < 5.0:
                try:
                    await ctx.message.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass

                await ctx.send(
                    f"{ctx.author.mention}, please wait {5.0 - time_since_last_cmd:.1f} more seconds before using this command again.",
                    delete_after=5
                )
                return
            state.last_omegle_command_time = current_time
        
        return await func(ctx, *args, **kwargs)
    return wrapper

def require_user_preconditions():
    """
    A decorator for user-facing commands.
    It enforces that non-admin users must:
    1. Not be disabled.
    2. Use the command in the designated command channel.
    3. Be in the streaming voice channel with their camera on.
    It provides specific feedback to the user based on which condition fails.
    Allowed users are exempt from these checks.
    """
    async def predicate(ctx):
        if ctx.author.id in bot_config.ALLOWED_USERS:
            return True

        async with state.moderation_lock:
            if ctx.author.id in state.omegle_disabled_users:
                await ctx.send("You are currently disabled from using any commands.", delete_after=10)
                return False

        if ctx.channel.id != bot_config.COMMAND_CHANNEL_ID:
            await ctx.send(f"All commands should be used in <#{bot_config.COMMAND_CHANNEL_ID}>.", delete_after=10)
            return False
        
        if is_user_in_streaming_vc_with_camera(ctx.author):
            return True

        await ctx.send("You must be in the Streaming VC with your camera on to use commands.", delete_after=10)
        return False
        
    return commands.check(predicate)

def require_admin_preconditions():
    """
    A decorator for admin-level commands. It first checks for permission
    (ALLOWED_USER or ADMIN_ROLE_NAME). If the user is only an ADMIN_ROLE_NAME,
    it enforces that they are not disabled, and then checks the same channel
    and VC/camera status as a regular user.
    ALLOWED_USERS are exempt from all location/state checks.
    """
    async def predicate(ctx):
        is_allowed = ctx.author.id in bot_config.ALLOWED_USERS
        is_admin_role = isinstance(ctx.author, discord.Member) and any(role.name in bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles)

        if not (is_allowed or is_admin_role):
            await ctx.send("⛔ You do not have permission to use this command.", delete_after=10)
            return False

        if is_allowed:
            return True
        
        async with state.moderation_lock:
            if ctx.author.id in state.omegle_disabled_users:
                await ctx.send("You are currently disabled from using any commands.", delete_after=10)
                return False

        if ctx.channel.id != bot_config.COMMAND_CHANNEL_ID:
            await ctx.send(f"All commands should be used in <#{bot_config.COMMAND_CHANNEL_ID}>.", delete_after=10)
            return False

        if is_user_in_streaming_vc_with_camera(ctx.author):
            return True

        await ctx.send("You must be in the Streaming VC with your camera on to use commands.", delete_after=10)
        return False

    return commands.check(predicate)

def require_allowed_user():
    """A decorator that restricts command usage to ALLOWED_USERS only."""
    async def predicate(ctx):
        if ctx.author.id in bot_config.ALLOWED_USERS:
            return True
        await ctx.send("⛔ This command can only be used by bot owners.")
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
    async with state.moderation_lock:
        if (member.id in state.users_received_rules or
            member.id in state.users_with_dms_disabled or
            member.id in state.failed_dm_users):
            return

    try:
        await member.send(bot_config.RULES_MESSAGE)
        async with state.moderation_lock:
            state.users_received_rules.add(member.id)
        logger.info(f"Sent rules to {member.display_name}")
    except discord.Forbidden:
        async with state.moderation_lock:
            state.users_with_dms_disabled.add(member.id)
            state.failed_dm_users.add(member.id)
        logger.warning(f"Could not DM {member.display_name} (DMs disabled or blocked).")
    except Exception as e:
        async with state.moderation_lock:
            state.failed_dm_users.add(member.id)
        logger.error(f"Generic error sending DM to {member.name}: {e}", exc_info=True)


async def _check_for_auto_pause(vc: discord.VoiceChannel, reason: str):
    """
    Checks if the conditions for an automatic stream refresh (pause) are met.
    This is typically triggered when the last user with a camera leaves or turns it off.
    This behavior can be disabled via the EMPTY_VC_PAUSE config setting.
    """
    if not vc or not bot_config.EMPTY_VC_PAUSE:
        return

    users_with_camera = [m for m in vc.members if m.voice and m.voice.self_video and m.id not in bot_config.ALLOWED_USERS and not m.bot]

    async with state.vc_lock:
        if not users_with_camera and (time.time() - state.last_auto_pause_time >= 1):
            state.last_auto_pause_time = time.time()
            should_refresh = True
        else:
            should_refresh = False

    if should_refresh:
        await omegle_handler.refresh()
        logger.info(reason)
        if (command_channel := vc.guild.get_channel(bot_config.COMMAND_CHANNEL_ID)):
            try:
                await command_channel.send("Stream automatically paused")
            except Exception as e:
                logger.error(f"Failed to send auto-refresh notification: {e}")

async def _join_camera_failsafe_check(member: discord.Member, config: BotConfig):
    """
    After a user joins, waits 5 seconds and checks if their camera is on.
    If it is, and they are server-muted/deafened, it removes the mute/deafen.
    This acts as a failsafe for race conditions during VC join and camera activation.
    """
    await asyncio.sleep(5)
    
    guild = member.guild
    if not guild: return
        
    current_member_state = guild.get_member(member.id)
    if not current_member_state or not current_member_state.voice or not current_member_state.voice.channel:
        return

    is_in_streaming_vc = current_member_state.voice.channel.id == config.STREAMING_VC_ID
    is_camera_on = current_member_state.voice.self_video

    if is_in_streaming_vc and is_camera_on:
        is_server_muted = current_member_state.voice.mute and not current_member_state.voice.self_mute
        is_server_deafened = current_member_state.voice.deaf and not current_member_state.voice.self_deaf

        if is_server_muted or is_server_deafened:
            logger.info(f"Failsafe triggered for {current_member_state.name}. Camera is on but they are server-muted/deafened. Correcting.")
            try:
                await current_member_state.edit(mute=False, deafen=False)
                logger.info(f"Failsafe successfully unmuted/undeafened {current_member_state.name}.")
            except Exception as e:
                logger.error(f"Failsafe failed to unmute/undeafen {current_member_state.name}: {e}")

async def _soundboard_grace_protocol(member: discord.Member, config: BotConfig):
    """
    Handles the soundboard grace period. Unmutes a user upon joining,
    waits a few seconds, and then re-applies mute/deafen if their camera is still off.
    """
    try:
        if member.voice and (member.voice.mute or member.voice.deaf):
            await member.edit(mute=False, deafen=False)
    except Exception:
        pass 
        
    await asyncio.sleep(2.0)
    
    guild = member.guild
    if not guild: return
    
    member_after_sleep = guild.get_member(member.id)
    
    is_in_moderated_vc = lambda ch: ch and ch.id in (config.STREAMING_VC_ID, config.ALT_VC_ID)

    if (member_after_sleep and member_after_sleep.voice and
            member_after_sleep.voice.channel and is_in_moderated_vc(member_after_sleep.voice.channel)
            and not member_after_sleep.voice.self_video):
        try:
            await member_after_sleep.edit(mute=True, deafen=True)
            logger.info(f"Re-applied mute/deafen for {member_after_sleep.name} after soundboard grace period.")
        except Exception as e:
            logger.error(f"Failed to re-mute {member_after_sleep.name} after grace period: {e}")

#########################################
# Bot Event Handlers
#########################################

async def init_vc_moderation():
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
            if not member.bot and member.id not in state.active_vc_sessions:
                state.active_vc_sessions[member.id] = time.time()
                logger.info(f"Started tracking VC time for existing member: {member.name} (ID: {member.id})")
            if (not member.bot and member.id not in bot_config.ALLOWED_USERS and not (member.voice and member.voice.self_video)):
                try:
                    await asyncio.sleep(1)
                    await member.edit(mute=True, deafen=True)
                    logger.info(f"Auto-muted/deafened {member.name} for camera off.")
                except Exception as e:
                    logger.error(f"Failed to auto mute/deafen {member.name}: {e}")
                state.camera_off_timers[member.id] = time.time()

@bot.event
async def on_ready() -> None:
    logger.info(f"Bot is online as {bot.user}")
    bot.state.is_interrupting_for_search = False
    try:
        channel = bot.get_channel(bot_config.CHAT_CHANNEL_ID)
        if channel:
            await channel.send("✅ Bot is online and ready!")
    except Exception as e:
        logger.error(f"Failed to send online message: {e}")

    try:
        await load_state_async()
        logger.info("State loaded successfully")
    except Exception as e:
        logger.error(f"Error loading state: {e}", exc_info=True)

    try:
        if not periodic_state_save.is_running(): periodic_state_save.start()
        if not periodic_cleanup.is_running(): periodic_cleanup.start()
        if not periodic_menu_update.is_running(): periodic_menu_update.start()
        if not timeout_unauthorized_users_task.is_running(): timeout_unauthorized_users_task.start()
        if not periodic_geometry_save.is_running(): periodic_geometry_save.start()
        
        if not daily_auto_stats_clear.is_running():
            daily_auto_stats_clear.start()
            logger.info("Daily auto-stats task started.")

        if not await omegle_handler.initialize():
            logger.critical("Selenium initialization failed.")

        asyncio.create_task(init_vc_moderation())

        async def register_hotkey(enabled_flag: bool, key_combo: str, callback_func: Callable, name: str):
            if not enabled_flag: return
            try:
                await asyncio.to_thread(keyboard.remove_hotkey, key_combo)
            except (KeyError, ValueError): pass
            def callback_wrapper():
                bot.loop.call_soon_threadsafe(lambda: asyncio.create_task(callback_func()))
            try:
                await asyncio.to_thread(keyboard.add_hotkey, key_combo, callback_wrapper)
                logger.info(f"Registered global {name} hotkey: {key_combo}")
            except Exception as e:
                logger.error(f"Failed to register {name} hotkey '{key_combo}': {e}")
        
        await register_hotkey(bot_config.ENABLE_GLOBAL_HOTKEY, bot_config.GLOBAL_HOTKEY_COMBINATION, global_skip, "skip")

        logger.info("Initialization complete")

    except Exception as e:
        logger.error(f"Error during on_ready: {e}", exc_info=True)

# --- Member Event Handlers ---
@bot.event
@handle_errors
async def on_member_join(member: discord.Member) -> None:
    await helper.handle_member_join(member)

@bot.event
@handle_errors
async def on_member_ban(guild: discord.Guild, user: discord.User) -> None:
    await helper.handle_member_ban(guild, user)

@bot.event
@handle_errors
async def on_member_unban(guild: discord.Guild, user: discord.User) -> None:
    await helper.handle_member_unban(guild, user)

@bot.event
@handle_errors
async def on_member_remove(member: discord.Member) -> None:
    await helper.handle_member_remove(member)

@bot.event
@handle_errors
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
    """
    Handles all updates to a member's voice state.
    This is a critical event for tracking VC time, enforcing camera rules, and auto-pausing the stream.
    """
    if member.id == bot.user.id or member.bot:
        return

    is_in_moderated_vc = lambda ch: ch and ch.id in (bot_config.STREAMING_VC_ID, bot_config.ALT_VC_ID)
    was_in_mod_vc = is_in_moderated_vc(before.channel)
    is_now_in_mod_vc = is_in_moderated_vc(after.channel)

    was_in_streaming_vc = before.channel and before.channel.id == bot_config.STREAMING_VC_ID
    is_now_in_streaming_vc = after.channel and after.channel.id == bot_config.STREAMING_VC_ID

    async with state.vc_lock:
        if is_now_in_streaming_vc and not was_in_streaming_vc:
            if member.id not in state.active_vc_sessions:
                state.active_vc_sessions[member.id] = time.time()
                if member.id not in state.vc_time_data:
                    state.vc_time_data[member.id] = {"total_time": 0, "sessions": [], "username": member.name, "display_name": member.display_name}
                logger.info(f"VC Time Tracking: '{member.display_name}' started session.")
        
        elif was_in_streaming_vc and not is_now_in_streaming_vc:
            if member.id in state.active_vc_sessions:
                start_time = state.active_vc_sessions.pop(member.id)
                duration = time.time() - start_time
                if member.id in state.vc_time_data:
                    state.vc_time_data[member.id]["total_time"] += duration
                    state.vc_time_data[member.id]["sessions"].append({"start": start_time, "end": time.time(), "duration": duration, "vc_name": before.channel.name})
                    logger.info(f"VC Time Tracking: '{member.display_name}' ended session, adding {duration:.1f}s.")

    async with state.vc_lock:
        is_mod_active = state.vc_moderation_active
        is_hush_active = state.hush_override_active
        
    if is_mod_active:
        # User joins a moderated VC
        if is_now_in_mod_vc and not was_in_mod_vc:
            if is_now_in_streaming_vc:
                logger.info(f"VC JOIN: {member.display_name} ({member.name} | ID: {member.id}).")
                asyncio.create_task(_handle_stream_vc_join(member))
                if member.id not in bot_config.ALLOWED_USERS:
                    asyncio.create_task(_join_camera_failsafe_check(member, bot_config))

            if member.id not in bot_config.ALLOWED_USERS:
                async with state.vc_lock:
                    state.camera_off_timers[member.id] = time.time()
                    logger.info(f"Started camera grace period timer for '{member.display_name}'.")

                asyncio.create_task(_soundboard_grace_protocol(member, bot_config))

        # User leaves a moderated VC
        elif was_in_mod_vc and not is_now_in_mod_vc:
            # Specifically check if the channel they left was the streaming VC
            if before.channel.id == bot_config.STREAMING_VC_ID:
                logger.info(f"VC LEAVE: {member.display_name} ({member.name} | ID: {member.id}).")
                # Trigger the auto-pause check, passing the channel they left
                asyncio.create_task(_check_for_auto_pause(before.channel, f"Auto Refreshed - '{member.display_name}' left the streaming VC."))

        # User changes state within the same moderated VC
        elif was_in_mod_vc and is_now_in_mod_vc:
            # FIX: Explicitly check if the user moved *away* from the streaming VC,
            # even if it's to another moderated VC (like the ALT_VC).
            if before.channel.id == bot_config.STREAMING_VC_ID and after.channel.id != bot_config.STREAMING_VC_ID:
                logger.info(f"VC SWITCH: {member.display_name} ({member.name} | ID: {member.id}).")
                # Trigger the auto-pause check, passing the channel they left.
                asyncio.create_task(_check_for_auto_pause(before.channel, f"Auto Refreshed - '{member.display_name}' switched VCs."))

            camera_turned_on = not before.self_video and after.self_video
            camera_turned_off = before.self_video and not after.self_video

            if member.id not in bot_config.ALLOWED_USERS:
                if camera_turned_off:
                    async with state.vc_lock:
                        state.camera_off_timers[member.id] = time.time()
                    try:
                        await member.edit(mute=True, deafen=True)
                        logger.info(f"Auto-muted/deafened '{member.display_name}' for turning camera off.")
                    except Exception as e:
                        logger.error(f"Failed to auto-mute '{member.display_name}': {e}")
                    if after.channel.id == bot_config.STREAMING_VC_ID:
                        asyncio.create_task(_check_for_auto_pause(after.channel, "Auto Refreshed - Camera Turned Off"))

                elif camera_turned_on:
                    async with state.vc_lock:
                        state.camera_off_timers.pop(member.id, None)
                    if not is_hush_active:
                        try:
                            await member.edit(mute=False, deafen=False)
                            logger.info(f"Auto-unmuted '{member.display_name}' after turning camera on.")
                        except Exception as e:
                            logger.error(f"Failed to auto-unmute '{member.display_name}': {e}")

    if is_now_in_mod_vc and member.id in bot_config.ALLOWED_USERS:
        if member.voice and ((member.voice.mute and not member.voice.self_mute) or (member.voice.deaf and not member.voice.self_deaf)):
            try:
                await member.edit(mute=False, deafen=False)
                logger.info(f"Reverted server mute/deafen for allowed user '{member.display_name}'")
            except Exception as e:
                logger.error(f"Failed to revert mute/deafen for '{member.display_name}': {e}")

    if after.channel and after.channel.id == bot_config.PUNISHMENT_VC_ID:
        if member.voice and (member.voice.mute or member.voice.deaf):
            try:
                await member.edit(mute=False, deafen=False)
                logger.info(f"Automatically unmuted/undeafened '{member.display_name}' in Punishment VC.")
            except Exception as e:
                logger.error(f"Failed to unmute/undeafen '{member.display_name}' in Punishment VC: {e}")

@bot.event
@handle_errors
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    if before.roles != after.roles:
        roles_gained = [role for role in after.roles if role not in before.roles and role.name != "@everyone"]
        roles_lost = [role for role in before.roles if role not in after.roles and role.name != "@everyone"]
        
        if roles_gained or roles_lost:
            async with state.moderation_lock:
                state.recent_role_changes.append((
                    after.id,
                    after.name,
                    [r.name for r in roles_gained],
                    [r.name for r in roles_lost],
                    datetime.now(timezone.utc)
                ))
            
            channel = after.guild.get_channel(bot_config.CHAT_CHANNEL_ID)
            if channel:
                embed = await build_role_update_embed(after, roles_gained, roles_lost)
                await channel.send(embed=embed)

    if before.is_timed_out() != after.is_timed_out():
        if after.is_timed_out():
            async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                if entry.target.id == after.id and hasattr(entry.after, "timed_out_until") and entry.after.timed_out_until is not None:
                    duration = (entry.after.timed_out_until - datetime.now(timezone.utc)).total_seconds()
                    reason = entry.reason or "No reason provided"
                    moderator = entry.user
                    await helper.send_timeout_notification(after, moderator, int(duration), reason)
                    await helper._log_timeout_in_state(after, int(duration), reason, moderator.name, moderator.id)
                    break
        else:
            async with state.moderation_lock:
                if after.id in state.pending_timeout_removals:
                    return
                state.pending_timeout_removals[after.id] = True

            try:
                moderator_name = "System"
                moderator_id = None
                reason = "Timeout Expired Naturally"
                found_log = False
                for _ in range(5):
                    try:
                        async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update, after=datetime.now(timezone.utc) - timedelta(seconds=15)):
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
                    await asyncio.sleep(1)

                async with state.moderation_lock:
                    start_timestamp = state.active_timeouts.get(after.id, {}).get("start_timestamp", time.time())
                    duration = int(time.time() - start_timestamp)
                    state.recent_untimeouts.append((after.id, after.name, after.display_name, datetime.now(timezone.utc), reason, moderator_name, moderator_id))
                    if len(state.recent_untimeouts) > 100:
                        state.recent_untimeouts.pop(0)
                    state.active_timeouts.pop(after.id, None)
                await helper.send_timeout_removal_notification(after, duration, reason)
            finally:
                async with state.moderation_lock:
                    state.pending_timeout_removals.pop(after.id, None)

@bot.event
@handle_errors
async def on_message(message: discord.Message) -> None:
    if message.author.bot or not message.guild or message.guild.id != bot_config.GUILD_ID:
        return

    if bot_config.MEDIA_ONLY_CHANNEL_ID and message.channel.id == bot_config.MEDIA_ONLY_CHANNEL_ID:
        if bot_config.MOD_MEDIA:
            if message.author.id not in bot_config.ALLOWED_USERS:
                is_media_present = False
                if message.attachments:
                    is_media_present = True
                if not is_media_present and message.embeds:
                    for embed in message.embeds:
                        if embed.type in ['image', 'gifv', 'video']:
                            is_media_present = True
                            break
                if not is_media_present:
                    try:
                        await message.delete()
                        logger.info(f"Deleted message from {message.author} in media-only channel #{message.channel.name} because it contained no media.")
                        await message.channel.send(
                            f"{message.author.mention}, this channel only allows photos and other media.",
                            delete_after=10
                        )
                    except discord.Forbidden:
                        logger.warning(f"Missing permissions to delete message in media-only channel #{message.channel.name}.")
                    except discord.NotFound:
                        pass
                    except Exception as e:
                        logger.error(f"Error deleting message in media-only channel: {e}")
                    return

    await bot.process_commands(message)

# --- Menu Update Task ---

@tasks.loop(minutes=2)
async def periodic_menu_update() -> None:
    try:
        guild = bot.get_guild(bot_config.GUILD_ID)
        if not guild: return
        channel = guild.get_channel(bot_config.COMMAND_CHANNEL_ID)
        if not channel:
            logger.warning(f"Help menu channel with ID {bot_config.COMMAND_CHANNEL_ID} not found.")
            return

        await safe_purge(channel, limit=100)
        
        await helper.send_help_menu(channel)

    except Exception as e:
        logger.error(f"Periodic menu update task failed: {e}", exc_info=True)
        await asyncio.sleep(300) 

async def safe_purge(channel: Any, limit: int = 100) -> None:
    if not hasattr(channel, 'purge'):
        logger.warning(f"Attempted to purge channel '{channel.name}' which is not a messageable channel.")
        return
        
    two_weeks_ago = datetime.now(timezone.utc) - timedelta(days=14)
        
    try:
        deleted = await channel.purge(limit=limit, check=lambda m: m.created_at > two_weeks_ago)
        if deleted:
            logger.info(f"Purged {len(deleted)} messages in {channel.name}")
            await asyncio.sleep(1)
    except discord.HTTPException as e:
        if e.status == 429:
            wait = max(e.retry_after, 10)
            logger.warning(f"Purge rate limited in {channel.name}. Waiting {wait}s")
            await asyncio.sleep(wait)
        else:
            logger.error(f"An HTTP error occurred during purge: {e}", exc_info=True)
    except discord.Forbidden:
        logger.warning(f"Missing permissions to purge messages in {channel.name}.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during purge: {e}", exc_info=True)


@tasks.loop(time=dt_time(bot_config.AUTO_STATS_HOUR_UTC, bot_config.AUTO_STATS_MINUTE_UTC))
async def daily_auto_stats_clear() -> None:
    stats_channel_id = bot_config.AUTO_STATS_CHAN or bot_config.CHAT_CHANNEL_ID
    channel = bot.get_channel(stats_channel_id)
    if not channel:
        logger.error(f"Daily stats channel with ID {stats_channel_id} not found! Cannot run daily stats clear.")
        return

    report_sent_successfully = False
    try:
        await helper.show_analytics_report(channel)
        report_sent_successfully = True
    except Exception as e:
        logger.error(f"Daily auto-stats failed during 'show_analytics_report': {e}", exc_info=True)
        try:
            await channel.send("⚠️ **Critical Error:** Failed to generate the daily stats report. **Statistics will NOT be cleared.** Please check the logs.")
        except Exception as e_inner:
            logger.error(f"Failed to send the critical error message to the channel: {e_inner}")

    if report_sent_successfully:
        try:
            streaming_vc = channel.guild.get_channel(bot_config.STREAMING_VC_ID)
            alt_vc = channel.guild.get_channel(bot_config.ALT_VC_ID)
            current_members = []
            if streaming_vc: current_members.extend([m for m in streaming_vc.members if not m.bot])
            if alt_vc: current_members.extend([m for m in alt_vc.members if not m.bot])

            async with state.vc_lock, state.analytics_lock, state.moderation_lock:
                state.vc_time_data = {}
                state.active_vc_sessions = {}
                state.analytics = {"command_usage": {}, "command_usage_by_user": {}, "violation_events": 0}
                state.user_violations = {}
                state.camera_off_timers = {}

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

    moderated_vcs = []
    if streaming_vc := guild.get_channel(bot_config.STREAMING_VC_ID):
        moderated_vcs.append(streaming_vc)
    if bot_config.ALT_VC_ID and (alt_vc := guild.get_channel(bot_config.ALT_VC_ID)):
        if alt_vc not in moderated_vcs:
            moderated_vcs.append(alt_vc)

    if not moderated_vcs:
        logger.warning("No valid moderated VCs found.")
        return

    users_to_check = []
    current_time = time.time()
    async with state.vc_lock:
        for member_id, start_time in list(state.camera_off_timers.items()):
            if current_time - start_time >= bot_config.CAMERA_OFF_ALLOWED_TIME:
                users_to_check.append(member_id)

    for member_id in users_to_check:
        member = guild.get_member(member_id)
        if not member or not member.voice or not member.voice.channel:
            async with state.vc_lock:
                state.camera_off_timers.pop(member_id, None)
            continue

        vc = member.voice.channel
        
        async with state.vc_lock:
            timer_start_time = state.camera_off_timers.get(member_id)
            if not timer_start_time or (time.time() - timer_start_time < bot_config.CAMERA_OFF_ALLOWED_TIME):
                continue
            
            state.camera_off_timers.pop(member_id, None)

        violation_count = 0
        async with state.moderation_lock:
            state.analytics["violation_events"] += 1
            state.user_violations[member_id] = state.user_violations.get(member_id, 0) + 1
            violation_count = state.user_violations[member_id]

        try:
            punishment_applied = ""
            if violation_count == 1:
                reason = f"Must have camera on in {vc.name}."
                await member.move_to(punishment_vc, reason=reason)
                punishment_applied = "moved"
                await helper.send_punishment_vc_notification(member, reason, bot.user.mention)
                logger.info(f"Moved {member.name} to PUNISHMENT VC (from {vc.name}).")
            elif violation_count == 2:
                timeout_duration = bot_config.TIMEOUT_DURATION_SECOND_VIOLATION
                reason = f"2nd camera violation in {vc.name}."
                await member.timeout(timedelta(seconds=timeout_duration), reason=reason)
                punishment_applied = "timed out"
                await helper._log_timeout_in_state(member, timeout_duration, reason, "AutoMod")
                logger.info(f"Timed out {member.name} for {timeout_duration}s (from {vc.name}).")
            else:
                timeout_duration = bot_config.TIMEOUT_DURATION_THIRD_VIOLATION
                reason = f"Repeated camera violations in {vc.name}."
                await member.timeout(timedelta(seconds=timeout_duration), reason=reason)
                punishment_applied = "timed out"
                await helper._log_timeout_in_state(member, timeout_duration, reason, "AutoMod")
                logger.info(f"Timed out {member.name} for {timeout_duration}s (from {vc.name}).")

            is_dm_disabled = False
            async with state.moderation_lock:
                is_dm_disabled = member_id in state.users_with_dms_disabled

            if not is_dm_disabled:
                try:
                    await member.send(f"You've been {punishment_applied} for not having a camera on in the VC.")
                except discord.Forbidden:
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
@require_admin_preconditions()
@handle_errors
async def help_command(ctx):
    await helper.send_help_menu(ctx)

@bot.command(name='skip', aliases=['start'])
@require_user_preconditions()
@omegle_command_cooldown
@handle_errors
async def skip(ctx):
    command_name = f"!{ctx.invoked_with}"
    record_command_usage(state.analytics, command_name)
    record_command_usage_by_user(state.analytics, ctx.author.id, command_name)
    await omegle_handler.custom_skip(ctx)

@bot.command(name='refresh', aliases=['pause'])
@require_user_preconditions()
@omegle_command_cooldown
@handle_errors
async def refresh(ctx):
    command_name = f"!{ctx.invoked_with}"
    record_command_usage(state.analytics, command_name)
    record_command_usage_by_user(state.analytics, ctx.author.id, command_name)
    await omegle_handler.refresh(ctx)

@bot.command(name='purge')
@require_allowed_user()
@handle_errors
async def purge(ctx, count: int) -> None:
    logger.info(f"Purge command received with count: {count}")
    deleted = await ctx.channel.purge(limit=count + 1)
    logger.info(f"Purged {len(deleted)} messages.")


@purge.error
async def purge_error(ctx, error: Exception) -> None:
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: !purge <number>")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("⛔ You do not have permission to use this command.")
    else:
        await ctx.send("An error occurred in the purge command.")
        logger.error(f"Error in purge command: {error}", exc_info=True)

@bot.command(name='shutdown')
@require_allowed_user()
@handle_errors
async def shutdown(ctx) -> None:
    if getattr(bot, "_is_shutting_down", False):
        await ctx.send("🛑 Shutdown already in progress.")
        return

    confirm_msg = await ctx.send("⚠️ **Are you sure you want to shut down the bot?**\nReact with ✅ to confirm or ❌ to cancel.")
    for emoji in ("✅", "❌"): await confirm_msg.add_reaction(emoji)

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in {"✅", "❌"} and reaction.message.id == confirm_msg.id

    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=30.0, check=check)
        if str(reaction.emoji) == "❌":
            await confirm_msg.edit(content="🟢 Shutdown cancelled.")
            return
    except asyncio.TimeoutError:
        await confirm_msg.edit(content="🟢 Shutdown timed out.")
        return
    finally:
        try: await confirm_msg.clear_reactions()
        except discord.HTTPException: pass

    await _initiate_shutdown(ctx)

async def _initiate_shutdown(ctx: Optional[commands.Context] = None):
    if getattr(bot, "_is_shutting_down", False): return
    bot._is_shutting_down = True
    author_name = ctx.author.name if ctx else "the system"
    logger.critical(f"Shutdown initiated by {author_name} (ID: {ctx.author.id if ctx else 'N/A'})")
    if ctx: await ctx.send("🛑 **Bot is shutting down...**")
    async def unregister_hotkey(enabled, combo, name):
        if enabled:
            try: await asyncio.to_thread(keyboard.remove_hotkey, combo)
            except Exception: pass
    await unregister_hotkey(bot_config.ENABLE_GLOBAL_HOTKEY, bot_config.GLOBAL_HOTKEY_COMBINATION, "skip")
    await bot.close()

@bot.command(name='hush')
@require_allowed_user()
@handle_errors
async def hush(ctx) -> None:
    async with state.vc_lock: state.hush_override_active = True
    streaming_vc = ctx.guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        impacted = []
        for member in streaming_vc.members:
            if not member.bot and member.id not in bot_config.ALLOWED_USERS:
                try: await member.edit(mute=True); impacted.append(member.name)
                except Exception as e: logger.error(f"Error muting {member.name}: {e}")
        await ctx.send("Muted: " + ", ".join(impacted) if impacted else "No users muted.")
    else: await ctx.send("Streaming VC not found.")

@bot.command(name='secret')
@require_allowed_user()
@handle_errors
async def secret(ctx) -> None:
    async with state.vc_lock: state.hush_override_active = True
    streaming_vc = ctx.guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        impacted = []
        for member in streaming_vc.members:
            if not member.bot and member.id not in bot_config.ALLOWED_USERS:
                try: await member.edit(mute=True, deafen=True); impacted.append(member.name)
                except Exception as e: logger.error(f"Error muting/deafening {member.name}: {e}")
        await ctx.send("Muted & Deafened: " + ", ".join(impacted) if impacted else "No users to mute/deafen.")
    else: await ctx.send("Streaming VC not found.")

@bot.command(name='rhush', aliases=['removehush'])
@require_allowed_user()
@handle_errors
async def rhush(ctx) -> None:
    async with state.vc_lock: state.hush_override_active = False
    streaming_vc = ctx.guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        impacted = []
        for member in streaming_vc.members:
            if not member.bot and (is_user_in_streaming_vc_with_camera(member) or member.id in bot_config.ALLOWED_USERS):
                try: await member.edit(mute=False); impacted.append(member.name)
                except Exception as e: logger.error(f"Error unmuting {member.name}: {e}")
        await ctx.send("Unmuted: " + ", ".join(impacted) if impacted else "No users to unmute.")
    else: await ctx.send("Streaming VC not found.")

@bot.command(name='rsecret', aliases=['removesecret'])
@require_allowed_user()
@handle_errors
async def rsecret(ctx) -> None:
    async with state.vc_lock: state.hush_override_active = False
    streaming_vc = ctx.guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        impacted = []
        for member in streaming_vc.members:
            if not member.bot and (is_user_in_streaming_vc_with_camera(member) or member.id in bot_config.ALLOWED_USERS):
                try: await member.edit(mute=False, deafen=False); impacted.append(member.name)
                except Exception as e: logger.error(f"Error removing mute/deafen from {member.name}: {e}")
        await ctx.send("Unmuted & Undeafened: " + ", ".join(impacted) if impacted else "No users to unmute/undeafen.")
    else: await ctx.send("Streaming VC not found.")

@bot.command(name='modoff')
@require_allowed_user()
@handle_errors
async def modoff(ctx):
    async with state.vc_lock: state.vc_moderation_active = False
    logger.warning(f"VC Moderation DISABLED by {ctx.author.name}")
    await ctx.send("🛡️ VC Moderation has been temporarily **DISABLED**.")

@bot.command(name='modon')
@require_allowed_user()
@handle_errors
async def modon(ctx):
    async with state.vc_lock: state.vc_moderation_active = True
    logger.warning(f"VC Moderation ENABLED by {ctx.author.name}")
    await ctx.send("🛡️ VC Moderation has been **ENABLED**.")

@bot.command(name='disablenotifications')
@require_allowed_user()
@handle_errors
async def disablenotifications(ctx):
    """Disables certain server event notifications."""
    if not state.notifications_enabled:
        await ctx.send("❌ Notifications are already disabled.", delete_after=10)
        return
    state.notifications_enabled = False
    await ctx.send("✅ Notifications for unbans, leaves, kicks, and timeout removals have been **DISABLED**.")
    logger.info(f"Notifications DISABLED by {ctx.author.name}")

@bot.command(name='enablenotifications')
@require_allowed_user()
@handle_errors
async def enablenotifications(ctx):
    """Enables certain server event notifications."""
    if state.notifications_enabled:
        await ctx.send("✅ Notifications are already enabled.", delete_after=10)
        return
    state.notifications_enabled = True
    await ctx.send("✅ Notifications for unbans, leaves, kicks, and timeout removals have been **ENABLED**.")
    logger.info(f"Notifications ENABLED by {ctx.author.name}")

@bot.command(name='disable')
@require_allowed_user()
@handle_errors
async def disable(ctx, user: discord.User):
    if not user:
        await ctx.send("Could not find that user.")
        return

    if user.id in bot_config.ALLOWED_USERS:
        await ctx.send("Cannot disable Allowed Users.")
        return

    async with state.moderation_lock:
        if user.id in state.omegle_disabled_users:
            await ctx.send(f"User {user.mention} is already disabled.")
            return
        state.omegle_disabled_users.add(user.id)
    await ctx.send(f"✅ User {user.mention} has been **disabled** from using any commands.")
    logger.info(f"User {user.name} disabled from all commands by {ctx.author.name}.")


@bot.command(name='enable')
@require_allowed_user()
@handle_errors
async def enable(ctx, user: discord.User):
    if not user:
        await ctx.send("Could not find that user.")
        return
    async with state.moderation_lock:
        if user.id not in state.omegle_disabled_users:
            await ctx.send(f"User {user.mention} is not disabled.")
            return
        state.omegle_disabled_users.remove(user.id)
    await ctx.send(f"✅ User {user.mention} has been **re-enabled** and can use commands again.")
    logger.info(f"User {user.name} re-enabled for all commands by {ctx.author.name}.")


@bot.command(name='ban')
@require_allowed_user()
@handle_errors
async def ban(ctx, *, user_ids_str: str):
    """Bans one or more users by their ID with confirmation and a reason prompt. Usage: !ban <id1> <id2>..."""
    user_ids = user_ids_str.split()
    if not user_ids:
        await ctx.send("Usage: `!ban <user_id_1> <user_id_2> ...`")
        return

    users_to_ban = []
    failed_to_find = []
    for user_id in user_ids:
        try:
            # Ensure we're dealing with an integer ID
            user_to_ban = await bot.fetch_user(int(user_id))
            users_to_ban.append(user_to_ban)
        except ValueError:
            failed_to_find.append(f"`{user_id}` (Invalid ID format)")
        except discord.NotFound:
            failed_to_find.append(f"`{user_id}` (User not found)")
        except Exception as e:
            failed_to_find.append(f"`{user_id}` (Error: {e})")

    if not users_to_ban:
        await ctx.send("Could not find any valid users to ban.\n" + "\n".join(failed_to_find))
        return

    # --- Step 1: Confirmation ---
    user_list_str = "\n".join([f"- **{user.name}** (`{user.id}`)" for user in users_to_ban])
    confirm_msg_content = f"⚠️ **Are you sure you want to ban the following user(s)?**\n{user_list_str}\n\nReact with ✅ to confirm or ❌ to cancel."
    
    confirm_msg = await ctx.send(confirm_msg_content)
    for emoji in ("✅", "❌"): await confirm_msg.add_reaction(emoji)

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in {"✅", "❌"} and reaction.message.id == confirm_msg.id

    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=60.0, check=check)
        if str(reaction.emoji) == "❌":
            await confirm_msg.edit(content="🟢 Ban command cancelled.", view=None)
            return
    except asyncio.TimeoutError:
        await confirm_msg.edit(content="⌛ Ban command timed out.", view=None)
        return
    finally:
        try: await confirm_msg.clear_reactions()
        except discord.HTTPException: pass

    # --- Step 2: Ask for Reason ---
    try:
        await confirm_msg.edit(content="📝 **Please provide a reason for the ban.**\nYour next message in this channel will be used as the reason. You have 2 minutes.", view=None)
    except discord.NotFound: # If the original message was deleted somehow
        confirm_msg = await ctx.send("📝 **Please provide a reason for the ban.**\nYour next message in this channel will be used as the reason. You have 2 minutes.")


    def reason_check(message):
        return message.author == ctx.author and message.channel == ctx.channel

    try:
        reason_message = await bot.wait_for("message", timeout=120.0, check=reason_check)
        reason_text = reason_message.content
        try:
            await reason_message.delete() # Clean up the reason message
        except (discord.Forbidden, discord.NotFound):
            pass # Ignore if we can't delete it
    except asyncio.TimeoutError:
        await confirm_msg.edit(content="⌛ Reason prompt timed out. Ban command cancelled.", view=None)
        return

    # --- Step 3: Apply Bans ---
    await confirm_msg.edit(content=f"⏳ Banning {len(users_to_ban)} user(s) with reason: *{reason_text}*", view=None)
    
    successes = []
    failures = failed_to_find  # Start with users we couldn't find
    final_reason = f"Banned by {ctx.author.name} (ID: {ctx.author.id}): {reason_text}"

    for user_to_ban in users_to_ban:
        try:
            await ctx.guild.ban(user_to_ban, reason=final_reason, delete_message_days=0)
            successes.append(f"`{user_to_ban.name}` (ID: {user_to_ban.id})")
            logger.info(f"Successfully banned user {user_to_ban.name} (ID: {user_to_ban.id}) on behalf of {ctx.author.name}.")
        except discord.Forbidden:
            failures.append(f"`{user_to_ban.name}` (Missing permissions to ban this user)")
        except discord.HTTPException as e:
            failures.append(f"`{user_to_ban.name}` (Failed due to a network error: {e})")
        except Exception as e:
            failures.append(f"`{user_to_ban.name}` (An unexpected error occurred: {e})")
            logger.error(f"Unexpected error during !ban for {user_to_ban.name}: {e}", exc_info=True)

    response_message = ""
    if successes:
        response_message += f"✅ **Successfully banned:**\n" + "\n".join(f"- {s}" for s in successes)
    if failures:
        response_message += f"\n\n❌ **Failed actions:**\n" + "\n".join(f"- {f}" for f in failures)
    
    await confirm_msg.edit(content=response_message)


@bot.command(name='unban')
@require_allowed_user()
@handle_errors
async def unban(ctx, *, user_ids_str: str):
    """Unbans one or more users by ID with confirmation. Usage: !unban <id1>,<id2>,..."""
    if not user_ids_str:
        await ctx.send("Usage: `!unban <user_id_1>, <user_id_2>, ...`")
        return
    
    user_ids = [uid.strip() for uid in user_ids_str.split(',')]
    
    users_to_unban = []
    failed_to_find = []
    
    banned_users = {entry.user.id: entry.user async for entry in ctx.guild.bans()}

    for user_id in user_ids:
        try:
            user_id_int = int(user_id)
            if user_id_int in banned_users:
                users_to_unban.append(banned_users[user_id_int])
            else:
                failed_to_find.append(f"`{user_id}` (User is not banned or does not exist)")
        except ValueError:
            failed_to_find.append(f"`{user_id}` (Invalid ID format)")

    if not users_to_unban:
        await ctx.send("Could not find any valid banned users to unban.\n" + "\n".join(failed_to_find))
        return

    user_list_str = "\n".join([f"- **{user.name}** (`{user.id}`)" for user in users_to_unban])
    confirm_msg_content = f"⚠️ **Are you sure you want to unban the following user(s)?**\n{user_list_str}\n\nReact with ✅ to confirm or ❌ to cancel."
    
    confirm_msg = await ctx.send(confirm_msg_content)
    for emoji in ("✅", "❌"): await confirm_msg.add_reaction(emoji)

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in {"✅", "❌"} and reaction.message.id == confirm_msg.id

    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=60.0, check=check)
        if str(reaction.emoji) == "❌":
            await confirm_msg.edit(content="🟢 Unban command cancelled.", view=None)
            return
    except asyncio.TimeoutError:
        await confirm_msg.edit(content="⌛ Unban command timed out.", view=None)
        return

    await confirm_msg.edit(content="⏳ Unbanning users...", view=None)
    successes = []
    failures = failed_to_find
    for user_to_unban in users_to_unban:
        try:
            reason = f"Unbanned by {ctx.author.name} (ID: {ctx.author.id}) via bot command."
            await ctx.guild.unban(user_to_unban, reason=reason)
            successes.append(f"`{user_to_unban.name}` (ID: {user_to_unban.id})")
        except Exception as e:
            failures.append(f"`{user_to_unban.name}` (Failed to unban: {e})")

    response_message = ""
    if successes:
        response_message += f"✅ **Successfully unbanned:**\n" + "\n".join(f"- {s}" for s in successes)
    if failures:
        response_message += f"\n\n❌ **Failed actions:**\n" + "\n".join(f"- {f}" for f in failures)
    
    await confirm_msg.edit(content=response_message)


@bot.command(name='unbanall')
@require_allowed_user()
@handle_errors
async def unbanall(ctx):
    """Unbans all users from the server with confirmation."""
    ban_entries = [entry async for entry in ctx.guild.bans()]
    
    if not ban_entries:
        await ctx.send("There are no users currently banned from this server.")
        return

    confirm_msg_content = f"⚠️ **CRITICAL ACTION** ⚠️\n\nAre you sure you want to unban all **{len(ban_entries)}** users from the server? This cannot be undone.\n\nReact with ✅ to confirm or ❌ to cancel."
    
    confirm_msg = await ctx.send(confirm_msg_content)
    for emoji in ("✅", "❌"): await confirm_msg.add_reaction(emoji)

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in {"✅", "❌"} and reaction.message.id == confirm_msg.id

    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=60.0, check=check)
        if str(reaction.emoji) == "❌":
            await confirm_msg.edit(content="🟢 Unban All command cancelled.", view=None)
            return
    except asyncio.TimeoutError:
        await confirm_msg.edit(content="⌛ Unban All command timed out.", view=None)
        return

    await confirm_msg.edit(content=f"⏳ Unbanning all {len(ban_entries)} users...", view=None)
    
    success_count = 0
    failures = []
    
    for ban_entry in ban_entries:
        try:
            reason = f"Mass unban by {ctx.author.name} (ID: {ctx.author.id})."
            await ctx.guild.unban(ban_entry.user, reason=reason)
            success_count += 1
            await asyncio.sleep(1) # Sleep to avoid hitting rate limits on large servers
        except Exception as e:
            failures.append(f"`{ban_entry.user.name}` (ID: {ban_entry.user.id}) - Error: {e}")

    response_message = f"✅ **Finished. Unbanned {success_count} of {len(ban_entries)} users.**"
    if failures:
        response_message += f"\n\n❌ **Failed to unban:**\n" + "\n".join(f"- {f}" for f in failures)
    
    await confirm_msg.edit(content=response_message)


# --- Commands Delegated to BotHelper ---
@bot.command(name='bans', aliases=['banned'])
@require_admin_preconditions()
@handle_errors
async def bans(ctx) -> None: await helper.show_bans(ctx)

@bot.command(name='top')
@require_allowed_user()
@handle_errors
async def top_members(ctx) -> None: await helper.show_top_members(ctx)

@bot.command(name='info', aliases=['about'])
@require_user_preconditions()
@handle_errors
async def info(ctx) -> None: await helper.show_info(ctx)

@bot.command(name='roles')
@require_allowed_user()
@handle_errors
async def roles(ctx) -> None: await helper.list_roles(ctx)

@bot.command(name='admin', aliases=['owner', 'admins', 'owners'])
@require_allowed_user()
@handle_errors
async def admin(ctx) -> None: await helper.show_admin_list(ctx)

@bot.command(name='commands')
@require_admin_preconditions()
@handle_errors
async def commands_list(ctx) -> None: await helper.show_commands_list(ctx)

@bot.command(name='whois')
@require_allowed_user()
@handle_errors
async def whois(ctx) -> None: await helper.show_whois(ctx)

@bot.command(name='rtimeouts')
@require_admin_preconditions()
@handle_errors
async def remove_timeouts(ctx) -> None: await helper.remove_timeouts(ctx)

@bot.command(name='rules')
@require_user_preconditions()
@handle_errors
async def rules(ctx) -> None: await helper.show_rules(ctx)

@bot.command(name='timeouts')
@require_admin_preconditions()
@handle_errors
async def timeouts(ctx) -> None: await helper.show_timeouts(ctx)

@bot.command(name='times')
@require_user_preconditions()
@handle_errors
async def time_report(ctx) -> None: await helper.show_times_report(ctx)

@bot.command(name='stats')
@require_allowed_user()
@handle_errors
async def analytics_report(ctx) -> None: await helper.show_analytics_report(ctx)

@bot.command(name='join')
@require_allowed_user()
@handle_errors
async def join(ctx) -> None: await helper.send_join_invites(ctx)

@bot.command(name='clearstats')
@require_allowed_user()
@handle_errors
async def clear_stats(ctx) -> None:
    record_command_usage(state.analytics, "!clearstats")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!clearstats")
    await helper.clear_stats(ctx)

@bot.command(name='clearwhois')
@require_allowed_user()
@handle_errors
async def clear_whois(ctx) -> None:
    record_command_usage(state.analytics, "!clearwhois")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!clearwhois")
    await helper.clear_whois_data(ctx)

#########################################
# Main Execution
#########################################
if __name__ == "__main__":
    required_vars = ["BOT_TOKEN"]
    if missing := [var for var in required_vars if not os.getenv(var)]:
        logger.critical(f"Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    def handle_shutdown(signum, _frame):
        logger.info("Graceful shutdown initiated by signal")
        if not getattr(bot, "_is_shutting_down", False):
            bot.loop.create_task(_initiate_shutdown(None))

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        bot.run(os.getenv("BOT_TOKEN"))
    except discord.LoginFailure as e:
        logger.critical(f"Invalid token: {e}"); sys.exit(1)
    except Exception as e:
        logger.critical(f"Fatal error during bot run: {e}", exc_info=True); raise
    finally:
        logger.info("Starting final shutdown process...")
        async def unregister_all_hotkeys():
            async def unregister_hotkey(enabled, combo, name):
                if enabled:
                    try: await asyncio.to_thread(keyboard.remove_hotkey, combo)
                    except Exception: pass
            if bot_config := globals().get('bot_config'):
                await unregister_hotkey(bot_config.ENABLE_GLOBAL_HOTKEY, bot_config.GLOBAL_HOTKEY_COMBINATION, "skip")
        if 'keyboard' in globals(): asyncio.run(unregister_all_hotkeys())
        if 'omegle_handler' in globals() and omegle_handler.driver: asyncio.run(omegle_handler.close())
        if 'state' in globals():
            logger.info("Performing final state save..."); asyncio.run(save_state_async())
        logger.info("Shutdown complete")
