# Discord Server Configuration
GUILD_ID = 123456789012345678              # Replace with your Discord server ID
COMMAND_CHANNEL_ID = 987654321098765432    # Channel ID for bot commands
CHAT_CHANNEL_ID = 112233445566778899       # General chat channel ID
STREAMING_VC_ID = 876543210987654321       # Main streaming voice channel ID
ALT_VC_ID = 555555555555555555             # Alternate voice channel ID
PUNISHMENT_VC_ID = 999999999999999999      # "PUNISHMENT" VC for violators
AUTO_STATS_CHAN = 1111222233334444         # Channel for automatic stats posting

# Automated Stats Schedule (UTC)
AUTO_STATS_HOUR_UTC = 14                   # UTC hour to post stats (2 PM)
AUTO_STATS_MINUTE_UTC = 30                 # Minute to post stats

# User Permissions Configuration
ALLOWED_USERS = {                          # User IDs with full command access
    111111111111111111,
    222222222222222222,
    333333333333333333
}

# Role Configuration
ADMIN_ROLE_NAME = ["Admin", "Moderator"]   # Roles that can use admin commands
MUSIC_BOT = 444444444444444444             # ID of music bot (excluded from moderation)
STATS_EXCLUDED_USERS = {                   # Users excluded from statistics
    111111111111111111,
    444444444444444444
}

# Browser Automation Settings
OMEGLE_VIDEO_URL = "https://omegle.com"    # URL for video chat service
EDGE_USER_DATA_DIR = "C:\\Path\\To\\Edge\\User Data"  # Edge profile path

# Invite Message Configuration
JOIN_INVITE_MESSAGE = (
    "The Stream Bot is Live! Join our Group VC: "
    "https://discord.com/channels/SERVER_ID/CHANNEL_ID"
)

# Hotkey Configuration
ENABLE_GLOBAL_HOTKEY = True                # Enable/disable global hotkey
GLOBAL_HOTKEY_COMBINATION = "alt+grave"    # Hotkey for skip command

# Voice Channel Moderation Settings
VC_MODERATION_PERMANENTLY_DISABLED = False # Master switch for VC moderation
COMMAND_COOLDOWN = 5                       # Seconds between command uses
HELP_COOLDOWN = 5                          # Seconds between help menu uses

# Moderation Timing Configuration
CAMERA_OFF_ALLOWED_TIME = 30               # Seconds allowed with camera off
TIMEOUT_DURATION_SECOND_VIOLATION = 60     # Timeout for second violation (seconds)
TIMEOUT_DURATION_THIRD_VIOLATION = 300     # Timeout for third+ violations (seconds)

# Server Rules
RULES_MESSAGE = """# Streaming VC Rules

1. Camera must be ON while in voice channels
2. Keep your face visible in frame
3. No extended AFK (>5 minutes)
4. Follow the streamer's instructions
5. Be respectful to all participants"""

# Information Messages
INFO_MESSAGES = ["""# Community Streaming Bot

**About**: 
Our Discord features a streaming bot that hosts group video chats

**Commands**:
- !skip: Skip current video partner
- !help: Show available commands
- !rules: Display server rules

**Premium Features**:
Support our server to unlock:
- VIP roles with special permissions
- Extended command access
- Customization options"""]

# Optional Skip Key Configuration
# SKIP_COMMAND_KEY = ["Escape", "Escape"]  # Uncomment to customize skip keys
