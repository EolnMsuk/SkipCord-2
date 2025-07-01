# read all of my bot files and tell me what to fix /gemini 

#!/usr/bin/env python

# Standard library imports
import asyncio
import json
import logging
import logging.config
import os
import signal
import time
import atexit
from datetime import datetime, timezone, timedelta, time as dt_time
from functools import wraps
from typing import Any, Callable, Optional, Union, List

# Third-party imports
import discord
import keyboard
from discord.ext import commands, tasks
from discord.ui import View, Button
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager

# Local application imports
import config
from tools import (
    BotConfig,
    BotState,
    build_embed,
    build_role_update_embed,
    get_bot_state,
    get_discord_age,
    handle_errors,
    log_command_usage,
    ordinal,
    record_command_usage,
    record_command_usage_by_user,
    set_bot_state_instance
)

# Load environment variables
load_dotenv()

# Initialize configuration and state
bot_config = BotConfig.from_config_module(config)
state = BotState(bot_config)
set_bot_state_instance(state)  # Set global reference

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", help_command=None, intents=intents)

# Constants
STATE_FILE = "data.json"
DRIVER_INIT_RETRIES = 2  # Attempts to connect driver
DRIVER_INIT_DELAY = 5  # Seconds between retry attempts

#########################################
# Persistence Functions
#########################################

@tasks.loop(hours=1)
async def periodic_cleanup():
    """Executes unified cleanup hourly"""
    try:
        state.clean_old_entries()
        logging.info("Unified cleanup completed (24h/100-entry rules)")
    except Exception as e:
        logging.error(f"Cleanup error: {e}", exc_info=True)

def save_state() -> None:
    """Saves bot state to disk, including active VC sessions as completed sessions"""
    current_time = time.time()
    
    # Create a copy of vc_time_data to modify
    vc_data_to_save = {user_id: data.copy() for user_id, data in state.vc_time_data.items()}
    
    # Process active sessions to save them as completed
    for user_id, session_start in state.active_vc_sessions.items():
        session_duration = current_time - session_start
        
        # Initialize user data if not exists
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
        
        # Add the active session to completed sessions
        vc_data_to_save[user_id]["sessions"].append({
            "start": session_start,
            "end": current_time,
            "duration": session_duration,
            "vc_name": "Streaming VC"  # You could make this dynamic if needed
        })
        
        # Update total time
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
        # Updated VC time tracking data
        "vc_time_data": {
            str(user_id): {
                "total_time": data["total_time"],
                "sessions": data["sessions"],
                "username": data.get("username", "Unknown"),
                "display_name": data.get("display_name", "Unknown")
            }
            for user_id, data in vc_data_to_save.items()
        },
        # Active sessions are now empty since we've saved them as completed
        "active_vc_sessions": {}
    }
    
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(serializable_state, f)
        logging.info("Bot state saved, including active VC sessions")
    except Exception as e:
        logging.error(f"Failed to save bot state: {e}")
