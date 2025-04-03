#!/usr/bin/env python

import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import asyncio
from datetime import timedelta, datetime, timezone
import logging
import time
import os
import sys
import subprocess
from dotenv import load_dotenv
import keyboard  # Global hotkey support

# Selenium imports for browser automation
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager

# Load environment variables from .env file (ensure BOT_TOKEN is defined there)
load_dotenv()

# Import configuration settings (make sure config.py is sanitized)
import config

# Initialize bot with necessary intents and disable the default help command.
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", help_command=None, intents=intents)

# Logging setup: logs both to file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

# Helper function to get ordinal number (e.g. 1st, 2nd, 3rd, etc.)
def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return str(n) + suffix

def get_discord_age(created_at: datetime) -> str:
    """
    Returns a string representing how long ago the account was created,
    expressed in years, months, and days.
    """
    now = datetime.now(timezone.utc)
    delta = now - created_at
    years = delta.days // 365
    months = (delta.days % 365) // 30
    days = (delta.days % 365) % 30
    parts = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if not parts:  # Account created less than a day ago
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        if hours:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return ", ".join(parts) if parts else "Just now"

# Global variables used across the bot
voice_client = None
driver = None
cooldowns = {}             # Command cooldown tracking for users
button_cooldowns = {}      # Cooldown tracking for button interactions
camera_off_timers = {}     # Tracks when users turn their camera off
user_violations = {}       # Counts camera policy violations per user
users_received_rules = set()       # Tracks users who have received the rules DM
users_with_dms_disabled = set()    # Tracks users who have DMs disabled
active_timeouts = {}       # Stores active timeout information for users
user_last_join = {}        # Tracks whether a user is in the streaming VC

vc_moderation_active = True    # Flag to indicate if VC moderation is active
hush_override_active = False   # Flag for hush override state

recent_joins = []    # List to record recent joins to the VC
recent_leaves = []   # List to record recent leaves from the VC

# --- New Analytics Tracking ---
analytics = {
    "command_usage": {},
    "command_usage_by_user": {},  # Records per-user command usage
    "violation_events": 0
}

def record_command_usage(command_name: str):
    analytics["command_usage"][command_name] = analytics["command_usage"].get(command_name, 0) + 1

def record_command_usage_by_user(user_id: int, command_name: str):
    if user_id not in analytics["command_usage_by_user"]:
        analytics["command_usage_by_user"][user_id] = {}
    analytics["command_usage_by_user"][user_id][command_name] = analytics["command_usage_by_user"][user_id].get(command_name, 0) + 1
# --- End Analytics Tracking ---

def init_selenium():
    """
    Initializes the Selenium WebDriver using Microsoft Edge.
    Opens the OMEGLE_VIDEO_URL page as specified in the configuration.
    """
    global driver
    try:
        service = EdgeService(EdgeChromiumDriverManager().install())
        options = webdriver.EdgeOptions()
        options.add_argument(f"user-data-dir={config.EDGE_USER_DATA_DIR}")
        driver = webdriver.Edge(service=service, options=options)
        driver.maximize_window()
        driver.get(config.OMEGLE_VIDEO_URL)
        logging.info("Selenium: Opened OMEGLE_VIDEO_URL page.")
    except Exception as e:
        logging.error(f"Failed to initialize Selenium driver: {e}")
        driver = None

async def selenium_custom_skip():
    """
    Sends customizable skip key events to the page based on config.SKIP_COMMAND_KEY.
    If multiple keys are specified, each is sent sequentially with a 1 second delay.
    """
    if driver is None:
        logging.error("Selenium driver not initialized; cannot skip.")
        return
    keys = getattr(config, "SKIP_COMMAND_KEY", ["Escape"])
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
            driver.execute_script(script)
            logging.info(f"Selenium: Sent {key} key event to page.")
            if i < len(keys) - 1:
                await asyncio.sleep(1)
    except Exception as e:
        logging.error(f"Selenium custom skip failed: {e}")

async def selenium_refresh():
    """
    Refreshes the current page in the Selenium browser.
    If the refresh fails, attempts to quit and reinitialize the driver.
    """
    global driver
    if driver is None:
        logging.error("Selenium driver not initialized; attempting to reinitialize.")
        init_selenium()
        return
    try:
        driver.refresh()
        logging.info("Selenium: Page refreshed.")
    except Exception as e:
        logging.error(f"Selenium refresh failed: {e}. Attempting to reinitialize the driver.")
        try:
            driver.quit()
        except Exception as ex:
            logging.error(f"Error quitting driver: {ex}")
        driver = None
        init_selenium()

async def selenium_start():
    """
    Starts the stream by navigating to the OMEGLE_VIDEO_URL page and triggering a skip.
    """
    if driver is None:
        logging.error("Selenium driver not initialized; cannot start.")
        return
    try:
        driver.get(config.OMEGLE_VIDEO_URL)
        logging.info("Selenium: Navigated to OMEGLE_VIDEO_URL page for start.")
        await asyncio.sleep(3)
        await selenium_custom_skip()
    except Exception as e:
        logging.error(f"Selenium start failed: {e}")

async def selenium_pause():
    """
    Pauses the stream by refreshing the page.
    """
    if driver is None:
        logging.error("Selenium driver not initialized; cannot pause.")
        return
    try:
        driver.refresh()
        logging.info("Selenium: Performed refresh for pause command.")
    except Exception as e:
        logging.error(f"Selenium pause failed: {e}")

async def selenium_paid():
    """
    Handles the 'paid' command by navigating to the OMEGLE_VIDEO_URL page.
    """
    if driver is None:
        logging.error("Selenium driver not initialized; cannot process paid command.")
        return
    try:
        driver.get(config.OMEGLE_VIDEO_URL)
        logging.info("Selenium: Navigated to OMEGLE_VIDEO_URL page for paid command.")
    except Exception as e:
        logging.error(f"Selenium paid failed: {e}")

