#!/usr/bin/env python

# Standard library imports
import asyncio
import json
import logging
import logging.config
import os
import signal
import time
from datetime import datetime, timezone, timedelta
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

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", help_command=None, intents=intents)
# Constants
STATE_FILE = "data.json"
DRIVER_INIT_RETRIES = 1  # Only attempt initialization once
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
    """Saves bot state to disk"""
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
        "recent_untimeouts": [[e[0], e[1], e[2], e[3].isoformat(), e[4]] for e in state.recent_untimeouts]
    }
    
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(serializable_state, f)
        logging.info("Bot state saved after cleanup")
    except Exception as e:
        logging.error(f"Failed to save bot state: {e}")
def load_state() -> None:
    """Loads the bot state from disk if available."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
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
            logging.info("Bot state loaded successfully.")
        except Exception as e:
            logging.error(f"Failed to load bot state: {e}")
    else:
        logging.info("No saved state file found, starting with a fresh state.")

@tasks.loop(minutes=7)
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
async def selenium_refresh(ctx: Optional[Union[commands.Context, discord.Interaction]] = None) -> bool:
    """
    Navigates to OMEGLE_VIDEO_URL (replacing the standard refresh functionality).
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
        logging.info("Selenium: Navigated to OMEGLE_VIDEO_URL for refresh command.")
        if ctx:
            if isinstance(ctx, discord.Interaction):
                await ctx.response.send_message("Redirected to Omegle video URL.")
            else:
                await ctx.send("Redirected to Omegle video URL.")
        return True
    except Exception as e:
        logging.error(f"Selenium refresh failed: {e}")
        if ctx:
            if isinstance(ctx, discord.Interaction):
                await ctx.response.send_message("Failed to process refresh command in browser.")
            else:
                await ctx.send("Failed to process refresh command in browser.")
        return False
async def selenium_start(ctx: Optional[commands.Context] = None) -> bool:
    """
    Starts the stream by navigating to OMEGLE_VIDEO_URL and triggering a skip.
    Returns True if successful, False otherwise.
    """
    if not state.is_driver_healthy():
        if ctx:
            await ctx.send("Browser connection is not available. Please restart the bot manually.")
        return False
    try:
        state.driver.get(bot_config.OMEGLE_VIDEO_URL)
        logging.info("Selenium: Navigated to OMEGLE_VIDEO_URL for start.")
        await asyncio.sleep(3)
        return await selenium_custom_skip(ctx)
    except Exception as e:
        logging.error(f"Selenium start failed: {e}")
        if ctx:
            await ctx.send("Failed to start browser session.")
        return False
async def selenium_pause(ctx: Optional[commands.Context] = None) -> bool:
    """
    Pauses the stream by refreshing the page.
    Returns True if successful, False otherwise.
    """
    if not state.is_driver_healthy():
        if ctx:
            await ctx.send("Browser connection is not available. Please restart the bot manually.")
        return False
    try:
        state.driver.refresh()
        logging.info("Selenium: Refresh performed for pause command.")
        return True
    except Exception as e:
        logging.error(f"Selenium pause failed: {e}")
        if ctx:
            await ctx.send("Failed to pause browser session.")
        return False