def load_state() -> None:
    """Loads the bot state from disk if available."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            
            # Existing state loading
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
            
            # New VC time tracking data loading
            state.vc_time_data = {
                int(user_id): {
                    "total_time": data["total_time"],
                    "sessions": data["sessions"],
                    "username": data.get("username", "Unknown"),
                    "display_name": data.get("display_name", "Unknown")  # ADD THIS LINE
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
        # Initialize empty VC tracking data if new state
        state.vc_time_data = {}
        state.active_vc_sessions = {}

@tasks.loop(minutes=14)
async def periodic_state_save() -> None:
    save_state()
#########################################
# Selenium Management Functions
#########################################
def init_selenium() -> bool:
    """
    Initializes the Selenium WebDriver.
    Returns True if successful, False otherwise.
    """
    for attempt in range(DRIVER_INIT_RETRIES):
        try:
            if state.driver is not None:
                try:
                    state.driver.quit()
                except Exception:
                    pass
            service = EdgeService(EdgeChromiumDriverManager().install())
            options = webdriver.EdgeOptions()
            options.add_argument("--log-level=3")  # Suppress most logging output
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--allow-running-insecure-content')
            options.add_argument(f"user-data-dir={bot_config.EDGE_USER_DATA_DIR}")
            state.driver = webdriver.Edge(service=service, options=options)
            state.driver.maximize_window()
            state.driver.get(bot_config.OMEGLE_VIDEO_URL)
            state._driver_initialized = True
            logging.info("Selenium driver initialized successfully.")
            return True
        except WebDriverException as e:
            logging.error(f"Selenium initialization attempt {attempt + 1} failed: {e}")
            if attempt < DRIVER_INIT_RETRIES - 1:
                time.sleep(DRIVER_INIT_DELAY)
        except Exception as e:
            logging.error(f"Unexpected error during Selenium initialization: {e}")
            break
    logging.critical("Failed to initialize Selenium driver after retries. The bot will continue without browser automation.")
    return False
async def selenium_custom_skip(ctx: Optional[commands.Context] = None) -> bool:
    """
    Sends skip key events to the page.
    Returns True if successful, False otherwise.
    """
    if not state.is_driver_healthy():
        if ctx:
            await ctx.send("Browser connection is not available. Please restart the bot manually.")
        return False
    keys = getattr(config, "SKIP_COMMAND_KEY", ["Escape", "Escape"])
    if not isinstance(keys, list):
        keys = [keys]
    try:
        for i, key in enumerate(keys):
            script = f"""
            var evt = new KeyboardEvent('keydown', {{
                bubbles: true,
                cancelable: true,
                key: '{key}',
                code: '{key}'
            }});
            document.dispatchEvent(evt);
            """
            state.driver.execute_script(script)
            logging.info(f"Selenium: Sent {key} key event to page.")
            if i < len(keys) - 1:
                await asyncio.sleep(1)
        return True
    except Exception as e:
        logging.error(f"Selenium custom skip failed: {e}")
        if ctx:
            await ctx.send("Failed to execute skip command in browser.")
        return False
async def selenium_refresh(ctx: Optional[Union[commands.Context, discord.Message, discord.Interaction]] = None, is_pause: bool = False) -> bool:
    """Handles both refresh and pause functionality"""
    if not state.is_driver_healthy():
        if ctx:
            if isinstance(ctx, discord.Interaction):
                await ctx.response.send_message("Browser connection is not available. Please restart the bot manually.")
            elif hasattr(ctx, 'send'):
                await ctx.send("Browser connection is not available. Please restart the bot manually.")
        return False
    
    try:
        if is_pause:
            state.driver.refresh()
            log_msg = "Selenium: Refresh performed for pause command."
            response_msg = "Stream paused temporarily!"
        else:
            state.driver.get(bot_config.OMEGLE_VIDEO_URL)
            log_msg = "Selenium: Navigated to OMEGLE_VIDEO_URL for refresh command."
            response_msg = "Page refreshed!"
        
        logging.info(log_msg)
        
        if ctx:
            if isinstance(ctx, discord.Interaction):
                if ctx.response.is_done():
                    await ctx.followup.send(response_msg)
                else:
                    await ctx.response.send_message(response_msg)
            elif hasattr(ctx, 'send'):
                await ctx.send(response_msg)
        
        return True
    except Exception as e:
        log_error = f"Selenium {'pause' if is_pause else 'refresh'} failed: {e}"
        logging.error(log_error)
        
        if ctx:
            error_msg = f"Failed to process {'pause' if is_pause else 'refresh'} command in browser."
            if isinstance(ctx, discord.Interaction):
                if ctx.response.is_done():
                    await ctx.followup.send(error_msg)
                else:
                    await ctx.response.send_message(error_msg)
            elif hasattr(ctx, 'send'):
                await ctx.send(error_msg)
        return False
async def selenium_start(ctx: Optional[Union[commands.Context, discord.Interaction]] = None, is_paid: bool = False) -> bool:
    """
    Starts the stream by navigating to OMEGLE_VIDEO_URL and triggering a skip.
    Can be used for both !start and !paid commands.
    Returns True if successful, False otherwise.
    """
    if not state.is_driver_healthy():
        if ctx:
            if isinstance(ctx, discord.Interaction):
                await ctx.response.send_message("Browser connection is not available. Please restart the bot manually.")
            else:
                await ctx.send("Browser connection is not available. Please restart the bot manually.")
        return False
    
    try:
        state.driver.get(bot_config.OMEGLE_VIDEO_URL)
        log_msg = "Selenium: Navigated to OMEGLE_VIDEO_URL for paid command." if is_paid else "Selenium: Navigated to OMEGLE_VIDEO_URL for start."
        logging.info(log_msg)
        
        if ctx:
            response_msg = "Redirected to Omegle video URL." if is_paid else "Stream started!"
            if isinstance(ctx, discord.Interaction):
                await ctx.response.send_message(response_msg)
            else:
                await ctx.send(response_msg)
        
        await asyncio.sleep(3)
        return await selenium_custom_skip(ctx)
    except Exception as e:
        log_error = f"Selenium {'paid' if is_paid else 'start'} failed: {e}"
        logging.error(log_error)
        
        if ctx:
            error_msg = f"Failed to process {'paid' if is_paid else 'start'} command in browser."
            if isinstance(ctx, discord.Interaction):
                await ctx.response.send_message(error_msg)
            else:
                await ctx.send(error_msg)
        return False

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
        await selenium_custom_skip()
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
# Notification Functions
#########################################

def create_message_chunks(
    entries: List[Any], 
    title: str, 
    process_entry: Callable[[Any], str], 
    max_chunk_size: int = 50,
    max_length: int = 1900,
    as_embed: bool = False,
    embed_color: Optional[discord.Color] = None
) -> Union[List[str], List[discord.Embed]]:
    """
    Creates message chunks from entries while respecting both count and length limits.
    Can return either text chunks or embed chunks.
    
    Args:
        entries: List of items to process
        title: Section title to prepend to each chunk
        process_entry: Function that converts an entry to a string
        max_chunk_size: Maximum number of entries per chunk (default: 50)
        max_length: Maximum character length per chunk (default: 1900)
        as_embed: Whether to return embeds instead of text (default: False)
        embed_color: Color to use for embeds (required if as_embed=True)
        
    Returns:
        List of formatted message strings or embeds that are under both limits
    """
    if as_embed and embed_color is None:
        raise ValueError("embed_color must be provided when as_embed=True")
        
    chunks = []
    current_chunk = []
    current_length = 0
    
    title_text = f"**{title} ({len(entries)} total)**\n"
    title_length = len(title_text)
    
    for entry in entries:
        processed = process_entry(entry)
        if processed:
            entry_length = len(processed) + 1  # +1 for newline
            
            # Check if adding this entry would exceed limits
            if (current_length + entry_length + title_length > max_length and current_chunk) or \
               (len(current_chunk) >= max_chunk_size):
                if as_embed:
                    embed = discord.Embed(
                        title=title,
                        description="\n".join(current_chunk),
                        color=embed_color
                    )
                    chunks.append(embed)
                else:
                    chunks.append(title_text + "\n".join(current_chunk))
                current_chunk = []
                current_length = 0
                
            current_chunk.append(processed)
            current_length += entry_length
    
    if current_chunk:
        if as_embed:
            embed = discord.Embed(
                title=title,
                description="\n".join(current_chunk),
                color=embed_color
            )
            chunks.append(embed)
        else:
            chunks.append(title_text + "\n".join(current_chunk))
    
    return chunks

@bot.event
async def on_member_join(member: discord.Member) -> None:
    """
    Logs new member joins by sending an embed message in the chat channel.
    """
    try:
        if member.guild.id == bot_config.GUILD_ID:
            chat_channel = member.guild.get_channel(bot_config.CHAT_CHANNEL_ID)
            if chat_channel:
                # Create embed
                embed = discord.Embed(
                    description=f"{member.mention} **JOINED the SERVER**!",
                    color=discord.Color.green())
                
                # Add user info
                avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
                embed.set_author(name=member.name, icon_url=avatar_url)
                embed.set_thumbnail(url=avatar_url)
                
                # Try to get banner if available
                try:
                    user = await bot.fetch_user(member.id)
                    if user.banner:
                        embed.set_image(url=user.banner.url)
                except:
                    pass
                
                # Add account age
                embed.add_field(
                    name="Account Age",
                    value=get_discord_age(member.created_at),
                    inline=True)
                
                await chat_channel.send(embed=embed)
            
            # Record the join
            state.recent_joins.append((
                member.id,
                member.name,
                member.display_name,
                datetime.now(timezone.utc)
            ))
                  
            logging.info(f"{member.name} joined the server {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
            
    except Exception as e:
        logging.error(f"Error in on_member_join: {e}")

async def send_timeout_notification(member: discord.Member, moderator: discord.User, duration: int, reason: str = None) -> None:
    """Sends a notification when a member is timed out with proper @mentions."""
    try:
        chat_channel = member.guild.get_channel(bot_config.CHAT_CHANNEL_ID)
        if not chat_channel:
            return

        # Convert duration to human-readable format
        hours, remainder = divmod(duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        duration_str = ""
        if hours > 0:
            duration_str += f"{hours} hour{'s' if hours != 1 else ''} "
        if minutes > 0:
            duration_str += f"{minutes} minute{'s' if minutes != 1 else ''} "
        if seconds > 0 or duration_str == "":
            duration_str += f"{seconds} second{'s' if seconds != 1 else ''}"

        embed = discord.Embed(
            description=f"{member.mention} **was TIMED OUT**",
            color=discord.Color.orange())
   
        embed.set_author(
            name=f"{member.name}",
            icon_url=member.display_avatar.url
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        
        try:
            user_obj = await bot.fetch_user(member.id)
            if user_obj.banner:
                embed.set_image(url=user_obj.banner.url)
        except Exception:
            pass
        
        # Add duration and moderator fields
        embed.add_field(
            name="", 
            value=f"⏱️ {duration_str.strip()}",
            inline=True
        )
        embed.add_field(
            name="", 
            value=f"🛡️ {moderator.name}",
            inline=True
        )
        
        # Only add reason field if one exists
        if reason and reason.strip() and reason.lower() != "no reason provided":
            embed.add_field(
                name="", 
                value=f"📝 {reason.strip()}",
                inline=False
            )
        
        await chat_channel.send(embed=embed)
        
    except Exception as e:
        logging.error(f"Error sending timeout notification: {e}", exc_info=True)
        
async def send_timeout_removal_notification(member: discord.Member, duration: int, reason: str = "Expired Naturally") -> None:
    """Sends a notification when a member's timeout is removed with proper @mentions."""
    try:
        chat_channel = member.guild.get_channel(bot_config.CHAT_CHANNEL_ID)
        if not chat_channel:
            return

        # Convert duration to human-readable format
        hours, remainder = divmod(duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        duration_str = ""
        if hours > 0:
            duration_str += f"{hours} hour{'s' if hours != 1 else ''} "
        if minutes > 0:
            duration_str += f"{minutes} minute{'s' if minutes != 1 else ''} "
        if seconds > 0 or duration_str == "":
            duration_str += f"{seconds} second{'s' if seconds != 1 else ''}"

        embed = discord.Embed(
            description=f"{member.mention} **TIMEOUT REMOVED**",
            color=discord.Color.orange())
        
        embed.set_author(
            name=f"{member.name}",
            icon_url=member.display_avatar.url
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        try:
            user_obj = await bot.fetch_user(member.id)
            if user_obj.banner:
                embed.set_image(url=user_obj.banner.url)
        except:
            pass

        # Add duration served
        embed.add_field(
            name="", 
            value=f"⏱️ {duration_str.strip()}",
            inline=True
        )

        # Process reason to include username if manually removed
        if "manually removed by" in reason.lower():
            try:
                # Split reason to get moderator info
                reason_text, mod_name = reason.rsplit("by", 1)
                mod_name = mod_name.strip()
                
                # Find moderator in guild members
                mod_member = discord.utils.find(
                    lambda m: m.name == mod_name or m.display_name == mod_name,
                    member.guild.members
                )
                
                # Use username if found, otherwise show name as is
                mod_display = mod_member.name if mod_member else mod_name
                reason = f"{reason_text.strip()} by {mod_display}"
            except Exception as e:
                logging.error(f"Error processing moderator name: {e}")

        # Add reason field
        embed.add_field(
            name="", 
            value=f"📝 {reason}",
            inline=False
        )

        await chat_channel.send(embed=embed)

        # Record the untimeout with the processed reason
        state.recent_untimeouts.append((
            member.id,
            member.name,
            member.display_name,
            datetime.now(timezone.utc),
            reason
        ))

        if len(state.recent_untimeouts) > 100:
            state.recent_untimeouts.pop(0)

    except Exception as e:
        logging.error(f"Error sending timeout removal notification: {e}", exc_info=True)

async def send_unban_notification(user: discord.User, moderator: discord.User) -> None:
    """Sends a notification when a user is unbanned."""
    try:
        chat_channel = bot.get_guild(bot_config.GUILD_ID).get_channel(bot_config.CHAT_CHANNEL_ID)
        if chat_channel:
            embed = discord.Embed(
                description=f"{user.mention} **UNBANNED**",
                color=discord.Color.green())
            
            embed.set_author(name=user.name, icon_url=user.display_avatar.url)
            embed.set_thumbnail(url=user.display_avatar.url)
            
            try:
                user_obj = await bot.fetch_user(user.id)
                if user_obj.banner:
                    embed.set_image(url=user_obj.banner.url)
            except:
                pass
            
            embed.add_field(name="Moderator", value=moderator.mention, inline=True)
            
            await chat_channel.send(embed=embed)
            
            # Record the unban
            state.recent_unbans.append((
                user.id,
                user.name,
                user.display_name,
                datetime.now(timezone.utc),
                moderator.name
            ))
            
            # Keep only recent unbans (last 100)
            if len(state.recent_unbans) > 100:
                state.recent_unbans.pop(0)
    except Exception as e:
        logging.error(f"Error sending unban notification: {e}")

#########################################
# Bot Event Handlers
#########################################
@bot.event
async def on_ready() -> None:
    """Handles bot initialization when it comes online."""
    logging.info(f"Bot is online as {bot.user}")
    
    # Load state FIRST using the original instance
    try:
        load_state()
        logging.info("State loaded successfully")
    except Exception as e:
        logging.error(f"Error loading state: {e}", exc_info=True)
    
    try:
        # Start periodic tasks AFTER state is loaded
        if not periodic_state_save.is_running():
            periodic_state_save.start()
        if not periodic_cleanup.is_running():
            periodic_cleanup.start()
        if not periodic_help_menu.is_running():
            periodic_help_menu.start()
        if not timeout_unauthorized_users.is_running():
            timeout_unauthorized_users.start()
        if not daily_auto_stats_clear.is_running():
            daily_auto_stats_clear.start()
            logging.info("Daily auto-stats task started")
        
        # Initialize Selenium
        selenium_success = init_selenium()
        if not selenium_success:
            logging.critical("Selenium initialization failed. Browser commands will not work until bot restart.")
        
        # Process VC moderation asynchronously
        async def init_vc_moderation():
            guild = bot.get_guild(bot_config.GUILD_ID)
            if not guild:
                return
                
            streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
            if not streaming_vc:
                return
                
            for member in streaming_vc.members:
                if not member.bot and member.id not in state.active_vc_sessions:
                    state.active_vc_sessions[member.id] = time.time()
                    logging.info(f"Started tracking VC time for existing member: {member.name} (ID: {member.id})")
                
                if (not member.bot 
                    and member.id not in bot_config.ALLOWED_USERS 
                    and member.id != bot_config.MUSIC_BOT
                    and not (member.voice and member.voice.self_video)):
                    try:
                        if not bot_config.VC_MODERATION_PERMANENTLY_DISABLED and state.vc_moderation_active:
                            await member.edit(mute=True, deafen=True)
                            logging.info(f"Auto-muted/deafened {member.name} for camera off.")
                    except Exception as e:
                        logging.error(f"Failed to auto mute/deafen {member.name}: {e}")
                    state.camera_off_timers[member.id] = time.time()
        
        asyncio.create_task(init_vc_moderation())
        
        # Hotkey registration:
        if bot_config.ENABLE_GLOBAL_HOTKEY:
            # Remove existing hotkey first
            try:
                keyboard.remove_hotkey(bot_config.GLOBAL_HOTKEY_COMBINATION)
            except (KeyError, ValueError) as e:
                logging.debug(f"Hotkey not registered: {e}")
    
            def hotkey_callback() -> None:
                logging.info("Global hotkey pressed, triggering skip command.")
                bot.loop.call_soon_threadsafe(lambda: asyncio.create_task(global_skip()))
    
            try:
                keyboard.add_hotkey(bot_config.GLOBAL_HOTKEY_COMBINATION, hotkey_callback)
                logging.info(f"Registered global hotkey: {bot_config.GLOBAL_HOTKEY_COMBINATION}")
            except Exception as e:
                logging.error(f"Failed to register hotkey: {e}")
                # Disable hotkey functionality if registration fails
                bot_config.ENABLE_GLOBAL_HOTKEY = False
                logging.warning("Global hotkey functionality disabled due to registration failure")
        
        logging.info("Initialization complete")
    
    except Exception as e:
        logging.error(f"Error during on_ready: {e}", exc_info=True)

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User) -> None:
    """
    Logs when a user is banned from the server.
    """
    try:
        chat_channel = guild.get_channel(bot_config.CHAT_CHANNEL_ID)
        if not chat_channel:
            return
            
        # Try to get ban reason
        try:
            ban_entry = await guild.fetch_ban(user)
            reason = ban_entry.reason or "No reason provided"
        except:
            reason = "No reason provided"
        
        # Get moderator who banned
        moderator = "Unknown"
        async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
            if entry.target.id == user.id:
                moderator = entry.user.mention
                break
        
        # Try to get member object before they were banned to check roles
        member = None
        roles = []
        try:
            # Check if we have a recent join record
            for join_entry in state.recent_joins[-100:]:  # Check last 100 joins
                if join_entry[0] == user.id:
                    # Try to get member from guild (might still be in cache)
                    member = guild.get_member(user.id)
                    if member:
                        roles = [role for role in member.roles if role.name != "@everyone"]
                    break
        except Exception as e:
            logging.error(f"Error trying to get member info for ban: {e}")

        # Create embed
        embed = discord.Embed(
            description=f"{user.mention} **BANNED**",
            color=discord.Color.red())
        
        # Add user info - use user.name if member is None
        username = member.name if member else user.name
        embed.set_author(name=username, icon_url=user.display_avatar.url)
        embed.set_thumbnail(url=user.display_avatar.url)
        
        # Try to get banner if available
        try:
            user_obj = await bot.fetch_user(user.id)
            if user_obj.banner:
                embed.set_image(url=user_obj.banner.url)
        except:
            pass
        
        # Add fields - moderator first
        embed.add_field(name="Moderator", value=moderator, inline=True)
        
        # Add roles if we have them (only if there are any non-everyone roles)
        if roles:
            embed.add_field(
                name="Roles", 
                value=", ".join([role.name for role in roles]),
                inline=False
            )
        
        # Add reason field
        embed.add_field(name="Reason", value=reason, inline=False)
        
        await chat_channel.send(embed=embed)
    
        # Record the ban
        state.recent_bans.append((
            user.id,
            user.name,
            user.display_name if hasattr(user, 'display_name') else None,
            datetime.now(timezone.utc),
            reason
        ))
        
        # Keep only recent bans (last 100)
        if len(state.recent_bans) > 100:
            state.recent_bans.pop(0)
            
        logging.info(f"{user.name} was banned from the server. Reason: {reason}")
        
    except Exception as e:
        logging.error(f"Error in on_member_ban: {e}", exc_info=True)

@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User) -> None:
    """
    Logs when a user is unbanned from the server.
    """
    try:
        async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
            if entry.target.id == user.id:
                await send_unban_notification(user, entry.user)
                break
    except Exception as e:
        logging.error(f"Error in on_member_unban: {e}")
@bot.event
async def on_member_remove(member: discord.Member) -> None:
    """
    Logs departures by sending an embed message in the chat channel.
    Also checks if the member was kicked and logs accordingly.
    """
    try:
        guild = member.guild
        current_time = datetime.now(timezone.utc)
        
        # Check if this was a ban
        try:
            await guild.fetch_ban(member)
            return  # Bans are handled in on_member_ban
        except discord.NotFound:
            pass
            
        # Check if this was a recent kick we already tracked
        if member.id in state.recent_kick_timestamps:
            kick_time = state.recent_kick_timestamps[member.id]
            if (current_time - kick_time) < timedelta(minutes=2):
                # We already handled this kick, ignore
                del state.recent_kick_timestamps[member.id]
                return

        # Check audit logs for kicks within the last 2 minutes
        async for entry in guild.audit_logs(
            limit=10,
            action=discord.AuditLogAction.kick,
            after=current_time - timedelta(minutes=2)
        ):
            if entry.target.id == member.id:
                # Verify the kick happened at almost the same time as the leave
                if abs((entry.created_at - current_time).total_seconds()) > 30:
                    continue  # Kick too old to be related to this leave
                    
                # This was a legitimate kick
                state.recent_kick_timestamps[member.id] = current_time
                
                chat_channel = guild.get_channel(bot_config.CHAT_CHANNEL_ID)
                if chat_channel:
                    # Get roles (excluding @everyone)
                    roles = [role for role in member.roles if role.name != "@everyone"]
                    
                    embed = discord.Embed(
                        description=f"{member.mention} **KICKED**",
                        color=discord.Color.orange(),
                        timestamp=current_time)
                    
                    avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
                    embed.set_author(name=member.name, icon_url=avatar_url)
                    embed.set_thumbnail(url=avatar_url)
                    
                    try:
                        user = await bot.fetch_user(member.id)
                        if user.banner:
                            embed.set_image(url=user.banner.url)
                    except:
                        pass
                    
                    # Add fields
                    embed.add_field(name="Reason", value=entry.reason or "No reason provided", inline=False)
                    embed.add_field(name="Kicked by", value=entry.user.mention, inline=True)
                    
                    # Only add roles field if user had any roles
                    if roles:
                        embed.add_field(
                            name="Roles", 
                            value=", ".join([role.name for role in roles]),
                            inline=False
                        )
                    
                    await chat_channel.send(embed=embed)
                
                # Record the kick
                state.recent_kicks.append((
                    member.id,
                    member.name,
                    member.nick,
                    current_time,
                    entry.reason or "No reason provided",
                    entry.user.mention,  # the mod who kicked
                    ", ".join([role.name for role in member.roles if role.name != "@everyone"]) or None  # Store roles
                ))

                if len(state.recent_kicks) > 100:
                    state.recent_kicks.pop(0)
                
                logging.info(f"{member.name} was kicked. Reason: {entry.reason}")
                return
        
        # If we get here, it was a voluntary leave
        if guild.id == bot_config.GUILD_ID:
            chat_channel = guild.get_channel(bot_config.CHAT_CHANNEL_ID)
            if chat_channel:
                join_time = member.joined_at or current_time
                duration = current_time - join_time
                duration_str = f"{duration.days}d {duration.seconds//3600}h {(duration.seconds%3600)//60}m {duration.seconds%60}s"
                avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
                
                # Get roles (excluding @everyone)
                roles = [role for role in member.roles if role.name != "@everyone"]
                
                embed = discord.Embed(color=discord.Color.red())
                embed.set_author(name=member.name, icon_url=avatar_url)
                embed.description = f"{member.mention} **LEFT the SERVER**"
                embed.set_thumbnail(url=avatar_url)
                
                # Add fields
                embed.add_field(name="Time in Server", value=duration_str, inline=True)
                
                # Only add roles field if user had any roles
                if roles:
                    embed.add_field(
                        name="Roles", 
                        value=", ".join([role.name for role in roles]),
                        inline=True
                    )
                
                await chat_channel.send(embed=embed)
            
            logging.info(f"{member.name} left the server voluntarily.")
        
        # Record the leave (including roles in the record)
        state.recent_leaves.append((
            member.id,
            member.name,
            member.nick,
            current_time,
            ", ".join([role.name for role in member.roles if role.name != "@everyone"]) or None
        ))
        if len(state.recent_leaves) > 100:
            state.recent_leaves.pop(0)
            
    except Exception as e:
        logging.error(f"Error in on_member_remove: {e}")

