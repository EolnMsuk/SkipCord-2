# Discord Server Configuration
GUILD_ID = 123456789012345678              # Your Discord server ID
COMMAND_CHANNEL_ID = 987654321098765432    # Channel ID for bot commands
CHAT_CHANNEL_ID = 112233445566778899       # General chat channel ID
STREAMING_VC_ID = 123456789012345670       # Main streaming voice channel ID
ALT_VC_ID = 123456789012345671             # Alternate voice channel ID
PUNISHMENT_VC_ID = 123456789012345672      # "PUNISHMENT" VC for violators

# User Permissions
ALLOWED_USERS = {
    123456789012345678,  # User IDs with full command access
    987654321098765432   # (Replace with your actual user IDs)
}

MUSIC_BOT = 876543210987654321  # ID of your music bot (excluded from moderation)

# Browser Automation Settings
OMEGLE_VIDEO_URL = "https://uhmegle.com/video"  # URL for Omegle video
EDGE_USER_DATA_DIR = "C:\\Users\\USERNAME\\AppData\\Local\\Microsoft\\Edge\\User Data"  # Edge profile path
SOUND_FILE = "skip.mp3"  # Sound file to play for commands

# Role and Invite Configuration
ADMIN_ROLE_NAME = ["Admin", "Admen", "God"]  # Roles that can use admin commands
JOIN_INVITE_MESSAGE = (
    "The Stream Bot is Live! Please join for OmegleStream Group VC: "
    "https://discord.gg/EXAMPLEINVITE"
)

# Hotkey Configuration
ENABLE_GLOBAL_HOTKEY = True  # Enable/disable global hotkey
GLOBAL_HOTKEY_COMBINATION = "alt+grave"  # Hotkey for skip command

# Voice Channel Moderation Settings
VC_MODERATION_PERMANENTLY_DISABLED = False  # Master switch for VC moderation
COMMAND_COOLDOWN = 5  # Seconds between command uses
HELP_COOLDOWN = 5     # Seconds between help menu uses

# Moderation Timing Configuration
CAMERA_OFF_ALLOWED_TIME = 29  # Seconds allowed with camera off before violation
TIMEOUT_DURATION_SECOND_VIOLATION = 60  # Timeout for second violation (seconds)
TIMEOUT_DURATION_THIRD_VIOLATION = 300  # Timeout for third+ violations (seconds)

# Server Rules and Information
RULES_MESSAGE = """
# OmegleStream

1. You must have Camera on while in the VC or the bot will auto deafen / mute / timeout you.
2. Control skipping strangers and more via the command channel. 

Thank you for your cooperation! 

**About**: This Discord features a streaming VC with a [SkipCord-2](https://github.com/EolnMsuk/SkipCord-2/) Discord Bot which hosts a 24/7 Group Omegle Call for anyone 18+ to join.

**Extra Roles**: Donate to get special roles (details removed for public sharing)
"""

# Info messages (can have multiple INFO#_MESSAGE entries)
INFO1_MESSAGE = """
# OmegleStream

**About**: This Discord features a streaming VC with a [SkipCord-2](https://github.com/EolnMsuk/SkipCord-2/) Discord Bot which hosts a 24/7 Group Omegle Call for anyone 18+ to join.
**Skipping**: Use the command channel to control the omegle bot - !help command for more info.
**Rules**: You must have Camera on while in the VC or the bot will auto deafen / mute / timeout you.

**Extra Roles**: Donate to get special roles (details removed for public sharing)
"""

# Skip Command Key Configuration (optional)
# SKIP_COMMAND_KEY = ["Escape", "Escape"]  # Uncomment to customize skip keys
