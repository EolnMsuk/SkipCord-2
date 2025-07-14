#!/usr/bin/env python

# Standard library imports
import asyncio
import json
import logging
import logging.config
import os
import signal
import sys
import time
from datetime import datetime, timezone, timedelta, time as dt_time
from functools import wraps
from typing import Any, Callable, Optional, Union, List

# Third-party imports
import discord
import keyboard
from discord.ext import commands, tasks
from discord.ui import View, Button
from dotenv import load_dotenv

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
    log_command_usage,
    set_bot_state_instance
)

# Load environment variables
load_dotenv()

# Initialize configuration and state
bot_config = BotConfig.from_config_module(config)
state = BotState(bot_config)
set_bot_state_instance(state)
omegle_handler = OmegleHandler(bot_config)

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", help_command=None, intents=intents)


# Constants
STATE_FILE = "data.json"

#########################################
# Persistence Functions
#########################################

@tasks.loop(minutes=59)
async def periodic_cleanup():
    """Executes unified cleanup"""
    try:
        await state.clean_old_entries()
        logging.info("Unified cleanup completed (24h/100-entry rules)")
    except Exception as e:
        logging.error(f"Cleanup error: {e}", exc_info=True)

def _blocking_json_dump(file_path: str, data: dict) -> None:
    """Synchronous helper for json.dump to be run in a separate thread."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

def _blocking_json_load(file_path: str) -> dict:
    """Synchronous helper for json.load to be run in a separate thread."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

async def save_state_async() -> None:
    """Saves bot state to disk asynchronously, including active VC sessions."""
    current_time = time.time()
    
    # Use locks to ensure data consistency during the save operation
    async with state.vc_lock, state.analytics_lock, state.moderation_lock:
        vc_data_to_save = {user_id: data.copy() for user_id, data in state.vc_time_data.items()}
        
        for user_id, session_start in state.active_vc_sessions.items():
            session_duration = current_time - session_start
            
            if user_id not in vc_data_to_save:
                member = bot.get_guild(bot_config.GUILD_ID).get_member(user_id)
                username = member.name if member else "Unknown"
                display_name = member.display_name if member else "Unknown"
                vc_data_to_save[user_id] = {
                    "total_time": 0,
                    "sessions": [],
                    "username": username,
                    "display_name": display_name
                }
            
            vc_data_to_save[user_id]["sessions"].append({
                "start": session_start,
                "end": current_time,
                "duration": session_duration,
                "vc_name": "Streaming VC"
            })
            
            vc_data_to_save[user_id]["total_time"] += session_duration
        
        serializable_state = {
            "analytics": state.analytics,
            "users_received_rules": list(state.users_received_rules),
            "user_violations": state.user_violations,
            "active_timeouts": state.active_timeouts,
            "recent_joins": [[e[0], e[1], e[2], e[3].isoformat()] for e in state.recent_joins],
            "recent_leaves": [[e[0], e[1], e[2], e[3].isoformat()] for e in state.recent_leaves],
            "users_with_dms_disabled": list(state.users_with_dms_disabled),
            "recent_bans": [[e[0], e[1], e[2], e[3].isoformat(), e[4]] for e in state.recent_bans],
            "recent_kicks": [[e[0], e[1], e[2], e[3].isoformat(), e[4]] for e in state.recent_kicks],
            "recent_unbans": [[e[0], e[1], e[2], e[3].isoformat(), e[4]] for e in state.recent_unbans],
            "recent_untimeouts": [[e[0], e[1], e[2], e[3].isoformat(), e[4]] for e in state.recent_untimeouts],
            "vc_time_data": {
                str(user_id): {
                    "total_time": data["total_time"],
                    "sessions": data["sessions"],
                    "username": data.get("username", "Unknown"),
                    "display_name": data.get("display_name", "Unknown")
                }
                for user_id, data in vc_data_to_save.items()
            },
            "active_vc_sessions": {} # Active sessions are merged into vc_time_data for saving
        }
    
    try:
        # Run the blocking file I/O in a separate thread to not block the event loop
        await asyncio.to_thread(_blocking_json_dump, STATE_FILE, serializable_state)
        logging.info("Bot state saved, including active VC sessions")
    except Exception as e:
        logging.error(f"Failed to save bot state: {e}")

def save_state_sync():
    """Synchronous wrapper for saving state, used on shutdown."""
    asyncio.run(save_state_async())


async def load_state_async() -> None:
    """Loads the bot state from disk asynchronously if available."""
    if os.path.exists(STATE_FILE):
        try:
            data = await asyncio.to_thread(_blocking_json_load, STATE_FILE)
            
            analytics = data.get("analytics", {"command_usage": {}, "command_usage_by_user": {}, "violation_events": 0})
            if "command_usage_by_user" in analytics:
                analytics["command_usage_by_user"] = {int(k): v for k, v in analytics["command_usage_by_user"].items()}
            state.analytics = analytics
            state.user_violations = {int(k): v for k, v in data.get("user_violations", {}).items()}
            state.active_timeouts = {int(k): v for k, v in data.get("active_timeouts", {}).items()}
            state.users_received_rules = set(data.get("users_received_rules", []))
            state.users_with_dms_disabled = set(data.get("users_with_dms_disabled", []))
            state.recent_joins = [(entry[0], entry[1], entry[2], datetime.fromisoformat(entry[3])) for entry in data.get("recent_joins", [])]
            state.recent_leaves = [(entry[0], entry[1], entry[2], datetime.fromisoformat(entry[3])) for entry in data.get("recent_leaves", [])]
            state.recent_bans = [(entry[0], entry[1], entry[2], datetime.fromisoformat(entry[3]), entry[4]) for entry in data.get("recent_bans", [])]
            state.recent_kicks = [(entry[0], entry[1], entry[2], datetime.fromisoformat(entry[3]), entry[4]) for entry in data.get("recent_kicks", [])]
            state.recent_unbans = [(entry[0], entry[1], entry[2], datetime.fromisoformat(entry[3]), entry[4]) for entry in data.get("recent_unbans", [])]
            state.recent_untimeouts = [(entry[0], entry[1], entry[2], datetime.fromisoformat(entry[3]), entry[4]) for entry in data.get("recent_untimeouts", [])]
            
            state.vc_time_data = {
                int(user_id): {
                    "total_time": data["total_time"],
                    "sessions": data["sessions"],
                    "username": data.get("username", "Unknown"),
                    "display_name": data.get("display_name", "Unknown")
                }
                for user_id, data in data.get("vc_time_data", {}).items()
            }
            
            state.active_vc_sessions = {
                int(user_id): start_time
                for user_id, start_time in data.get("active_vc_sessions", {}).items()
            }
            
            logging.info("Bot state loaded successfully.")
        except Exception as e:
            logging.error(f"Failed to load bot state: {e}")
    else:
        logging.info("No saved state file found, starting with a fresh state.")
        state.vc_time_data = {}
        state.active_vc_sessions = {}

