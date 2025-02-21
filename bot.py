import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from pynput.keyboard import Controller, Key
import asyncio
from pywinauto import Application
from datetime import timedelta, datetime
import logging
import time
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# -----------------------------------------------------------------------
# Import config from config.py (unchanged)
# -----------------------------------------------------------------------
import config

# Initialize bot and keyboard controller
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

keyboard = Controller()

# Cooldown trackers
cooldowns = {}
button_cooldowns = {}

# Track users without cameras in the Streaming VC
camera_off_timers = {}

# Track user violations
user_violations = {}

# Track users who have received the rules message
users_received_rules = set()

# Track users who have DMs disabled
users_with_dms_disabled = set()

# Global variable to store the voice client
voice_client = None

# Logging setup
logging.basicConfig(level=logging.INFO)

# -----------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------

async def send_keys_to_browser(key, delay=0):
    """Send keystrokes to the configured browser window."""
    try:
        app = Application(backend="win32").connect(title_re=config.BROWSER_WINDOW_TITLE)
        window = app.window(title_re=config.BROWSER_WINDOW_TITLE)
        await asyncio.sleep(delay)
        window.type_keys(key)
    except Exception as e:
        logging.error(f"Failed to send keys to browser window: {e}")

async def press_key(key, delay=0):
    """Press a key using pynput."""
    await asyncio.sleep(delay)
    keyboard.press(key)
    keyboard.release(key)

def is_user_in_streaming_vc_with_camera(user: discord.Member) -> bool:
    """Check if a user is in the configured Streaming VC with camera on."""
    streaming_vc = user.guild.get_channel(config.STREAMING_VC_ID)
    if streaming_vc and user in streaming_vc.members:
        if user.voice and user.voice.self_video:
            return True
    return False

async def play_sound_in_vc(guild: discord.Guild, sound_file: str):
    """Play a sound in the Streaming VC with a 2-second delay."""
    global voice_client
    try:
        await asyncio.sleep(2)  # Delay for 2 seconds
        streaming_vc = guild.get_channel(config.STREAMING_VC_ID)
        if streaming_vc:  # Always connect if the channel exists
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

# -----------------------------------------------------------------------
# Bot Events
# -----------------------------------------------------------------------

@bot.event
async def on_ready():
    logging.info(f"Bot is online as {bot.user}")
    try:
        periodic_help_menu.start()
        timeout_unauthorized_users.start()
    except Exception as e:
        logging.error(f"Failed to start background tasks: {e}")

    # Initialize camera_off_timers for members already in the Streaming VC
    guild = discord.utils.get(bot.guilds, name=config.GUILD_NAME)
    if guild:
        streaming_vc = guild.get_channel(config.STREAMING_VC_ID)
        if streaming_vc:
            for member in streaming_vc.members:
                if not member.bot and member.name not in config.ALLOWED_USERS:
                    if not (member.voice and member.voice.self_video):
                        camera_off_timers[member.id] = time.time()

@bot.event
async def on_voice_state_update(member, before, after):
    """Handle when users join/leave the Streaming VC, send them rules, set camera timers, etc."""
    if member == bot.user:
        return

    streaming_vc = member.guild.get_channel(config.STREAMING_VC_ID)
    
    # If the member *joins* the Streaming VC
    if after.channel and after.channel.id == config.STREAMING_VC_ID:
        # Print the name of the user who joined the Streaming VC to the CMD window
        print(f"{member.name} joined the Streaming VC.")

        # Send them the rules if they haven't seen them
        if member.id not in users_received_rules:
            try:
                if member.id not in users_with_dms_disabled:
                    await member.send(config.RULES_MESSAGE)
                    users_received_rules.add(member.id)
                    logging.info(f"Sent rules to {member.name}.")
            except discord.Forbidden:
                # Log at WARNING instead of ERROR
                users_with_dms_disabled.add(member.id)
                logging.warning(f"Could not send DM to {member.name} (DMs disabled?).")
            except discord.HTTPException as e:
                logging.error(f"Failed to send DM to {member.name}: {e}")

        # If they do NOT have the camera on, start a timer
        if not (member.voice and member.voice.self_video):
            if member.id not in camera_off_timers:
                camera_off_timers[member.id] = time.time()
        else:
            # If they do have a camera on, remove any timer
            camera_off_timers.pop(member.id, None)
    else:
        # If the user leaves the Streaming VC
        if before.channel and before.channel.id == config.STREAMING_VC_ID:
            # Remove them from the timers
            camera_off_timers.pop(member.id, None)