@bot.event
async def on_voice_state_update(member: discord.Member, before, after) -> None:
    """Handles voice state updates with batch processing and rate limit protection."""
    await asyncio.sleep(0.1)  # Batch processing
    
    # Helper functions for rate limit protection
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
            if e.status == 429:
                retry_after = e.retry_after + 1
                logging.warning(f"Rate limited on member.send. Waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                try: await member.send(content)
                except Exception as e2: logging.error(f"Retry failed: {e2}")
            else: raise

    try:
        if member == bot.user: return
        
        # Initialize user_last_join if needed
        if member.id not in state.user_last_join:
            state.user_last_join[member.id] = False
            
        streaming_vc = member.guild.get_channel(bot_config.STREAMING_VC_ID)
        alt_vc = member.guild.get_channel(bot_config.ALT_VC_ID)
        punishment_vc = member.guild.get_channel(bot_config.PUNISHMENT_VC_ID)

        # ===== VC TIME TRACKING =====
        if not member.bot:
            # Track streaming VC join/leave
            if after.channel and after.channel.id == bot_config.STREAMING_VC_ID:
                if member.id not in state.active_vc_sessions:
                    state.active_vc_sessions[member.id] = time.time()
                    if member.id not in state.vc_time_data:
                        state.vc_time_data[member.id] = {
                            "total_time": 0, "sessions": [],
                            "username": member.name, "display_name": member.display_name
                        }
                    else:  # Update names if changed
                        state.vc_time_data[member.id]["username"] = member.name
                        state.vc_time_data[member.id]["display_name"] = member.display_name
                    logging.info(f"VC Time Tracking: {member.display_name} started session in Streaming VC")
                    
            elif before.channel and before.channel.id == bot_config.STREAMING_VC_ID:
                if member.id in state.active_vc_sessions:
                    duration = time.time() - state.active_vc_sessions[member.id]
                    if member.id not in state.vc_time_data:
                        state.vc_time_data[member.id] = {
                            "total_time": 0, "sessions": [],
                            "username": member.name, "display_name": member.display_name
                        }
                    state.vc_time_data[member.id]["total_time"] += duration
                    state.vc_time_data[member.id]["sessions"].append({
                        "start": state.active_vc_sessions[member.id],
                        "end": time.time(), "duration": duration,
                        "vc_name": before.channel.name
                    })
                    logging.info(f"VC Time Tracking: {member.display_name} added {duration:.1f}s from Streaming VC")
                    del state.active_vc_sessions[member.id]

        # ===== CAMERA & ALLOWED USER HANDLING =====
        # Revert mute/deafen for allowed users
        if after.channel and after.channel.id in [bot_config.STREAMING_VC_ID, bot_config.ALT_VC_ID] and member.id in bot_config.ALLOWED_USERS:
            if member.voice:
                if member.voice.mute and not member.voice.self_mute:
                    await safe_edit(member, mute=False)
                    logging.info(f"Reverted server mute for allowed user {member.display_name}")
                if member.voice.deaf and not member.voice.self_deaf:
                    await safe_edit(member, deafen=False)
                    logging.info(f"Reverted server deafen for allowed user {member.display_name}")

        # ===== STREAMING VC SPECIFIC LOGIC =====
        if after.channel and after.channel.id == bot_config.STREAMING_VC_ID:
            # Join tracking and rules
            if not state.user_last_join[member.id]:
                state.user_last_join[member.id] = True
                logging.info(f"{member.display_name} joined Streaming VC")
                
                # Send rules if needed
                if (member.id not in state.users_received_rules and 
                    member.id not in state.users_with_dms_disabled and
                    member.id not in state.failed_dm_users):
                    try:
                        await safe_dm(member, bot_config.RULES_MESSAGE)
                        state.users_received_rules.add(member.id)
                        logging.info(f"Sent rules to {member.display_name}")
                    except discord.Forbidden:
                        state.users_with_dms_disabled.add(member.id)
                        state.failed_dm_users.add(member.id)
                        logging.warning(f"Could not DM {member.display_name} (DMs disabled)")
                    except discord.HTTPException as e:
                        state.failed_dm_users.add(member.id)
                        logging.error(f"Failed to send DM to {member.display_name}: {e}")

            # Camera moderation
            if (member.id not in bot_config.ALLOWED_USERS and 
                member.id != bot_config.MUSIC_BOT and 
                state.vc_moderation_active and 
                not bot_config.VC_MODERATION_PERMANENTLY_DISABLED):
                
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
            if (before.self_video and not after.self_video and 
                streaming_vc and member.id not in bot_config.ALLOWED_USERS):
                users_with_camera = [m for m in streaming_vc.members 
                                    if m.voice is not None and m.voice.self_video and 
                                    m.id not in bot_config.ALLOWED_USERS and not m.bot]
                if not users_with_camera and (time.time() - state.last_auto_pause_time >= 1):
                    state.last_auto_pause_time = time.time()
                    await selenium_refresh(is_pause=True)
                    logging.info("Auto Paused - No Cameras Detected")
                    if (command_channel := member.guild.get_channel(bot_config.COMMAND_CHANNEL_ID)):
                        await safe_send(command_channel, "Automatically paused")
                        
        elif before.channel and before.channel.id == bot_config.STREAMING_VC_ID:
            # Leave tracking
            if state.user_last_join.get(member.id, False):
                state.user_last_join[member.id] = False
                logging.info(f"{member.display_name} left Streaming VC")
            state.camera_off_timers.pop(member.id, None)
            
            # Auto-pause when last user with camera leaves
            remaining_non_allowed = [m for m in before.channel.members
                                    if not m.bot and m.id not in bot_config.ALLOWED_USERS and 
                                    m.voice is not None and m.voice.self_video]
            if not remaining_non_allowed and (time.time() - state.last_auto_pause_time >= 1):
                state.last_auto_pause_time = time.time()
                await selenium_refresh(is_pause=True)
                logging.info("Auto Paused - Last user with camera left")
                if (command_channel := member.guild.get_channel(bot_config.COMMAND_CHANNEL_ID)):
                    await safe_send(command_channel, "Automatically paused")

        # ===== ALT VC LOGGING =====
        if after.channel and after.channel.id == bot_config.ALT_VC_ID:
            logging.info(f"{member.display_name} joined Alt VC")
        elif before.channel and before.channel.id == bot_config.ALT_VC_ID:
            logging.info(f"{member.display_name} left Alt VC")

    except discord.HTTPException as e:
        if e.status == 429:  # Rate limit handling
            retry_after = e.retry_after + 1
            logging.warning(f"Global rate limit. Waiting {retry_after}s")
            await asyncio.sleep(retry_after)
        else:
            logging.error(f"HTTP error in voice state update: {e}", exc_info=True)
    except Exception as e:
        logging.error(f"General error in on_voice_state_update: {e}", exc_info=True)
        
@bot.command(name='bans', aliases=['banned'])
@require_command_channel
@handle_errors
async def bans(ctx) -> None:
    """
    Lists all banned users in compact format.
    Shows username, ID, and available ban info in one line per user.
    """
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return

    record_command_usage(state.analytics, "!bans")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!bans")

    try:
        # Get all bans
        ban_entries = []
        async for entry in ctx.guild.bans():
            ban_entries.append(entry)
        
        if not ban_entries:
            await ctx.send("No users are currently banned.")
            return

        async def process_ban(entry):
            user = entry.user
            line = f"• `{user.name}` (`{user.id}`)"
            
            # Try to find ban details in audit logs
            async for log in ctx.guild.audit_logs(action=discord.AuditLogAction.ban, limit=20):
                if log.target.id == user.id:
                    if log.reason:
                        line += f" | Reason: {log.reason}"
                    if log.user:
                        line += f" | Banned by: {log.user.name}"
                    break
            return line

        # Process all bans
        processed_entries = []
        for entry in ban_entries:
            processed_line = await process_ban(entry)
            processed_entries.append(processed_line)

        # Create embed chunks
        embeds = create_message_chunks(
            entries=processed_entries,
            title=f"Banned Users (Total: {len(ban_entries)})",
            process_entry=lambda x: x,  # Already processed
            as_embed=True,
            embed_color=discord.Color.red()
        )

        # Send all embeds
        for embed in embeds:
            await ctx.send(embed=embed)
            
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to view bans.")
    except Exception as e:
        logging.error(f"Error in !bans command: {e}", exc_info=True)
        await ctx.send("⚠️ An error occurred while fetching bans.")


@bot.command(name='top')
@handle_errors
async def top_members(ctx) -> None:
    """
    Lists:
    1. Top 10 oldest server members (by join date)
    2. Top 10 oldest Discord accounts in the server (by account creation date)
    Only usable by allowed users.
    """
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    
    record_command_usage(state.analytics, "!top")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!top")
    
    try:
        # Part 1: Top 10 oldest server members (by join date)
        await ctx.send("**🏆 Top 10 Oldest Server Members (by join date)**")
        
        # Get all members and sort by join date (oldest first)
        joined_members = sorted(
            ctx.guild.members,
            key=lambda m: m.joined_at or datetime.now(timezone.utc)
        )[:10]  # Get top 10
        
        if not joined_members:
            await ctx.send("No members found in the server.")
            return
            
        # Create an embed for each member
        for i, member in enumerate(joined_members, 1):
            # Try to get full user object with banner
            try:
                user = await bot.fetch_user(member.id)
            except:
                user = member
                
            # Create embed with normal title format
            embed = discord.Embed(
                title=f"#{i} - {member.display_name}",
                description=f"{member.mention}",
                color=discord.Color.gold()
            )
            
            # Set author with avatar
            embed.set_author(
                name=f"{member.name}#{member.discriminator}",
                icon_url=member.avatar.url if member.avatar else member.default_avatar.url)
            
            # Set thumbnail (avatar)
            embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
            
            # Set banner if available
            if hasattr(user, 'banner') and user.banner:
                embed.set_image(url=user.banner.url)
            
            # Add fields
            embed.add_field(
                name="Account Created",
                value=f"{member.created_at.strftime('%Y-%m-%d')}\n({get_discord_age(member.created_at)} old)",
                inline=True)
            
            if member.joined_at:
                embed.add_field(
                    name="Joined Server",
                    value=f"{member.joined_at.strftime('%Y-%m-%d')}\n({get_discord_age(member.joined_at)} ago)",
                    inline=True)
            else:
                embed.add_field(
                    name="Joined Server",
                    value="Unknown",
                    inline=True)
            
            # Add roles (excluding @everyone)
            roles = [role.mention for role in member.roles if role.name != "@everyone"]
            if roles:
                embed.add_field(
                    name=f"Roles ({len(roles)})",
                    value=" ".join(roles) if len(", ".join(roles)) < 1024 else "Too many roles to display",
                    inline=False)
            
            await ctx.send(embed=embed)
        
        # Part 2: Top 10 oldest Discord accounts in the server (by creation date)
        await ctx.send("**🕰️ Top 10 Oldest Discord Accounts (by creation date)**")
        
        # Get all members and sort by account creation date (oldest first)
        created_members = sorted(
            ctx.guild.members,
            key=lambda m: m.created_at
        )[:10]  # Get top 10
        
        # Create an embed for each member
        for i, member in enumerate(created_members, 1):
            # Try to get full user object with banner
            try:
                user = await bot.fetch_user(member.id)
            except:
                user = member
                
            # Create embed with normal title format
            embed = discord.Embed(
                title=f"#{i} - {member.display_name}",
                description=f"{member.mention}",
                color=discord.Color.blue()
            )
            
            # Set author with avatar
            embed.set_author(
                name=f"{member.name}#{member.discriminator}",
                icon_url=member.avatar.url if member.avatar else member.default_avatar.url)
            
            # Set thumbnail (avatar)
            embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
            
            # Set banner if available
            if hasattr(user, 'banner') and user.banner:
                embed.set_image(url=user.banner.url)
            
            # Add fields
            embed.add_field(
                name="Account Created",
                value=f"{member.created_at.strftime('%Y-%m-%d')}\n({get_discord_age(member.created_at)} old)",
                inline=True)
            
            if member.joined_at:
                embed.add_field(
                    name="Joined Server",
                    value=f"{member.joined_at.strftime('%Y-%m-%d')}\n({get_discord_age(member.joined_at)} ago)",
                    inline=True)
            else:
                embed.add_field(
                    name="Joined Server",
                    value="Unknown",
                    inline=True)
            
            # Add roles (excluding @everyone)
            roles = [role.mention for role in member.roles if role.name != "@everyone"]
            if roles:
                embed.add_field(
                    name=f"Roles ({len(roles)})",
                    value=" ".join(roles) if len(", ".join(roles)) < 1024 else "Too many roles to display",
                    inline=False)
            
            await ctx.send(embed=embed)
            
    except Exception as e:
        logging.error(f"Error in !top command: {e}", exc_info=True)
        await ctx.send("⚠️ An error occurred while processing the command.")

@bot.command(name='info', aliases=['about'])
@require_command_channel
@handle_errors
async def info(ctx) -> None:
    """
    Sends the info messages in the channel only.
    Aliases: about
    """
    command_name = f"!{ctx.invoked_with}"
    record_command_usage(state.analytics, command_name)
    record_command_usage_by_user(state.analytics, ctx.author.id, command_name)
    
    # Send all info messages from config
    for msg in bot_config.INFO_MESSAGES:
        await ctx.send(msg)


@bot.command(name='roles')
@require_command_channel
@handle_errors
async def roles(ctx) -> None:
    """
    Lists each role and its members.
    Only allowed users (as defined in config.ALLOWED_USERS) can use this command.
    """
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("You do not have permission to use this command.")
        return
    
    record_command_usage(state.analytics, "!roles")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!roles")
    
    for role in reversed(ctx.guild.roles):
        if role.name != "@everyone" and role.members:
            def process_member(member):
                return f"{member.display_name} ({member.name}#{member.discriminator})"

            # Create embed chunks for this role
            embeds = create_message_chunks(
                entries=role.members,
                title=f"Role: {role.name}",
                process_entry=process_member,
                as_embed=True,
                embed_color=role.color
            )

            # Add footer to each embed part
            for i, embed in enumerate(embeds):
                if len(embeds) > 1:
                    embed.title = f"{embed.title} (Part {i + 1})"
                embed.set_footer(text=f"Total members: {len(role.members)}")
                await ctx.send(embed=embed)

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    """Handles member updates including timeouts, role changes, and timeout removals."""
    try:
        # Handle role changes (keep existing code)
        if before.roles != after.roles:
            roles_gained = [role for role in after.roles if role not in before.roles and role.name != "@everyone"]
            roles_lost = [role for role in before.roles if role not in after.roles and role.name != "@everyone"]
            if roles_gained or roles_lost:
                channel = after.guild.get_channel(bot_config.CHAT_CHANNEL_ID)
                if channel:
                    embed = await build_role_update_embed(after, roles_gained, roles_lost)
                    await channel.send(embed=embed)

        # Handle timeout changes
        if before.is_timed_out() != after.is_timed_out():
            if after.is_timed_out():
                # Timeout was applied (keep existing code)
                async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                    if entry.target.id == after.id and hasattr(entry.after, "timed_out_until"):
                        duration = (entry.after.timed_out_until - datetime.now(timezone.utc)).total_seconds()
                        await send_timeout_notification(after, entry.user, int(duration), entry.reason or "No reason provided")
                        state.active_timeouts[after.id] = {
                            "timeout_end": time.time() + duration,
                            "reason": entry.reason or "No reason provided",
                            "timed_by": entry.user.name,
                            "timed_by_id": entry.user.id,
                            "start_timestamp": time.time()
                        }
                        break
            else:
                # Timeout was removed
                if after.id not in state.pending_timeout_removals:
                    state.pending_timeout_removals[after.id] = True
                    
                    async def handle_timeout_removal():
                        await asyncio.sleep(5)  # Give audit logs time to update
                        
                        duration = 0
                        reason = "Timeout Ended"
                        moderator_name = "System"
                        moderator_id = None

                        # Get duration from active_timeouts if available
                        if after.id in state.active_timeouts:
                            timeout_data = state.active_timeouts[after.id]
                            duration = int(time.time() - timeout_data["start_timestamp"])
                            
                        # Check audit logs for manual removal
                        try:
                            async for entry in after.guild.audit_logs(
                                limit=10,
                                action=discord.AuditLogAction.member_update,
                                after=datetime.now(timezone.utc) - timedelta(minutes=1)
                            ):
                                if (entry.target.id == after.id and 
                                    getattr(entry.before, "timed_out_until", None) is not None and
                                    getattr(entry.after, "timed_out_until", None) is None):
                                    
                                    moderator_name = entry.user.name
                                    moderator_id = entry.user.id
                                    reason = f"Timeout removed by 🛡️ {moderator_name}"
                                    break
                        except Exception as e:
                            logging.error(f"Error checking audit logs: {e}")

                        # Only record if this is the most recent untimeout
                        if not state.recent_untimeouts or state.recent_untimeouts[-1][0] != after.id:
                            state.recent_untimeouts.append((
                                after.id,
                                after.name,
                                after.display_name,
                                datetime.now(timezone.utc),
                                reason,
                                moderator_name,
                                moderator_id
                            ))

                            # Keep only recent untimeouts (last 100)
                            if len(state.recent_untimeouts) > 100:
                                state.recent_untimeouts.pop(0)

                        await send_timeout_removal_notification(after, duration, reason)
                        state.active_timeouts.pop(after.id, None)
                        state.pending_timeout_removals.pop(after.id, None)

                    bot.loop.create_task(handle_timeout_removal())

    except Exception as e:
        logging.error(f"Error in on_member_update: {e}", exc_info=True)

class HelpView(View):
    """
    A Discord UI view for quick command buttons.
    """
    def __init__(self) -> None:
        super().__init__()
        commands_dict = {
            "Skip/Start": "!skip",
            "Pause": "!pause",
            "Refresh": "!refresh",
            "Rules/Info": "!info" 
        }
        for label, command in commands_dict.items():
            self.add_item(HelpButton(label, command))
class HelpButton(Button):
    """
    A Discord UI button that sends a command when clicked.
    """
    def __init__(self, label: str, command: str) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.command = command
    async def callback(self, interaction: discord.Interaction) -> None:
        """
        Callback for button clicks: checks cooldowns and processes the command.
        """
        try:
            # Log the button command usage
            log_command_usage(interaction, self.command)
            
            user_id = interaction.user.id
            if user_id not in bot_config.ALLOWED_USERS and interaction.channel.id != bot_config.COMMAND_CHANNEL_ID:
                await interaction.response.send_message(
                    f"All commands (including !help) should be used in https://discord.com/channels/{bot_config.GUILD_ID}/{bot_config.COMMAND_CHANNEL_ID}",
                    ephemeral=True
                )
                return
            current_time = time.time()
            if user_id in state.button_cooldowns:
                last_used, warned = state.button_cooldowns[user_id]
                time_left = bot_config.COMMAND_COOLDOWN - (current_time - last_used)
                if time_left > 0:
                    if not warned:
                        await interaction.response.send_message(
                            f"{interaction.user.mention}, wait {int(time_left)}s before using another button.",
                            ephemeral=True
                        )
                        state.button_cooldowns[user_id] = (last_used, True)
                    return
            state.button_cooldowns[user_id] = (current_time, False)
            await interaction.response.defer()
            await interaction.channel.send(f"{interaction.user.mention} used {self.command}")
            fake_message = interaction.message
            fake_message.content = self.command
            fake_message.author = interaction.user
            await on_message(fake_message)
        except Exception as e:
            logging.error(f"Error in HelpButton callback: {e}")
@bot.event
async def on_message(message: discord.Message) -> None:
    """
    Processes incoming messages, enforcing cooldowns and permission checks.
    """
    try:
        if message.author == bot.user or not message.guild:
            return
        if not message.content.startswith("!"):
            return
        if message.guild.id != bot_config.GUILD_ID:
            return
        # Log command usage
        command = message.content.split()[0].lower()
        log_command_usage(message, command)
        if message.author.id not in bot_config.ALLOWED_USERS and message.channel.id != bot_config.COMMAND_CHANNEL_ID:
            await message.channel.send(
                f"All commands (including !help) should be used in https://discord.com/channels/{bot_config.GUILD_ID}/{bot_config.COMMAND_CHANNEL_ID}"
            )
            return
        if (message.content.lower().startswith("!top") or
            message.content.lower().startswith("!stats") or
            message.content.lower().startswith("!commands") or
            message.content.lower().startswith("!purge")):
            await bot.process_commands(message)
            return
        user_id = message.author.id
        current_time = time.time()
        if user_id in state.cooldowns:
            last_used, warned = state.cooldowns[user_id]
            time_left = bot_config.COMMAND_COOLDOWN - (current_time - last_used)
            if time_left > 0:
                if not warned:
                    await message.channel.send(f"Please wait {int(time_left)} seconds and try again.")
                    state.cooldowns[user_id] = (last_used, True)
                return
        state.cooldowns[user_id] = (current_time, False)
        
        async def handle_skip(guild: discord.Guild, ctx: Union[commands.Context, discord.Message, discord.Interaction]) -> None:
            await selenium_custom_skip(ctx)

        async def handle_refresh(guild: discord.Guild, ctx: Union[commands.Context, discord.Message, discord.Interaction]) -> None:
            await selenium_refresh(ctx, is_pause=False)
            await asyncio.sleep(3)
            await selenium_custom_skip(ctx)

        async def handle_pause(guild: discord.Guild, ctx: Union[commands.Context, discord.Message, discord.Interaction]) -> None:
            await selenium_refresh(ctx, is_pause=True)

        async def handle_start(guild: discord.Guild, ctx: Union[commands.Context, discord.Message, discord.Interaction]) -> None:
            await selenium_start(ctx, is_paid=False)

        async def handle_paid(guild: discord.Guild, ctx: Union[commands.Context, discord.Message, discord.Interaction]) -> None:
            await selenium_start(ctx, is_paid=True)
        
        command_actions = {
            "!skip": lambda: asyncio.create_task(handle_skip(message.guild, message if not isinstance(message, discord.Interaction) else message)),
            "!refresh": lambda: asyncio.create_task(handle_refresh(message.guild, message if not isinstance(message, discord.Interaction) else message)),
            "!pause": lambda: asyncio.create_task(handle_pause(message.guild, message if not isinstance(message, discord.Interaction) else message)),
            "!start": lambda: asyncio.create_task(handle_start(message.guild, message if not isinstance(message, discord.Interaction) else message)),
            "!paid": lambda: asyncio.create_task(handle_paid(message.guild, message if not isinstance(message, discord.Interaction) else message))
        }
        command = message.content.lower()
        handled = False
        if command in command_actions:
            if message.author.id not in bot_config.ALLOWED_USERS and not is_user_in_streaming_vc_with_camera(message.author):
                await message.channel.send("You must be in the Streaming VC with your camera on to use that command.")
                return
            record_command_usage(state.analytics, command)
            record_command_usage_by_user(state.analytics, message.author.id, command)
            await command_actions[command]()
            handled = True
        command_messages = {
            "!skip": "Omegle skipped!",
            "!refresh": "Page refreshed!",
            "!pause": "Stream paused temporarily!",
            "!start": "Stream started!",
            "!paid": "Redirected back to Omegle",
            "!help": "Help"
        }
        if command in command_messages:
            if command == "!help":
                await send_help_menu(message)
            else:
                await message.channel.send(command_messages[command])
        
        if not handled:
            await bot.process_commands(message)
        
    except Exception as e:
        logging.error(f"Error in on_message: {e}")
@bot.command(name='purge')
async def purge(ctx, count: int) -> None:
    """
    Purges a specified number of messages from the channel (allowed users only).
    """
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
async def send_help_menu(target: Any) -> None:
    """
    Sends an embedded help menu with available commands and interactive buttons.
    Works in both text channels and voice channel chats.
    """
    try:
        help_description = """
**Skip/Start** -- Skip/Start Omegle
**Pause** ------- Pause Omegle
**Refresh** ----- Refresh Omegle
**Info** --------- Server Info
**!commands** - Admin Commands
"""
        embed = build_embed("SkipCord-2 v4", help_description, discord.Color.blue())
        
        # Handle different target types
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
async def handle_wrong_channel(message: discord.Message) -> None:
    """
    Notifies users when commands are used in the wrong channel.
    """
    try:
        user_id = message.author.id
        current_time = time.time()
        if user_id in state.cooldowns:
            last_used, warned = state.cooldowns[user_id]
            time_left = bot_config.COMMAND_COOLDOWN - (current_time - last_used)
            if time_left > 0:
                if not warned:
                    await message.channel.send(f"{message.author.mention}, please wait {int(time_left)} seconds before trying again.")
                    state.cooldowns[user_id] = (last_used, True)
                return
        await message.channel.send(f"{message.author.mention}, use all commands (including !help) in the command channel.")
        state.cooldowns[user_id] = (current_time, False)
    except Exception as e:
        logging.error(f"Error in handle_wrong_channel: {e}")

@tasks.loop(minutes=2)
async def periodic_help_menu() -> None:
    """
    Periodically updates the help menu in the command channel.
    Works in both text channels and voice channel chats.
    """
    try:
        guild = bot.get_guild(bot_config.GUILD_ID)
        if not guild:
            return

        channel = guild.get_channel(bot_config.COMMAND_CHANNEL_ID)
        if not channel or not hasattr(channel, 'send'):
            return

        try:
            # Send refresh message (delete after 5 seconds)
            refresh_msg = await channel.send("🔁 Refreshing help menu...")
            await asyncio.sleep(2)
            
            # Purge messages (safe limit of 50)
            await safe_purge(channel, limit=50)
            
            # Send new help menu
            await send_help_menu(channel)
            
            # Delete the refresh message after delay
            await asyncio.sleep(3)
            try:
                await refresh_msg.delete()
            except:
                pass
                
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                wait = e.retry_after + 5
                logging.warning(f"Rate limited. Retrying in {wait}s")
                await asyncio.sleep(wait)
                return
            raise

    except Exception as e:
        logging.error(f"Help menu update failed: {e}", exc_info=True)
        await asyncio.sleep(300)

async def safe_purge(channel: discord.TextChannel, limit: int = 50) -> None:
    """
    Safely purges messages with strict rate limiting.
    Never deletes more than 'limit' messages (default: 50).
    """
    try:
        # Discord only allows 100 messages/5sec, so we stay well below
        deleted = await channel.purge(limit=min(limit, 50))  # Hard cap at 50
        
        if deleted:
            msg = await channel.send(f"🧹 Purged {len(deleted)} messages.", delete_after=5)
            logging.info(f"Purged {len(deleted)} messages in {channel.name}")
            await asyncio.sleep(1)  # Delay before next operation
    except discord.HTTPException as e:
        if e.status == 429:
            wait = max(e.retry_after, 10)  # Minimum 10s wait if rate-limited
            logging.warning(f"Purge rate limited in {channel.name}. Waiting {wait}s")
            await asyncio.sleep(wait)
        else:
            raise
        
        
@bot.command(name='shutdown')
@handle_errors
async def shutdown(ctx) -> None:
    """
    Shuts down the bot completely (allowed users only).
    Uses a confirmation flow and graceful termination.
    """
    # Permission check
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    
    # Prevent multiple concurrent shutdowns
    if getattr(bot, "_is_shutting_down", False):
        await ctx.send("🛑 Shutdown already in progress")
        return
        
    # Confirmation step
    confirm_msg = await ctx.send(
        "⚠️ **Are you sure you want to shut down the bot?**\n"
        "React with ✅ to confirm or ❌ to cancel."
    )
    for emoji in ("✅", "❌"):
        await confirm_msg.add_reaction(emoji)
    
    def check(reaction, user):
        return (
            user == ctx.author
            and str(reaction.emoji) in {"✅", "❌"}
            and reaction.message.id == confirm_msg.id
        )
    
    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=30.0, check=check)
        if str(reaction.emoji) == "❌":
            await confirm_msg.edit(content="🟢 Shutdown cancelled")
            return
    except asyncio.TimeoutError:
        await confirm_msg.edit(content="🟢 Shutdown timed out")
        return

    # Start shutdown process
    bot._is_shutting_down = True
    logging.critical(f"Shutdown confirmed by {ctx.author.name} (ID: {ctx.author.id})")
    await ctx.send("🛑 **Bot is shutting down...**")
    
    # Remove global hotkey if enabled
    if bot_config.ENABLE_GLOBAL_HOTKEY:
        try:
            keyboard.remove_hotkey(bot_config.GLOBAL_HOTKEY_COMBINATION)
            logging.info("Unregistered global hotkey during shutdown")
        except (KeyError, ValueError) as e:
            logging.debug(f"Hotkey not registered during shutdown: {e}")
        except Exception as e:
            logging.error(f"Error unregistering hotkey during shutdown: {e}")
    
    # Initiate graceful shutdown
    await bot.close()

