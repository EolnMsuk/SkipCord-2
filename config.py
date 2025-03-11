# config.py

# Discord server and channel IDs (replace with your actual IDs)
GUILD_ID = 123456789012345678            # Replace with your Discord server ID
COMMAND_CHANNEL_ID = 123456789012345679   # Replace with the ID of your command channel
CHAT_CHANNEL_ID = 123456789012345680       # Replace with the ID of your chat channel
STREAMING_VC_ID = 123456789012345681       # Replace with the ID of your Streaming Voice Channel
HELL_VC_ID = 123456789012345682            # Replace with the ID of your Hell Voice Channel (for moderation)

# Allowed user IDs (users with elevated permissions; replace with actual user IDs)
ALLOWED_USERS = {
    123456789012345683,  # Replace with an allowed user ID
    123456789012345684,  # Replace with an allowed user ID
}

# Role names allowed to use the !whois command in addition to ALLOWED_USERS.
WHOIS_ALLOWED_ROLE_NAMES = ["Admin", "Moderator"]

# URLs and paths (update as necessary)
OMEGLE_VIDEO_URL = "https://uhmegle.com/video"  # URL of the Omegle video page
EDGE_USER_DATA_DIR = "C:\\Users\\YOUR_USERNAME\\AppData\\Local\\Microsoft\\Edge\\User Data"  # Replace YOUR_USERNAME with your actual Windows username
SOUND_FILE = "skip.mp3"  # Path to your sound file

# !join Command configuration
ADMIN_ROLE_NAME = ["Admin", "Moderator"]  # Role names to be notified for join invites
JOIN_INVITE_MESSAGE = "Your bot is live! Join the Streaming VC: https://discord.com/channels/YOUR_GUILD_ID/YOUR_STREAMING_VC_ID"  # Replace placeholders with actual IDs

# Global hotkey configuration for skipping Omegle stranger
ENABLE_GLOBAL_HOTKEY = True
GLOBAL_HOTKEY_COMBINATION = "alt+`"  # Hotkey combination to trigger the skip command

# Voice channel moderation settings
VC_MODERATION_PERMANENTLY_DISABLED = False  # Set to True to disable auto-moderation of the voice channel

# Command cooldowns and purge delay (in seconds)
COMMAND_COOLDOWN = 5  
HELP_COOLDOWN = 5     
PURGE_DELAY = 5       

# Welcome message (displayed when a new member joins)
WELCOME_MESSAGE = (
    "Welcome to Discord {mention}! 😎\n"
    "Go to https://discord.com/channels/{GUILD_ID}/{COMMAND_CHANNEL_ID} then type !help"
)

# Rules message (sent to users joining the Streaming VC)
RULES_MESSAGE = (
    "Welcome to the **Streaming VC**!\n\n"
    "**Rules:**\n"
    "1. Please have your camera on while in the Streaming VC. If your camera is off, you may be muted and deafened. Repeated violations may result in timeouts.\n"
    "2. Use commands responsibly to control the stream.\n"
    "3. Ensure to stop the bot when not in use to avoid unnecessary bans.\n\n"
    "Thank you for your cooperation!"
)

# Camera enforcement timing configuration
CAMERA_OFF_ALLOWED_TIME = 30  # Seconds allowed with camera off before recording a violation.
TIMEOUT_DURATION_SECOND_VIOLATION = 60  # Timeout duration in seconds for the second violation.
TIMEOUT_DURATION_THIRD_VIOLATION = 300  # Timeout duration in seconds for the third or subsequent violations.