async def play_sound_in_vc(guild: discord.Guild, sound_file: str):
    """
    Connects to the Streaming VC and plays the specified sound file.
    If already connected, uses the existing connection.
    """
    global voice_client
    try:
        await asyncio.sleep(2)
        streaming_vc = guild.get_channel(config.STREAMING_VC_ID)
        if streaming_vc:
            if voice_client is None or not voice_client.is_connected():
                try:
                    voice_client = await streaming_vc.connect()
                except discord.ClientException as e:
                    if "already connected" in str(e).lower():
                        logging.info("Already connected to voice channel.")
                    else:
                        raise
            voice_client.play(discord.FFmpegPCMAudio(executable="ffmpeg", source=sound_file))
            while voice_client.is_playing():
                await asyncio.sleep(1)
    except Exception as e:
        logging.error(f"Failed to play sound in VC: {e}")

async def disconnect_from_vc():
    """
    Disconnects the bot from the voice channel.
    """
    global voice_client
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        voice_client = None

def is_user_in_streaming_vc_with_camera(user: discord.Member) -> bool:
    """
    Checks if the user is in the Streaming VC and has their camera turned on.
    Returns True if the camera is on.
    """
    streaming_vc = user.guild.get_channel(config.STREAMING_VC_ID)
    if streaming_vc and user in streaming_vc.members:
        if user.voice and user.voice.self_video:
            return True
    return False

async def global_skip():
    """
    Executes a global skip command, triggered via a global hotkey.
    """
    guild = bot.get_guild(config.GUILD_ID)
    if guild:
        await selenium_custom_skip()
        await play_sound_in_vc(guild, config.SOUND_FILE)
        logging.info("Executed global skip command via global hotkey.")
    else:
        logging.error("Guild not found for global skip.")

async def ensure_voice_connection():
    """
    Checks if the bot's voice client is connected. If not, attempts to reconnect.
    If already connected, logs that status.
    """
    global voice_client
    guild = bot.get_guild(config.GUILD_ID)
    if not guild:
        logging.error("Guild not found in ensure_voice_connection.")
        return
    streaming_vc = guild.get_channel(config.STREAMING_VC_ID)
    if streaming_vc:
        if voice_client is None or not voice_client.is_connected():
            try:
                voice_client = await streaming_vc.connect()
                logging.info("Reconnected to voice channel.")
            except discord.ClientException as e:
                if "already connected" in str(e).lower():
                    logging.info("Already connected to voice channel.")
                else:
                    logging.error(f"Failed to reconnect to voice: {e}")

@tasks.loop(seconds=30)
async def check_voice_connection():
    """
    Periodic task to ensure the voice connection is active.
    """
    await ensure_voice_connection()

@bot.event
async def on_ready():
    """
    Called when the bot is ready and connected.
    Initializes Selenium, starts periodic tasks, and registers the global hotkey.
    """
    logging.info(f"Bot is online as {bot.user}")
    try:
        init_selenium()
        periodic_help_menu.start()
        timeout_unauthorized_users.start()
        check_voice_connection.start()
        guild = bot.get_guild(config.GUILD_ID)
        if guild:
            streaming_vc = guild.get_channel(config.STREAMING_VC_ID)
            if streaming_vc:
                for member in streaming_vc.members:
                    if not member.bot and member.id not in config.ALLOWED_USERS:
                        if not (member.voice and member.voice.self_video):
                            try:
                                if not config.VC_MODERATION_PERMANENTLY_DISABLED and vc_moderation_active:
                                    await member.edit(mute=True, deafen=True)
                                    logging.info(f"Auto-muted and deafened {member.name} on join due to camera off.")
                            except Exception as e:
                                logging.error(f"Failed to auto mute/deafen {member.name}: {e}")
                            camera_off_timers[member.id] = time.time()
    except Exception as e:
        logging.error(f"Error during on_ready setup: {e}")
    if config.ENABLE_GLOBAL_HOTKEY:
        def hotkey_callback():
            logging.info("Global hotkey pressed, triggering skip command.")
            asyncio.run_coroutine_threadsafe(global_skip(), bot.loop)
        keyboard.add_hotkey(config.GLOBAL_HOTKEY_COMBINATION, hotkey_callback)
        logging.info(f"Global hotkey {config.GLOBAL_HOTKEY_COMBINATION} registered for !skip command.")