@bot.command(name='rtimeouts')
@handle_errors
async def remove_timeouts(ctx) -> None:
    """
    Removes timeouts from all members and reports which users had timeouts removed.
    Requires confirmation via reaction.
    """
    # Permission check
    if not (ctx.author.id in bot_config.ALLOWED_USERS or 
            any(role.name in bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles)):
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    
    # Record command usage
    record_command_usage(state.analytics, "!rtimeouts")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!rtimeouts")
    
    # Get timed out members
    timed_out_members = [m for m in ctx.guild.members if m.is_timed_out()]
    
    if not timed_out_members:
        await ctx.send("No users are currently timed out.")
        return
    
    # Create confirmation message
    confirm_msg = await ctx.send(
        f"⚠️ **WARNING:** This will remove timeouts from {len(timed_out_members)} members!\n"
        "React with ✅ to confirm or ❌ to cancel within 30 seconds."
    )
    
    # Add reactions
    for emoji in ["✅", "❌"]:
        await confirm_msg.add_reaction(emoji)
    
    # Wait for confirmation
    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id
    
    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=30.0, check=check)
        
        if str(reaction.emoji) == "❌":
            await ctx.send("Command cancelled.")
            return
    except asyncio.TimeoutError:
        await ctx.send("⌛ Command timed out. No changes were made.")
        return
    
    # Proceed with removal
    removed_timeouts = []
    failed_removals = []
    
    for member in timed_out_members:
        try:
            await member.timeout(None, reason=f"Timeout removed by {ctx.author.name} ({ctx.author.id})")
            removed_timeouts.append(member.name)
            
            # Update state
            if member.id in state.active_timeouts:
                # Record untimeout
                state.recent_untimeouts.append((
                    member.id,
                    member.name,
                    member.display_name,
                    datetime.now(timezone.utc),
                    f"Manually removed by {ctx.author.name}"
                ))
                del state.active_timeouts[member.id]
                
            logging.info(f"Removed timeout from {member.name} (ID: {member.id}) by {ctx.author.name}")
            
        except discord.Forbidden:
            failed_removals.append(f"{member.name} (Missing Permissions)")
            logging.warning(f"Missing permissions to remove timeout from {member.name}.")
        except discord.HTTPException as e:
            failed_removals.append(f"{member.name} (Error: {e})")
            logging.error(f"Failed to remove timeout from {member.name}: {e}")

    # Send results
    result_msg = []
    if removed_timeouts:
        result_msg.append("**✅ Removed timeouts from:**")
        result_msg.extend([f"- {name}" for name in removed_timeouts])
    
    if failed_removals:
        result_msg.append("\n**❌ Failed to remove timeouts from:**")
        result_msg.extend([f"- {name}" for name in failed_removals])
    
    # Split message if too long
    chunks = []
    current_chunk = ""
    
    for line in result_msg:
        if len(current_chunk) + len(line) + 1 > 2000:
            chunks.append(current_chunk)
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"
    
    if current_chunk:
        chunks.append(current_chunk)
    
    for chunk in chunks:
        await ctx.send(chunk)
    
    # Send to chat channel
    chat_channel = ctx.guild.get_channel(bot_config.CHAT_CHANNEL_ID)
    if chat_channel:
        await chat_channel.send(
            f"⏰ **Mass Timeout Removal**\n"
            f"Executed by {ctx.author.mention}\n"
            f"Removed: {len(removed_timeouts)} | Failed: {len(failed_removals)}"
        )
