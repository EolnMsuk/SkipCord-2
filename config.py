# config.py

# Replace with proper IDs
GUILD_ID = 123456789012345678            # Replace with ID of your Discord server
COMMAND_CHANNEL_ID = 234567890123456789  # Replace with the actual ID of the command channel
CHAT_CHANNEL_ID = 345678901234567890     # Replace with the actual ID of the chat channel
STREAMING_VC_ID = 456789012345678901     # Replace with the actual ID of the Streaming VC
HELL_VC_ID = 567890123456789012          # Replace with the actual ID of the Hell VC

# !join Command configuration
ADMIN_ROLE_NAME = "Admin"  # Role name for members to be DMed
JOIN_INVITE_MESSAGE = "The Stream Bot is Live!" # Msg to send them

# Hotkey for host to skip omegle stranger
ENABLE_GLOBAL_HOTKEY = True
GLOBAL_HOTKEY_COMBINATION = "alt+`"

# When set to True, the VC moderation features (auto muting, deafening, moving, timeouts) are permanently disabled.
# In that case, the !modon and !modoff commands will have no effect.
VC_MODERATION_PERMANENTLY_DISABLED = False

# Replace with IDs of Admins who have access to mod commands / do not need camera on in Streaming VC
ALLOWED_USERS = {
    111111111111111111,  # Replace with the actual user ID
    222222222222222222,  # Replace with the actual user ID
    333333333333333333,  # Replace with the actual user ID
    444444444444444444   # Replace with the actual user ID
}

SOUND_FILE = "skip.mp3"  # Path to your sound file
OMEGLE_VIDEO_URL = "https://omegle.com/video"  # URL of the Uhmegle site (video page)
EDGE_USER_DATA_DIR = "C:\\Users\\your_username\\AppData\\Local\\Microsoft\\Edge\\User Data"  # Edge browser user data directory
COMMAND_COOLDOWN = 5  # Seconds
HELP_COOLDOWN = 5     # Seconds
PURGE_DELAY = 5       # Delay between purge actions in seconds

# General Chat welcome msg for new members to the servers
WELCOME_MESSAGE = (
    "Welcome to the Discord {mention}! 😎\n"
    f"Go to https://discord.com/channels/{GUILD_ID}/{COMMAND_CHANNEL_ID} then type !help"
)

# Users will be sent this when they join the Streaming VC for the first time
RULES_MESSAGE = (
    "Welcome to the **Streaming  📷** VC!\n\n"
    "**Rules:**\n"
    "1. Please have your camera on while in the Streaming VC. If your camera is off, you will be moved out, repeated violations may result in longer timeouts.\n"
    "2. Control skipping and more for the Omegle Stream Bot https://discord.com/channels/123456789012345678/234567890123456789 GC.\n"
    "3. Please be sure to !pause the bot when no one is using it (prevents ban).\n\n"
    "Thank you for your cooperation!"
)
