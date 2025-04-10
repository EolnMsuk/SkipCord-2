#!/usr/bin/env python

import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import asyncio
from datetime import datetime, timezone, timedelta
import logging
import logging.config
import time
import os
import subprocess
from dotenv import load_dotenv
import json  # For persistence
import keyboard  # Global hotkey support
from functools import wraps
from typing import Any, Callable

# Selenium imports for browser automation
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager

# Load environment variables from .env file
load_dotenv()

import config
from tools import (
    handle_errors,
    send_message_both,
    BotConfig,
    BotState,
    ordinal,
    get_discord_age,
    record_command_usage,
    record_command_usage_by_user,
    build_embed,
    build_role_update_embed  # New helper for role update embeds
)

# Initialize configuration and state objects
bot_config = BotConfig.from_config_module(config)
state = BotState()

# Configure logging
logging_config = {
    "version": 1,
    "formatters": {
        "detailed": {
            "format": "%(asctime)s - %(levelname)s - %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "detailed",
            "level": "INFO"
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": "log.log",
            "formatter": "detailed",
            "level": "INFO"
        }
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO"
    }
}
logging.config.dictConfig(logging_config)

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", help_command=None, intents=intents)

#########################################
# Persistence Functions
#########################################

STATE_FILE = "data.json"

def save_state() -> None:
    """
    Saves a serializable version of the bot's state to disk.
    """
    serializable_state = {
        "analytics": state.analytics,
        "users_received_rules": list(state.users_received_rules),
        "user_violations": state.user_violations,
        "active_timeouts": state.active_timeouts,
        "recent_joins": [[entry[0], entry[1], entry[2], entry[3].isoformat()] for entry in state.recent_joins],
        "recent_leaves": [[entry[0], entry[1], entry[2], entry[3].isoformat()] for entry in state.recent_leaves],
    }
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(serializable_state, f)
        logging.info("Bot state saved successfully.")
    except Exception as e:
        logging.error(f"Failed to save bot state: {e}")

def load_state() -> None:
    """
    Loads the bot state from disk if available.
    """
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
            state.recent_joins = [(entry[0], entry[1], entry[2], datetime.fromisoformat(entry[3])) for entry in data.get("recent_joins", [])]
            state.recent_leaves = [(entry[0], entry[1], entry[2], datetime.fromisoformat(entry[3])) for entry in data.get("recent_leaves", [])]
            logging.info("Bot state loaded successfully.")
        except Exception as e:
            logging.error(f"Failed to load bot state: {e}")
    else:
        logging.info("No saved state file found, starting with a fresh state.")

@tasks.loop(minutes=5)
async def periodic_state_save() -> None:
    save_state()

#########################################
# Selenium Management Functions (Unchanged)
#########################################

def init_selenium() -> None:
    """
    Initializes the Selenium WebDriver using Microsoft Edge.
    Opens the OMEGLE_VIDEO_URL page.
    """
    try:
        service = EdgeService(EdgeChromiumDriverManager().install())
        options = webdriver.EdgeOptions()
        options.add_argument(f"user-data-dir={bot_config.EDGE_USER_DATA_DIR}")
        state.driver = webdriver.Edge(service=service, options=options)
        state.driver.maximize_window()
        state.driver.get(bot_config.OMEGLE_VIDEO_URL)
        logging.info("Selenium: Opened OMEGLE_VIDEO_URL page.")
    except Exception as e:
        logging.error(f"Failed to initialize Selenium driver: {e}")
        state.driver = None

async def selenium_custom_skip() -> None:
    """
    Sends skip key events to the page.
    """
    if state.driver is None:
        logging.error("Selenium driver not initialized; cannot skip.")
        return
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
    except Exception as e:
        logging.error(f"Selenium custom skip failed: {e}")

async def selenium_refresh() -> None:
    """
    Refreshes the Selenium page. Reinitializes the driver if refresh fails.
    """
    if state.driver is None:
        logging.error("Selenium driver not initialized; attempting reinitialization.")
        init_selenium()
        return
    try:
        state.driver.refresh()
        logging.info("Selenium: Page refreshed.")
    except Exception as e:
        logging.error(f"Selenium refresh failed: {e}. Attempting to reinitialize the driver.")
        try:
            state.driver.quit()
        except Exception as ex:
            logging.error(f"Error quitting driver: {ex}")
        state.driver = None
        init_selenium()