@bot.command(name='hush')
@handle_errors
async def hush(ctx) -> None:
    """
    Mutes all users in the Streaming VC (except allowed users) to enforce silence.
    """
    state.hush_override_active = True
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    guild = ctx.guild
    streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        impacted = []
        for member in streaming_vc.members:
            if not member.bot and member.id not in bot_config.ALLOWED_USERS:
                try:
                    await member.edit(mute=True)
                    impacted.append(member.name)
                    logging.info(f"Muted {member.name}.")
                except Exception as e:
                    logging.error(f"Error muting {member.name}: {e}")
        msg = "Muted the following users: " + ", ".join(impacted) if impacted else "No users muted."
        logging.info(msg)
        await ctx.send(msg)
    else:
        await ctx.send("Streaming VC not found.")
@bot.command(name='secret')
@handle_errors
async def secret(ctx) -> None:
    """
    Mutes and deafens all users in the Streaming VC (except allowed users) for stricter moderation.
    """
    state.hush_override_active = True
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    guild = ctx.guild
    streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        impacted = []
        for member in streaming_vc.members:
            if not member.bot and member.id not in bot_config.ALLOWED_USERS:
                try:
                    await member.edit(mute=True, deafen=True)
                    impacted.append(member.name)
                    logging.info(f"Muted and deafened {member.name}.")
                except Exception as e:
                    logging.error(f"Error muting and deafening {member.name}: {e}")
        msg = "Muted and deafened the following users: " + ", ".join(impacted) if impacted else "No users muted/deafened."
        logging.info(msg)
        await ctx.send(msg)
    else:
        await ctx.send("Streaming VC not found.")
@bot.command(name='rhush')
@handle_errors
async def rhush(ctx) -> None:
    """
    Unmutes and undeafens all users in the Streaming VC.
    """
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    guild = ctx.guild
    streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        impacted = []
        for member in streaming_vc.members:
            if not member.bot:
                try:
                    await member.edit(mute=False, deafen=False)
                    impacted.append(member.name)
                    logging.info(f"Unmuted and undeafened {member.name}.")
                except Exception as e:
                    logging.error(f"Error unmuting/undeafening {member.name}: {e}")
        msg = "Unmuted and undeafened the following users: " + ", ".join(impacted) if impacted else "No users unmuted/undeafened."
        logging.info(msg)
        await ctx.send(msg)
    else:
        await ctx.send("Streaming VC not found.")
    state.hush_override_active = False
@bot.command(name='rsecret')
@handle_errors
async def rsecret(ctx) -> None:
    """
    Removes mute and deafen statuses from all users in the Streaming VC.
    """
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    guild = ctx.guild
    streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        impacted = []
        for member in streaming_vc.members:
            if not member.bot:
                try:
                    await member.edit(mute=False, deafen=False)
                    impacted.append(member.name)
                    logging.info(f"Removed mute and deafen from {member.name}.")
                except Exception as e:
                    logging.error(f"Error removing mute and deafen from {member.name}: {e}")
        msg = "Removed mute and deafen from the following users: " + ", ".join(impacted) if impacted else "No users had mute or deafen removed."
        logging.info(msg)
        await ctx.send(msg)
    else:
        await ctx.send("Streaming VC not found.")
    state.hush_override_active = False
@bot.command(name='join')
@handle_errors
async def join(ctx) -> None:
    """
    Sends a join invite DM to all members with an admin role.
    """
    if ctx.author.id not in bot_config.ALLOWED_USERS:  # Changed from previous check
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    record_command_usage(state.analytics, "!join")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!join")
        
    guild = ctx.guild
    admin_role_names = bot_config.ADMIN_ROLE_NAME
    join_message = bot_config.JOIN_INVITE_MESSAGE
    impacted = []
    for member in guild.members:
        if any(role.name in admin_role_names for role in member.roles):
            try:
                await member.send(join_message)
                impacted.append(member.name)
                logging.info(f"Sent join invite to {member.name}.")
            except Exception as e:
                logging.error(f"Error DMing {member.name}: {e}")
    if impacted:
        msg = "Sent join invite DM to: " + ", ".join(impacted)
        logging.info(msg)
        await ctx.send(msg)
    else:
        await ctx.send("No members with the specified admin roles found to DM.")
        
@bot.command(name='clear')
@handle_errors
async def clear_stats(ctx) -> None:
    """
    Resets all statistics data (VC time tracking, command usage, violations, and timers).
    Only usable by allowed users.
    """
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return

    # Confirm with the user
    confirm_msg = await ctx.send(
        "⚠️ This will reset ALL statistics data (VC times, command usage, violations).\n"
        "React with ✅ to confirm or ❌ to cancel."
    )
    await confirm_msg.add_reaction("✅")
    await confirm_msg.add_reaction("❌")

    def check(reaction, user):
        return (
            user == ctx.author
            and str(reaction.emoji) in ["✅", "❌"]
            and reaction.message.id == confirm_msg.id
        )

    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=30.0, check=check)
        
        if str(reaction.emoji) == "✅":
            # Get current VC members in both streaming and alt VCs
            guild = ctx.guild
            streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
            alt_vc = guild.get_channel(bot_config.ALT_VC_ID)
            current_members = []
            
            if streaming_vc:
                current_members.extend([m for m in streaming_vc.members if not m.bot])
            if alt_vc:
                current_members.extend([m for m in alt_vc.members if not m.bot])

            # Reset ALL statistics data
            state.vc_time_data = {}
            state.active_vc_sessions = {}
            state.analytics = {
                "command_usage": {},
                "command_usage_by_user": {},
                "violation_events": 0
            }
            state.user_violations = {}
            state.camera_off_timers = {}
            
            # Restart tracking for current VC members
            if current_members:
                current_time = time.time()
                for member in current_members:
                    state.active_vc_sessions[member.id] = current_time
                    state.vc_time_data[member.id] = {
                        "total_time": 0,
                        "sessions": [],
                        "username": member.name,
                        "display_name": member.display_name
                    }
                logging.info(f"Restarted VC tracking for {len(current_members)} current members")
            
            await ctx.send("✅ All statistics data has been reset.")
            logging.info(f"Statistics cleared by {ctx.author.name} (ID: {ctx.author.id})")
        else:
            await ctx.send("❌ Statistics reset cancelled.")
            
    except asyncio.TimeoutError:
        await ctx.send("⌛ Command timed out. No changes were made.")
    finally:
        try:
            await confirm_msg.delete()
        except:
            pass