@bot.event
async def on_voice_state_update(member, before, after):
    """
    Handles voice state updates for members.
    Manages camera checks, auto-muting, and recording join/leave times.
    """
    try:
        if member == bot.user:
            return
        streaming_vc = member.guild.get_channel(config.STREAMING_VC_ID)
        if member.id not in user_last_join:
            user_last_join[member.id] = False
        if after.channel and after.channel.id == config.STREAMING_VC_ID:
            if not user_last_join[member.id]:
                user_last_join[member.id] = True
                logging.info(f"{member.name} joined the Streaming VC at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
            if member.id not in users_received_rules:
                try:
                    if member.id not in users_with_dms_disabled:
                        await member.send(config.RULES_MESSAGE)
                        users_received_rules.add(member.id)
                        logging.info(f"Sent rules to {member.name}.")
                except discord.Forbidden:
                    users_with_dms_disabled.add(member.id)
                    logging.warning(f"Could not send DM to {member.name} (DMs disabled?).")
                except discord.HTTPException as e:
                    logging.error(f"Failed to send DM to {member.name}: {e}")
            if member.id not in config.ALLOWED_USERS and vc_moderation_active and not config.VC_MODERATION_PERMANENTLY_DISABLED:
                if not (after.self_video):
                    if member.voice and (not member.voice.mute or not member.voice.deaf):
                        try:
                            await member.edit(mute=True, deafen=True)
                            logging.info(f"Auto-muted and deafened {member.name} for having camera off.")
                        except Exception as e:
                            logging.error(f"Failed to auto mute/deafen {member.name}: {e}")
                    camera_off_timers[member.id] = time.time()
                else:
                    if not hush_override_active:
                        if member.voice and (member.voice.mute or member.voice.deaf):
                            try:
                                await member.edit(mute=False, deafen=False)
                                logging.info(f"Auto-unmuted and undeafened {member.name} after turning camera on.")
                            except Exception as e:
                                logging.error(f"Failed to auto unmute/undeafened {member.name}: {e}")
                    else:
                        logging.info(f"Hush override active; leaving {member.name} muted/deafened despite camera on.")
                    camera_off_timers.pop(member.id, None)
        elif before.channel and before.channel.id == config.STREAMING_VC_ID:
            if user_last_join.get(member.id, False):
                user_last_join[member.id] = False
                logging.info(f"{member.name} left the Streaming VC at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
            camera_off_timers.pop(member.id, None)
    except Exception as e:
        logging.error(f"Error in on_voice_state_update: {e}")

@bot.event
async def on_member_join(member):
    """
    Welcomes a new member to the server by sending an embed message in the chat channel.
    """
    try:
        guild = member.guild
        if guild.id == config.GUILD_ID:
            chat_channel = guild.get_channel(config.CHAT_CHANNEL_ID)
            if chat_channel:
                embed = discord.Embed(
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
                embed.set_author(name=f"{member.name}", icon_url=avatar_url)
                embed.description = f"Welcome <@{member.id}>"
                embed.set_thumbnail(url=avatar_url)
                user = await bot.fetch_user(member.id)
                if user.banner:
                    embed.set_image(url=user.banner.url)
                discord_age = get_discord_age(member.created_at)
                embed.add_field(name="Discord Age", value=discord_age, inline=True)
                join_order = ordinal(guild.member_count)
                embed.add_field(name="Join Order", value=f"{join_order} to join", inline=True)
                await chat_channel.send(embed=embed)
            logging.info(f"{member.name} joined the server at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
        global recent_joins
        recent_joins.append((member.id, member.name, member.nick, datetime.now(timezone.utc)))
    except Exception as e:
        logging.error(f"Error in on_member_join: {e}")

@bot.event
async def on_member_remove(member):
    """
    Logs when a member leaves the server by sending an embed message in the chat channel.
    """
    try:
        guild = member.guild
        if guild.id == config.GUILD_ID:
            chat_channel = guild.get_channel(config.CHAT_CHANNEL_ID)
            if chat_channel:
                join_time = member.joined_at or datetime.now(timezone.utc)
                duration = datetime.now(timezone.utc) - join_time
                days = duration.days
                hours, remainder = divmod(duration.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                duration_str = f"{days}d {hours}h {minutes}m {seconds}s"
                embed = discord.Embed(
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
                embed.set_author(name=f"{member.name}", icon_url=avatar_url)
                embed.description = f"<@{member.id}> left the server"
                embed.set_thumbnail(url=avatar_url)
                embed.add_field(name="Time in Server", value=duration_str, inline=True)
                roles = [role.name for role in member.roles if role.name != "@everyone"]
                roles_str = ", ".join(roles) if roles else "None"
                embed.add_field(name="Roles", value=roles_str, inline=True)
                await chat_channel.send(embed=embed)
            logging.info(f"{member.name} left the server at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
        global recent_leaves
        recent_leaves.append((member.id, member.name, member.nick, datetime.now(timezone.utc)))
    except Exception as e:
        logging.error(f"Error in on_member_remove: {e}")

class HelpView(View):
    """
    A Discord UI view that creates buttons for quick command execution.
    """
    def __init__(self):
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
    def __init__(self, label, command):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.command = command

    async def callback(self, interaction: discord.Interaction):
        """
        Callback function for button click.
        Checks cooldowns and executes the corresponding command.
        """
        try:
            user_id = interaction.user.id
            if user_id not in config.ALLOWED_USERS and interaction.channel.id != config.COMMAND_CHANNEL_ID:
                await interaction.response.send_message(
                    f"All commands (including !help) should be used in https://discord.com/channels/{config.GUILD_ID}/{config.COMMAND_CHANNEL_ID}",
                    ephemeral=True
                )
                return
            current_time = time.time()
            if user_id in button_cooldowns:
                last_used, warned = button_cooldowns[user_id]
                time_left = config.COMMAND_COOLDOWN - (current_time - last_used)
                if time_left > 0:
                    if not warned:
                        await interaction.response.send_message(
                            f"{interaction.user.mention}, wait {int(time_left)}s before using another button.",
                            ephemeral=True
                        )
                        button_cooldowns[user_id] = (last_used, True)
                    return
            button_cooldowns[user_id] = (current_time, False)
            await interaction.response.defer()
            await interaction.channel.send(f"{interaction.user.mention} used {self.command}")
            fake_message = interaction.message
            fake_message.content = self.command
            fake_message.author = interaction.user
            await on_message(fake_message)
        except Exception as e:
            logging.error(f"Error in HelpButton callback: {e}")

@bot.event
async def on_message(message):
    """
    Handles incoming messages and routes commands to appropriate handlers.
    Applies cooldowns and checks permissions before processing commands.
    """
    try:
        if message.author == bot.user or not message.guild:
            return
        if not message.content.startswith("!"):
            return
        if message.guild.id != config.GUILD_ID:
            return

        if message.author.id not in config.ALLOWED_USERS and message.channel.id != config.COMMAND_CHANNEL_ID:
            await message.channel.send(
                f"All commands (including !help) should be used in https://discord.com/channels/{config.GUILD_ID}/{config.COMMAND_CHANNEL_ID}"
            )
            return

        # Special cases: let !top, !analytics, !purge, and !commands be processed by command framework
        if (message.content.lower().startswith("!top") or
            message.content.lower().startswith("!analytics") or
            message.content.lower().startswith("!purge") or
            message.content.lower().startswith("!commands")):
            await bot.process_commands(message)
            return

        # Process mod commands separately
        if (message.content.lower().startswith("!modoff") or 
            message.content.lower().startswith("!modon") or 
            message.content.lower().startswith("!rtimeouts") or 
            message.content.lower().startswith("!hush") or 
            message.content.lower().startswith("!secret") or 
            message.content.lower().startswith("!rhush") or 
            message.content.lower().startswith("!rsecret") or 
            message.content.lower().startswith("!join") or 
            message.content.lower().startswith("!whois") or 
            message.content.lower().startswith("!roles")):
            await bot.process_commands(message)
            return

        # Command processing for allowed users in the designated channel
        user_id = message.author.id
        current_time = time.time()
        if user_id in cooldowns:
            last_used, warned = cooldowns[user_id]
            time_left = config.COMMAND_COOLDOWN - (current_time - last_used)
            if time_left > 0:
                if not warned:
                    await message.channel.send(f"Please wait {int(time_left)} seconds and try again.")
                    cooldowns[user_id] = (last_used, True)
                return
        cooldowns[user_id] = (current_time, False)
        
        # Define command actions mapped to functions
        async def handle_skip(guild):
            await selenium_custom_skip()
            await play_sound_in_vc(guild, config.SOUND_FILE)
        async def handle_refresh(guild):
            await selenium_refresh()
            await asyncio.sleep(3)
            await selenium_custom_skip()
            await play_sound_in_vc(guild, config.SOUND_FILE)
        async def handle_pause(guild):
            await selenium_pause()
            await play_sound_in_vc(guild, config.SOUND_FILE)
        async def handle_start(guild):
            await selenium_start()
            await play_sound_in_vc(guild, config.SOUND_FILE)
        async def handle_paid(guild):
            await selenium_paid()
            await asyncio.sleep(1)
            await selenium_custom_skip()
            await play_sound_in_vc(guild, config.SOUND_FILE)
        
        command_actions = {
            "!skip": lambda: asyncio.create_task(handle_skip(message.guild)),
            "!refresh": lambda: asyncio.create_task(handle_refresh(message.guild)),
            "!pause": lambda: asyncio.create_task(handle_pause(message.guild)),
            "!start": lambda: asyncio.create_task(handle_start(message.guild)),
            "!paid": lambda: asyncio.create_task(handle_paid(message.guild))
        }
        command = message.content.lower()
        handled = False  # flag to indicate manual handling

        if command in command_actions:
            if message.author.id not in config.ALLOWED_USERS and not is_user_in_streaming_vc_with_camera(message.author):
                await message.channel.send("You must be in the Streaming VC with your camera on to use that command.")
                return
            record_command_usage(command)
            record_command_usage_by_user(message.author.id, command)
            await command_actions[command]()
            handled = True

        command_messages = {
            "!skip": "Omegle skipped!",
            "!refresh": "Page refreshed!",
            "!pause": "Stream paused temporarily!",
            "!start": "Stream started!",
            "!paid": "Redirected back to OMEGLE_VIDEO",
            "!help": "Help"
        }
        if command in command_messages:
            if command == "!help":
                await send_help_menu(message)
            else:
                await message.channel.send(command_messages[command])
        
        # Only call process_commands for messages that were not manually handled.
        if not handled:
            await bot.process_commands(message)
        
    except Exception as e:
        logging.error(f"Error in on_message: {e}")

@bot.command(name='purge')
async def purge(ctx, count: int = 5):
    """
    Purges a specified number of messages from the channel.
    """
    if ctx.author.id not in config.ALLOWED_USERS:
        await ctx.send("You do not have permission to use this command.")
        return
    try:
        await ctx.send(f"Purging {count} messages...")
        deleted = await ctx.channel.purge(limit=count)
        await ctx.send(f"Purged {len(deleted)} messages!", delete_after=5)
        logging.info(f"Purged {len(deleted)} messages.")
    except Exception as e:
        logging.error(f"Error in purge command: {e}")

async def send_help_menu(target):
    """
    Sends an embedded help menu with available commands and attaches interactive buttons.
    """
    try:
        embed = discord.Embed(
            title="Bot Help Menu",
            description=( 
                "This controls the Streaming VC Bot!\n\n"
                "**Commands:**\n"
                "!skip - Skips the omegle\n"
                "!refresh - Refreshes the page\n"
                "!pause - Pauses the stream\n"
                "!start - Re-initiates Omegle by skipping.\n"
                "!paid - Redirects after payment (for unban)\n"
                "\nCooldown: 5 seconds per command"
            ),
            color=discord.Color.blue()
        )
        if isinstance(target, discord.Message):
            await target.channel.send(embed=embed, view=HelpView())
        elif isinstance(target, discord.TextChannel):
            await target.send(embed=embed, view=HelpView())
        else:
            raise ValueError("Invalid target type. Expected discord.Message or discord.TextChannel.")
    except Exception as e:
        logging.error(f"Error in send_help_menu: {e}")

async def handle_wrong_channel(message):
    """
    Notifies users when they use a command in the wrong channel.
    """
    try:
        user_id = message.author.id
        current_time = time.time()
        if user_id in cooldowns:
            last_used, warned = cooldowns[user_id]
            time_left = config.COMMAND_COOLDOWN - (current_time - last_used)
            if time_left > 0:
                if not warned:
                    await message.channel.send(f"{message.author.mention}, please wait {int(time_left)} seconds before trying again.")
                    cooldowns[user_id] = (last_used, True)
                return
        await message.channel.send(f"{message.author.mention}, use all commands (including !help) in the command channel.")
        cooldowns[user_id] = (current_time, False)
    except Exception as e:
        logging.error(f"Error in handle_wrong_channel: {e}")

@tasks.loop(minutes=2)
async def periodic_help_menu():
    """
    Periodically purges messages and sends the help menu in the command channel.
    """
    try:
        guild = bot.get_guild(config.GUILD_ID)
        if guild:
            command_channel = guild.get_channel(config.COMMAND_CHANNEL_ID)
            if command_channel:
                non_allowed_users = [member for member in guild.members if member.id not in config.ALLOWED_USERS]
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

async def purge_messages(channel, limit=5000):
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
async def remove_timeouts(ctx):
    """
    Removes timeouts from all members in the guild and reports which users had timeouts removed.
    """
    try:
        if not (ctx.author.id in config.ALLOWED_USERS or any(role.name in config.ADMIN_ROLE_NAME for role in ctx.author.roles)):
            await ctx.send("You do not have permission to use this command.")
            return
        record_command_usage("!rtimeouts")
        record_command_usage_by_user(ctx.author.id, "!rtimeouts")
        
        removed_timeouts = []
        for member in ctx.guild.members:
            if member.is_timed_out():
                try:
                    await member.timeout(None, reason="Timeout removed by allowed user.")
                    removed_timeouts.append(member.name)
                    logging.info(f"Removed timeout from {member.name}.")
                    if member.id in active_timeouts:
                        del active_timeouts[member.id]
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
    except Exception as e:
        logging.error(f"Error in remove_timeouts: {e}")

@bot.command(name='hush')
async def hush(ctx):
    """
    Mutes all users in the Streaming VC (excluding allowed users) to enforce silence.
    """
    global hush_override_active
    hush_override_active = True
    try:
        if ctx.author.id not in config.ALLOWED_USERS:
            await ctx.send("You do not have permission to use this command.")
            return
        guild = ctx.guild
        streaming_vc = guild.get_channel(config.STREAMING_VC_ID)
        if streaming_vc:
            impacted = []
            for member in streaming_vc.members:
                if not member.bot and member.id not in config.ALLOWED_USERS:
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
    except Exception as e:
        logging.error(f"Error in hush command: {e}")

@bot.command(name='secret')
async def secret(ctx):
    """
    Mutes and deafens all users in the Streaming VC (excluding allowed users) for stricter moderation.
    """
    global hush_override_active
    hush_override_active = True
    try:
        if ctx.author.id not in config.ALLOWED_USERS:
            await ctx.send("You do not have permission to use this command.")
            return
        guild = ctx.guild
        streaming_vc = guild.get_channel(config.STREAMING_VC_ID)
        if streaming_vc:
            impacted = []
            for member in streaming_vc.members:
                if not member.bot and member.id not in config.ALLOWED_USERS:
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
    except Exception as e:
        logging.error(f"Error in secret command: {e}")

@bot.command(name='rhush')
async def rhush(ctx):
    """
    Unmutes and undeafens all users in the Streaming VC.
    """
    global hush_override_active
    try:
        if ctx.author.id not in config.ALLOWED_USERS:
            await ctx.send("You do not have permission to use this command.")
            return
        guild = ctx.guild
        streaming_vc = guild.get_channel(config.STREAMING_VC_ID)
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
    except Exception as e:
        logging.error(f"Error in rhush command: {e}")
    finally:
        hush_override_active = False

@bot.command(name='rsecret')
async def rsecret(ctx):
    """
    Removes mute and deafen statuses from all users in the Streaming VC.
    """
    try:
        if ctx.author.id not in config.ALLOWED_USERS:
            await ctx.send("You do not have permission to use this command.")
            return
        guild = ctx.guild
        streaming_vc = guild.get_channel(config.STREAMING_VC_ID)
        if streaming_vc:
            impacted = []
            for member in streaming_vc.members:
                if not member.bot:
                    try:
                        await member.edit(mute=False, deafen=False)
                        impacted.append(member.name)
                        logging.info(f"Removed mute and deafening from {member.name}.")
                    except Exception as e:
                        logging.error(f"Error removing mute and deafening from {member.name}: {e}")
            msg = "Removed mute and deafen from the following users: " + ", ".join(impacted) if impacted else "No users had mute or deafen removed."
            logging.info(msg)
            await ctx.send(msg)
        else:
            await ctx.send("Streaming VC not found.")
    except Exception as e:
        logging.error(f"Error in rsecret command: {e}")
    global hush_override_active
    hush_override_active = False

@bot.command(name='join')
async def join(ctx):
    """
    Sends a join invite DM to all members with a role listed in ADMIN_ROLE_NAME.
    """
    try:
        if not (ctx.author.id in config.ALLOWED_USERS or any(role.name in config.ADMIN_ROLE_NAME for role in ctx.author.roles)):
            await ctx.send("You do not have permission to use this command.")
            return
        record_command_usage("!join")
        record_command_usage_by_user(ctx.author.id, "!join")
        
        guild = ctx.guild
        admin_role_names = config.ADMIN_ROLE_NAME  # List of role names to notify
        join_message = config.JOIN_INVITE_MESSAGE
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
    except Exception as e:
        logging.error(f"Error in join command: {e}")

# --- New !commands Command ---
@bot.command(name='commands')
async def commands_list(ctx):
    """
    Lists all available bot commands with a brief description.
    The commands are separated into three groups:
      1. User Commands (Anyone in VC with Cam on)
      2. Admin/Allowed Commands
      3. Allowed Users Only Commands
    Accessible by allowed users and admin role members.
    """
    if ctx.author.id not in config.ALLOWED_USERS and not any(role.name in config.ADMIN_ROLE_NAME for role in ctx.author.roles):
        await ctx.send("You do not have permission to use this command.")
        return

    embed = discord.Embed(title="Bot Commands", color=discord.Color.green())
    
    user_commands = (
        "**!skip** - Skips the current stranger on Omegle.\n"
        "**!refresh** - Refreshes page (fix disconnected).\n"
        "**!pause** - Pauses Omegle temporarily.\n"
        "**!start** - Re-initiates Omegle by skipping.\n"
        "**!paid** - Redirects after someone pays for unban.\n"
        "**!rules** - Displays and DMs Server rules.\n"
        "**!about** - Displays and DMs Server info.\n"
        "**!info** - Displays and DMs Server info.\n"
        "**!help** - Displays Omegle controls with buttons."
    )
    embed.add_field(name="User Commands (Anyone in VC with Cam on)", value=user_commands, inline=False)
    
    admin_allowed_commands = (
        "**!whois** - Lists timed out, recently left, and joined members.\n"
        "**!rtimeouts** - Removes timeouts from ALL members.\n"
        "**!roles** - Lists roles and their members.\n"
        "**!join** - Sends a join invite DM to admin role members.\n"
        "**!top** - Lists the top 5 oldest Discord accounts.\n"
        "**!analytics** - Shows command usage statistics.\n"
        "**!commands** - Lists all bot commands."
    )
    embed.add_field(name="Admin/Allowed Commands", value=admin_allowed_commands, inline=False)
    
    allowed_only_commands = (
        "**!purge [count]** - Purges messages from the channel.\n"
        "**!hush** - Server mutes everyone in the Streaming VC.\n"
        "**!secret** - Server mutes + deafens everyone in Streaming VC.\n"
        "**!rhush** - Removes the mute status from everyone in Streaming VC.\n"
        "**!rsecret** - Removes mute and deafen statuses from Streaming VC.\n"
        "**!modoff** - Temporarily disables VC moderation for non-allowed users.\n"
        "**!modon** - Re-enables VC moderation after it has been disabled."
    )
    embed.add_field(name="Allowed Users Only Commands", value=allowed_only_commands, inline=False)
    
    await ctx.send(embed=embed)
# --- End of !commands Command ---

@bot.command(name='whois')
async def whois(ctx):
    """
    Displays a report with 3 separate messages:
      1. Who is currently timed out.
      2. Who has joined the server in the last 24 hours.
      3. Who has left the server in the last 24 hours.
    Accessible by ALLOWED_USERS or users with specified roles.
    """
    try:
        allowed = (ctx.author.id in config.ALLOWED_USERS or 
                   any(role.name in config.WHOIS_ALLOWED_ROLE_NAMES for role in ctx.author.roles))
        if not allowed:
            await ctx.send("You do not have permission to use this command.")
            return

        record_command_usage("!whois")
        record_command_usage_by_user(ctx.author.id, "!whois")
        
        def format_member(member_id, username, nickname):
            return f"<@{member_id}>"

        timed_out_members = [member for member in ctx.guild.members if member.is_timed_out()]
        timed_out_list = [format_member(member.id, member.name, member.nick) for member in timed_out_members]
        report1 = "Timed Out Members Report:\n" + ("\n".join(timed_out_list) if timed_out_list else "No members are currently timed out.")
        await ctx.send(report1)

        now = datetime.now(timezone.utc)
        join_list = [format_member(entry[0], entry[1], entry[2])
                     for entry in recent_joins if now - entry[3] <= timedelta(hours=24)]
        report2 = "Recent Joins (last 24 hours):\n" + ("\n".join(join_list) if join_list else "No members joined in the last 24 hours.")
        await ctx.send(report2)

        leave_list = [format_member(entry[0], entry[1], entry[2])
                      for entry in recent_leaves if now - entry[3] <= timedelta(hours=24)]
        report3 = "Recent Leaves (last 24 hours):\n" + ("\n".join(leave_list) if leave_list else "No members left in the last 24 hours.")
        await ctx.send(report3)
    except Exception as e:
        logging.error(f"Error in whois command: {e}")
        await ctx.send("An error occurred while generating the report.")

@bot.command(name='roles')
async def roles(ctx):
    """
    Lists out each role (excluding @everyone) and the users in it.
    Accessible only by ALLOWED_USERS or users with roles in WHOIS_ALLOWED_ROLE_NAMES.
    """
    try:
        allowed = (ctx.author.id in config.ALLOWED_USERS or
                   any(role.name in config.WHOIS_ALLOWED_ROLE_NAMES for role in ctx.author.roles))
        if not allowed:
            await ctx.send("You do not have permission to use this command.")
            return

        record_command_usage("!roles")
        record_command_usage_by_user(ctx.author.id, "!roles")
        
        for role in reversed(ctx.guild.roles):
            if role.name != "@everyone" and role.members:
                members = "\n".join([member.mention for member in role.members])
                await ctx.send(f"**Role: {role.name}**\n{members}")
    except Exception as e:
        logging.error(f"Error in roles command: {e}")
        await ctx.send("An error occurred while generating the roles report.")

@bot.command(name='top')
async def top(ctx):
    """
    Lists the top 5 oldest Discord accounts (excluding bots) in the server.
    Displays information such as account age, join date, and join order.
    """
    if not (ctx.author.id in config.ALLOWED_USERS or any(role.name in config.ADMIN_ROLE_NAME for role in ctx.author.roles)):
        await ctx.send("You do not have permission to use this command.")
        return

    record_command_usage("!top")
    record_command_usage_by_user(ctx.author.id, "!top")
    
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
            banner_url = user.banner.url if user.banner else None
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
async def modoff(ctx):
    """
    Temporarily disables voice channel moderation.
    """
    try:
        if ctx.author.id not in config.ALLOWED_USERS:
            await ctx.send("You do not have permission to use this command.")
            return
        if config.VC_MODERATION_PERMANENTLY_DISABLED:
            await ctx.send("VC Moderation is permanently disabled via config.")
            return
        global vc_moderation_active
        vc_moderation_active = False
        guild = ctx.guild
        streaming_vc = guild.get_channel(config.STREAMING_VC_ID)
        if streaming_vc:
            for member in streaming_vc.members:
                if member.id not in config.ALLOWED_USERS:
                    try:
                        await member.edit(mute=False, deafen=False)
                    except Exception as e:
                        logging.error(f"Error unmoderating {member.name}: {e}")
        await ctx.send("VC moderation has been temporarily disabled (modoff).")
    except Exception as e:
        logging.error(f"Error in modoff command: {e}")

@bot.command(name='modon')
async def modon(ctx):
    """
    Re-enables voice channel moderation.
    """
    try:
        if ctx.author.id not in config.ALLOWED_USERS:
            await ctx.send("You do not have permission to use this command.")
            return
        if config.VC_MODERATION_PERMANENTLY_DISABLED:
            await ctx.send("VC Moderation is permanently disabled via config.")
            return
        global vc_moderation_active
        vc_moderation_active = True
        await ctx.send("VC moderation has been re-enabled (modon).")
    except Exception as e:
        logging.error(f"Error in modon command: {e}")

# --- Updated Analytics Report Command ---
@bot.command(name='analytics')
async def analytics_report(ctx):
    """
    Sends a report showing command usage statistics (overall and by user)
    and a breakdown of violation events by user.
    The report is split into three separate messages to prevent exceeding character limits.
    Accessible by allowed users and admin role members.
    """
    if ctx.author.id not in config.ALLOWED_USERS and not any(role.name in config.ADMIN_ROLE_NAME for role in ctx.author.roles):
        await ctx.send("You do not have permission to use this command.")
        return
    record_command_usage("analytics")
    record_command_usage_by_user(ctx.author.id, "analytics")
    
    overall_report = "**Report**\n**Overall Command Usage:**\n"
    if analytics["command_usage"]:
        for cmd, count in analytics["command_usage"].items():
            overall_report += f"`{cmd}`: {count} times\n"
    else:
        overall_report += "No commands used.\n"
    
    usage_by_user_report = "**Command Usage by User:**\n"
    if analytics["command_usage_by_user"]:
        sorted_users = sorted(analytics["command_usage_by_user"].items(), key=lambda item: item[1].get("!skip", 0), reverse=True)
        for user_id, commands in sorted_users:
            usage_details = ", ".join([f"{cmd}: {cnt}" for cmd, cnt in commands.items()])
            usage_by_user_report += f"<@{user_id}>: {usage_details}\n"
    else:
        usage_by_user_report += "No command usage recorded.\n"
    
    violations_report = "**Violations by User:**\n"
    if user_violations:
        sorted_violations = sorted(user_violations.items(), key=lambda item: item[1], reverse=True)
        for user_id, violation_count in sorted_violations:
            violations_report += f"<@{user_id}>: {violation_count} violation(s)\n"
    else:
        violations_report += "No violations recorded.\n"
    
    await ctx.send(overall_report)
    await ctx.send(usage_by_user_report)
    await ctx.send(violations_report)
# --- End Analytics Report Command ---

# --- New !rules Command ---
@bot.command(name='rules')
async def rules(ctx):
    """
    Sends the rules message from the configuration in both the command channel and via DM.
    Can be used by any user in the designated command channel; allowed users can use it in any channel.
    """
    if ctx.author.id not in config.ALLOWED_USERS and ctx.channel.id != config.COMMAND_CHANNEL_ID:
        await ctx.send(f"All commands (including !rules) should be used in <#{config.COMMAND_CHANNEL_ID}>")
        return
    try:
        await ctx.send(config.RULES_MESSAGE)
    except Exception as e:
        logging.error(f"Error sending rules in channel: {e}")
    try:
        await ctx.author.send(config.RULES_MESSAGE)
    except discord.Forbidden:
        logging.warning(f"Could not send DM to {ctx.author.name} (DMs disabled?).")
    except Exception as e:
        logging.error(f"Error sending DM for rules: {e}")
# --- End of !rules Command ---

# --- New !info Command ---
@bot.command(name='info')
async def info(ctx):
    """
    Sends the info messages from the configuration in both the command channel and via DM.
    The configuration can define up to 5 separate messages: INFO1_MESSAGE, INFO2_MESSAGE, ... INFO5_MESSAGE.
    """
    if ctx.author.id not in config.ALLOWED_USERS and ctx.channel.id != config.COMMAND_CHANNEL_ID:
        await ctx.send(f"All commands (including !info) should be used in <#{config.COMMAND_CHANNEL_ID}>")
        return

    for i in range(1, 6):
        info_message = getattr(config, f"INFO{i}_MESSAGE", None)
        if info_message:
            try:
                await ctx.send(info_message)
            except Exception as e:
                logging.error(f"Error sending INFO{i}_MESSAGE in channel: {e}")

    for i in range(1, 6):
        info_message = getattr(config, f"INFO{i}_MESSAGE", None)
        if info_message:
            try:
                await ctx.author.send(info_message)
            except discord.Forbidden:
                logging.warning(f"Could not send DM to {ctx.author.name} for INFO{i}_MESSAGE (DMs disabled?).")
            except Exception as e:
                logging.error(f"Error sending DM for INFO{i}_MESSAGE: {e}")
# --- End of !info Command ---

# --- New !about Command ---
@bot.command(name='about')
async def about(ctx):
    """
    Sends the info messages from the configuration (same as !info) in both the command channel and via DM.
    This command behaves exactly like !info.
    """
    if ctx.author.id not in config.ALLOWED_USERS and ctx.channel.id != config.COMMAND_CHANNEL_ID:
        await ctx.send(f"All commands (including !about) should be used in <#{config.COMMAND_CHANNEL_ID}>")
        return

    for i in range(1, 6):
        info_message = getattr(config, f"INFO{i}_MESSAGE", None)
        if info_message:
            try:
                await ctx.send(info_message)
            except Exception as e:
                logging.error(f"Error sending INFO{i}_MESSAGE in channel (about): {e}")

    for i in range(1, 6):
        info_message = getattr(config, f"INFO{i}_MESSAGE", None)
        if info_message:
            try:
                await ctx.author.send(info_message)
            except discord.Forbidden:
                logging.warning(f"Could not send DM to {ctx.author.name} for INFO{i}_MESSAGE (about) (DMs disabled?).")
            except Exception as e:
                logging.error(f"Error sending DM for INFO{i}_MESSAGE (about): {e}")
# --- End of !about Command ---

@tasks.loop(seconds=10)
async def timeout_unauthorized_users():
    """
    Periodically checks for users in the Streaming VC without an active camera.
    Issues violations by moving them to a designated VC or timing them out.
    """
    try:
        if config.VC_MODERATION_PERMANENTLY_DISABLED or not vc_moderation_active:
            return
        guild = bot.get_guild(config.GUILD_ID)
        if guild:
            streaming_vc = guild.get_channel(config.STREAMING_VC_ID)
            hell_vc = guild.get_channel(config.HELL_VC_ID)
            if streaming_vc and hell_vc:
                for member in streaming_vc.members:
                    if member.bot:
                        continue
                    if member.id not in config.ALLOWED_USERS:
                        if not (member.voice and member.voice.self_video):
                            if member.id in camera_off_timers:
                                if time.time() - camera_off_timers[member.id] >= config.CAMERA_OFF_ALLOWED_TIME:
                                    analytics["violation_events"] += 1
                                    user_violations[member.id] = user_violations.get(member.id, 0) + 1
                                    violation_count = user_violations[member.id]
                                    try:
                                        if violation_count == 1:
                                            await member.move_to(hell_vc, reason="No camera detected in Streaming VC.")
                                            logging.info(f"Moved {member.name} to Hell VC.")
                                            try:
                                                if member.id not in users_with_dms_disabled:
                                                    await member.send("You have been moved to Hell VC because you did not have your camera on in Streaming VC.")
                                            except discord.Forbidden:
                                                users_with_dms_disabled.add(member.id)
                                                logging.warning(f"Could not send DM to {member.name} (DMs disabled?).")
                                            except discord.HTTPException as e:
                                                logging.error(f"Failed to send DM to {member.name}: {e}")
                                        elif violation_count == 2:
                                            timeout_duration = config.TIMEOUT_DURATION_SECOND_VIOLATION
                                            await member.timeout(timedelta(seconds=timeout_duration), reason="Repeated violations of camera policy.")
                                            logging.info(f"Timed out {member.name} for {timeout_duration} seconds.")
                                            active_timeouts[member.id] = {
                                                "timeout_end": time.time() + timeout_duration,
                                                "reason": "Repeated violations of camera policy (2nd offense).",
                                                "timed_by": "AutoMod - Camera Enforcer",
                                                "start_timestamp": time.time()
                                            }
                                            try:
                                                if member.id not in users_with_dms_disabled:
                                                    await member.send(f"You have been timed out for {timeout_duration} seconds - Must have camera on while in the Streaming VC.")
                                            except discord.Forbidden:
                                                users_with_dms_disabled.add(member.id)
                                                logging.warning(f"Could not send DM to {member.name} (DMs disabled?).")
                                            except discord.HTTPException as e:
                                                logging.error(f"Failed to send DM to {member.name}: {e}")
                                        else:
                                            timeout_duration = config.TIMEOUT_DURATION_THIRD_VIOLATION
                                            await member.timeout(timedelta(seconds=timeout_duration), reason="Repeated violations of camera policy.")
                                            logging.info(f"Timed out {member.name} for {timeout_duration} seconds.")
                                            active_timeouts[member.id] = {
                                                "timeout_end": time.time() + timeout_duration,
                                                "reason": "Repeated violations of camera policy (3rd+ offense).",
                                                "timed_by": "AutoMod - Camera Enforcer",
                                                "start_timestamp": time.time()
                                            }
                                            try:
                                                if member.id not in users_with_dms_disabled:
                                                    await member.send(f"You have been timed out for {timeout_duration} seconds - Must have camera on while in the Streaming VC.")
                                            except discord.Forbidden:
                                                users_with_dms_disabled.add(member.id)
                                                logging.warning(f"Could not send DM to {member.name} (DMs disabled?).")
                                            except discord.HTTPException as e:
                                                logging.error(f"Failed to send DM to {member.name}: {e}")
                                        camera_off_timers.pop(member.id, None)
                                    except discord.Forbidden:
                                        logging.warning(f"Missing permissions to move or timeout {member.name}.")
                                    except discord.HTTPException as e:
                                        logging.error(f"Failed to move or timeout {member.name}: {e}")
                        else:
                            camera_off_timers.pop(member.id, None)
                    else:
                        camera_off_timers.pop(member.id, None)
    except Exception as e:
        logging.error(f"Error in timeout_unauthorized_users: {e}")

async def purge_messages(channel, limit=5000):
    """
    Purges messages from the given channel up to the specified limit.
    """
    try:
        deleted = await channel.purge(limit=limit)
        await channel.send(f"Purged {len(deleted)} messages!", delete_after=5)
        logging.info(f"Purged {len(deleted)} messages.")
    except Exception as e:
        logging.error(f"Failed to purge messages: {e}")

if __name__ == "__main__":
    """
    Entry point for the bot.
    The bot token should be set as an environment variable (BOT_TOKEN).
    """
    try:
        bot.run(os.getenv("BOT_TOKEN"))
    except Exception as e:
        logging.error(f"Bot crashed: {e}")