async def selenium_start() -> None:
    """
    Starts the stream by navigating to OMEGLE_VIDEO_URL and triggering a skip.
    """
    if state.driver is None:
        logging.error("Selenium driver not initialized; cannot start.")
        return
    try:
        state.driver.get(bot_config.OMEGLE_VIDEO_URL)
        logging.info("Selenium: Navigated to OMEGLE_VIDEO_URL for start.")
        await asyncio.sleep(3)
        await selenium_custom_skip()
    except Exception as e:
        logging.error(f"Selenium start failed: {e}")

async def selenium_pause() -> None:
    """
    Pauses the stream by refreshing the page.
    """
    if state.driver is None:
        logging.error("Selenium driver not initialized; cannot pause.")
        return
    try:
        state.driver.refresh()
        logging.info("Selenium: Refresh performed for pause command.")
    except Exception as e:
        logging.error(f"Selenium pause failed: {e}")

async def selenium_paid() -> None:
    """
    Processes the 'paid' command by navigating to OMEGLE_VIDEO_URL.
    """
    if state.driver is None:
        logging.error("Selenium driver not initialized; cannot process paid command.")
        return
    try:
        state.driver.get(bot_config.OMEGLE_VIDEO_URL)
        logging.info("Selenium: Navigated to OMEGLE_VIDEO_URL for paid command.")
    except Exception as e:
        logging.error(f"Selenium paid failed: {e}")

#########################################
# Voice Connection Functions (Unchanged)
#########################################

async def play_sound_in_vc(guild: discord.Guild, sound_file: str) -> None:
    """
    Connects to the Streaming VC and plays the specified sound file.
    """
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
    """
    Disconnects from the voice channel.
    """
    if state.voice_client and state.voice_client.is_connected():
        await state.voice_client.disconnect()
        state.voice_client = None

def is_user_in_streaming_vc_with_camera(user: discord.Member) -> bool:
    """
    Checks if a user in the Streaming VC has their camera on.
    """
    streaming_vc = user.guild.get_channel(bot_config.STREAMING_VC_ID)
    return bool(streaming_vc and user in streaming_vc.members and user.voice and user.voice.self_video)

async def global_skip() -> None:
    """
    Executes the global skip command, triggered via a global hotkey.
    """
    guild = bot.get_guild(bot_config.GUILD_ID)
    if guild:
        await selenium_custom_skip()
        await play_sound_in_vc(guild, bot_config.SOUND_FILE)
        logging.info("Executed global skip command via hotkey.")
    else:
        logging.error("Guild not found for global skip.")

async def ensure_voice_connection() -> None:
    """
    Ensures that the bot is connected to the voice channel.
    """
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

@tasks.loop(seconds=30)
async def check_voice_connection() -> None:
    """Periodic task to ensure active voice connection."""
    await ensure_voice_connection()

#########################################
# Decorator for Command Channel Enforcement
#########################################

def require_command_channel(func: Callable) -> Callable:
    """
    Decorator to enforce that non-allowed users use the designated command channel.
    """
    @wraps(func)
    async def wrapper(ctx, *args, **kwargs):
        if ctx.author.id not in bot_config.ALLOWED_USERS and ctx.channel.id != bot_config.COMMAND_CHANNEL_ID:
            await ctx.send(f"All commands (including !{func.__name__}) should be used in <#{bot_config.COMMAND_CHANNEL_ID}>")
            return
        return await func(ctx, *args, **kwargs)
    return wrapper

#########################################
# Bot Event Handlers and Commands
#########################################