@bot.command(name='admin', aliases=['owner', 'admins', 'owners'])
@require_command_channel
@handle_errors
async def admin(ctx) -> None:
    """
    Lists all current admins and owners.
    - Owners: Members whose IDs are in ALLOWED_USERS (displayed in a yellow/gold embed).
    - Admins: Members with a role in ADMIN_ROLE_NAME (displayed in a red embed).
    """
    record_command_usage(state.analytics, "!admin")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!admin")
    guild = ctx.guild
    if not guild:
        return
    owners_list = []
    admins_list = []
    for member in guild.members:
        if member.id in bot_config.ALLOWED_USERS:
            owners_list.append(f"{member.name} ({member.display_name})")
        elif any(role.name in bot_config.ADMIN_ROLE_NAME for role in member.roles):
            admins_list.append(f"{member.name} ({member.display_name})")
    owners_text = "\n".join(owners_list) if owners_list else "👑 No owners found."
    admins_text = "\n".join(admins_list) if admins_list else "🛡️ No admins found."
    embed_owners = discord.Embed(title="👑 Owners", description=owners_text, color=discord.Color.gold())
    embed_admins = discord.Embed(title="🛡️ Admins", description=admins_text, color=discord.Color.red())
    await ctx.send(embed=embed_owners)
    await ctx.send(embed=embed_admins)

@bot.command(name='commands')
@require_command_channel
@handle_errors
async def commands_list(ctx) -> None:
    """
    Lists all available bot commands divided into three groups:
      - User Commands (Blue)
      - Admin/Allowed Commands (Red)
      - Allowed Users Only Commands (Yellow/Gold)
    """
    record_command_usage(state.analytics, "!commands")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!commands")
    user_commands = (
        "**!skip** - Skips the current stranger on Omegle.\n"
        "**!refresh** - Refreshes page.\n"
        "**!pause** - Pauses Omegle.\n"
        "**!start** - Starts Omegle.\n"
        "**!paid** - Redirects back to Omegle URL.\n"
        "**!help** - Displays Omegle controls with buttons.\n"
        "**!rules** - Lists and DMs Server rules.\n"
        "**!admin** - Lists Admins and Owners.\n"
        "**!owner** - Lists Admins and Owners.\n"
        "**!info** - Lists Server Info.\n"
        "**!about** - Lists Server Info.\n"
        "**!commands** - Full list of all bot commands."
    )
    admin_commands = (
        "**!timeouts** - Lists current timeouts / removals.\n"
        "**!times** - Shows VC User Time Stats.\n"
        "**!roles** - Lists roles and their members.\n"
        "**!rtimeouts** - Removes timeouts from ALL members."
    )
    allowed_commands = (
        "**!purge [number]** - Purges messages from the channel.\n"
        "**!top** - Lists the top 10 longest members of the server.\n"
        "**!join** - Sends a join invite DM to admin role members.\n"
        "**!bans** - Lists all users who are server banned.\n"
        "**!whois** - Lists timeouts, untimeouts, joins, leaves, kicks.\n"
        "**!stats** - Lists VC Time / Command usage Stats.\n"
        "**!banned** - Lists all users who are server banned.\n"
        "**!clear** - Clears the VC / Command usage data.\n"
        "**!hush** - Server mutes everyone in the Streaming VC.\n"
        "**!secret** - Server mutes + deafens everyone in Streaming VC.\n"
        "**!rhush** - Removes mute status from everyone in Streaming VC.\n"
        "**!rsecret** - Removes mute and deafen statuses from Streaming VC.\n"
        "**!modoff** - Temporarily disables VC moderation for non-allowed users.\n"
        "**!modon** - Re-enables VC moderation after it has been disabled."
    )
    user_embed = build_embed("👤 User Commands", user_commands, discord.Color.blue())
    admin_embed = build_embed("🛡️ Admin/Allowed Commands", admin_commands, discord.Color.red())
    allowed_embed = build_embed("👑 Allowed Users Only Commands", allowed_commands, discord.Color.gold())
    await ctx.send(embed=user_embed)
    await ctx.send(embed=admin_embed)
    await ctx.send(embed=allowed_embed)

@bot.command(name='whois')
@require_command_channel
@handle_errors
async def whois(ctx) -> None:
    """Displays a report with all user actions in a clean format."""
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return

    record_command_usage(state.analytics, "!whois")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!whois")

    now = datetime.now(timezone.utc)
    reports = {}
    has_data = False  # Flag to track if any data exists

    # Helper function to get proper mention without double @
    def get_clean_mention(identifier):
        """Convert user ID or name to proper mention without double @"""
        if identifier is None:
            return "Unknown"
        
        # Try to find member by ID first
        if isinstance(identifier, int):
            member = ctx.guild.get_member(identifier)
            if member:
                return member.mention
        
        # Try to find by name if not found by ID
        member = discord.utils.find(
            lambda m: m.name == str(identifier) or m.display_name == str(identifier),
            ctx.guild.members
        )
        return member.mention if member else identifier  # Return raw name if member not found

    # Helper function to get user display info for left users
    async def get_left_user_display_info(user_id, stored_username=None):
        """Get user display information for users who left the server"""
        try:
            user = bot.get_user(user_id)
            if user is None:
                user = await bot.fetch_user(user_id)
            
            return f"{user.name} [ID: {user_id}]"
        except:
            # Fallback to stored username or unknown
            if stored_username:
                return f"{stored_username} [ID: {user_id}]"
            else:
                return f"Unknown User [ID: {user_id}]"

    # Timed Out Members (Orange)
    timed_out_members = [member for member in ctx.guild.members if member.is_timed_out()]
    if timed_out_members:
        has_data = True
        def process_timeout(member):
            timed_by = None
            reason = None
            if member.id in state.active_timeouts:
                timeout_data = state.active_timeouts[member.id]
                timed_by = timeout_data.get("timed_by_id", timeout_data.get("timed_by"))
                reason = timeout_data.get("reason")
            
            line = f"• {member.mention}"
            if timed_by and timed_by != "Unknown":
                clean_mention = get_clean_mention(timed_by)
                line += f" - TimedOut by: {clean_mention}"
            if reason and reason != "No reason provided":
                line += f" | Reason: {reason}"
            return line
        
        reports["⏳ Timed Out Members"] = create_message_chunks(
            timed_out_members,
            "⏳ Timed Out Members",
            process_timeout,
            max_length=1800  # Reduced from 1900 for extra safety
        )

    # Recent Untimeouts (Orange) - Filter out entries without mod info
    untimeout_list = [
        entry for entry in state.recent_untimeouts 
        if now - entry[3] <= timedelta(hours=24)
        and (len(entry) > 5 and entry[5] is not None)  # Ensure mod name exists
    ]
    
    if untimeout_list:
        has_data = True
        processed_users = set()
        
        def process_untimeout(entry):
            user_id = entry[0]
            if user_id in processed_users:
                return None
            processed_users.add(user_id)
            
            mod_name = entry[5]
            mod_id = entry[6] if len(entry) > 6 else None
            
            mod_mention = None
            if mod_id:
                mod_mention = get_clean_mention(mod_id)
            elif mod_name and mod_name != "System":
                mod_mention = get_clean_mention(mod_name)
            
            line = f"• <@{user_id}>"
            if mod_mention and mod_mention != "Unknown":
                line += f" - Removed by: {mod_mention}"
            return line
        
        reports["🔓 Recent Untimeouts"] = create_message_chunks(
            untimeout_list,
            "🔓 Recent Untimeouts",
            process_untimeout,
            max_length=1800
        )

    # Recent Kicks (Red)
    kick_list = [entry for entry in state.recent_kicks if now - entry[3] <= timedelta(hours=24)]
    if kick_list:
        has_data = True
        async def process_kick(entry):
            user_id = entry[0]
            stored_username = entry[1] if len(entry) > 1 else None
            reason = entry[4]
            kicker = entry[5] if len(entry) > 5 else None
            
            # Get user display info
            user_display = await get_left_user_display_info(user_id, stored_username)
            line = f"• {user_display}"
            
            if kicker and kicker != "Unknown":
                clean_mention = get_clean_mention(kicker)
                line += f" - Kicked by: {clean_mention}"
            if reason and reason != "No reason provided":
                line += f" | Reason: {reason}"
            return line
        
        # Use create_message_chunks for consistent chunking
        reports["👢 Recent Kicks"] = await create_async_message_chunks(
            kick_list,
            "👢 Recent Kicks",
            process_kick,
            max_length=1800
        )

    # Recent Bans (Red)
    ban_list = [entry for entry in state.recent_bans if now - entry[3] <= timedelta(hours=24)]
    if ban_list:
        has_data = True
        async def process_ban(entry):
            user_id = entry[0]
            stored_username = entry[1] if len(entry) > 1 else None
            reason = entry[4]
        
            # Get user mention and display info
            user_mention = f"<@{user_id}>"
            user_display = await get_left_user_display_info(user_id, stored_username)
        
            # Start with mention and full username
            line = f"• {user_mention} ({user_display})"
        
            # Add reason if available
            if reason and reason != "No reason provided":
                if " by " in reason.lower():
                    # Split reason to get moderator info
                    parts = reason.rsplit(" by ", 1)
                    reason_text = parts[0]
                    mod_name = parts[1]
                    clean_mention = get_clean_mention(mod_name)
                    line += f" - Reason: {reason_text} by {clean_mention}"
                else:
                    line += f" - Reason: {reason}"
            return line
    
        reports["🔨 Recent Bans"] = await create_async_message_chunks(
            ban_list,
            "🔨 Recent Bans",
            process_ban,
            max_length=1800
        )

    # Recent Unbans (Blue)
    unban_list = [entry for entry in state.recent_unbans if now - entry[3] <= timedelta(hours=24)]
    if unban_list:
        has_data = True
        def process_unban(entry):
            user_id = entry[0]
            mod_name = entry[4]
            
            line = f"• <@{user_id}>"
            if mod_name and mod_name != "Unknown":
                clean_mention = get_clean_mention(mod_name)
                line += f" - Unbanned by: {clean_mention}"
            return line
        
        reports["🔓 Recent Unbans"] = create_message_chunks(
            unban_list,
            "🔓 Recent Unbans",
            process_unban,
            max_length=1800
        )

    # Recent Joins (Green)
    join_list = [entry for entry in state.recent_joins if now - entry[3] <= timedelta(hours=24)]
    if join_list:
        has_data = True
        async def process_join(entry):
            user_id = entry[0]
            stored_username = entry[1] if len(entry) > 1 else None
            
            # Try to get current member info
            member = ctx.guild.get_member(user_id)
            if member:
                # Show username (nickname) [ID: user_id] format
                if member.display_name != member.name:
                    return f"• {member.name} ({member.display_name}) [ID: {user_id}]"
                else:
                    return f"• {member.name} [ID: {user_id}]"
            else:
                # User left server, use stored username if available
                if stored_username:
                    return f"• {stored_username} [ID: {user_id}] (left server)"
                else:
                    return f"• Unknown User [ID: {user_id}] (left server)"
        
        reports["🎉 Recent Joins"] = await create_async_message_chunks(
            join_list,
            "🎉 Recent Joins",
            process_join,
            max_length=1800
        )

    # Recent Leaves (Red)
    leave_list = [entry for entry in state.recent_leaves if now - entry[3] <= timedelta(hours=24)]
    if leave_list:
        has_data = True
        async def process_leave(entry):
            user_id = entry[0]
            stored_username = entry[1] if len(entry) > 1 else None
            user_display = await get_left_user_display_info(user_id, stored_username)
            return f"• {user_display}"
        
        reports["🚪 Recent Leaves"] = await create_async_message_chunks(
            leave_list,
            "🚪 Recent Leaves",
            process_leave,
            max_length=1800
        )

    # Send all non-empty reports in order with additional safety checks
    report_order = [
        "⏳ Timed Out Members",
        "🔓 Recent Untimeouts",
        "👢 Recent Kicks",
        "🔨 Recent Bans",
        "🔓 Recent Unbans",
        "🎉 Recent Joins",
        "🚪 Recent Leaves"
    ]
    
    for report_type in report_order:
        if report_type in reports and reports[report_type]:
            for chunk in reports[report_type]:
                try:
                    if len(chunk) > 2000:
                        # Emergency split if somehow chunk is too large
                        parts = [chunk[i:i+2000] for i in range(0, len(chunk), 2000)]
                        for part in parts:
                            await ctx.send(part)
                    else:
                        await ctx.send(chunk)
                except Exception as e:
                    logging.error(f"Error sending {report_type} report: {e}")
                    continue
    
    # If no data was found in any report section
    if not has_data:
        await ctx.send("📭 No recent activity data available")