@bot.event
async def on_member_join(member):
    """Welcome new members in the chat channel."""
    guild = member.guild
    if guild.name == config.GUILD_NAME:
        chat_channel = guild.get_channel(config.CHAT_CHANNEL_ID)
        if chat_channel:
            await chat_channel.send(config.WELCOME_MESSAGE.format(member=member))

# -----------------------------------------------------------------------
# Help Menu UI
# -----------------------------------------------------------------------

class HelpView(View):
    """A View containing help buttons for quick command usage."""
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
    """A button that triggers a command when clicked."""
    def __init__(self, label, command):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.command = command

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        current_time = time.time()

        # Button-level cooldown check
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

        # Check if user is allowed or in the streaming VC with camera
        if interaction.user.name not in config.ALLOWED_USERS and not is_user_in_streaming_vc_with_camera(interaction.user):
            await interaction.response.send_message(
                f"{interaction.user.mention}, you must be in the **Streaming VC** with your camera on to use this.",
                ephemeral=True
            )
            return

        # Update the button cooldown
        button_cooldowns[user_id] = (current_time, False)

        # Defer and re-route the command to on_message logic
        await interaction.response.defer()
        await interaction.channel.send(f"{interaction.user.mention} used {self.command}")
        
        # Manually create a 'fake' message object for on_message
        fake_message = interaction.message
        fake_message.content = self.command
        fake_message.author = interaction.user
        await on_message(fake_message)

# -----------------------------------------------------------------------
# Bot Commands / on_message
# -----------------------------------------------------------------------

@bot.event
async def on_message(message):
    """Main handler for text commands."""
    if message.author == bot.user or not message.guild:
        return

    # Only process messages that start with "!"
    if not message.content.startswith("!"):
        return

    # Only respond in the correct guild
    if message.guild.name != config.GUILD_NAME:
        return

    in_command_channel = (message.channel.id == config.COMMAND_CHANNEL_ID)
    in_chat_channel = (message.channel.id == config.CHAT_CHANNEL_ID)

    # Handle !purge in either command or chat channel
    if message.content.lower().startswith("!purge") and (in_chat_channel or in_command_channel):
        await handle_purge(message)
        return

    # Handle !help
    if message.content.lower().startswith("!help"):
        if not in_command_channel:
            await handle_wrong_channel(message)
            return
        await send_help_menu(message)
        return

    # Handle !rtimeouts
    if message.content.lower().startswith("!rtimeouts"):
        await bot.process_commands(message)
        return

    # If user tried a different command in the chat channel, advise them to use the correct channel
    if in_chat_channel:
        await handle_wrong_channel(message)
        return

    # Check if unauthorized user is in streaming VC with camera
    if message.author.name not in config.ALLOWED_USERS and not is_user_in_streaming_vc_with_camera(message.author):
        if in_command_channel:
            await message.channel.send(
                f"{message.author.mention}, you must be in the **Streaming VC** with your camera on to use this command."
            )
        return

    # Apply a command cooldown
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

    # Define command actions
    command_actions = {
        "!skip": lambda: asyncio.create_task(skip_command(message.guild)),
        "!refresh": lambda: asyncio.create_task(refresh_command(message.guild)),
        "!start": lambda: asyncio.create_task(start_command(message.guild)),
        "!pause": lambda: asyncio.create_task(pause_command(message.guild))
    }

    async def skip_command(guild):
        await send_keys_to_browser("{ESC}")
        await asyncio.sleep(1)
        await send_keys_to_browser("{ESC}")
        await play_sound_in_vc(guild, config.SOUND_FILE)

    async def refresh_command(guild):
        await send_keys_to_browser("{F5}")
        await asyncio.sleep(3)
        await send_keys_to_browser("{ESC}")
        await play_sound_in_vc(guild, config.SOUND_FILE)

    async def start_command(guild):
        await send_keys_to_browser("{F5}")
        await asyncio.sleep(3)
        await send_keys_to_browser("{ESC}")
        await play_sound_in_vc(guild, config.SOUND_FILE)

    async def pause_command(guild):
        await send_keys_to_browser("{F5}")
        await play_sound_in_vc(guild, config.SOUND_FILE)

    command = message.content.lower()
    if command in command_actions:
        await command_actions[command]()

    # Send a response in the chat
    command_messages = {
        "!skip": "Omegle skipped!",
        "!refresh": "Refreshed Omegle!",
        "!start": "Stream started!",
        "!pause": "Stream paused temporarily!",
        "!help": "help"
    }
    if command in command_messages:
        # If it's !help, show the help menu
        if command == "!help":
            await send_help_menu(message)
        else:
            await message.channel.send(command_messages[command])