@bot.event
async def on_ready() -> None:
    logging.info(f"Bot is online as {bot.user}")
    load_state()
    periodic_state_save.start()
    try:
        init_selenium()
        periodic_help_menu.start()
        timeout_unauthorized_users.start()
        check_voice_connection.start()
        guild = bot.get_guild(bot_config.GUILD_ID)
        if guild:
            streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
            if streaming_vc:
                for member in streaming_vc.members:
                    # Exclude allowed users and the designated MUSIC_BOT from moderation
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
        logging.error(f"Error during on_ready setup: {e}")
    if bot_config.ENABLE_GLOBAL_HOTKEY:
        def hotkey_callback() -> None:
            logging.info("Global hotkey pressed, triggering skip command.")
            asyncio.run_coroutine_threadsafe(global_skip(), bot.loop)
        keyboard.add_hotkey(bot_config.GLOBAL_HOTKEY_COMBINATION, hotkey_callback)
        logging.info(f"Global hotkey {bot_config.GLOBAL_HOTKEY_COMBINATION} registered for !skip command.")

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
        # New: If an allowed user in the Streaming VC gets server muted or deafened, immediately revert it.
        if after.channel and after.channel.id == bot_config.STREAMING_VC_ID and member.id in bot_config.ALLOWED_USERS:
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
        if member.id not in state.user_last_join:
            state.user_last_join[member.id] = False
        if after.channel and after.channel.id == bot_config.STREAMING_VC_ID:
            if not state.user_last_join[member.id]:
                state.user_last_join[member.id] = True
                logging.info(f"{member.name} joined Streaming VC at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
            if member.id not in state.users_received_rules:
                try:
                    if member.id not in state.users_with_dms_disabled:
                        await member.send(bot_config.RULES_MESSAGE)
                        state.users_received_rules.add(member.id)
                        logging.info(f"Sent rules to {member.name}.")
                except discord.Forbidden:
                    state.users_with_dms_disabled.add(member.id)
                    logging.warning(f"Could not send DM to {member.name} (DMs disabled).")
                except discord.HTTPException as e:
                    logging.error(f"Failed to send DM to {member.name}: {e}")
            # Exempt allowed users and the designated MUSIC_BOT from moderation
            if member.id not in bot_config.ALLOWED_USERS and member.id != bot_config.MUSIC_BOT and state.vc_moderation_active and not bot_config.VC_MODERATION_PERMANENTLY_DISABLED:
                if not (after.self_video):
                    if member.voice and (not member.voice.mute or not member.voice.deaf):
                        try:
                            await member.edit(mute=True, deafen=True)
                            logging.info(f"Auto-muted and deafened {member.name} for camera off.")
                        except Exception as e:
                            logging.error(f"Failed to auto mute/deafen {member.name}: {e}")
                    state.camera_off_timers[member.id] = time.time()
                else:
                    if not state.hush_override_active:
                        if member.voice and (member.voice.mute or member.voice.deaf):
                            try:
                                await member.edit(mute=False, deafen=False)
                                logging.info(f"Auto-unmuted {member.name} after camera on.")
                            except Exception as e:
                                logging.error(f"Failed to auto unmute/undeafen {member.name}: {e}")
                    else:
                        logging.info(f"Hush override active; leaving {member.name} muted/deafened.")
                    state.camera_off_timers.pop(member.id, None)
        elif before.channel and before.channel.id == bot_config.STREAMING_VC_ID:
            if state.user_last_join.get(member.id, False):
                state.user_last_join[member.id] = False
                logging.info(f"{member.name} left Streaming VC at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
            state.camera_off_timers.pop(member.id, None)
    except Exception as e:
        logging.error(f"Error in on_voice_state_update: {e}")

@bot.event
async def on_member_join(member: discord.Member) -> None:
    """
    Welcomes new members with an embed message in the chat channel.
    """
    try:
        guild = member.guild
        if guild.id == bot_config.GUILD_ID:
            chat_channel = guild.get_channel(bot_config.CHAT_CHANNEL_ID)
            if chat_channel:
                avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
                embed = discord.Embed(color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
                embed.set_author(name=member.name, icon_url=avatar_url)
                embed.description = f"Welcome <@{member.id}>"
                embed.set_thumbnail(url=avatar_url)
                user = await bot.fetch_user(member.id)
                if getattr(user, "banner", None):
                    embed.set_image(url=user.banner.url)
                embed.add_field(name="Discord Age", value=get_discord_age(member.created_at), inline=True)
                embed.add_field(name="Join Order", value=f"{ordinal(guild.member_count)} to join", inline=True)
                await chat_channel.send(embed=embed)
            logging.info(f"{member.name} joined the server at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
        state.recent_joins.append((member.id, member.name, member.nick, datetime.now(timezone.utc)))
    except Exception as e:
        logging.error(f"Error in on_member_join: {e}")

@bot.event
async def on_member_remove(member: discord.Member) -> None:
    """
    Logs departures by sending an embed message in the chat channel.
    """
    try:
        guild = member.guild
        if guild.id == bot_config.GUILD_ID:
            chat_channel = guild.get_channel(bot_config.CHAT_CHANNEL_ID)
            if chat_channel:
                join_time = member.joined_at or datetime.now(timezone.utc)
                duration = datetime.now(timezone.utc) - join_time
                duration_str = f"{duration.days}d {duration.seconds//3600}h {(duration.seconds%3600)//60}m {duration.seconds%60}s"
                avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
                embed = discord.Embed(color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
                embed.set_author(name=member.name, icon_url=avatar_url)
                embed.description = f"<@{member.id}> left the server"
                embed.set_thumbnail(url=avatar_url)
                embed.add_field(name="Time in Server", value=duration_str, inline=True)
                roles = [role.name for role in member.roles if role.name != "@everyone"]
                embed.add_field(name="Roles", value=", ".join(roles) if roles else "None", inline=True)
                await chat_channel.send(embed=embed)
            logging.info(f"{member.name} left the server at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
        state.recent_leaves.append((member.id, member.name, member.nick, datetime.now(timezone.utc)))
    except Exception as e:
        logging.error(f"Error in on_member_remove: {e}")

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    """
    Posts a message when a user's roles change by calling the helper function from tools.py.
    The embed includes the user's mention, profile picture, banner (if available),
    basic server info, and the roles that were gained or lost.
    """
    try:
        if before.roles == after.roles:
            return  # No role changes detected.
        roles_gained = [role for role in after.roles if role not in before.roles and role.name != "@everyone"]
        roles_lost = [role for role in before.roles if role not in after.roles and role.name != "@everyone"]
        if not roles_gained and not roles_lost:
            return
        channel = after.guild.get_channel(bot_config.CHAT_CHANNEL_ID)
        if channel is None:
            return
        embed = await build_role_update_embed(after, roles_gained, roles_lost)
        await channel.send(embed=embed)
    except Exception as e:
        logging.error(f"Error in on_member_update: {e}")

class HelpView(View):
    """
    A Discord UI view for quick command buttons.
    """
    def __init__(self) -> None:
        super().__init__()
        commands_dict = {
            "Skip": "!skip",
            "Refresh": "!refresh",
            "Pause": "!pause",
            "Start": "!start",
            "Paid": "!paid"
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
            await selenium_custom_skip()
            await play_sound_in_vc(guild, bot_config.SOUND_FILE)
        async def handle_refresh(guild: discord.Guild) -> None:
            await selenium_refresh()
            await asyncio.sleep(3)
            await selenium_custom_skip()
            await play_sound_in_vc(guild, bot_config.SOUND_FILE)
        async def handle_pause(guild: discord.Guild) -> None:
            await selenium_pause()
            await play_sound_in_vc(guild, bot_config.SOUND_FILE)
        async def handle_start(guild: discord.Guild) -> None:
            await selenium_start()
            await play_sound_in_vc(guild, bot_config.SOUND_FILE)
        async def handle_paid(guild: discord.Guild) -> None:
            await selenium_paid()
            await asyncio.sleep(1)
            await selenium_custom_skip()
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
        await ctx.send("You do not have permission to use this command.")
        return
    logging.info(f"Purge command received with count: {count}")
    try:
        deleted = await ctx.channel.purge(limit=count)
        await ctx.send(f"Purged {len(deleted)} messages!", delete_after=5)
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
        help_description = (
            "This controls the Streaming VC Bot!\n\n"
            "**Omegle Commands:**\n"
            "!skip - Skips the omegle\n"
            "!refresh - Refreshes the page\n"
            "!pause - Pauses the stream\n"
            "!start - Starts the stream\n"
            "!paid - Run after unbanned\n\n"
            "**Other Commands:**\n"
            "m!play SongName - Play any song\n"
            "!info - Lists and DMs Server info\n"
            "!rules - Lists and DMs Server rules\n"
            "!owner - Lists Admins and Owners\n"
            "!commands - Lists all commands"
        )
        embed = build_embed("Bot Help Menu", help_description, discord.Color.blue())
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

@tasks.loop(minutes=2)
async def periodic_help_menu() -> None:
    """
    Periodically purges messages and sends the help menu in the command channel.
    """
    try:
        guild = bot.get_guild(bot_config.GUILD_ID)
        if guild:
            command_channel = guild.get_channel(bot_config.COMMAND_CHANNEL_ID)
            if command_channel:
                non_allowed_users = [member for member in guild.members if member.id not in bot_config.ALLOWED_USERS]
                if non_allowed_users:
                    try:
                        await command_channel.send("Purging messages...")
                        await purge_messages(command_channel)
                        await asyncio.sleep(1)
                        await send_help_menu(command_channel)
                    except Exception as e:
                        logging.error(f"Failed to send help menu: {e}")
    except Exception as e:
        logging.error(f"Error in periodic_help_menu: {e}")

async def purge_messages(channel: discord.TextChannel, limit: int = 5000) -> None:
    """
    Purges messages from the given channel up to the specified limit.
    """
    try:
        deleted = await channel.purge(limit=limit)
        await channel.send(f"Purged {len(deleted)} messages!", delete_after=5)
        logging.info(f"Purged {len(deleted)} messages.")
    except Exception as e:
        logging.error(f"Failed to purge messages: {e}")

@bot.command(name='rtimeouts')
@handle_errors
async def remove_timeouts(ctx) -> None:
    """
    Removes timeouts from all members and reports which users had timeouts removed.
    """
    if not (ctx.author.id in bot_config.ALLOWED_USERS or any(role.name in bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles)):
        await ctx.send("You do not have permission to use this command.")
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
        await ctx.send("You do not have permission to use this command.")
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
        await ctx.send("You do not have permission to use this command.")
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
        await ctx.send("You do not have permission to use this command.")
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
        await ctx.send("You do not have permission to use this command.")
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
    if not (ctx.author.id in bot_config.ALLOWED_USERS or any(role.name in bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles)):
        await ctx.send("You do not have permission to use this command.")
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

# --- New Admin/Owner Command ---
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
    owners_text = "\n".join(owners_list) if owners_list else "No owners found."
    admins_text = "\n".join(admins_list) if admins_list else "No admins found."
    embed_owners = discord.Embed(title="Owners", description=owners_text, color=discord.Color.gold())
    embed_admins = discord.Embed(title="Admins", description=admins_text, color=discord.Color.red())
    await ctx.send(embed=embed_owners)
    await ctx.send(embed=embed_admins)

# --- Modified !commands Command (with require_command_channel) ---
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
        "**!refresh** - Refreshes page (fix disconnected).\n"
        "**!pause** - Pauses Omegle temporarily.\n"
        "**!start** - Re-initiates Omegle by skipping.\n"
        "**!paid** - Redirects after someone pays for unban.\n"
        "**!help** - Displays Omegle controls with buttons.\n"
        "**!rules** - Lists and DMs Server rules.\n"
        "**!admin** - Lists Admins and Owners.\n"
        "**!owner** - Lists Admins and Owners.\n"
        "**!info** - Lists and DMs Server info.\n"
        "**!about** - Lists and DMs Server info.\n"
        "**!commands** - Full list of all bot commands.\n"
        "**m!play <song or url>** - Plays Music Bot."
    )
    admin_commands = (
        "**!stats** - Shows command usage statistics.\n"
        "**!whois** - Lists timed out, recently left, and joined members.\n"
        "**!rtimeouts** - Removes timeouts from ALL members.\n"
        "**!join** - Sends a join invite DM to admin role members.\n"
        "**!top** - Lists the top 5 oldest Discord accounts."
    )
    allowed_commands = (
        "**!purge [number]** - Purges messages from the channel.\n"
        "**!roles** - Lists roles and their members.\n"
        "**!hush** - Server mutes everyone in the Streaming VC.\n"
        "**!secret** - Server mutes + deafens everyone in Streaming VC.\n"
        "**!rhush** - Removes mute status from everyone in Streaming VC.\n"
        "**!rsecret** - Removes mute and deafen statuses from Streaming VC.\n"
        "**!modoff** - Temporarily disables VC moderation for non-allowed users.\n"
        "**!modon** - Re-enables VC moderation after it has been disabled."
    )
    user_embed = build_embed("User Commands (Anyone in VC with Cam on)", user_commands, discord.Color.blue())
    admin_embed = build_embed("Admin/Allowed Commands", admin_commands, discord.Color.red())
    allowed_embed = build_embed("Allowed Users Only Commands", allowed_commands, discord.Color.gold())
    await ctx.send(embed=user_embed)
    await ctx.send(embed=admin_embed)
    await ctx.send(embed=allowed_embed)

@bot.command(name='whois')
@require_command_channel
@handle_errors
async def whois(ctx) -> None:
    """
    Displays a report with timed out members, recent joins, and recent leaves.
    """
    allowed = (ctx.author.id in bot_config.ALLOWED_USERS or 
               any(role.name in bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles))
    if not allowed:
        await ctx.send("You do not have permission to use this command.")
        return
    record_command_usage(state.analytics, "!whois")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!whois")
    def format_member(member_id: int, username: str, nickname: str) -> str:
        return f"<@{member_id}>"
    timed_out_members = [member for member in ctx.guild.members if member.is_timed_out()]
    timed_out_list = [format_member(member.id, member.name, member.nick) for member in timed_out_members]
    report1 = "Timed Out Members Report:\n" + ("\n".join(timed_out_list) if timed_out_list else "No members are currently timed out.")
    await ctx.send(report1)
    now = datetime.now(timezone.utc)
    join_list = [format_member(entry[0], entry[1], entry[2])
                 for entry in state.recent_joins if now - entry[3] <= timedelta(hours=24)]
    report2 = "Recent Joins (last 24 hours):\n" + ("\n".join(join_list) if join_list else "No members joined in the last 24 hours.")
    await ctx.send(report2)
    leave_list = [format_member(entry[0], entry[1], entry[2])
                  for entry in state.recent_leaves if now - entry[3] <= timedelta(hours=24)]
    report3 = "Recent Leaves (last 24 hours):\n" + ("\n".join(leave_list) if leave_list else "No members left in the last 24 hours.")
    await ctx.send(report3)

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
            members = "\n".join([member.mention for member in role.members])
            await ctx.send(f"**Role: {role.name}**\n{members}")

@bot.command(name='top')
@require_command_channel
@handle_errors
async def top(ctx) -> None:
    """
    Lists the top 5 oldest Discord accounts (excluding bots).
    """
    if not (ctx.author.id in bot_config.ALLOWED_USERS or any(role.name in bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles)):
        await ctx.send("You do not have permission to use this command.")
        return
    record_command_usage(state.analytics, "!top")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!top")
    human_members = [member for member in ctx.guild.members if not member.bot and member.joined_at]
    if not human_members:
        await ctx.send("No human members found.")
        return
    sorted_by_account = sorted(human_members, key=lambda m: m.created_at)
    top_members = sorted_by_account[:5]
    sorted_by_join = sorted(human_members, key=lambda m: m.joined_at)
    join_order_dict = {member.id: ordinal(idx + 1) for idx, member in enumerate(sorted_by_join)}
    embed_list = []
    for idx, member in enumerate(top_members, start=1):
        avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
        join_order = join_order_dict.get(member.id, "N/A")
        join_date = member.joined_at.strftime('%Y-%m-%d') if member.joined_at else "Unknown"
        discord_age = get_discord_age(member.created_at)
        try:
            user = await bot.fetch_user(member.id)
            banner_url = user.banner.url if getattr(user, "banner", None) else None
        except Exception as e:
            logging.error(f"Error fetching user for banner: {e}")
            banner_url = None
        embed = discord.Embed(
            title=f"{idx}. {member.display_name}",
            description=(f"<@{member.id}>\n"
                         f"**Discord Age:** {discord_age}\n"
                         f"**Joined on:** {join_date}\n"
                         f"**Join Order:** {join_order} to join"),
            color=discord.Color.blue(),
            timestamp=member.joined_at or datetime.now(timezone.utc)
        )
        embed.set_author(name=member.display_name, icon_url=avatar_url)
        embed.set_thumbnail(url=avatar_url)
        if banner_url:
            embed.set_image(url=banner_url)
        embed_list.append(embed)
    await ctx.send(embeds=embed_list)

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
        await ctx.send("You do not have permission to use this command.")
        return
    if bot_config.VC_MODERATION_PERMANENTLY_DISABLED:
        await ctx.send("VC Moderation is permanently disabled via config.")
        return
    state.vc_moderation_active = True
    await ctx.send("VC moderation has been re-enabled (modon).")

@bot.command(name='stats')
@require_command_channel
@handle_errors
async def analytics_report(ctx) -> None:
    """
    Sends a report showing command usage statistics and violation events.
    """
    if ctx.author.id not in bot_config.ALLOWED_USERS and not any(role.name in bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles):
        await ctx.send("You do not have permission to use this command.")
        return
    record_command_usage(state.analytics, "!stats")
    record_command_usage_by_user(state.analytics, ctx.author.id, "stats")
    overall_report = "**Report**\n**Overall Command Usage:**\n"
    if state.analytics["command_usage"]:
        for cmd, count in state.analytics["command_usage"].items():
            overall_report += f"`{cmd}`: {count} times\n"
    else:
        overall_report += "No commands used.\n"
    usage_by_user_report = "**Command Usage by User:**\n"
    if state.analytics["command_usage_by_user"]:
        sorted_users = sorted(state.analytics["command_usage_by_user"].items(), key=lambda item: item[1].get("!skip", 0), reverse=True)
        for user_id, commands in sorted_users:
            usage_details = ", ".join([f"{cmd}: {cnt}" for cmd, cnt in commands.items()])
            usage_by_user_report += f"<@{user_id}>: {usage_details}\n"
    else:
        usage_by_user_report += "No command usage recorded.\n"
    violations_report = "**Violations by User:**\n"
    if state.user_violations:
        sorted_violations = sorted(state.user_violations.items(), key=lambda item: item[1], reverse=True)
        for user_id, violation_count in sorted_violations:
            violations_report += f"<@{user_id}>: {violation_count} violation(s)\n"
    else:
        violations_report += "No violations recorded.\n"
    await ctx.send(overall_report)
    await ctx.send(usage_by_user_report)
    await ctx.send(violations_report)

# --- New !rules Command ---
@bot.command(name='rules')
@require_command_channel
@handle_errors
async def rules(ctx) -> None:
    """
    Lists the server rules in the channel and DMs them to the user.
    """
    record_command_usage(state.analytics, "!rules")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!rules")
    # List the rules in the current channel
    await ctx.send(bot_config.RULES_MESSAGE)
    try:
        # DM the rules to the user
        await ctx.author.send(bot_config.RULES_MESSAGE)
        await ctx.send("I also sent you the rules in DM!")
    except discord.Forbidden:
        await ctx.send("Rules listed above, but couldn't DM you the rules (check your DM settings).")

async def send_info(ctx) -> None:
    """
    Sends info messages (from configuration) in both the channel and via DM.
    """
    for info_message in bot_config.INFO_MESSAGES:
        try:
            await ctx.send(info_message)
        except Exception as e:
            logging.error(f"Error sending info message in channel: {e}")
    for info_message in bot_config.INFO_MESSAGES:
        try:
            await ctx.author.send(info_message)
        except discord.Forbidden:
            logging.warning(f"Could not send DM to {ctx.author.name} (DMs disabled).")
        except Exception as e:
            logging.error(f"Error sending DM for info message: {e}")

@bot.command(name='info')
@require_command_channel
@handle_errors
async def info(ctx) -> None:
    """
    Sends the info messages in both the channel and via DM.
    """
    record_command_usage(state.analytics, "!info")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!info")
    await send_info(ctx)

@bot.command(name='about')
@require_command_channel
@handle_errors
async def about(ctx) -> None:
    """
    Sends the same info messages as !info in both the channel and via DM.
    """
    record_command_usage(state.analytics, "!about")
    record_command_usage_by_user(state.analytics, ctx.author.id, "!about")
    await send_info(ctx)

# --- Moderation Loop: Check for Camera-Off Violations ---
@tasks.loop(seconds=10)
@handle_errors
async def timeout_unauthorized_users() -> None:
    """
    Periodically checks for users in the Streaming VC without an active camera
    and issues violations accordingly.
    """
    if bot_config.VC_MODERATION_PERMANENTLY_DISABLED or not state.vc_moderation_active:
        return
    guild = bot.get_guild(bot_config.GUILD_ID)
    if guild:
        streaming_vc = guild.get_channel(bot_config.STREAMING_VC_ID)
        hell_vc = guild.get_channel(bot_config.HELL_VC_ID)
        if streaming_vc and hell_vc:
            for member in streaming_vc.members:
                if member.bot:
                    continue
                # Exclude allowed users and MUSIC_BOT from enforcement
                if member.id not in bot_config.ALLOWED_USERS and member.id != bot_config.MUSIC_BOT:
                    if not (member.voice and member.voice.self_video):
                        if member.id in state.camera_off_timers:
                            if time.time() - state.camera_off_timers[member.id] >= bot_config.CAMERA_OFF_ALLOWED_TIME:
                                state.analytics["violation_events"] += 1
                                state.user_violations[member.id] = state.user_violations.get(member.id, 0) + 1
                                violation_count = state.user_violations[member.id]
                                try:
                                    if violation_count == 1:
                                        await member.move_to(hell_vc, reason="No camera detected in Streaming VC.")
                                        logging.info(f"Moved {member.name} to Hell VC.")
                                        try:
                                            if member.id not in state.users_with_dms_disabled:
                                                await member.send("You have been moved to Hell VC because you did not have your camera on in Streaming VC.")
                                        except discord.Forbidden:
                                            state.users_with_dms_disabled.add(member.id)
                                            logging.warning(f"Could not send DM to {member.name} (DMs disabled).")
                                        except discord.HTTPException as e:
                                            logging.error(f"Failed to send DM to {member.name}: {e}")
                                    elif violation_count == 2:
                                        timeout_duration = bot_config.TIMEOUT_DURATION_SECOND_VIOLATION
                                        await member.timeout(timedelta(seconds=timeout_duration), reason="Repeated violations of camera policy.")
                                        logging.info(f"Timed out {member.name} for {timeout_duration} seconds.")
                                        state.active_timeouts[member.id] = {
                                            "timeout_end": time.time() + timeout_duration,
                                            "reason": "Repeated violations of camera policy (2nd offense).",
                                            "timed_by": "AutoMod - Camera Enforcer",
                                            "start_timestamp": time.time()
                                        }
                                        try:
                                            if member.id not in state.users_with_dms_disabled:
                                                await member.send(f"You have been timed out for {timeout_duration} seconds - Must have camera on while in the Streaming VC.")
                                        except discord.Forbidden:
                                            state.users_with_dms_disabled.add(member.id)
                                            logging.warning(f"Could not send DM to {member.name} (DMs disabled).")
                                        except discord.HTTPException as e:
                                            logging.error(f"Failed to send DM to {member.name}: {e}")
                                    else:
                                        timeout_duration = bot_config.TIMEOUT_DURATION_THIRD_VIOLATION
                                        await member.timeout(timedelta(seconds=timeout_duration), reason="Repeated violations of camera policy.")
                                        logging.info(f"Timed out {member.name} for {timeout_duration} seconds.")
                                        state.active_timeouts[member.id] = {
                                            "timeout_end": time.time() + timeout_duration,
                                            "reason": "Repeated violations of camera policy (3rd+ offense).",
                                            "timed_by": "AutoMod - Camera Enforcer",
                                            "start_timestamp": time.time()
                                        }
                                        try:
                                            if member.id not in state.users_with_dms_disabled:
                                                await member.send(f"You have been timed out for {timeout_duration} seconds - Must have camera on while in the Streaming VC.")
                                        except discord.Forbidden:
                                            state.users_with_dms_disabled.add(member.id)
                                            logging.warning(f"Could not send DM to {member.name} (DMs disabled).")
                                        except discord.HTTPException as e:
                                            logging.error(f"Failed to send DM to {member.name}: {e}")
                                    state.camera_off_timers.pop(member.id, None)
                                except discord.Forbidden:
                                    logging.warning(f"Missing permissions to move or timeout {member.name}.")
                                except discord.HTTPException as e:
                                    logging.error(f"Failed to move or timeout {member.name}: {e}")
                    else:
                        state.camera_off_timers.pop(member.id, None)
                else:
                    state.camera_off_timers.pop(member.id, None)

if __name__ == "__main__":
    try:
        bot.run(os.getenv("BOT_TOKEN"))
    except Exception as e:
        logging.error(f"Bot crashed: {e}")