async def create_async_message_chunks(entries, title, process_entry, max_chunk_size=50, max_length=1800):
    """Async version of create_message_chunks for async process_entry functions"""
    chunks = []
    current_chunk = []
    current_length = 0
    
    title_text = f"**{title} ({len(entries)} total)**\n"
    title_length = len(title_text)
    
    for entry in entries:
        processed = await process_entry(entry)
        if processed:
            entry_length = len(processed) + 1  # +1 for newline
            
            # Check if adding this entry would exceed limits
            if (current_length + entry_length + title_length > max_length and current_chunk) or \
               (len(current_chunk) >= max_chunk_size):
                chunks.append(title_text + "\n".join(current_chunk))
                current_chunk = []
                current_length = 0
                
            current_chunk.append(processed)
            current_length += entry_length
    
    if current_chunk:
        chunks.append(title_text + "\n".join(current_chunk))
    
    return chunks
                
                
@bot.command(name='modoff')
@handle_errors
async def modoff(ctx) -> None:
    """
    Temporarily disables voice channel moderation.
    """
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("You do not have permission to use this command.")
        return
    if bot_config.VC_MODERATION_PERMANENTLY_DISABLED:
        await ctx.send("VC Moderation is permanently disabled via config.")
        return
    state.vc_moderation_active = False
    guild = ctx.guild
    streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        for member in streaming_vc.members:
            if member.id not in bot_config.ALLOWED_USERS:
                try:
                    await member.edit(mute=False, deafen=False)
                except Exception as e:
                    logging.error(f"Error unmoderating {member.name}: {e}")
    await ctx.send("VC moderation has been temporarily disabled (modoff).")

@bot.command(name='modon')
@handle_errors
async def modon(ctx) -> None:
    """
    Re-enables voice channel moderation.
    """
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    if bot_config.VC_MODERATION_PERMANENTLY_DISABLED:
        await ctx.send("⚙️ VC Moderation is permanently disabled via config.")
        return
    state.vc_moderation_active = True
    await ctx.send("🔒 VC moderation has been re-enabled (modon).")

@bot.command(name='rules')
@require_command_channel
@handle_errors
async def rules(ctx) -> None:
    """
    Lists the server rules in the channel.
    """
    record_command_usage(state.analytics, "!rules")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!rules")
    # List the rules in the current channel only
    await ctx.send("📜 **Server Rules:**\n" + bot_config.RULES_MESSAGE)
    
@bot.command(name='timeouts')
@require_command_channel
@handle_errors
async def timeouts(ctx) -> None:
    """Displays a report of currently timed out members and all untimeouts."""
    allowed = (ctx.author.id in bot_config.ALLOWED_USERS or 
               any(role.name in bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles))
    if not allowed:
        await ctx.send("⛔ You do not have permission to use this command.")
        return

    record_command_usage(state.analytics, "!timeouts")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!timeouts")

    reports = {}
    has_data = False

    # Helper function to get proper mention without double @
    def get_clean_mention(identifier):
        """Convert user ID or name to proper mention without double @"""
        if identifier is None:
            return "Unknown"
        
        # Try to find member by ID first
        if isinstance(identifier, int):
            member = ctx.guild.get_member(identifier)
            if member:
                return member.mention
        
        # Try to find by name if not found by ID
        member = discord.utils.find(
            lambda m: m.name == str(identifier) or m.display_name == str(identifier),
            ctx.guild.members
        )
        return member.mention if member else identifier  # Return raw name if member not found

    # Currently Timed Out Members (all of them)
    timed_out_members = [member for member in ctx.guild.members if member.is_timed_out()]
    if timed_out_members:
        has_data = True
        
        async def process_timeout(member):
            timed_by = None
            reason = None
            if member.id in state.active_timeouts:
                timeout_data = state.active_timeouts[member.id]
                timed_by = timeout_data.get("timed_by_id", timeout_data.get("timed_by"))
                reason = timeout_data.get("reason")
            
            line = f"• {member.mention}"
            if timed_by and timed_by != "Unknown":
                clean_mention = get_clean_mention(timed_by)
                line += f" - Timed out by: {clean_mention}"
            if reason and reason != "No reason provided":
                line += f" | Reason: {reason}"
            return line
        
        reports["⏳ Currently Timed Out"] = await create_async_message_chunks(
            timed_out_members,
            "⏳ Currently Timed Out",
            process_timeout,
            max_length=1800
        )

    # All Untimeouts (no time limit) - Filter out entries without mod info
    untimeout_entries = [
        entry for entry in state.recent_untimeouts 
        if len(entry) > 5 and entry[5] is not None  # Ensure mod name exists
    ]
    
    if untimeout_entries:
        has_data = True
        processed_users = set()
        
        async def process_untimeout(entry):
            user_id = entry[0]
            if user_id in processed_users:
                return None
            processed_users.add(user_id)
            
            mod_name = entry[5]
            mod_id = entry[6] if len(entry) > 6 else None
            
            mod_mention = None
            if mod_id:
                mod_mention = get_clean_mention(mod_id)
            elif mod_name and mod_name != "System":
                mod_mention = get_clean_mention(mod_name)
            
            line = f"• <@{user_id}>"
            if mod_mention and mod_mention != "Unknown":
                line += f" - Removed by: {mod_mention}"
            return line
        
        reports["🔓 All Untimeouts"] = await create_async_message_chunks(
            untimeout_entries,
            "🔓 All Untimeouts",
            process_untimeout,
            max_length=1800
        )

    # Send all non-empty reports in order
    report_order = [
        "⏳ Currently Timed Out",
        "🔓 All Untimeouts"
    ]
    
    for report_type in report_order:
        if report_type in reports and reports[report_type]:
            for chunk in reports[report_type]:
                try:
                    if len(chunk) > 2000:
                        # Emergency split if somehow chunk is too large
                        parts = [chunk[i:i+2000] for i in range(0, len(chunk), 2000)]
                        for part in parts:
                            await ctx.send(part)
                    else:
                        await ctx.send(chunk)
                except Exception as e:
                    logging.error(f"Error sending {report_type} report: {e}")
                    continue
    
    # If no data was found in any report section
    if not has_data:
        await ctx.send("📭 No active timeouts or untimeouts found")


