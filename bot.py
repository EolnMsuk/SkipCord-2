import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import asyncio
from datetime import timedelta
import logging
import time
import os
from dotenv import load_dotenv

# Selenium imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager

# Load environment variables
load_dotenv()

# Import configuration
import config

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

# Global variables
voice_client = None
driver = None
cooldowns = {}
button_cooldowns = {}
camera_off_timers = {}
user_violations = {}
users_received_rules = set()
users_with_dms_disabled = set()
active_timeouts = {}

def init_selenium():
    """Initialize the Edge browser with Selenium."""
    global driver
    try:
        service = EdgeService(EdgeChromiumDriverManager().install())
        options = webdriver.EdgeOptions()
        edge_profile_path = "C:\\Users\\owner\\AppData\\Local\\Microsoft\\Edge\\User Data"
        options.add_argument(f"user-data-dir={edge_profile_path}")
        driver = webdriver.Edge(service=service, options=options)
        driver.maximize_window()
        driver.get(config.UHMEGLE_VIDEO_URL)
        logging.info("Selenium: Opened Uhmegle video page.")
    except Exception as e:
        logging.error(f"Failed to initialize Selenium driver: {e}")

async def selenium_skip():
    """Send an Escape key event to skip the current Omegle session."""
    if driver is None:
        logging.error("Selenium driver not initialized; cannot skip.")
        return
    try:
        driver.execute_script("""
            var evt = new KeyboardEvent('keydown', {
                bubbles: true,
                cancelable: true,
                key: 'Escape',
                code: 'Escape'
            });
            document.dispatchEvent(evt);
        """)
        logging.info("Selenium: Sent ESC key event to Uhmegle page.")
    except Exception as e:
        logging.error(f"Selenium skip failed: {e}")

async def selenium_refresh():
    """Refresh the Uhmegle page."""
    if driver is None:
        logging.error("Selenium driver not initialized; cannot refresh.")
        return
    try:
        driver.refresh()
        logging.info("Selenium: Page refreshed.")
    except Exception as e:
        logging.error(f"Selenium refresh failed: {e}")

async def selenium_start():
    """Start the Omegle stream by refreshing and skipping."""
    if driver is None:
        logging.error("Selenium driver not initialized; cannot start.")
        return
    try:
        driver.get(config.UHMEGLE_VIDEO_URL)
        logging.info("Selenium: Navigated to Uhmegle video page for start.")
        await asyncio.sleep(3)
        await selenium_skip()
    except Exception as e:
        logging.error(f"Selenium start failed: {e}")

async def selenium_pause():
    """Pause the Omegle stream by refreshing the page."""
    if driver is None:
        logging.error("Selenium driver not initialized; cannot stop.")
        return
    try:
        driver.refresh()
        logging.info("Selenium: Performed refresh for pause command.")
    except Exception as e:
        logging.error(f"Selenium pause failed: {e}")

async def play_sound_in_vc(guild: discord.Guild, sound_file: str):
    """Play a sound in the Streaming VC with a 2-second delay."""
    global voice_client
    try:
        await asyncio.sleep(2)
        streaming_vc = guild.get_channel(config.STREAMING_VC_ID)
        if streaming_vc:
            if voice_client is None or not voice_client.is_connected():
                voice_client = await streaming_vc.connect()
            voice_client.play(discord.FFmpegPCMAudio(executable="ffmpeg", source=sound_file))
            while voice_client.is_playing():
                await asyncio.sleep(1)
    except Exception as e:
        logging.error(f"Failed to play sound in VC: {e}")

async def disconnect_from_vc():
    """Disconnect the bot from the Streaming VC, if connected."""
    global voice_client
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        voice_client = None

def is_user_in_streaming_vc_with_camera(user: discord.Member) -> bool:
    """Check if a user is in the Streaming VC with their camera on."""
    streaming_vc = user.guild.get_channel(config.STREAMING_VC_ID)
    if streaming_vc and user in streaming_vc.members:
        if user.voice and user.voice.self_video:
            return True
    return False

