# Replace with proper IDs
GUILD_ID = 1234567891234567890            # Replace with ID of your Discord server
COMMAND_CHANNEL_ID = 1234567891234567890   # Replace with the actual ID of the command channel
CHAT_CHANNEL_ID = 1234567891234567890       # Replace with the actual ID of the chat channel
STREAMING_VC_ID = 1234567891234567890       # Replace with the actual ID of the Streaming VC
HELL_VC_ID = 1234567891234567890            # Replace with the actual ID of the Hell VC

# Replace with IDs of Admins who have access to mod commands / do not need camera on in Streaming VC
ALLOWED_USERS = {
    1234567891234567890,  # Replace with the actual user ID
    1234567891234567890  # Replace with the actual user ID
}

MUSIC_BOT = 1234567891234567890  # User ID of the Music bot that can have its camera off but not have roles

OMEGLE_VIDEO_URL = "https://uhmegle.com/video"  # URL of the Uhmegle site (video page)
EDGE_USER_DATA_DIR = "C:\\Users\\USERNAME\\AppData\\Local\\Microsoft\\Edge\\User Data"  # Edge browser user data directory
SOUND_FILE = "skip.mp3"  # Path to your sound file

# !join Command configuration
# Now you can specify multiple role names for DMing using a list.
ADMIN_ROLE_NAME = ["Role1", "Role2"]
JOIN_INVITE_MESSAGE = "The Stream Bot is Live! Please join for OmegleStream Group VC: https://discord.com/channels/1234567891234567890/1234567891234567890"  # Message to send to Admins to join

# Hotkey for host to skip omegle stranger
ENABLE_GLOBAL_HOTKEY = True  # Set to False (captial F) to disable global skip hotkey
GLOBAL_HOTKEY_COMBINATION = "alt+grave"  # AKA alt + ` Configure keyboard press combination flor global skip of host

# VC Moderation settings
VC_MODERATION_PERMANENTLY_DISABLED = False  # Leave this False unless having issues

COMMAND_COOLDOWN = 5  # Seconds between cooldowns
HELP_COOLDOWN = 5     # Seconds between button cooldowns
PURGE_DELAY = 5       # Delay between purge actions in seconds

# Rul=es message
RULES_MESSAGE = (
    "Welcome to **ServerName**!\n\n"
    "**Rules:**\n"
    "1. Please have your camera on while in the Streaming VC. If your camera is off, you will muted and deafened, repeated violations may result in timeouts.\n"
    "2. Control skipping strangers and more via the https://discord.com/channels/1234567891234567890/1234567891234567890 GC.\n"
    "3. Please be sure to !pause the bot when no one is using it (prevents ban).\n\n"
    "Thank you for your cooperation!"
)

# Info message
INFO1_MESSAGE = """
**Info:** 🎉 We now have a 24/7 live host bot 🤖!

Use [#skip-refresh](https://discord.com/channels/1234567891234567890/1234567891234567890) to control the bot (use the `!help` command to see all available commands).

If you are new here, this Discord server features a **Streaming VC** that—when the host is present—streams a group call to Omegle, allowing audio and video to pass through and creating a **GROUP OMEGLE CALL** for anyone 18+ to join. Must have Camera on in the VC or the bot will deafen / mute you.
"""

INFO2_MESSAGE = """
Invite your friends using the link below:

[Invite Code](https://discord.gg/1234567891234567890)
"""

INFO3_MESSAGE = """
[SkipCord-2 on GitHub](https://github.com/EolnMsuk/SkipCord-2/)
"""

INFO4_MESSAGE = """
Channel Boosters and users who donate earn the @SugarDaddy or @VIP roles, which allow access to photos, files, and the soundboard, as well as the [Hidden VC](https://discord.com/channels/1234567891234567890/1234567891234567890)
"""

INFO5_MESSAGE = """
Thanks!
"""

# Camera enforcement timing configuration
CAMERA_OFF_ALLOWED_TIME = 30  # Seconds allowed with camera off before a violation is recorded.
TIMEOUT_DURATION_SECOND_VIOLATION = 60  # Timeout in seconds for a second violation.
TIMEOUT_DURATION_THIRD_VIOLATION = 300  # Timeout in seconds for a third or subsequent violation.