@bot.command(name='times')
@require_command_channel
@handle_errors
async def time_report(ctx) -> None:
    """Shows VC time tracking information"""
    # Permission check for ALLOWED_USERS OR ADMIN_ROLE_NAME
    if (ctx.author.id not in bot_config.ALLOWED_USERS and 
        not any(role.name in bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles)):
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    
    record_command_usage(state.analytics, "!times")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!times")

    # Reuse helper functions from !stats
    async def get_user_display_info(user_id):
        """Get user display information with mentions, role, and username"""
        try:
            user = bot.get_user(user_id)
            if user is None:
                user = await bot.fetch_user(user_id)
            
            # Get member object to check roles
            member = ctx.guild.get_member(user_id)
            if member:
                # Get highest non-everyone role
                roles = [role for role in member.roles if role.name != "@everyone"]
                if roles:
                    highest_role = max(roles, key=lambda r: r.position)
                    role_display = f"**[{highest_role.name}]**"
                else:
                    role_display = ""
                return f"{user.mention} {role_display} ({user.name})"
            return f"{user.mention} ({user.name})"
        except:
            return f"<@{user_id}> (Unknown User)"

    def is_excluded(user_id):
        """Check if user should be excluded from stats"""
        return user_id in getattr(bot_config, 'STATS_EXCLUDED_USERS', set())

    def get_vc_time_data():
        """Get all VC time data including total time and top users"""
        current_time = time.time()
        combined_data = {}
        total_time_all_users = 0

        # Process all historical data
        for user_id, data in state.vc_time_data.items():
            if is_excluded(user_id):
                continue
            
            combined_data[user_id] = {
                "username": data.get("username", "Unknown"),
                "display_name": data.get("display_name", "Unknown"),
                "total_time": data["total_time"]
            }
            total_time_all_users += data["total_time"]

        # Add active session times
        for user_id, start_time in state.active_vc_sessions.items():
            if is_excluded(user_id):
                continue
            
            active_duration = current_time - start_time
            member = ctx.guild.get_member(user_id)
        
            if user_id in combined_data:
                combined_data[user_id]["total_time"] += active_duration
            else:
                username = member.name if member else "Unknown"
                display_name = member.display_name if member else "Unknown"
                combined_data[user_id] = {
                    "username": username,
                    "display_name": display_name,
                    "total_time": active_duration
                }
            total_time_all_users += active_duration

        # Sort and return top 10
        sorted_users = sorted(
            [
                (
                    uid, 
                    data["username"],
                    data["total_time"]
                )
                for uid, data in combined_data.items()
            ],
            key=lambda x: x[2],  # Sort by total_time
            reverse=True
        )[:10]
    
        return total_time_all_users, sorted_users

    # Calculate total tracking time (since first session)
    total_tracking_seconds = 0
    if state.vc_time_data:
        # Find the earliest session start time across all users
        earliest_session = min(
            [session["start"] for user_data in state.vc_time_data.values() 
             for session in user_data["sessions"]],
            default=0
        )
        if earliest_session > 0:
            total_tracking_seconds = time.time() - earliest_session
    
    # Format total tracking time in consistent format (1h 1m 10s)
    hours = int(total_tracking_seconds // 3600)
    minutes = int((total_tracking_seconds % 3600) // 60)
    seconds = int(total_tracking_seconds % 60)
    
    time_parts = []
    if hours > 0:
        time_parts.append(f"{hours}h")
    if minutes > 0:
        time_parts.append(f"{minutes}m")
    if seconds > 0 or not time_parts:  # Always show at least seconds if no hours/minutes
        time_parts.append(f"{seconds}s")
    
    tracking_time_str = ' '.join(time_parts)
    
    # Send tracking time report
    await ctx.send(f"⏳ **Tracking Started:** {tracking_time_str} ago\n")

    # Get VC time data
    total_time_all_users, top_vc_users = get_vc_time_data()
    
    # Top VC Members
    if top_vc_users:
        async def process_vc_entry(entry):
            user_id, username, total_seconds = entry
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            seconds = int(total_seconds % 60)
    
            time_parts = []
            if hours > 0:
                time_parts.append(f"{hours}h")
            if minutes > 0:
                time_parts.append(f"{minutes}m")
            time_parts.append(f"{seconds}s")
    
            user_display = await get_user_display_info(user_id)
            return f"• {user_display}: {' '.join(time_parts)}"

        # Process all entries
        processed_entries = [await process_vc_entry(entry) for entry in top_vc_users]
        
        vc_chunks = create_message_chunks(
            entries=processed_entries,
            title="🏆 Top 10 VC Members",
            process_entry=lambda x: x,
            max_chunk_size=10
        )
        
        for chunk in vc_chunks:
            await ctx.send(chunk)
    else:
        await ctx.send("No VC time data available yet.")

    # Total VC Time for All Users
    hours = int(total_time_all_users // 3600)
    minutes = int((total_time_all_users % 3600) // 60)
    seconds = int(total_time_all_users % 60)
    
    time_parts = []
    if hours > 0:
        time_parts.append(f"{hours}h")
    if minutes > 0:
        time_parts.append(f"{minutes}m")
    time_parts.append(f"{seconds}s")
    
    await ctx.send(f"⏱ **Total VC Time (All Users):** {' '.join(time_parts)}")

"""
Sends a report showing command usage statistics and violation events.
Uses create_message_chunks for consistent formatting of all sections.
Excludes users listed in config.STATS_EXCLUDED_USERS.
"""
@bot.command(name='stats')
@require_command_channel
@handle_errors
async def analytics_report(ctx) -> None:
    # Change permission check to only ALLOWED_USERS
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return

    record_command_usage(state.analytics, "!stats")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!stats")

    async def get_user_display_info(user_id):
        """Get user display information with mentions, role, and username (without discriminator)"""
        try:
            user = bot.get_user(user_id)
            if user is None:
                user = await bot.fetch_user(user_id)
            
            # Get member object to check roles
            member = ctx.guild.get_member(user_id)
            if member:
                # Get highest non-everyone role
                roles = [role for role in member.roles if role.name != "@everyone"]
                if roles:
                    highest_role = max(roles, key=lambda r: r.position)
                    role_display = f"**[{highest_role.name}]**"
                else:
                    role_display = ""
                return f"{user.mention} {role_display} ({user.name})"
            return f"{user.mention} ({user.name})"
        except:
            return f"<@{user_id}> (Unknown User)"

    def is_excluded(user_id):
        """Check if user should be excluded from stats"""
        return user_id in getattr(bot_config, 'STATS_EXCLUDED_USERS', set())

    def get_vc_time_data():
        """Get all VC time data including total time and top users"""
        current_time = time.time()
        combined_data = {}
        total_time_all_users = 0

        # Process all historical data
        for user_id, data in state.vc_time_data.items():
            if is_excluded(user_id):
                continue
            
            combined_data[user_id] = {
                "username": data.get("username", "Unknown"),
                "display_name": data.get("display_name", "Unknown"),
                "total_time": data["total_time"]
            }
            total_time_all_users += data["total_time"]

        # Add active session times
        for user_id, start_time in state.active_vc_sessions.items():
            if is_excluded(user_id):
                continue
            
            active_duration = current_time - start_time
            member = ctx.guild.get_member(user_id)
        
            if user_id in combined_data:
                combined_data[user_id]["total_time"] += active_duration
            else:
                username = member.name if member else "Unknown"
                display_name = member.display_name if member else "Unknown"
                combined_data[user_id] = {
                    "username": username,
                    "display_name": display_name,
                    "total_time": active_duration
                }
            total_time_all_users += active_duration

        # Sort and return top 10
        sorted_users = sorted(
            [
                (
                    uid, 
                    data["username"],
                    data["total_time"]
                )
                for uid, data in combined_data.items()
            ],
            key=lambda x: x[2],  # Sort by total_time
            reverse=True
        )[:10]
    
        return total_time_all_users, sorted_users

    # New: Calculate total tracking time (since first session)
    total_tracking_seconds = 0
    if state.vc_time_data:
        # Find the earliest session start time across all users
        earliest_session = min(
            [session["start"] for user_data in state.vc_time_data.values() 
             for session in user_data["sessions"]],
            default=0
        )
        if earliest_session > 0:
            total_tracking_seconds = time.time() - earliest_session
    
    # Format total tracking time in consistent format (1h 1m 10s)
    hours = int(total_tracking_seconds // 3600)
    minutes = int((total_tracking_seconds % 3600) // 60)
    seconds = int(total_tracking_seconds % 60)
    
    time_parts = []
    if hours > 0:
        time_parts.append(f"{hours}h")
    if minutes > 0:
        time_parts.append(f"{minutes}m")
    if seconds > 0 or not time_parts:  # Always show at least seconds if no hours/minutes
        time_parts.append(f"{seconds}s")
    
    tracking_time_str = ' '.join(time_parts)
    
    # Send tracking time report (first)
    await ctx.send(f"⏳ **Tracking Started:** {tracking_time_str} ago\n")

    # 1. Top VC Members - Using the new tracking system
    total_time_all_users, top_vc_users = get_vc_time_data()
    if top_vc_users:
        async def process_vc_entry(entry):
            user_id, username, total_seconds = entry
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            seconds = int(total_seconds % 60)
    
            time_parts = []
            if hours > 0:
                time_parts.append(f"{hours}h")
            if minutes > 0:
                time_parts.append(f"{minutes}m")
            time_parts.append(f"{seconds}s")
    
            user_display = await get_user_display_info(user_id)
            return f"• {user_display}: {' '.join(time_parts)}"

        # Process all entries first
        processed_entries = [await process_vc_entry(entry) for entry in top_vc_users]
        
        vc_chunks = create_message_chunks(
            entries=processed_entries,
            title="🏆 Top 10 VC Members",
            process_entry=lambda x: x,
            max_chunk_size=10
        )
        
        for chunk in vc_chunks:
            await ctx.send(chunk)

    # 2. Total VC Time for All Users (excluding excluded users)
    # Format total time
    hours = int(total_time_all_users // 3600)
    minutes = int((total_time_all_users % 3600) // 60)
    seconds = int(total_time_all_users % 60)
    
    time_parts = []
    if hours > 0:
        time_parts.append(f"{hours}h")
    if minutes > 0:
        time_parts.append(f"{minutes}m")
    time_parts.append(f"{seconds}s")
    
    await ctx.send(f"⏱ **Total VC Time (All Users):** {' '.join(time_parts)}\n")

    # 3. Overall Command Usage
    if state.analytics.get("command_usage"):
        commands = sorted(
            state.analytics["command_usage"].items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        def process_command(cmd_entry):
            cmd, count = cmd_entry
            return f"• `{cmd}`: {count} times"
            
        command_chunks = create_message_chunks(
            entries=commands,
            title="📊 Overall Command Usage",
            process_entry=process_command
        )
        
        for chunk in command_chunks:
            await ctx.send(chunk)
    
    # 4. Command Usage by User (Top 10 only)
    if state.analytics.get("command_usage_by_user"):
        # Filter out excluded users before sorting
        filtered_users = [
            (user_id, commands) 
            for user_id, commands in state.analytics["command_usage_by_user"].items()
            if not is_excluded(user_id)
        ]
        
        sorted_users = sorted(
            filtered_users,
            key=lambda item: sum(item[1].values()),
            reverse=True
        )[:10]  # Only take top 10 users
        
        async def process_user_usage(user_entry):
            user_id, commands = user_entry
            user_display = await get_user_display_info(user_id)
            usage_details = ", ".join([f"{cmd}: {cnt}" for cmd, cnt in sorted(commands.items(), key=lambda x: x[1], reverse=True)])
            return f"• {user_display}: {usage_details}"
        
        processed_entries = [await process_user_usage(entry) for entry in sorted_users]
        user_chunks = create_message_chunks(
            entries=processed_entries,
            title="👤 Top 10 Command Users",
            process_entry=lambda x: x
        )
        
        for chunk in user_chunks:
            await ctx.send(chunk)
    
    # 5. Violations by User (Top 10 only)
    if state.user_violations:
        # Filter out excluded users before sorting
        filtered_violations = [
            (user_id, count) 
            for user_id, count in state.user_violations.items()
            if not is_excluded(user_id)
        ]
        
        sorted_violations = sorted(
            filtered_violations,
            key=lambda item: item[1],
            reverse=True
        )[:10]  # Only take top 10 violators
        
        async def process_violation(violation_entry):
            user_id, count = violation_entry
            user_display = await get_user_display_info(user_id)
            return f"• {user_display}: {count} violation(s)"
        
        processed_entries = [await process_violation(entry) for entry in sorted_violations]
        violation_chunks = create_message_chunks(
            entries=processed_entries,
            title="⚠️ No-Cam Detected Report",
            process_entry=lambda x: x
        )
        
        for chunk in violation_chunks:
            await ctx.send(chunk)
    
    if not any([top_vc_users, state.analytics.get("command_usage"), 
                state.analytics.get("command_usage_by_user"), state.user_violations]):
        await ctx.send("📊 Statistics\nNo statistics data available yet.")

@tasks.loop(time=dt_time(bot_config.AUTO_STATS_HOUR_UTC, bot_config.AUTO_STATS_MINUTE_UTC))
async def daily_auto_stats_clear() -> None:
    """Automatically posts VC time stats and clears all statistics at specified UTC time daily"""
    channel = bot.get_channel(bot_config.AUTO_STATS_CHAN)
    if not channel:
        logging.error("AUTO_STATS_CHAN channel not found!")
        return
    
    class SimpleCtx:
        def __init__(self, channel):
            self.channel = channel
            self.guild = channel.guild
            self.send = channel.send
            self.author = bot.user
    
    fake_ctx = SimpleCtx(channel)
    
    # Run times command to show final VC time report
    await time_report(fake_ctx)
    
    # Get current members in both VCs
    streaming_vc = channel.guild.get_channel(bot_config.STREAMING_VC_ID)
    alt_vc = channel.guild.get_channel(bot_config.ALT_VC_ID)
    current_members = []
    
    if streaming_vc:
        current_members.extend([m for m in streaming_vc.members if not m.bot])
    if alt_vc:
        current_members.extend([m for m in alt_vc.members if not m.bot])

    # Clear ALL statistics data (same as !clear)
    state.vc_time_data = {}
    state.active_vc_sessions = {}
    state.analytics = {
        "command_usage": {},
        "command_usage_by_user": {},
        "violation_events": 0
    }
    state.user_violations = {}
    state.camera_off_timers = {}
    
    # Restart tracking for current members
    if current_members:
        current_time = time.time()
        for member in current_members:
            state.active_vc_sessions[member.id] = current_time
            state.vc_time_data[member.id] = {
                "total_time": 0,
                "sessions": [],
                "username": member.name,
                "display_name": member.display_name
            }
        logging.info(f"Restarted VC tracking for {len(current_members)} members after auto-clear")
    
    await channel.send("✅ Statistics automatically cleared and tracking restarted!")

@tasks.loop(seconds=16)
@handle_errors
async def timeout_unauthorized_users() -> None:
    """
    Periodically checks for users in Streaming VC OR Alt VC without an active camera
    and issues violations accordingly.
    """
    if bot_config.VC_MODERATION_PERMANENTLY_DISABLED or not state.vc_moderation_active:
        return

    guild = bot.get_guild(bot_config.GUILD_ID)
    if not guild:
        return

    # Get both voice channels to monitor
    streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
    alt_vc = guild.get_channel(bot_config.ALT_VC_ID)
    punishment_vc = guild.get_channel(bot_config.PUNISHMENT_VC_ID)

    if not all([streaming_vc, alt_vc, punishment_vc]):
        return

    # Check both VCs for violations
    for vc in [streaming_vc, alt_vc]:
        for member in vc.members:
            if member.bot or member.id in bot_config.ALLOWED_USERS or member.id == bot_config.MUSIC_BOT:
                state.camera_off_timers.pop(member.id, None)  # Clear timer if exempt
                continue

            # Camera enforcement logic (same as original)
            if not (member.voice and member.voice.self_video):
                if member.id in state.camera_off_timers:
                    if time.time() - state.camera_off_timers[member.id] >= bot_config.CAMERA_OFF_ALLOWED_TIME:
                        # Apply punishment (same logic as original)
                        state.analytics["violation_events"] += 1
                        state.user_violations[member.id] = state.user_violations.get(member.id, 0) + 1
                        violation_count = state.user_violations[member.id]

                        try:
                            if violation_count == 1:
                                await member.move_to(punishment_vc, reason=f"No camera detected in {vc.name}.")
                                logging.info(f"Moved {member.name} to PUNISHMENT VC (from {vc.name}).")
                                try:
                                    if member.id not in state.users_with_dms_disabled:
                                        await member.send(f"You were moved out of the VC because you didn't have your camera on.")
                                except discord.Forbidden:
                                    state.users_with_dms_disabled.add(member.id)
                                    logging.warning(f"Could not DM {member.name} (DMs disabled).")
                            elif violation_count == 2:
                                timeout_duration = bot_config.TIMEOUT_DURATION_SECOND_VIOLATION
                                await member.timeout(timedelta(seconds=timeout_duration), 
                                    reason=f"2nd camera violation in {vc.name}.")
                                logging.info(f"Timed out {member.name} for {timeout_duration}s (from {vc.name}).")
                                state.active_timeouts[member.id] = {
                                    "timeout_end": time.time() + timeout_duration,
                                    "reason": f"2nd camera violation in {vc.name}",
                                    "timed_by": "AutoMod",
                                    "start_timestamp": time.time()
                                }
                            else:  # 3+ violations
                                timeout_duration = bot_config.TIMEOUT_DURATION_THIRD_VIOLATION
                                await member.timeout(timedelta(seconds=timeout_duration),
                                    reason=f"Repeated camera violations in {vc.name}.")
                                logging.info(f"Timed out {member.name} for {timeout_duration}s (from {vc.name}).")
                                state.active_timeouts[member.id] = {
                                    "timeout_end": time.time() + timeout_duration,
                                    "reason": f"3rd+ camera violation in {vc.name}",
                                    "timed_by": "AutoMod",
                                    "start_timestamp": time.time()
                                }

                            # Send DM if possible (same as original)
                            if violation_count >= 1 and member.id not in state.users_with_dms_disabled:
                                try:
                                    await member.send(
                                        f"You've been {'moved' if violation_count == 1 else 'timed out'} "
                                        f"for not having a camera on in the VC."
                                    )
                                except discord.Forbidden:
                                    state.users_with_dms_disabled.add(member.id)

                            state.camera_off_timers.pop(member.id, None)  # Reset after punishment

                        except discord.Forbidden:
                            logging.warning(f"Missing permissions to punish {member.name} in {vc.name}.")
                        except discord.HTTPException as e:
                            logging.error(f"Failed to punish {member.name} in {vc.name}: {e}")

                else:
                    state.camera_off_timers[member.id] = time.time()  # Start timer
            else:
                state.camera_off_timers.pop(member.id, None)  # Clear timer if camera is on
if __name__ == "__main__":
    # Validate environment variables (safe addition)
    required_vars = ["BOT_TOKEN"]
    if missing := [var for var in required_vars if not os.getenv(var)]:
        logging.critical(f"Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    # Register shutdown handler (complements existing finally block)
    def handle_shutdown(signum, frame):
        logging.info("Graceful shutdown initiated")
        # Let the existing finally block handle cleanup
        sys.exit(0)

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
        # Always clean up hotkeys in finally block
        try:
            # Check if config exists and hotkey is enabled
            if 'bot_config' in globals() and getattr(bot_config, 'ENABLE_GLOBAL_HOTKEY', False):
                try:
                    keyboard.remove_hotkey(bot_config.GLOBAL_HOTKEY_COMBINATION)
                    logging.info("Unregistered global hotkey in finally block")
                except (KeyError, ValueError) as e:
                    logging.debug(f"Hotkey not registered in finally block: {e}")
                except Exception as e:
                    logging.error(f"Error unregistering hotkey in finally block: {e}")
        except NameError:
            pass  # bot_config not defined
        
        # Your existing cleanup remains unchanged
        try:
            state.close_driver()
        except NameError:
            pass  # state not defined
        try:
            save_state()
        except NameError:
            pass  # state not defined
        
        logging.info("Shutdown complete")