async def selenium_paid(ctx: Optional[Union[commands.Context, discord.Interaction]] = None) -> bool:
    """
    Processes the 'paid' command by navigating to OMEGLE_VIDEO_URL.
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
        logging.info("Selenium: Navigated to OMEGLE_VIDEO_URL for paid command.")
        if ctx:
            if isinstance(ctx, discord.Interaction):
                await ctx.response.send_message("Redirected to Omegle video URL.")
            else:
                await ctx.send("Redirected to Omegle video URL.")
        return True
    except Exception as e:
        logging.error(f"Selenium paid failed: {e}")
        if ctx:
            if isinstance(ctx, discord.Interaction):
                await ctx.response.send_message("Failed to process paid command in browser.")
            else:
                await ctx.send("Failed to process paid command in browser.")
        return False
#########################################
# Voice Connection Functions
#########################################
async def play_sound_in_vc(guild: discord.Guild, sound_file: str) -> None:
    """Connects to the Streaming VC and plays the specified sound file."""
    try:
        await asyncio.sleep(2)
        streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
        if streaming_vc:
            if state.voice_client is None or not state.voice_client.is_connected():
                try:
                    state.voice_client = await streaming_vc.connect()
                except discord.ClientException as e:
                    if "already connected" in str(e).lower():
                        logging.info("Already connected to voice channel.")
                    else:
                        raise
            state.voice_client.play(discord.FFmpegPCMAudio(executable="ffmpeg", source=sound_file))
            while state.voice_client.is_playing():
                await asyncio.sleep(1)
    except Exception as e:
        logging.error(f"Failed to play sound in VC: {e}")
async def disconnect_from_vc() -> None:
    """Disconnects from the voice channel."""
    if state.voice_client and state.voice_client.is_connected():
        await state.voice_client.disconnect()
        state.voice_client = None
def is_user_in_streaming_vc_with_camera(user: discord.Member) -> bool:
    """Checks if a user in the Streaming VC has their camera on."""
    streaming_vc = user.guild.get_channel(bot_config.STREAMING_VC_ID)
    return bool(streaming_vc and user in streaming_vc.members and user.voice and user.voice.self_video)
async def global_skip() -> None:
    """Executes the global skip command, triggered via a global hotkey."""
    guild = bot.get_guild(bot_config.GUILD_ID)
    if guild:
        await selenium_custom_skip()
        await play_sound_in_vc(guild, bot_config.SOUND_FILE)
        logging.info("Executed global skip command via hotkey.")
    else:
        logging.error("Guild not found for global skip.")
async def ensure_voice_connection() -> None:
    """Ensures that the bot is connected to the voice channel."""
    guild = bot.get_guild(bot_config.GUILD_ID)
    if not guild:
        logging.error("Guild not found in ensure_voice_connection.")
        return
    streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
    if streaming_vc:
        if state.voice_client is None or not state.voice_client.is_connected():
            try:
                state.voice_client = await streaming_vc.connect()
                logging.info("Reconnected to voice channel.")
            except discord.ClientException as e:
                if "already connected" in str(e).lower():
                    logging.info("Already connected to voice channel.")
                else:
                    logging.error(f"Failed to reconnect to voice: {e}")
                    
@tasks.loop(seconds=125)
async def check_voice_connection() -> None:
    """Periodic task to ensure active voice connection."""
    await ensure_voice_connection()

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

def create_message_chunks(entries: List[Any], title: str, process_entry: Callable[[Any], str], max_chunk_size: int = 50) -> List[str]:
    """
    Creates message chunks from entries with a given title, processing each entry.
    
    Args:
        entries: List of items to process
        title: Section title to prepend to each chunk
        process_entry: Function that converts an entry to a string
        max_chunk_size: Maximum number of entries per chunk
        
    Returns:
        List of formatted message strings
    """
    chunks = []
    current_chunk = []
    
    for entry in entries:
        processed = process_entry(entry)
        if processed:
            current_chunk.append(processed)
            
            if len(current_chunk) >= max_chunk_size:
                chunks.append(
                    f"**{title} ({len(entries)} total)**\n" + 
                    "\n".join(current_chunk)
                )
                current_chunk = []
    
    if current_chunk:
        chunks.append(
            f"**{title} ({len(entries)} total)**\n" + 
            "\n".join(current_chunk)
        )
    
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
                    title=f"Welcome {member.display_name}",
                    description=f"{member.mention} JOINED the server!",
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
            description=f"{member.mention} was **TIMED OUT**",
            color=discord.Color.orange())
   
        embed.set_author(
            name=f"{member.display_name}",
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
            value=f"🛡️ {moderator.mention}",
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
            description=f"{member.mention}'s **TIMEOUT was REMOVED**",
            color=discord.Color.orange())

        embed.set_author(name=member.name, icon_url=member.display_avatar.url)
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

        # Process reason to include proper @mention if manually removed
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
                
                # Use proper mention if found, otherwise show name
                mod_display = mod_member.mention if mod_member else mod_name
                reason = f"{reason_text.strip()} by {mod_display}"
            except Exception as e:
                logging.error(f"Error processing moderator mention: {e}")

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
                description=f"{user.mention} was UNBANNED",
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
    
    # Initialize state and set global instance
    global state
    state = BotState(bot_config) 
    set_bot_state_instance(state)  # Set the global instance for tools.py access
    load_state()
    
    try:
        # Start all periodic tasks
        periodic_state_save.start()
        periodic_cleanup.start()
        periodic_help_menu.start()
        timeout_unauthorized_users.start()
        check_voice_connection.start()
        
        # Initialize Selenium (only once, no automatic retries)
        selenium_success = init_selenium()
        if not selenium_success:
            logging.critical("Selenium initialization failed. Browser commands will not work until bot restart.")
        
        # Initialize VC moderation state
        guild = bot.get_guild(bot_config.GUILD_ID)
        if guild:
            streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
            if streaming_vc:
                # Bot joins VC and self-deafens
                try:
                    if state.voice_client is None or not state.voice_client.is_connected():
                        state.voice_client = await streaming_vc.connect()
                        await state.voice_client.guild.change_voice_state(
                            channel=streaming_vc, 
                            self_deaf=True
                        )
                        logging.info("Connected to voice channel and self-deafened")
                    
                    # Check existing members in VC
                    for member in streaming_vc.members:
                        if not member.bot and (member.id not in bot_config.ALLOWED_USERS and member.id != bot_config.MUSIC_BOT):
                            if not (member.voice and member.voice.self_video):
                                try:
                                    if not bot_config.VC_MODERATION_PERMANENTLY_DISABLED and state.vc_moderation_active:
                                        await member.edit(mute=True, deafen=True)
                                        logging.info(f"Auto-muted and deafened {member.name} for camera off.")
                                except Exception as e:
                                    logging.error(f"Failed to auto mute/deafen {member.name}: {e}")
                                state.camera_off_timers[member.id] = time.time()
                except Exception as e:
                    logging.error(f"Error initializing voice connection: {e}")
        
        # Register global hotkey if enabled
        if bot_config.ENABLE_GLOBAL_HOTKEY:
            def hotkey_callback() -> None:
                logging.info("Global hotkey pressed, triggering skip command.")
                asyncio.run_coroutine_threadsafe(global_skip(), bot.loop)
            
            try:
                keyboard.add_hotkey(bot_config.GLOBAL_HOTKEY_COMBINATION, hotkey_callback)
                logging.info(f"Global hotkey {bot_config.GLOBAL_HOTKEY_COMBINATION} registered for !skip command.")
            except Exception as e:
                logging.error(f"Failed to register global hotkey: {e}")
        
        # Initial cleanup of old entries
        state.clean_old_entries()
        logging.info("Initial state cleanup completed")
    
    except Exception as e:
        logging.error(f"Error during on_ready setup: {e}", exc_info=True)

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User) -> None:
    """
    Logs when a user is banned from the server.
    """
    try:
        chat_channel = guild.get_channel(bot_config.CHAT_CHANNEL_ID)
        if chat_channel:
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
            
            # Create embed
            embed = discord.Embed(
                description=f"{user.mention} was BANNED",
                color=discord.Color.red())
            
            # Add user info
            embed.set_author(name=user.name, icon_url=user.display_avatar.url)
            embed.set_thumbnail(url=user.display_avatar.url)
            
            # Try to get banner if available
            try:
                user_obj = await bot.fetch_user(user.id)
                if user_obj.banner:
                    embed.set_image(url=user_obj.banner.url)
            except:
                pass
            
            # Add fields
            embed.add_field(name="Moderator", value=moderator, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            
            await chat_channel.send(embed=embed)
        
        # Record the ban
        state.recent_bans.append((
            user.id,
            user.name,
            user.display_name,
            datetime.now(timezone.utc),
            reason
        ))
        
        # Keep only recent bans (last 100)
        if len(state.recent_bans) > 100:
            state.recent_bans.pop(0)
            
        logging.info(f"{user.name} was banned from the server. Reason: {reason}")
        
    except Exception as e:
        logging.error(f"Error in on_member_ban: {e}")
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
                    embed = discord.Embed(
                        description=f"{member.mention} was KICKED",
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
                    
                    embed.add_field(name="Reason", value=entry.reason or "No reason provided", inline=False)
                    embed.add_field(name="Kicked by", value=entry.user.mention, inline=True)
                    
                    await chat_channel.send(embed=embed)
                
                # Record the kick
                state.recent_kicks.append((
                    member.id,
                    member.name,
                    member.nick,
                    current_time,
                    entry.reason or "No reason provided",
                    entry.user.mention  # <- the mod who kicked
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
                embed = discord.Embed(color=discord.Color.red(), timestamp=current_time)
                embed.set_author(name=member.name, icon_url=avatar_url)
                embed.description = f"{member.mention} LEFT the server"
                embed.set_thumbnail(url=avatar_url)
                embed.add_field(name="Time in Server", value=duration_str, inline=True)
                roles = [role.name for role in member.roles if role.name != "@everyone"]
                embed.add_field(name="Roles", value=", ".join(roles) if roles else "None", inline=True)
                await chat_channel.send(embed=embed)
            
            logging.info(f"{member.name} left the server voluntarily.")
        
        state.recent_leaves.append((
            member.id,
            member.name,
            member.nick,
            current_time
        ))
        if len(state.recent_leaves) > 100:
            state.recent_leaves.pop(0)
            
    except Exception as e:
        logging.error(f"Error in on_member_remove: {e}")

@bot.event
async def on_voice_state_update(member: discord.Member, before, after) -> None:
    """
    Handles voice state updates, checking camera status, auto-muting, and tracking join/leave times.
    Additionally, for allowed users in the Streaming VC, this function will immediately revert any server mute or deafen actions.
    """
    try:
        if member == bot.user:
            return

        streaming_vc = member.guild.get_channel(bot_config.STREAMING_VC_ID)
        alt_vc = member.guild.get_channel(bot_config.ALT_VC_ID)

        # Revert server mute/deafen for allowed users
        if after.channel and after.channel.id in [bot_config.STREAMING_VC_ID, bot_config.ALT_VC_ID] and member.id in bot_config.ALLOWED_USERS:
            if member.voice:
                if member.voice.mute and not member.voice.self_mute:
                    try:
                        await member.edit(mute=False)
                        logging.info(f"Reverted server mute on allowed user {member.name}.")
                    except Exception as e:
                        logging.error(f"Failed to unmute allowed user {member.name}: {e}")
                if member.voice.deaf and not member.voice.self_deaf:
                    try:
                        await member.edit(deafen=False)
                        logging.info(f"Reverted server deafen on allowed user {member.name}.")
                    except Exception as e:
                        logging.error(f"Failed to undeafen allowed user {member.name}: {e}")

        # Track join/leave status - only for Streaming VC
        if member.id not in state.user_last_join:
            state.user_last_join[member.id] = False

        if after.channel and after.channel.id == bot_config.STREAMING_VC_ID:
            if not state.user_last_join[member.id]:
                state.user_last_join[member.id] = True
                logging.info(f"{member.name} joined Streaming VC at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")

            # Send rules if needed
            if member.id not in state.users_received_rules and member.id not in state.users_with_dms_disabled:
                try:
                    await member.send(bot_config.RULES_MESSAGE)
                    state.users_received_rules.add(member.id)
                    logging.info(f"Sent rules to {member.name}.")
                except discord.Forbidden:
                    state.users_with_dms_disabled.add(member.id)
                    logging.warning(f"Could not send DM to {member.name} (DMs disabled).")
                except discord.HTTPException as e:
                    logging.error(f"Failed to send DM to {member.name}: {e}")

            # VC moderation for non-allowed users
            if (member.id not in bot_config.ALLOWED_USERS and 
                member.id != bot_config.MUSIC_BOT and 
                state.vc_moderation_active and 
                not bot_config.VC_MODERATION_PERMANENTLY_DISABLED):

                if not after.self_video:
                    if member.voice and (not member.voice.mute or not member.voice.deaf):
                        try:
                            await member.edit(mute=True, deafen=True)
                            logging.info(f"Auto-muted and deafened {member.name} for camera off.")
                        except Exception as e:
                            logging.error(f"Failed to auto mute/deafen {member.name}: {e}")
                    state.camera_off_timers[member.id] = time.time()
                elif not state.hush_override_active:
                    if member.voice and (member.voice.mute or member.voice.deaf):
                        try:
                            await member.edit(mute=False, deafen=False)
                            logging.info(f"Auto-unmuted {member.name} after camera on.")
                        except Exception as e:
                            logging.error(f"Failed to auto unmute/undeafen {member.name}: {e}")
                    state.camera_off_timers.pop(member.id, None)
                else:
                    logging.info(f"Hush override active; leaving {member.name} muted/deafened.")

            # Auto-pause if last camera goes off (only applies in Streaming VC)
            if (before.self_video and not after.self_video and 
                streaming_vc and member.id not in bot_config.ALLOWED_USERS):

                # Check if this was the last non-allowed user with camera on in Streaming VC
                users_with_camera = [
                    m for m in streaming_vc.members 
                    if (m.voice and m.voice.self_video and 
                        m.id not in bot_config.ALLOWED_USERS and
                        not m.bot)
                ]

                if not users_with_camera:
                    try:
                        now = time.time()
                        if now - state.last_auto_pause_time >= 1:  # Minimal internal cooldown
                            state.last_auto_pause_time = now
                            await selenium_pause()
                            await play_sound_in_vc(member.guild, bot_config.SOUND_FILE)
                            logging.info("Auto Paused - No Cameras Detected in Streaming VC")

                            command_channel = member.guild.get_channel(bot_config.COMMAND_CHANNEL_ID)
                            if command_channel:
                                await command_channel.send("Automatically paused")
                        else:
                            logging.info("Auto-pause skipped due to internal bot cooldown")
                    except Exception as e:
                        logging.error(f"Failed to auto-execute pause: {e}")

        elif before.channel and before.channel.id == bot_config.STREAMING_VC_ID:
            if state.user_last_join.get(member.id, False):
                state.user_last_join[member.id] = False
                logging.info(f"{member.name} left Streaming VC at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
            state.camera_off_timers.pop(member.id, None)

            # Auto-pause if last non-allowed user just left the Streaming VC
            remaining_non_allowed = [
                m for m in before.channel.members
                if not m.bot and m.id not in bot_config.ALLOWED_USERS and 
                m.voice and m.voice.self_video
            ]
            if not remaining_non_allowed:
                try:
                    now = time.time()
                    if now - state.last_auto_pause_time >= 1:
                        state.last_auto_pause_time = now
                        await selenium_pause()
                        await play_sound_in_vc(member.guild, bot_config.SOUND_FILE)
                        logging.info("Auto Paused - Last non-allowed user with camera left Streaming VC")

                        command_channel = member.guild.get_channel(bot_config.COMMAND_CHANNEL_ID)
                        if command_channel:
                            await command_channel.send("Automatically paused")
                    else:
                        logging.info("Auto-pause (on leave) skipped due to internal bot cooldown")
                except Exception as e:
                    logging.error(f"Failed to auto-execute pause on leave: {e}")

        # Handle Alt VC separately - no auto-pause, just logging
        if after.channel and after.channel.id == bot_config.ALT_VC_ID:
            logging.info(f"{member.name} joined Alt VC at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
        elif before.channel and before.channel.id == bot_config.ALT_VC_ID:
            logging.info(f"{member.name} left Alt VC at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")

    except Exception as e:
        logging.error(f"Error in on_voice_state_update: {e}", exc_info=True)

@bot.command(name='bans', aliases=['banned'])
@require_command_channel
@handle_errors
async def bans(ctx) -> None:
    """
    Lists all banned users in compact format (50 per message).
    Shows username, ID, and available ban info in one line per user.
    """
    if ctx.author.id not in bot_config.ALLOWED_USERS:  # <-- Simplified check
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

        # Process bans in chunks of 50 per message
        for i in range(0, len(ban_entries), 50):
            description = []
            
            for entry in ban_entries[i:i+50]:
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
                
                description.append(line)
            
            embed = discord.Embed(
                title=f"Banned Users (Total: {len(ban_entries)})",
                description="\n".join(description),
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Showing bans {i+1}-{min(i+50, len(ban_entries))}")
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
    Lists the top 5 oldest members of the server with detailed information.
    Only usable by allowed users.
    """
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    
    record_command_usage(state.analytics, "!top")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!top")
    
    try:
        # Get all members and sort by join date (oldest first)
        members = sorted(
            ctx.guild.members,
            key=lambda m: m.joined_at or datetime.now(timezone.utc)
        )[:5]  # Get top 5
        
        if not members:
            await ctx.send("No members found in the server.")
            return
            
        # Create an embed for each member
        for i, member in enumerate(members, 1):
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
            # Prepare member list chunks
            member_list = [f"{member.display_name} ({member.name}#{member.discriminator})" 
                         for member in role.members]
            chunks = [member_list[i:i + 50] for i in range(0, len(member_list), 50)]
            
            # Create and send embeds for each chunk
            for i, chunk in enumerate(chunks):
                embed = discord.Embed(
                    title=f"Role: {role.name} (Part {i + 1})" if len(chunks) > 1 else f"Role: {role.name}",
                    color=role.color
                )
                embed.description = "\n".join(chunk)
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
                                    reason = f"Timeout manually removed by {moderator_name}"
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
            "Info": "!info" 
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
        
        async def handle_skip(guild: discord.Guild) -> None:
            await selenium_custom_skip(message)
            await play_sound_in_vc(guild, bot_config.SOUND_FILE)
        async def handle_refresh(guild: discord.Guild) -> None:
            await selenium_refresh(message)
            await asyncio.sleep(3)
            await selenium_custom_skip(message)
            await play_sound_in_vc(guild, bot_config.SOUND_FILE)
        async def handle_pause(guild: discord.Guild) -> None:
            await selenium_pause(message)
            await play_sound_in_vc(guild, bot_config.SOUND_FILE)
        async def handle_start(guild: discord.Guild) -> None:
            await selenium_start(message)
            await play_sound_in_vc(guild, bot_config.SOUND_FILE)
        async def handle_paid(guild: discord.Guild) -> None:
            await selenium_paid(message)
            await asyncio.sleep(1)
            await selenium_custom_skip(message)
            await play_sound_in_vc(guild, bot_config.SOUND_FILE)
        
        command_actions = {
            "!skip": lambda: asyncio.create_task(handle_skip(message.guild)),
            "!refresh": lambda: asyncio.create_task(handle_refresh(message.guild)),
            "!pause": lambda: asyncio.create_task(handle_pause(message.guild)),
            "!start": lambda: asyncio.create_task(handle_start(message.guild)),
            "!paid": lambda: asyncio.create_task(handle_paid(message.guild))
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
    """
    try:
        help_description = """
**Omegle Commands:**
Skip/Start - Skips/Starts Omegle
Pause - Pauses Omegle
Refresh - Refreshes Omegle
Info - Server information

**Other Commands:**
!paid - Run after unban
!rules - Lists and DMs Server rules
!owner - Lists Admins and Owners
!commands - Lists all commands
"""
        embed = build_embed("Omegle Skip Bot", help_description, discord.Color.blue())
        if isinstance(target, discord.Message):
            await target.channel.send(embed=embed, view=HelpView())
        elif isinstance(target, discord.TextChannel):
            await target.send(embed=embed, view=HelpView())
        else:
            raise ValueError("Invalid target type. Expected discord.Message or discord.TextChannel.")
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

@tasks.loop(minutes=2)  # Reduced frequency from 2min to 10min to prevent rate limits
async def periodic_help_menu() -> None:
    """
    Periodically updates the help menu with rate limit protection.
    Purges max 50 messages per execution.
    """
    try:
        guild = bot.get_guild(bot_config.GUILD_ID)
        if not guild:
            return

        channel = guild.get_channel(bot_config.COMMAND_CHANNEL_ID)
        if not channel:
            return

        # 1. Safe purge (max 50 messages with delay)
        try:
            await channel.send("🔁 Refreshing help menu...", delete_after=5)
            await safe_purge(channel, limit=50)  # Strict 50-message limit
            await asyncio.sleep(2)  # Mandatory cooldown
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                wait = e.retry_after + 5  # Extra buffer
                logging.warning(f"Rate limited. Retrying in {wait}s")
                await asyncio.sleep(wait)
                return
            raise

        # 2. Send updated help menu
        await send_help_menu(channel)

    except Exception as e:
        logging.error(f"Help menu update failed: {e}", exc_info=True)
        await asyncio.sleep(300)  # 5min backoff on critical errors

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
    - Disconnects from voice channels
    - Closes Selenium driver
    - Saves bot state
    - Terminates cleanly
    """
    if ctx.author.id not in bot_config.ALLOWED_USERS:
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    
    logging.critical(f"Shutdown command received from {ctx.author.name} (ID: {ctx.author.id})")
    await ctx.send("🛑 **Bot is shutting down...**")
    
    # Cleanup resources
    try:
        # 1. Disconnect from voice if connected
        if state.voice_client and state.voice_client.is_connected():
            await state.voice_client.disconnect()
            logging.info("Disconnected from voice channel during shutdown")
            
        # 2. Close Selenium driver
        state.close_driver()
        
        # 3. Save persistent state
        save_state()
        
    except Exception as e:
        logging.error(f"Error during shutdown cleanup: {e}")
        await ctx.send("⚠️ Warning: Some resources may not have closed cleanly")
    
    # 4. Close Discord connection
    await bot.close()
    
    # 5. Exit the Python process
    import signal
    os.kill(os.getpid(), signal.SIGTERM)

@bot.command(name='rtimeouts')
@handle_errors
async def remove_timeouts(ctx) -> None:
    """
    Removes timeouts from all members and reports which users had timeouts removed.
    """
    if not (ctx.author.id in bot_config.ALLOWED_USERS or any(role.name in bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles)):
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    record_command_usage(state.analytics, "!rtimeouts")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!rtimeouts")
        
    removed_timeouts = []
    for member in ctx.guild.members:
        if member.is_timed_out():
            try:
                await member.timeout(None, reason="Timeout removed by allowed user.")
                removed_timeouts.append(member.name)
                logging.info(f"Removed timeout from {member.name}.")
                if member.id in state.active_timeouts:
                    del state.active_timeouts[member.id]
            except discord.Forbidden:
                logging.warning(f"Missing permissions to remove timeout from {member.name}.")
            except discord.HTTPException as e:
                logging.error(f"Failed to remove timeout from {member.name}: {e}")
    if removed_timeouts:
        msg = "Removed timeouts from: " + ", ".join(removed_timeouts)
        logging.info(msg)
        await ctx.send(msg)
    else:
        await ctx.send("No users were timed out.")
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
        "**!pause** - Refreshes page.\n"
        "**!start** - Starts Omegle by skipping.\n"
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
        "**!whois** - Lists timeouts, untimeouts, joins, leaves, kicks.\n"
        "**!stats** - Shows command usage statistics.\n"
        "**!roles** - Lists roles and their members.\n"
        "**!rtimeouts** - Removes timeouts from ALL members."
    )
    allowed_commands = (
        "**!purge [number]** - Purges messages from the channel.\n"
        "**!top** - Lists the top 5 longest members of the server.\n"
        "**!join** - Sends a join invite DM to admin role members.\n"
        "**!bans** - Lists all users who are server banned.\n"
        "**!banned** - Lists all users who are server banned.\n"
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
    allowed = (ctx.author.id in bot_config.ALLOWED_USERS or 
               any(role.name in bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles))
    if not allowed:
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

    # Helper function to create message chunks for a list of entries
    def create_message_chunks(entries, title, process_entry):
        """Create message chunks from entries with given title, processing each entry with process_entry."""
        chunks = []
        current_entries = []
        
        for entry in entries:
            processed = process_entry(entry)
            if processed:
                current_entries.append(processed)
                
                if len(current_entries) >= 50:  # Higher limit for plain text
                    chunks.append(
                        f"**{title} ({len(entries)} total)**\n" + 
                        "\n".join(current_entries)
                    )
                    current_entries = []
        
        if current_entries:
            chunks.append(
                f"**{title} ({len(entries)} total)**\n" + 
                "\n".join(current_entries)
            )
        
        return chunks

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
            process_timeout
        )

    # Recent Untimeouts (Orange)
    untimeout_list = [entry for entry in state.recent_untimeouts if now - entry[3] <= timedelta(hours=24)]
    if untimeout_list:
        has_data = True
        processed_users = set()
        
        def process_untimeout(entry):
            user_id = entry[0]
            if user_id in processed_users:
                return None
            processed_users.add(user_id)
            
            reason = entry[4]
            mod_name = entry[5] if len(entry) > 5 else None
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
            process_untimeout
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
        
        # Process kick entries asynchronously
        kick_messages = []
        chunk_size = 50
        for i in range(0, len(kick_list), chunk_size):
            chunk = kick_list[i:i + chunk_size]
            processed_entries = []
            for entry in chunk:
                processed_entry = await process_kick(entry)
                processed_entries.append(processed_entry)
            
            content = f"**👢 Recent Kicks ({len(kick_list)} total)**\n" + "\n".join(processed_entries)
            kick_messages.append(content)
        
        reports["👢 Recent Kicks"] = kick_messages

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
    
        # Process ban entries asynchronously
        ban_messages = []
        chunk_size = 50
        for i in range(0, len(ban_list), chunk_size):
            chunk = ban_list[i:i + chunk_size]
            processed_entries = []
            for entry in chunk:
                processed_entry = await process_ban(entry)
                processed_entries.append(processed_entry)
        
            content = f"**🔨 Recent Bans ({len(ban_list)} total)**\n" + "\n".join(processed_entries)
            ban_messages.append(content)
    
        reports["🔨 Recent Bans"] = ban_messages

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
            process_unban
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
        
        # Process join entries asynchronously
        join_messages = []
        chunk_size = 50
        for i in range(0, len(join_list), chunk_size):
            chunk = join_list[i:i + chunk_size]
            processed_entries = []
            for entry in chunk:
                processed_entry = await process_join(entry)
                processed_entries.append(processed_entry)
            
            content = f"**🎉 Recent Joins ({len(join_list)} total)**\n" + "\n".join(processed_entries)
            join_messages.append(content)
        
        reports["🎉 Recent Joins"] = join_messages

    # Recent Leaves (Red)
    leave_list = [entry for entry in state.recent_leaves if now - entry[3] <= timedelta(hours=24)]
    if leave_list:
        has_data = True
        async def process_leave(entry):
            user_id = entry[0]
            stored_username = entry[1] if len(entry) > 1 else None
            user_display = await get_left_user_display_info(user_id, stored_username)
            return f"• {user_display}"
        
        # Process leave entries asynchronously
        leave_messages = []
        chunk_size = 50
        for i in range(0, len(leave_list), chunk_size):
            chunk = leave_list[i:i + chunk_size]
            processed_entries = []
            for entry in chunk:
                processed_entry = await process_leave(entry)
                processed_entries.append(processed_entry)
            
            content = f"**🚪 Recent Leaves ({len(leave_list)} total)**\n" + "\n".join(processed_entries)
            leave_messages.append(content)
        
        reports["🚪 Recent Leaves"] = leave_messages

    # Send all non-empty reports in order
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
                await ctx.send(chunk)
    
    # If no data was found in any report section
    if not has_data:
        await ctx.send("no data")
                
                
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