# -----------------------------------------------------------------------
# New Command: !rtimeouts
# -----------------------------------------------------------------------

@bot.command(name='rtimeouts')
async def remove_timeouts(ctx):
    """Remove timeouts from all users in the server."""
    # Check if the user is allowed to use this command
    if ctx.author.name not in config.ALLOWED_USERS:
        await ctx.send("You do not have permission to use this command.")
        return

    # Iterate through all members in the guild
    removed_timeouts = []
    for member in ctx.guild.members:
        if member.is_timed_out():
            try:
                await member.timeout(None, reason="Timeout removed by allowed user.")
                removed_timeouts.append(member.name)
                logging.info(f"Removed timeout from {member.name}.")
            except discord.Forbidden:
                logging.warning(f"Missing permissions to remove timeout from {member.name}.")
            except discord.HTTPException as e:
                logging.error(f"Failed to remove timeout from {member.name}: {e}")

    # Print the usernames of users who are no longer timed out to the cmd screen
    if removed_timeouts:
        print("Users who are no longer timed out:")
        for username in removed_timeouts:
            print(f"- {username}")

    await ctx.send("All timeouts have been removed.")

# -----------------------------------------------------------------------
# Utility Functions
# -----------------------------------------------------------------------

async def handle_purge(message):
    """Handle the !purge command."""
    if message.author.name in config.ALLOWED_USERS:
        await message.channel.send("Purging messages...")
        await purge_messages(message.channel)  # Pass the TextChannel object
    else:
        await message.channel.send("You do not have permission to use this command.")

async def purge_messages(channel):
    """Purge messages in the specified channel with a controlled limit."""
    try:
        deleted = await channel.purge(limit=5000)
        await channel.send(f"Purged {len(deleted)} messages!", delete_after=5)
        logging.info(f"Purged {len(deleted)} messages.")
    except Exception as e:
        logging.error(f"Failed to purge messages: {e}")

