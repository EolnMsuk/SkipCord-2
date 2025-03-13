# config.py

# Replace with proper IDs (as integers)
# Your Discord server's unique ID (e.g., 123456789012345678)
GUILD_ID = 123456789012345678            # Replace with your Discord Server ID

# Channel IDs used by the bot:
# - Command channel: where commands should be issued
# - Chat channel: for general chat messages
# - Streaming VC: the voice channel used for streaming
# - Hell VC: a channel used for auto-moderation actions
COMMAND_CHANNEL_ID = 234567890123456789   # Replace with your Command Channel ID
CHAT_CHANNEL_ID = 345678901234567890       # Replace with your Chat Channel ID
STREAMING_VC_ID = 456789012345678901       # Replace with your Streaming Voice Channel ID
HELL_VC_ID = 567890123456789012            # Replace with your Hell VC ID

# Replace with IDs of Admins who can bypass camera checks and run mod commands.
# Use your own Discord user IDs (as integers) below.
ALLOWED_USERS = {
    111111111111111111,  # Replace with the actual allowed user ID
    222222222222222222,  # Replace with the actual allowed user ID
    333333333333333333,  # Replace with the actual allowed user ID
    444444444444444444   # Replace with the actual allowed user ID
}

# Role names allowed to use the !whois command in addition to ALLOWED_USERS.
WHOIS_ALLOWED_ROLE_NAMES = ["Admin", "Admen"]

# URL of the Omegle (or similar) video page.
OMEGLE_VIDEO_URL = "https://uhmegle.com/video"  # Replace if using a different URL

# Edge browser user data directory.
# IMPORTANT: Replace YOUR_USERNAME with your actual Windows username.
EDGE_USER_DATA_DIR = "C:\\Users\\YOUR_USERNAME\\AppData\\Local\\Microsoft\\Edge\\User Data"

# Sound file path (ensure the file exists in your project folder or provide a full path)
SOUND_FILE = "skip.mp3"

# !join Command configuration
# Roles to notify via DM (use role names exactly as they appear in your server)
ADMIN_ROLE_NAME = ["Admin", "Admen"]
# Join invite message: update the channel IDs/links as needed.
JOIN_INVITE_MESSAGE = (
    "The Stream Bot is Live! Please join for OmegleStream Group VC: "
    "https://discord.com/channels/YOUR_GUILD_ID/YOUR_STREAMING_VC_ID"
)

# Global hotkey configuration for host to trigger a skip command.
ENABLE_GLOBAL_HOTKEY = True
GLOBAL_HOTKEY_COMBINATION = "alt+`"  # Adjust as needed

# Voice Channel (VC) Moderation settings:
VC_MODERATION_PERMANENTLY_DISABLED = False

# Cooldown settings (in seconds)
COMMAND_COOLDOWN = 5  # Seconds between allowed commands
HELP_COOLDOWN = 5     # Seconds between help menu triggers
PURGE_DELAY = 5       # Delay between purge actions

# Rules message sent via DM to new members joining the Streaming VC.
RULES_MESSAGE = (
    "Welcome to the **Streaming  📷** VC!\n\n"
    "**Rules:**\n"
    "1. Please have your camera on while in the Streaming VC. If your camera is off, you will be muted and deafened. Repeated violations may result in timeouts.\n"
    "2. Use stream control commands (like !skip) responsibly.\n"
    "3. Be sure to !stop the bot when no one is using it to prevent issues.\n\n"
    "Thank you for your cooperation!"
)

# Camera enforcement timing configuration:
CAMERA_OFF_ALLOWED_TIME = 30  # Seconds a non-allowed user's camera can be off before a violation is recorded.
TIMEOUT_DURATION_SECOND_VIOLATION = 60  # Timeout (in seconds) for a second violation.
TIMEOUT_DURATION_THIRD_VIOLATION = 300  # Timeout (in seconds) for a third or subsequent violation.