@bot.command(name='stats')
@require_command_channel
@handle_errors
async def analytics_report(ctx) -> None:
    """
    Sends a report showing command usage statistics and violation events in plain text format.
    Uses multiple messages with 50 entries max per section.
    """
    if ctx.author.id not in bot_config.ALLOWED_USERS and not any(role.name in bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles):
        await ctx.send("⛔ You do not have permission to use this command.")
        return
    
    record_command_usage(state.analytics, "!stats")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!stats")
    
    messages = []
    
    async def get_user_display_info(user_id):
        """Get user display information with mentions and full username"""
        try:
            user = bot.get_user(user_id)
            if user is None:
                user = await bot.fetch_user(user_id)
            return f"{user.mention} ({user.name}#{user.discriminator})"
        except:
            return f"<@{user_id}> (Unknown User)"
    
    # 1. Overall Command Usage
    if state.analytics.get("command_usage"):
        commands = sorted(
            state.analytics["command_usage"].items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        def process_command(cmd_entry):
            cmd, count = cmd_entry
            return f"• `{cmd}`: {count} times"
            
        messages.extend(create_message_chunks(
            entries=commands,
            title="📊 Overall Command Usage",
            process_entry=process_command
        ))
    
    # 2. Command Usage by User
    if state.analytics.get("command_usage_by_user"):
        sorted_users = sorted(
            state.analytics["command_usage_by_user"].items(),
            key=lambda item: sum(item[1].values()),
            reverse=True
        )
        
        async def process_user_usage(user_entry):
            user_id, commands = user_entry
            user_display = await get_user_display_info(user_id)
            usage_details = ", ".join([f"{cmd}: {cnt}" for cmd, cnt in sorted(commands.items(), key=lambda x: x[1], reverse=True)])
            return f"• {user_display}: {usage_details}"
        
        # Process all entries first (maintains order better than chunk-then-process)
        processed_entries = [await process_user_usage(entry) for entry in sorted_users]
        messages.extend(create_message_chunks(
            entries=processed_entries,
            title="👤 Command Usage by User",
            process_entry=lambda x: x  # Already processed
        ))
    
    # 3. Violations by User
    if state.user_violations:
        sorted_violations = sorted(
            state.user_violations.items(),
            key=lambda item: item[1],
            reverse=True
        )
        
        async def process_violation(violation_entry):
            user_id, count = violation_entry
            user_display = await get_user_display_info(user_id)
            return f"• {user_display}: {count} violation(s)"
        
        processed_entries = [await process_violation(entry) for entry in sorted_violations]
        messages.extend(create_message_chunks(
            entries=processed_entries,
            title="⚠️ Violations by User",
            process_entry=lambda x: x  # Already processed
        ))
    
    if messages:
        for message in messages:
            await ctx.send(message)
    else:
        await ctx.send("📊 Statistics\nNo statistics data available yet.")

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
        # Your existing cleanup remains unchanged
        state.close_driver()
        save_state()
        logging.info("Shutdown complete")