async def send_help_menu(target):
    """Send an embedded help menu with a help button view."""
    embed = discord.Embed(
        title="Bot Help Menu",
        description=(
            "This controls the Streaming VC Bot!\n\n"
            "**Commands:**\n"
            "!skip - Skips the Omegle bot\n"
            "!refresh - Fixes Disconnected\n"
            "!start - Starts the stream\n"
            "!pause - Pauses the stream b4 you leave\n"
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

async def handle_wrong_channel(message):
    """Notify users they must use the command channel, enforce a cooldown for repeated attempts."""
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

# -----------------------------------------------------------------------
# Background Tasks
# -----------------------------------------------------------------------

@tasks.loop(minutes=3)
async def periodic_help_menu():
    """Periodically post the help menu if non-allowed users are around."""
    guild = discord.utils.get(bot.guilds, name=config.GUILD_NAME)
    if guild:
        command_channel = guild.get_channel(config.COMMAND_CHANNEL_ID)
        if command_channel:
            non_allowed_users = [member for member in guild.members if member.name not in config.ALLOWED_USERS]
            if non_allowed_users:
                try:
                    # Purge messages 5 seconds before posting the help menu
                    await command_channel.send("Purging messages...")
                    await purge_messages(command_channel)  # Pass the TextChannel object
                    await asyncio.sleep(1)  # Wait 5 seconds after purging
                    await send_help_menu(command_channel)
                except Exception as e:
                    logging.error(f"Failed to send help menu: {e}")

@tasks.loop(seconds=10)
async def timeout_unauthorized_users():
    """
    Periodically move unauthorized users without cameras to Hell VC
    and apply incremental timeouts for repeated violations.
    """
    guild = discord.utils.get(bot.guilds, name=config.GUILD_NAME)
    if guild:
        streaming_vc = guild.get_channel(config.STREAMING_VC_ID)
        hell_vc = guild.get_channel(config.HELL_VC_ID)
        if streaming_vc and hell_vc:
            for member in streaming_vc.members:
                if member.bot:
                    continue

                # Check if user is unauthorized (not in ALLOWED_USERS)
                if member.name not in config.ALLOWED_USERS:
                    # Check if camera is off
                    if not (member.voice and member.voice.self_video):
                        if member.id in camera_off_timers:
                            # If they've been in the VC for >= 60 seconds with camera off
                            if time.time() - camera_off_timers[member.id] >= 60:
                                try:
                                    user_violations[member.id] = user_violations.get(member.id, 0) + 1
                                    violation_count = user_violations[member.id]

                                    # 1st violation => Move to Hell VC
                                    if violation_count == 1:
                                        await member.move_to(
                                            hell_vc, 
                                            reason="No camera detected in Streaming VC."
                                        )
                                        logging.info(f"Moved {member.name} to Hell VC.")
                                        try:
                                            if member.id not in users_with_dms_disabled:
                                                await member.send(
                                                    f"You have been moved to **Hell VC** because "
                                                    f"you did not have your camera on in **Streaming VC**."
                                                )
                                        except discord.Forbidden:
                                            users_with_dms_disabled.add(member.id)
                                            logging.warning(f"Could not send DM to {member.name} (DMs disabled?).")
                                        except discord.HTTPException as e:
                                            logging.error(f"Failed to send DM to {member.name}: {e}")

                                    # 2nd violation => 1-minute timeout
                                    elif violation_count == 2:
                                        timeout_duration = 60
                                        await member.timeout(
                                            timedelta(seconds=timeout_duration), 
                                            reason="Repeated violations of camera policy."
                                        )
                                        logging.info(f"Timed out {member.name} for {timeout_duration} seconds.")
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

                                    # 3rd+ violation => 5-minute timeout
                                    else:
                                        timeout_duration = 300
                                        await member.timeout(
                                            timedelta(seconds=timeout_duration), 
                                            reason="Repeated violations of camera policy."
                                        )
                                        logging.info(f"Timed out {member.name} for {timeout_duration} seconds.")
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

                                    # Safely remove user from camera_off_timers
                                    camera_off_timers.pop(member.id, None)

                                except discord.Forbidden:
                                    logging.warning(f"Missing permissions to move or timeout {member.name}.")
                                except discord.HTTPException as e:
                                    logging.error(f"Failed to move or timeout {member.name}: {e}")
                    else:
                        # If camera is on, remove them from timers
                        camera_off_timers.pop(member.id, None)
                else:
                    # If user is allowed, remove from timers
                    camera_off_timers.pop(member.id, None)

# -----------------------------------------------------------------------
# Run the Bot
# -----------------------------------------------------------------------

if __name__ == "__main__":
    bot.run(os.getenv("BOT_TOKEN"))
