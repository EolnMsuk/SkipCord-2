# config.py

# Discord IDs (use your actual IDs in production)
GUILD_ID = 123456789012345678            # Discord server ID placeholder
COMMAND_CHANNEL_ID = 234567890123456789   # Command channel ID placeholder for bot commands
CHAT_CHANNEL_ID = 345678901234567890       # Chat channel ID placeholder for general chat
STREAMING_VC_ID = 456789012345678901       # Voice channel ID for streaming (e.g., for video streaming)
HELL_VC_ID = 567890123456789012            # Voice channel ID for enforcement actions (e.g., "Hell VC")

# User IDs for Admins who have access to mod commands and are exempt from camera requirements
ALLOWED_USERS = {
    111111111111111111,  # Replace with an actual admin user ID
    222222222222222222,  # Replace with an actual admin user ID
    333333333333333333,  # Replace with an actual admin user ID
    444444444444444444   # Replace with an actual admin user ID
}

# Role names allowed to use the !whois command in addition to ALLOWED_USERS.
WHOIS_ALLOWED_ROLE_NAMES = ["Admin", "Moderator"]

# URLs and file paths
OMEGLE_VIDEO_URL = "https://example.com/video"  # URL of the video page (replace with your actual URL if needed)
EDGE_USER_DATA_DIR = "C:\\Users\\USERNAME\\AppData\\Local\\Microsoft\\Edge\\User Data" # Replace UserName
SOUND_FILE = "skip.mp3"  # Path to your sound file to play in the voice channel

# Specify roles to notify and the invite message for admins.
ADMIN_ROLE_NAME = ["Admin", "Moderator"]
JOIN_INVITE_MESSAGE = "The Stream Bot is Live! Please join for the Stream Group VC: YOUR_INVITE_LINK"  # Replace YOUR_INVITE_LINK with your actual invite URL

# Global hotkey configuration for the host to trigger the skip command
ENABLE_GLOBAL_HOTKEY = True
GLOBAL_HOTKEY_COMBINATION = "alt+grave"

# Voice Channel Moderation settings
VC_MODERATION_PERMANENTLY_DISABLED = False

# Command and help menu cooldown settings (in seconds)
COMMAND_COOLDOWN = 5
HELP_COOLDOWN = 5
PURGE_DELAY = 5  # Delay between purge actions in seconds

# Rules message for new members (displayed when they join the streaming VC)
RULES_MESSAGE = (
    "Welcome to the **Streaming 📷** VC!\n\n"
    "**Rules:**\n"
    "1. Please have your camera on while in the Streaming VC. If your camera is off, you will be muted and deafened; repeated violations may result in timeouts.\n"
    "2. Control skipping and more for the bot at the designated channel.\n"
    "3. Please be sure to !stop the bot when no one is using it (to prevent bans).\n\n"
    "Thank you for your cooperation!"
)

# Camera enforcement timing configuration
CAMERA_OFF_ALLOWED_TIME = 30  # Seconds allowed with camera off before a violation is recorded.
TIMEOUT_DURATION_SECOND_VIOLATION = 60  # Timeout duration in seconds for a second violation.
TIMEOUT_DURATION_THIRD_VIOLATION = 300  # Timeout duration in seconds for a third or subsequent violation.

# Customizable skip command keys.
# List of keys to be sent sequentially to the browser (each key is sent with a 1-second delay)
SKIP_COMMAND_KEY = ["Escape", "Escape"]