# Pass the save function to the helper for immediate persistence of critical events
helper = BotHelper(bot, state, bot_config, save_state_async)

@tasks.loop(minutes=14)
async def periodic_state_save() -> None:
    await save_state_async()

#########################################
# Voice Connection Functions
#########################################

def is_user_in_streaming_vc_with_camera(user: discord.Member) -> bool:
    """Checks if a user in the Streaming VC has their camera on."""
    streaming_vc = user.guild.get_channel(bot_config.STREAMING_VC_ID)
    return bool(streaming_vc and user in streaming_vc.members and user.voice and user.voice.self_video)

async def global_skip() -> None:
    """Executes the global skip command, triggered via a global hotkey."""
    guild = bot.get_guild(bot_config.GUILD_ID)
    if guild:
        await omegle_handler.custom_skip()
        logging.info("Executed global skip command via hotkey.")
    else:
        logging.error("Guild not found for global skip.")

#########################################
# Decorators
#########################################
def require_command_channel(func: Callable) -> Callable:
    """Decorator to enforce that non-allowed users use the designated command channel."""
    @wraps(func)
    async def wrapper(ctx, *args, **kwargs):
        if ctx.author.id not in bot_config.ALLOWED_USERS and ctx.channel.id != bot_config.COMMAND_CHANNEL_ID:
            await ctx.send(f"All commands (including !{func.__name__}) should be used in <#{bot_config.COMMAND_CHANNEL_ID}>")
            return
        return await func(ctx, *args, **kwargs)
    return wrapper

#########################################
# Bot Event Handlers
#########################################
@bot.event
async def on_ready() -> None:
    """Handles bot initialization when it comes online."""
    logging.info(f"Bot is online as {bot.user}")
    
    try:
        channel = bot.get_channel(bot_config.CHAT_CHANNEL_ID)
        if channel:
            await channel.send("✅ Bot is online and ready!")
    except Exception as e:
        logging.error(f"Failed to send online message: {e}")
    
    try:
        await load_state_async()
        logging.info("State loaded successfully")
    except Exception as e:
        logging.error(f"Error loading state: {e}", exc_info=True)
    
    try:
        if not periodic_state_save.is_running(): periodic_state_save.start()
        if not periodic_cleanup.is_running(): periodic_cleanup.start()
        if not periodic_help_menu.is_running(): periodic_help_menu.start()
        if not timeout_unauthorized_users.is_running(): timeout_unauthorized_users.start()
        if not daily_auto_stats_clear.is_running():
            daily_auto_stats_clear.start()
            logging.info("Daily auto-stats task started")
        
        if not await omegle_handler.initialize():
            logging.critical("Selenium initialization failed. Browser commands will not work until bot restart.")
        
        async def init_vc_moderation():
            guild = bot.get_guild(bot_config.GUILD_ID)
            if not guild: return
            streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
            if not streaming_vc: return
            
            async with state.vc_lock:
                for member in streaming_vc.members:
                    if not member.bot and member.id not in state.active_vc_sessions:
                        state.active_vc_sessions[member.id] = time.time()
                        logging.info(f"Started tracking VC time for existing member: {member.name} (ID: {member.id})")
                    
                    if (not member.bot and member.id not in bot_config.ALLOWED_USERS and member.id != bot_config.MUSIC_BOT and not (member.voice and member.voice.self_video)):
                        try:
                            if not bot_config.VC_MODERATION_PERMANENTLY_DISABLED and state.vc_moderation_active:
                                await member.edit(mute=True, deafen=True)
                                logging.info(f"Auto-muted/deafened {member.name} for camera off.")
                        except Exception as e:
                            logging.error(f"Failed to auto mute/deafen {member.name}: {e}")
                        state.camera_off_timers[member.id] = time.time()
        
        asyncio.create_task(init_vc_moderation())
        
        if bot_config.ENABLE_GLOBAL_HOTKEY:
            try: keyboard.remove_hotkey(bot_config.GLOBAL_HOTKEY_COMBINATION)
            except (KeyError, ValueError): pass
    
            def hotkey_callback() -> None:
                logging.info("Global hotkey pressed, triggering skip command.")
                bot.loop.call_soon_threadsafe(lambda: asyncio.create_task(global_skip()))
    
            try:
                keyboard.add_hotkey(bot_config.GLOBAL_HOTKEY_COMBINATION, hotkey_callback)
                logging.info(f"Registered global hotkey: {bot_config.GLOBAL_HOTKEY_COMBINATION}")
            except Exception as e:
                logging.error(f"Failed to register hotkey: {e}")
                bot_config.ENABLE_GLOBAL_HOTKEY = False
                logging.warning("Global hotkey functionality disabled due to registration failure")
        
        logging.info("Initialization complete")
    
    except Exception as e:
        logging.error(f"Error during on_ready: {e}", exc_info=True)

@bot.event
async def on_member_join(member: discord.Member) -> None:
    await helper.handle_member_join(member)

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User) -> None:
    await helper.handle_member_ban(guild, user)