@bot.event
async def on_ready():
    """Initialize the bot and Selenium when the bot is ready."""
    logging.info(f"Bot is online as {bot.user}")
    try:
        init_selenium()
        periodic_help_menu.start()
        timeout_unauthorized_users.start()
        guild = discord.utils.get(bot.guilds, name=config.GUILD_NAME)
        if guild:
            streaming_vc = guild.get_channel(config.STREAMING_VC_ID)
            if streaming_vc:
                for member in streaming_vc.members:
                    if not member.bot and member.name not in config.ALLOWED_USERS:
                        if not (member.voice and member.voice.self_video):
                            camera_off_timers[member.id] = time.time()
    except Exception as e:
        logging.error(f"Error during on_ready setup: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    """Handle voice state updates, particularly for the Streaming VC."""
    try:
        if member == bot.user:
            return
        streaming_vc = member.guild.get_channel(config.STREAMING_VC_ID)
        if after.channel and after.channel.id == config.STREAMING_VC_ID:
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
            if not (member.voice and member.voice.self_video):
                camera_off_timers[member.id] = time.time()
            else:
                camera_off_timers.pop(member.id, None)
        elif before.channel and before.channel.id == config.STREAMING_VC_ID:
            camera_off_timers.pop(member.id, None)
    except Exception as e:
        logging.error(f"Error in on_voice_state_update: {e}")

@bot.event
async def on_member_join(member):
    """Send a welcome message to new members."""
    try:
        guild = member.guild
        if guild.name == config.GUILD_NAME:
            chat_channel = guild.get_channel(config.CHAT_CHANNEL_ID)
            if chat_channel:
                welcome_message = (
                    f"Welcome to the Discord {member.mention}! 🎉\n"
                    "Go to https://discord.com/channels/1131770315740024962/1334294218826453072 then type !help"
                )
                await chat_channel.send(welcome_message)
    except Exception as e:
        logging.error(f"Error in on_member_join: {e}")

class HelpView(View):
    """A view for the help menu with buttons for commands."""
    def __init__(self):
        super().__init__()
        commands_dict = {
            "Skip": "!skip",
            "Refresh": "!refresh",
            "Start": "!start",
            "Pause": "!pause"
        }
        for label, command in commands_dict.items():
            self.add_item(HelpButton(label, command))

class HelpButton(Button):
    """A button for the help menu that triggers a command."""
    def __init__(self, label, command):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.command = command

    async def callback(self, interaction: discord.Interaction):
        """Handle button clicks with cooldown and permission checks."""
        try:
            user_id = interaction.user.id
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
            if interaction.user.name not in config.ALLOWED_USERS and not is_user_in_streaming_vc_with_camera(interaction.user):
                await interaction.response.send_message(
                    f"{interaction.user.mention}, you must be in the **Streaming VC** with your camera on to use this.",
                    ephemeral=True
                )
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
    """Handle incoming messages and execute commands."""
    try:
        if message.author == bot.user or not message.guild:
            return
        if not message.content.startswith("!"):
            return
        if message.guild.name != config.GUILD_NAME:
            return
        in_command_channel = (message.channel.id == config.COMMAND_CHANNEL_ID)
        in_chat_channel = (message.channel.id == config.CHAT_CHANNEL_ID)
        if message.content.lower().startswith("!purge") and (in_chat_channel or in_command_channel):
            await handle_purge(message)
            return
        if message.content.lower().startswith("!help"):
            if not in_command_channel:
                await handle_wrong_channel(message)
                return
            await send_help_menu(message)
            return
        if message.content.lower().startswith("!rtimeouts"):
            await bot.process_commands(message)
            return
        if in_chat_channel:
            await handle_wrong_channel(message)
            return
        if message.author.name not in config.ALLOWED_USERS and not is_user_in_streaming_vc_with_camera(message.author):
            if in_command_channel:
                await message.channel.send(
                    f"{message.author.mention}, you must be in the **Streaming VC** with your camera on to use this command."
                )
            return
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
        command_actions = {
            "!skip": lambda: asyncio.create_task(handle_skip(message.guild)),
            "!refresh": lambda: asyncio.create_task(handle_refresh(message.guild)),
            "!start": lambda: asyncio.create_task(handle_start(message.guild)),
            "!pause": lambda: asyncio.create_task(handle_pause(message.guild))
        }
        async def handle_skip(guild):
            await selenium_skip()
            await asyncio.sleep(1)
            await selenium_skip()
            await play_sound_in_vc(guild, config.SOUND_FILE)
        async def handle_refresh(guild):
            await selenium_refresh()
            await asyncio.sleep(3)
            await selenium_skip()
            await play_sound_in_vc(guild, config.SOUND_FILE)
        async def handle_start(guild):
            await selenium_start()
            await play_sound_in_vc(guild, config.SOUND_FILE)
        async def handle_pause(guild):
            await selenium_pause()
            await play_sound_in_vc(guild, config.SOUND_FILE)
        command = message.content.lower()
        if command in command_actions:
            await command_actions[command]()
        command_messages = {
            "!skip": "Omegle skipped!",
            "!refresh": "Refreshed Omegle!",
            "!start": "Stream started!",
            "!pause": "Stream paused temporarily!",
            "!help": "help"
        }
        if command in command_messages:
            if command == "!help":
                await send_help_menu(message)
            else:
                await message.channel.send(command_messages[command])
    except Exception as e:
        logging.error(f"Error in on_message: {e}")

@bot.command(name='rtimeouts')
async def remove_timeouts(ctx):
    """Remove all timeouts from members."""
    try:
        if ctx.author.name not in config.ALLOWED_USERS:
            await ctx.send("You do not have permission to use this command.")
            return
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
            print("Users who are no longer timed out:")
            for username in removed_timeouts:
                print(f"- {username}")
        await ctx.send("All timeouts have been removed.")
    except Exception as e:
        logging.error(f"Error in remove_timeouts: {e}")

async def handle_purge(message):
    """Handle the purge command."""
    try:
        if message.author.name in config.ALLOWED_USERS:
            await message.channel.send("Purging messages...")
            await purge_messages(message.channel)
        else:
            await message.channel.send("You do not have permission to use this command.")
    except Exception as e:
        logging.error(f"Error in handle_purge: {e}")

async def purge_messages(channel):
    """Purge messages from a channel."""
    try:
        deleted = await channel.purge(limit=5000)
        await channel.send(f"Purged {len(deleted)} messages!", delete_after=5)
        logging.info(f"Purged {len(deleted)} messages.")
    except Exception as e:
        logging.error(f"Failed to purge messages: {e}")

async def send_help_menu(target):
    """Send the help menu to a channel or user."""
    try:
        embed = discord.Embed(
            title="Bot Help Menu",
            description=(
                "This controls the Streaming VC Bot!\n\n"
                "**Commands:**\n"
                "!skip - Skips the Omegle bot\n"
                "!refresh - Fixes 'Disconnected'\n"
                "!start - Starts the stream\n"
                "!pause - Pause the stream before you leave\n"
                "\nCooldown: **5 seconds per command**"
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
    """Handle commands sent in the wrong channel."""
    try:
        user_id = message.author.id
        current_time = time.time()
        if user_id in cooldowns:
            last_used, warned = cooldowns[user_id]
            time_left = config.COMMAND_COOLDOWN - (current_time - last_used)
            if time_left > 0:
                if not warned:
                    await message.channel.send(
                        f"{message.author.mention}, please wait {int(time_left)} seconds before trying again."
                    )
                    cooldowns[user_id] = (last_used, True)
                return
        await message.channel.send(
            f"{message.author.mention}, use all commands (including !help) in the command channel."
        )
        cooldowns[user_id] = (current_time, False)
    except Exception as e:
        logging.error(f"Error in handle_wrong_channel: {e}")

@tasks.loop(minutes=2)
async def periodic_help_menu():
    """Periodically send the help menu in the command channel."""
    try:
        guild = discord.utils.get(bot.guilds, name=config.GUILD_NAME)
        if guild:
            command_channel = guild.get_channel(config.COMMAND_CHANNEL_ID)
            if command_channel:
                non_allowed_users = [member for member in guild.members if member.name not in config.ALLOWED_USERS]
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

@tasks.loop(seconds=10)
async def timeout_unauthorized_users():
    """Timeout users who violate the camera policy."""
    try:
        guild = discord.utils.get(bot.guilds, name=config.GUILD_NAME)
        if guild:
            streaming_vc = guild.get_channel(config.STREAMING_VC_ID)
            hell_vc = guild.get_channel(config.HELL_VC_ID)
            if streaming_vc and hell_vc:
                for member in streaming_vc.members:
                    if member.bot:
                        continue
                    if member.name not in config.ALLOWED_USERS:
                        if not (member.voice and member.voice.self_video):
                            if member.id in camera_off_timers:
                                if time.time() - camera_off_timers[member.id] >= 60:
                                    user_violations[member.id] = user_violations.get(member.id, 0) + 1
                                    violation_count = user_violations[member.id]
                                    try:
                                        if violation_count == 1:
                                            await member.move_to(
                                                hell_vc, 
                                                reason="No camera detected in Streaming VC."
                                            )
                                            logging.info(f"Moved {member.name} to Hell VC.")
                                            try:
                                                if member.id not in users_with_dms_disabled:
                                                    await member.send(
                                                        f"You have been moved to **Hell VC** because you did not "
                                                        f"have your camera on in **Streaming VC**."
                                                    )
                                            except discord.Forbidden:
                                                users_with_dms_disabled.add(member.id)
                                                logging.warning(f"Could not send DM to {member.name} (DMs disabled?).")
                                            except discord.HTTPException as e:
                                                logging.error(f"Failed to send DM to {member.name}: {e}")
                                        elif violation_count == 2:
                                            timeout_duration = 60
                                            await member.timeout(
                                                timedelta(seconds=timeout_duration), 
                                                reason="Repeated violations of camera policy."
                                            )
                                            logging.info(f"Timed out {member.name} for {timeout_duration} seconds.")
                                            active_timeouts[member.id] = {
                                                "timeout_end": time.time() + timeout_duration,
                                                "reason": "Repeated violations of camera policy (2nd offense).",
                                                "timed_by": "AutoMod - Camera Enforcer",
                                                "start_timestamp": time.time()
                                            }
                                            try:
                                                if member.id not in users_with_dms_disabled:
                                                    await member.send(
                                                        f"You have been timed out for {timeout_duration} seconds "
                                                        f"due to repeated camera policy violations."
                                                    )
                                            except discord.Forbidden:
                                                users_with_dms_disabled.add(member.id)
                                                logging.warning(f"Could not send DM to {member.name} (DMs disabled?).")
                                            except discord.HTTPException as e:
                                                logging.error(f"Failed to send DM to {member.name}: {e}")
                                        else:
                                            timeout_duration = 300
                                            await member.timeout(
                                                timedelta(seconds=timeout_duration), 
                                                reason="Repeated violations of camera policy."
                                            )
                                            logging.info(f"Timed out {member.name} for {timeout_duration} seconds.")
                                            active_timeouts[member.id] = {
                                                "timeout_end": time.time() + timeout_duration,
                                                "reason": "Repeated violations of camera policy (3rd+ offense).",
                                                "timed_by": "AutoMod - Camera Enforcer",
                                                "start_timestamp": time.time()
                                            }
                                            try:
                                                if member.id not in users_with_dms_disabled:
                                                    await member.send(
                                                        f"You have been timed out for {timeout_duration} seconds "
                                                        f"due to repeated camera policy violations."
                                                    )
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

if __name__ == "__main__":
    try:
        bot.run(os.getenv("BOT_TOKEN"))
    except Exception as e:
        logging.error(f"Bot crashed: {e}")