@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User) -> None:
    await helper.handle_member_unban(guild, user)

@bot.event
async def on_member_remove(member: discord.Member) -> None:
    await helper.handle_member_remove(member)

@bot.event
@handle_errors
async def on_voice_state_update(member: discord.Member, before, after) -> None:
    """Handles voice state updates with batch processing and rate limit protection."""
    await asyncio.sleep(0.1)
    
    async def safe_edit(member, **kwargs):
        try:
            await member.edit(**kwargs)
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = e.retry_after + 1
                logging.warning(f"Rate limited on member.edit. Waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                try: await member.edit(**kwargs)
                except Exception as e2: logging.error(f"Retry failed: {e2}")
            else: raise

    async def safe_send(target, content):
        try:
            await target.send(content)
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = e.retry_after + 1
                logging.warning(f"Rate limited on channel.send. Waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                try: await target.send(content)
                except Exception as e2: logging.error(f"Retry failed: {e2}")
            else: raise

    async def safe_dm(member, content):
        try:
            await member.send(content)
        except discord.HTTPException as e:
            if e.code == 50007:  # Cannot send messages to this user
                async with state.moderation_lock:
                    state.users_with_dms_disabled.add(member.id)
                    state.failed_dm_users.add(member.id)
                logging.warning(f"Could not DM {member.display_name} (DMs disabled or blocked).")
            elif e.status == 429:  # Rate limited
                retry_after = e.retry_after + 1
                logging.warning(f"Rate limited on member.send. Waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                try:
                    await member.send(content)
                except Exception as e2:
                    logging.error(f"Retry failed after rate limit: {e2}")
            else:
                logging.error(f"Unhandled HTTP error sending DM to {member.name}: {e}", exc_info=True)
        except Exception as e:
            logging.error(f"Generic error sending DM to {member.name}: {e}", exc_info=True)
            async with state.moderation_lock:
                state.failed_dm_users.add(member.id)

    # This top-level try/except is now complemented by the @handle_errors decorator
    # for any unhandled exceptions, while keeping specific logic for rate limiting.
    try:
        if member == bot.user: return
        
        streaming_vc = member.guild.get_channel(bot_config.STREAMING_VC_ID)
        alt_vc = member.guild.get_channel(bot_config.ALT_VC_ID)
        punishment_vc = member.guild.get_channel(bot_config.PUNISHMENT_VC_ID)

        # --- VC Time Tracking ---
        # Determine if the user's channel has actually changed.
        was_in_streaming_vc = before.channel and before.channel.id == bot_config.STREAMING_VC_ID
        is_now_in_streaming_vc = after.channel and after.channel.id == bot_config.STREAMING_VC_ID

        async with state.vc_lock:
            # A session starts ONLY if the user entered the streaming VC from another channel or from being disconnected.
            if is_now_in_streaming_vc and not was_in_streaming_vc:
                if member.id not in state.active_vc_sessions:
                    state.active_vc_sessions[member.id] = time.time()
                    if member.id not in state.vc_time_data:
                        state.vc_time_data[member.id] = {"total_time": 0, "sessions": [], "username": member.name, "display_name": member.display_name}
                    else:
                        # Update names in case they changed
                        state.vc_time_data[member.id]["username"] = member.name
                        state.vc_time_data[member.id]["display_name"] = member.display_name
                    logging.info(f"VC Time Tracking: {member.display_name} started session in Streaming VC")
            
            # A session ends ONLY if the user was in the streaming VC and left for another channel or disconnected.
            elif was_in_streaming_vc and not is_now_in_streaming_vc:
                if member.id in state.active_vc_sessions:
                    start_time = state.active_vc_sessions.pop(member.id)
                    duration = time.time() - start_time
                    if member.id not in state.vc_time_data:
                        state.vc_time_data[member.id] = {"total_time": 0, "sessions": [], "username": member.name, "display_name": member.display_name}
                    state.vc_time_data[member.id]["total_time"] += duration
                    state.vc_time_data[member.id]["sessions"].append({"start": start_time, "end": time.time(), "duration": duration, "vc_name": before.channel.name})
                    logging.info(f"VC Time Tracking: {member.display_name} added {duration:.1f}s from Streaming VC")
        # --- End VC Time Tracking ---

        # Revert server mutes for allowed users
        if after.channel and after.channel.id in [bot_config.STREAMING_VC_ID, bot_config.ALT_VC_ID] and member.id in bot_config.ALLOWED_USERS:
            if member.voice:
                if member.voice.mute and not member.voice.self_mute:
                    await safe_edit(member, mute=False)
                    logging.info(f"Reverted server mute for allowed user {member.display_name}")
                if member.voice.deaf and not member.voice.self_deaf:
                    await safe_edit(member, deafen=False)
                    logging.info(f"Reverted server deafen for allowed user {member.display_name}")

        # --- VC Moderation, Rules, and Auto-Pause Logic ---
        if after.channel and after.channel.id == bot_config.STREAMING_VC_ID:
            # Send rules on first join
            async with state.vc_lock:
                # This logic checks if this is the first voice state update that places the user in this VC
                just_joined = not was_in_streaming_vc
            
            if just_joined:
                logging.info(f"{member.display_name} joined Streaming VC")
                async with state.moderation_lock:
                    should_send_rules = (member.id not in state.users_received_rules and 
                                         member.id not in state.users_with_dms_disabled and 
                                         member.id not in state.failed_dm_users)
                if should_send_rules:
                    await safe_dm(member, bot_config.RULES_MESSAGE)
                    async with state.moderation_lock:
                        state.users_received_rules.add(member.id)
                    logging.info(f"Sent rules to {member.display_name}")

            # VC Moderation (camera check)
            async with state.vc_lock:
                if (member.id not in bot_config.ALLOWED_USERS and member.id != bot_config.MUSIC_BOT and state.vc_moderation_active and not bot_config.VC_MODERATION_PERMANENTLY_DISABLED):
                    if not after.self_video:
                        if member.voice and (not member.voice.mute or not member.voice.deaf):
                            await safe_edit(member, mute=True, deafen=True)
                            logging.info(f"Auto-muted/deafened {member.display_name} for camera off")
                        state.camera_off_timers[member.id] = time.time()
                    elif not state.hush_override_active:
                        if member.voice and (member.voice.mute or member.voice.deaf):
                            await safe_edit(member, mute=False, deafen=False)
                            logging.info(f"Auto-unmuted {member.display_name} after camera on")
                        state.camera_off_timers.pop(member.id, None)

            # Auto-pause when last camera turns off
            if (before.self_video and not after.self_video and streaming_vc and member.id not in bot_config.ALLOWED_USERS):
                users_with_camera = [m for m in streaming_vc.members if m.voice and m.voice.self_video and m.id not in bot_config.ALLOWED_USERS and not m.bot]
                async with state.vc_lock:
                    if not users_with_camera and (time.time() - state.last_auto_pause_time >= 1):
                        state.last_auto_pause_time = time.time()
                        await omegle_handler.refresh(is_pause=True)
                        logging.info("Auto Paused - No Cameras Detected")
                        if (command_channel := member.guild.get_channel(bot_config.COMMAND_CHANNEL_ID)):
                            await safe_send(command_channel, "Automatically paused")
                        
        elif before.channel and before.channel.id == bot_config.STREAMING_VC_ID:
            # Logic for when a user leaves the streaming VC
            async with state.vc_lock:
                state.camera_off_timers.pop(member.id, None)
            
            # Auto-pause when last user with camera leaves
            remaining_non_allowed = [m for m in before.channel.members if not m.bot and m.id not in bot_config.ALLOWED_USERS and m.voice and m.voice.self_video]
            async with state.vc_lock:
                if not remaining_non_allowed and (time.time() - state.last_auto_pause_time >= 1):
                    state.last_auto_pause_time = time.time()
                    await omegle_handler.refresh(is_pause=True)
                    logging.info("Auto Paused - Last user with camera left")
                    if (command_channel := member.guild.get_channel(bot_config.COMMAND_CHANNEL_ID)):
                        await safe_send(command_channel, "Automatically paused")
        # --- End Moderation Logic ---

        if after.channel and after.channel.id == bot_config.ALT_VC_ID:
            logging.info(f"{member.display_name} joined Alt VC")
        elif before.channel and before.channel.id == bot_config.ALT_VC_ID:
            logging.info(f"{member.display_name} left Alt VC")

        # Unmute user in punishment VC
        if after.channel and after.channel.id == bot_config.PUNISHMENT_VC_ID:
            if member.voice and (member.voice.mute or member.voice.deaf):
                try:
                    await member.edit(mute=False, deafen=False)
                    logging.info(f"Automatically unmuted and undeafened {member.name} in Punishment VC.")
                except Exception as e:
                    logging.error(f"Failed to unmute/undeafen {member.name} in Punishment VC: {e}")
                    
    except discord.HTTPException as e:
        if e.status == 429:
            retry_after = e.retry_after + 1
            logging.warning(f"Global rate limit in on_voice_state_update. Waiting {retry_after}s")
            await asyncio.sleep(retry_after)
        else:
            # Re-raise other HTTP exceptions so the decorator can catch them
            raise

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    """Handles member updates including timeouts, role changes, and timeout removals."""
    try:
        # Role change notifications
        if before.roles != after.roles:
            roles_gained = [role for role in after.roles if role not in before.roles and role.name != "@everyone"]
            roles_lost = [role for role in before.roles if role not in after.roles and role.name != "@everyone"]
            if roles_gained or roles_lost:
                channel = after.guild.get_channel(bot_config.CHAT_CHANNEL_ID)
                if channel:
                    embed = await build_role_update_embed(after, roles_gained, roles_lost)
                    await channel.send(embed=embed)

        # Timeout added/removed notifications
        if before.is_timed_out() != after.is_timed_out():
            if after.is_timed_out():
                # User was timed out
                async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                    if entry.target.id == after.id and hasattr(entry.after, "timed_out_until"):
                        duration = (entry.after.timed_out_until - datetime.now(timezone.utc)).total_seconds()
                        await helper.send_timeout_notification(after, entry.user, int(duration), entry.reason or "No reason provided")
                        async with state.moderation_lock:
                            state.active_timeouts[after.id] = {
                                "timeout_end": time.time() + duration,
                                "reason": entry.reason or "No reason provided",
                                "timed_by": entry.user.name,
                                "timed_by_id": entry.user.id,
                                "start_timestamp": time.time()
                            }
                        break
            else:
                # User's timeout was removed
                async with state.moderation_lock:
                    if after.id in state.pending_timeout_removals:
                        return # Already processing this removal
                    state.pending_timeout_removals[after.id] = True
                    
                async def handle_timeout_removal():
                    await asyncio.sleep(2) # Wait briefly for audit log
                    
                    duration = 0
                    reason = "Timeout Ended"
                    moderator_name = "System"
                    moderator_id = None

                    async with state.moderation_lock:
                        if after.id in state.active_timeouts:
                            timeout_data = state.active_timeouts[after.id]
                            duration = int(time.time() - timeout_data.get("start_timestamp", time.time()))
                            
                    try:
                        async for entry in after.guild.audit_logs(limit=10, action=discord.AuditLogAction.member_update, after=datetime.now(timezone.utc) - timedelta(seconds=30)):
                            if (entry.target.id == after.id and getattr(entry.before, "timed_out_until", None) is not None and getattr(entry.after, "timed_out_until", None) is None):
                                moderator_name = entry.user.name
                                moderator_id = entry.user.id
                                reason = f"Timeout removed by 🛡️ {moderator_name}"
                                break
                    except Exception as e:
                        logging.error(f"Error checking audit logs for un-timeout: {e}")
                    
                    async with state.moderation_lock:
                        if not state.recent_untimeouts or state.recent_untimeouts[-1][0] != after.id:
                            state.recent_untimeouts.append((after.id, after.name, after.display_name, datetime.now(timezone.utc), reason, moderator_name, moderator_id))
                            if len(state.recent_untimeouts) > 100:
                                state.recent_untimeouts.pop(0)

                        state.active_timeouts.pop(after.id, None)
                        state.pending_timeout_removals.pop(after.id, None)

                    await helper.send_timeout_removal_notification(after, duration, reason)
                
                bot.loop.create_task(handle_timeout_removal())

    except Exception as e:
        logging.error(f"Error in on_member_update: {e}", exc_info=True)

class HelpButton(Button):
    """A Discord UI button that sends a command when clicked."""
    def __init__(self, label: str, command: str) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.command = command

    async def callback(self, interaction: discord.Interaction) -> None:
        """Callback for button clicks: checks cooldowns and processes the command."""
        try:
            log_command_usage(interaction, self.command)
            
            user_id = interaction.user.id
            if user_id not in bot_config.ALLOWED_USERS and interaction.channel.id != bot_config.COMMAND_CHANNEL_ID:
                await interaction.response.send_message(f"All commands should be used in <#{bot_config.COMMAND_CHANNEL_ID}>", ephemeral=True)
                return

            current_time = time.time()
            async with state.cooldown_lock:
                if user_id in state.button_cooldowns:
                    last_used, warned = state.button_cooldowns[user_id]
                    time_left = bot_config.COMMAND_COOLDOWN - (current_time - last_used)
                    if time_left > 0:
                        if not warned:
                            await interaction.response.send_message(f"{interaction.user.mention}, wait {int(time_left)}s before using another button.", ephemeral=True)
                            state.button_cooldowns[user_id] = (last_used, True)
                        else:
                            # Acknowledge the interaction to prevent "interaction failed" message
                            await interaction.response.defer(ephemeral=True)
                        return
                state.button_cooldowns[user_id] = (current_time, False)

            await interaction.response.defer()
            # We need to fetch the command and invoke it properly
            cmd_name = self.command.lstrip("!")
            command_obj = bot.get_command(cmd_name)
            if command_obj:
                # Create a fake context for the command
                fake_message = await interaction.channel.send(f"{interaction.user.mention} used {self.command}")
                fake_message.content = self.command
                fake_message.author = interaction.user
                ctx = await bot.get_context(fake_message)
                await bot.invoke(ctx)
                await fake_message.delete() # Clean up the fake message
            else:
                logging.warning(f"Button tried to invoke non-existent command: {cmd_name}")
                await interaction.followup.send("Could not process that command.", ephemeral=True)
                
        except Exception as e:
            logging.error(f"Error in HelpButton callback: {e}", exc_info=True)


class HelpView(View):
    """A Discord UI view for quick command buttons."""
    def __init__(self) -> None:
        super().__init__(timeout=None) # Persistent view
        commands_dict = {"Skip/Start": "!skip", "Pause": "!pause", "Refresh": "!refresh", "Rules/Info": "!info"}
        for label, command in commands_dict.items():
            self.add_item(HelpButton(label, command))

@bot.event
async def on_message(message: discord.Message) -> None:
    """Processes incoming messages, enforcing cooldowns and permission checks."""
    try:
        if message.author == bot.user or not message.guild or message.guild.id != bot_config.GUILD_ID:
            return

        # Media-only channel moderation
        if bot_config.MEDIA_ONLY_CHANNEL_ID and message.channel.id == bot_config.MEDIA_ONLY_CHANNEL_ID:
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
                        logging.info(f"Deleted message from {message.author} in media-only channel #{message.channel.name} because it contained no media.")
                        await message.channel.send(
                            f"{message.author.mention}, this channel only allows photos and other media.",
                            delete_after=10
                        )
                    except discord.Forbidden:
                        logging.warning(f"Missing permissions to delete message in media-only channel #{message.channel.name}.")
                    except discord.NotFound:
                        pass 
                    except Exception as e:
                        logging.error(f"Error deleting message in media-only channel: {e}")
                    return

        if not message.content.startswith("!"):
            return
        
        await bot.process_commands(message)
        
    except Exception as e:
        logging.error(f"Error in on_message: {e}", exc_info=True)


async def send_help_menu(target: Any) -> None:
    """Sends an embedded help menu with available commands and interactive buttons."""
    try:
        help_description = """
**Skip/Start** -- Skip/Start Omegle
**Pause** ------- Pause Omegle
**Refresh** ----- Refresh Omegle
**Info** --------- Server Info
**!commands** - Admin Commands
"""
        embed = build_embed("SkipCord-2 v4", help_description, discord.Color.blue())
        
        if isinstance(target, (discord.TextChannel, discord.VoiceChannel, discord.Thread)):
            await target.send(embed=embed, view=HelpView())
        elif isinstance(target, discord.Message):
            await target.channel.send(embed=embed, view=HelpView())
        elif hasattr(target, 'channel') and hasattr(target.channel, 'send'):
            await target.channel.send(embed=embed, view=HelpView())
        else:
            logging.warning(f"Unsupported target type for help menu: {type(target)}")
            
    except Exception as e:
        logging.error(f"Error in send_help_menu: {e}")

@tasks.loop(minutes=2)
async def periodic_help_menu() -> None:
    """Periodically updates the help menu in the command channel."""
    try:
        guild = bot.get_guild(bot_config.GUILD_ID)
        if not guild: return
        channel = guild.get_channel(bot_config.COMMAND_CHANNEL_ID)
        if not channel or not hasattr(channel, 'send'): return

        try:
            refresh_msg = await channel.send("🔁 Refreshing help menu...")
            await asyncio.sleep(2)
            await safe_purge(channel, limit=50)
            await send_help_menu(channel)
            await asyncio.sleep(3)
            try: await refresh_msg.delete()
            except Exception: pass
        except discord.HTTPException as e:
            if e.status == 429:
                wait = e.retry_after + 5
                logging.warning(f"Rate limited. Retrying in {wait}s")
                await asyncio.sleep(wait)
    except Exception as e:
        logging.error(f"Help menu update failed: {e}", exc_info=True)
        await asyncio.sleep(300)

async def safe_purge(channel: discord.TextChannel, limit: int = 50) -> None:
    """Safely purges messages with strict rate limiting."""
    try:
        deleted = await channel.purge(limit=min(limit, 50))
        if deleted:
            await channel.send(f"🧹 Purged {len(deleted)} messages.", delete_after=5)
            logging.info(f"Purged {len(deleted)} messages in {channel.name}")
            await asyncio.sleep(1)
    except discord.HTTPException as e:
        if e.status == 429:
            wait = max(e.retry_after, 10)
            logging.warning(f"Purge rate limited in {channel.name}. Waiting {wait}s")
            await asyncio.sleep(wait)
        else: raise
    except Exception as e:
        logging.error(f"An error occurred during purge: {e}", exc_info=True)


@tasks.loop(time=dt_time(bot_config.AUTO_STATS_HOUR_UTC, bot_config.AUTO_STATS_MINUTE_UTC))
async def daily_auto_stats_clear() -> None:
    """Automatically posts VC time stats and clears all statistics at specified UTC time daily"""
    channel = bot.get_channel(bot_config.AUTO_STATS_CHAN)
    if not channel:
        logging.error("AUTO_STATS_CHAN channel not found! Cannot run daily stats clear.")
        return
    
    try:
        await helper.show_times_report(channel)
    except Exception as e:
        logging.error(f"Daily auto-stats failed during 'show_times_report': {e}", exc_info=True)
        # Continue to clear stats even if reporting fails
    
    try:
        streaming_vc = channel.guild.get_channel(bot_config.STREAMING_VC_ID)
        alt_vc = channel.guild.get_channel(bot_config.ALT_VC_ID)
        current_members = []
        if streaming_vc: current_members.extend([m for m in streaming_vc.members if not m.bot])
        if alt_vc: current_members.extend([m for m in alt_vc.members if not m.bot])

        # Lock state for clearing
        async with state.vc_lock, state.analytics_lock, state.moderation_lock:
            state.vc_time_data = {}
            state.active_vc_sessions = {}
            state.analytics = {"command_usage": {}, "command_usage_by_user": {}, "violation_events": 0}
            state.user_violations = {}
            state.camera_off_timers = {}
            
            # After clearing, re-initialize sessions for members currently in VC
            if current_members:
                current_time = time.time()
                for member in current_members:
                    state.active_vc_sessions[member.id] = current_time
                    state.vc_time_data[member.id] = {"total_time": 0, "sessions": [], "username": member.name, "display_name": member.display_name}
                logging.info(f"Restarted VC tracking for {len(current_members)} members after auto-clear")
    except Exception as e:
        logging.error(f"Daily auto-stats failed during state clearing: {e}", exc_info=True)
        return # Do not send confirmation if clearing failed
    
    try:
        await channel.send("✅ Statistics automatically cleared and tracking restarted!")
    except Exception as e:
        logging.error(f"Daily auto-stats failed to send confirmation message: {e}", exc_info=True)


@tasks.loop(seconds=16)
@handle_errors
async def timeout_unauthorized_users() -> None:
    """Periodically checks for users in Streaming VC OR Alt VC without an active camera and issues violations."""
    if bot_config.VC_MODERATION_PERMANENTLY_DISABLED or not state.vc_moderation_active: return
    guild = bot.get_guild(bot_config.GUILD_ID)
    if not guild: return
    
    streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
    alt_vc = guild.get_channel(bot_config.ALT_VC_ID)
    punishment_vc = guild.get_channel(bot_config.PUNISHMENT_VC_ID)
    if not all([streaming_vc, alt_vc, punishment_vc]): return

    for vc in [streaming_vc, alt_vc]:
        for member in vc.members:
            if member.bot or member.id in bot_config.ALLOWED_USERS or member.id == bot_config.MUSIC_BOT:
                async with state.vc_lock:
                    state.camera_off_timers.pop(member.id, None)
                continue

            if not (member.voice and member.voice.self_video):
                async with state.vc_lock, state.moderation_lock:
                    if member.id in state.camera_off_timers:
                        if time.time() - state.camera_off_timers[member.id] >= bot_config.CAMERA_OFF_ALLOWED_TIME:
                            state.analytics["violation_events"] += 1
                            state.user_violations[member.id] = state.user_violations.get(member.id, 0) + 1
                            violation_count = state.user_violations[member.id]

                            try:
                                if violation_count == 1:
                                    await member.move_to(punishment_vc, reason=f"No camera detected in {vc.name}.")
                                    logging.info(f"Moved {member.name} to PUNISHMENT VC (from {vc.name}).")
                                elif violation_count == 2:
                                    timeout_duration = bot_config.TIMEOUT_DURATION_SECOND_VIOLATION
                                    await member.timeout(timedelta(seconds=timeout_duration), reason=f"2nd camera violation in {vc.name}.")
                                    logging.info(f"Timed out {member.name} for {timeout_duration}s (from {vc.name}).")
                                    state.active_timeouts[member.id] = {"timeout_end": time.time() + timeout_duration, "reason": f"2nd camera violation in {vc.name}", "timed_by": "AutoMod", "start_timestamp": time.time()}
                                else:
                                    timeout_duration = bot_config.TIMEOUT_DURATION_THIRD_VIOLATION
                                    await member.timeout(timedelta(seconds=timeout_duration), reason=f"Repeated camera violations in {vc.name}.")
                                    logging.info(f"Timed out {member.name} for {timeout_duration}s (from {vc.name}).")
                                    state.active_timeouts[member.id] = {"timeout_end": time.time() + timeout_duration, "reason": f"3rd+ camera violation in {vc.name}", "timed_by": "AutoMod", "start_timestamp": time.time()}

                                if violation_count >= 1 and member.id not in state.users_with_dms_disabled:
                                    try:
                                        await member.send(f"You've been {'moved' if violation_count == 1 else 'timed out'} for not having a camera on in the VC.")
                                    except discord.Forbidden:
                                        state.users_with_dms_disabled.add(member.id)
                                    except Exception as e:
                                        logging.error(f"Failed to send violation DM to {member.name}: {e}")
                                state.camera_off_timers.pop(member.id, None) # Reset timer after punishment
                            except discord.Forbidden:
                                logging.warning(f"Missing permissions to punish {member.name} in {vc.name}.")
                            except discord.HTTPException as e:
                                logging.error(f"Failed to punish {member.name} in {vc.name}: {e}")
                    else:
                        # First time user is detected with camera off, start the timer
                        state.camera_off_timers[member.id] = time.time()
            else:
                # User has camera on, remove any existing timer
                async with state.vc_lock:
                    state.camera_off_timers.pop(member.id, None)

#########################################
# Bot Commands
#########################################
@bot.command(name='help')
@require_command_channel
async def help_command(ctx):
    """Sends the interactive help menu."""
    await send_help_menu(ctx)

@bot.command(name='skip')
@require_command_channel
@handle_errors
async def skip(ctx):
    """Skips the current Omegle user."""
    if ctx.author.id not in bot_config.ALLOWED_USERS and not is_user_in_streaming_vc_with_camera(ctx.author):
        await ctx.send("You must be in the Streaming VC with your camera on to use that command.")
        return
    await omegle_handler.custom_skip(ctx)

@bot.command(name='refresh')
@require_command_channel
@handle_errors
async def refresh(ctx):
    """Refreshes the Omegle page."""
    if ctx.author.id not in bot_config.ALLOWED_USERS and not is_user_in_streaming_vc_with_camera(ctx.author):
        await ctx.send("You must be in the Streaming VC with your camera on to use that command.")
        return
    await omegle_handler.refresh(ctx, is_pause=False)

@bot.command(name='pause')
@require_command_channel
@handle_errors
async def pause(ctx):
    """Pauses the Omegle stream."""
    if ctx.author.id not in bot_config.ALLOWED_USERS and not is_user_in_streaming_vc_with_camera(ctx.author):
        await ctx.send("You must be in the Streaming VC with your camera on to use that command.")
        return
    await omegle_handler.refresh(ctx, is_pause=True)

@bot.command(name='start')
@require_command_channel
@handle_errors
async def start(ctx):
    """Starts the Omegle stream."""
    if ctx.author.id not in bot_config.ALLOWED_USERS and not is_user_in_streaming_vc_with_camera(ctx.author):
        await ctx.send("You must be in the Streaming VC with your camera on to use that command.")
        return
    await omegle_handler.start_stream(ctx, is_paid=False)

@bot.command(name='paid')
@require_command_channel
@handle_errors
async def paid(ctx):
    """Redirects to the Omegle URL (for paid features)."""
    if ctx.author.id not in bot_config.ALLOWED_USERS and not is_user_in_streaming_vc_with_camera(ctx.author):
        await ctx.send("You must be in the Streaming VC with your camera on to use that command.")
        return
    await omegle_handler.start_stream(ctx, is_paid=True)

@bot.command(name='purge')
async def purge(ctx, count: int) -> None:
    """Purges a specified number of messages from the channel (allowed users only)."""
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    logging.info(f"Purge command received with count: {count}")
    try:
        deleted = await ctx.channel.purge(limit=count)
        await ctx.send(f"🧹 Purged {len(deleted)} messages!", delete_after=5)
        logging.info(f"Purged {len(deleted)} messages.")
    except Exception as e:
        logging.error(f"Error in purge command: {e}")
@purge.error
async def purge_error(ctx, error: Exception) -> None:
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: !purge <number>")
    else:
        await ctx.send("An error occurred in the purge command.")

@bot.command(name='shutdown')
@handle_errors
async def shutdown(ctx) -> None:
    """Shuts down the bot completely (allowed users only)."""
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    if getattr(bot, "_is_shutting_down", False):
        await ctx.send("🛑 Shutdown already in progress")
        return
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

    bot._is_shutting_down = True
    logging.critical(f"Shutdown confirmed by {ctx.author.name} (ID: {ctx.author.id})")
    await ctx.send("🛑 **Bot is shutting down...**")
    
    if bot_config.ENABLE_GLOBAL_HOTKEY:
        try:
            keyboard.remove_hotkey(bot_config.GLOBAL_HOTKEY_COMBINATION)
            logging.info("Unregistered global hotkey during shutdown")
        except Exception: pass
    
    await bot.close()

@bot.command(name='hush')
@handle_errors
async def hush(ctx) -> None:
    """Mutes all users in the Streaming VC (except allowed users)."""
    async with state.vc_lock:
        state.hush_override_active = True
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    streaming_vc = ctx.guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        impacted = []
        for member in streaming_vc.members:
            if not member.bot and member.id not in bot_config.ALLOWED_USERS:
                try:
                    await member.edit(mute=True)
                    impacted.append(member.name)
                except Exception as e:
                    logging.error(f"Error muting {member.name}: {e}")
        msg = "Muted: " + ", ".join(impacted) if impacted else "No users muted."
        await ctx.send(msg)
    else:
        await ctx.send("Streaming VC not found.")

@bot.command(name='secret')
@handle_errors
async def secret(ctx) -> None:
    """Mutes and deafens all users in the Streaming VC (except allowed users)."""
    async with state.vc_lock:
        state.hush_override_active = True
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    streaming_vc = ctx.guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        impacted = []
        for member in streaming_vc.members:
            if not member.bot and member.id not in bot_config.ALLOWED_USERS:
                try:
                    await member.edit(mute=True, deafen=True)
                    impacted.append(member.name)
                except Exception as e:
                    logging.error(f"Error muting/deafening {member.name}: {e}")
        msg = "Muted & Deafened: " + ", ".join(impacted) if impacted else "No users to mute/deafen."
        await ctx.send(msg)
    else:
        await ctx.send("Streaming VC not found.")

@bot.command(name='rhush')
@handle_errors
async def rhush(ctx) -> None:
    """Unmutes and undeafens all users in the Streaming VC."""
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    streaming_vc = ctx.guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        for member in streaming_vc.members:
            if not member.bot:
                try: await member.edit(mute=False, deafen=False)
                except Exception as e: logging.error(f"Error unmuting/undeafening {member.name}: {e}")
        await ctx.send("Unmuted and undeafened all users in Streaming VC.")
    
    async with state.vc_lock:
        state.hush_override_active = False

@bot.command(name='rsecret')
@handle_errors
async def rsecret(ctx) -> None:
    """Removes mute and deafen statuses from all users in the Streaming VC."""
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    streaming_vc = ctx.guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        for member in streaming_vc.members:
            if not member.bot:
                try: await member.edit(mute=False, deafen=False)
                except Exception as e: logging.error(f"Error removing mute/deafen from {member.name}: {e}")
        await ctx.send("Removed mute and deafen from all users in Streaming VC.")
    
    async with state.vc_lock:
        state.hush_override_active = False

@bot.command(name='modoff')
@handle_errors
async def modoff(ctx) -> None:
    """Temporarily disables voice channel moderation."""
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("You do not have permission to use this command.")
        return
    if bot_config.VC_MODERATION_PERMANENTLY_DISABLED:
        await ctx.send("VC Moderation is permanently disabled via config.")
        return
    
    async with state.vc_lock:
        state.vc_moderation_active = False
        
    streaming_vc = ctx.guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        for member in streaming_vc.members:
            if member.id not in bot_config.ALLOWED_USERS:
                try: await member.edit(mute=False, deafen=False)
                except Exception as e: logging.error(f"Error unmoderating {member.name}: {e}")
    await ctx.send("VC moderation has been temporarily disabled (modoff).")

@bot.command(name='modon')
@handle_errors
async def modon(ctx) -> None:
    """Re-enables voice channel moderation."""
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    if bot_config.VC_MODERATION_PERMANENTLY_DISABLED:
        await ctx.send("⚙️ VC Moderation is permanently disabled via config.")
        return
    
    async with state.vc_lock:
        state.vc_moderation_active = True
        
    await ctx.send("🔒 VC moderation has been re-enabled (modon).")

# Commands delegated to helper
@bot.command(name='bans', aliases=['banned'])
@require_command_channel
@handle_errors
async def bans(ctx) -> None:
    await helper.show_bans(ctx)

@bot.command(name='top')
@handle_errors
async def top_members(ctx) -> None:
    await helper.show_top_members(ctx)

@bot.command(name='info', aliases=['about'])
@require_command_channel
@handle_errors
async def info(ctx) -> None:
    await helper.show_info(ctx)

@bot.command(name='roles')
@require_command_channel
@handle_errors
async def roles(ctx) -> None:
    await helper.list_roles(ctx)

@bot.command(name='admin', aliases=['owner', 'admins', 'owners'])
@require_command_channel
@handle_errors
async def admin(ctx) -> None:
    await helper.show_admin_list(ctx)

@bot.command(name='commands')
@require_command_channel
@handle_errors
async def commands_list(ctx) -> None:
    await helper.show_commands_list(ctx)

@bot.command(name='whois')
@require_command_channel
@handle_errors
async def whois(ctx) -> None:
    await helper.show_whois(ctx)

@bot.command(name='rtimeouts')
@handle_errors
async def remove_timeouts(ctx) -> None:
    await helper.remove_timeouts(ctx)

@bot.command(name='rules')
@require_command_channel
@handle_errors
async def rules(ctx) -> None:
    await helper.show_rules(ctx)

@bot.command(name='timeouts')
@require_command_channel
@handle_errors
async def timeouts(ctx) -> None:
    await helper.show_timeouts(ctx)

@bot.command(name='times')
@require_command_channel
@handle_errors
async def time_report(ctx) -> None:
    await helper.show_times_report(ctx)

@bot.command(name='stats')
@require_command_channel
@handle_errors
async def analytics_report(ctx) -> None:
    await helper.show_analytics_report(ctx)

@bot.command(name='join')
@handle_errors
async def join(ctx) -> None:
    await helper.send_join_invites(ctx)

@bot.command(name='clear')
@handle_errors
async def clear_stats(ctx) -> None:
    await helper.clear_stats(ctx)

#########################################
# Main Execution
#########################################
if __name__ == "__main__":
    required_vars = ["BOT_TOKEN"]
    if missing := [var for var in required_vars if not os.getenv(var)]:
        logging.critical(f"Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    def handle_shutdown(signum, frame):
        logging.info("Graceful shutdown initiated")
        # Do not exit here, let bot.close() handle it
        bot.loop.create_task(shutdown(None))


    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        bot.run(os.getenv("BOT_TOKEN"))
    except discord.LoginFailure as e:
        logging.critical(f"Invalid token: {e}")
        sys.exit(1)
    except Exception as e:
        logging.critical(f"Fatal error: {e}", exc_info=True)
        raise
    finally:
        logging.info("Starting final shutdown process...")
        try:
            if 'bot_config' in globals() and getattr(bot_config, 'ENABLE_GLOBAL_HOTKEY', False):
                try:
                    keyboard.remove_hotkey(bot_config.GLOBAL_HOTKEY_COMBINATION)
                    logging.info("Unregistered global hotkey in finally block")
                except Exception: pass
        except NameError: pass
        
        if 'omegle_handler' in globals() and omegle_handler.driver:
            asyncio.run(omegle_handler.close())
        
        if 'state' in globals():
            save_state_sync()
        
        logging.info("Shutdown complete")
