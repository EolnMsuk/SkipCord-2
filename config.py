# config.py

# Replace channel names with their IDs
GUILD_ID = 123456789012345678            # Replace with ID of your Discord server
COMMAND_CHANNEL_ID = 123456789012345678  # Replace with the actual ID of the command channel
CHAT_CHANNEL_ID = 123456789012345678     # Replace with the actual ID of the chat channel
STREAMING_VC_ID = 123456789012345678     # Replace with the actual ID of the Streaming VC
HELL_VC_ID = 123456789012345678          # Replace with the actual ID of the Hell VC

ALLOWED_USERS = {
    "StreamBot1234",
    "ExampleBot#1234", 
    "AnotherBot#5678"
}

SOUND_FILE = "skip.mp3"  # Name of skip.mp3 (put in same folder)
OMEGLE_VIDEO_URL = "https://omegle.com/video" # Example Omegle URL
EDGE_USER_DATA_DIR = "C:\\Users\\YOURUSERNAME\\AppData\\Local\\Microsoft\\Edge\\User Data"  # Replace NAME with your username
COMMAND_COOLDOWN = 5  # Seconds
HELP_COOLDOWN = 5     # Seconds
PURGE_DELAY = 5       # Delay between purge actions in seconds

# Welcome message (for on_member_join)
WELCOME_MESSAGE = (
    "Welcome to the Discord {mention}! 🎉\n"
    f"Go to https://discord.com/channels/{GUILD_ID}/{COMMAND_CHANNEL_ID} then type !help"
)

# Rules message
RULES_MESSAGE = (
    "Welcome to the **Streaming  📷** VC!\n\n"
    "**Rules:**\n"
    "1. Please have your camera on while in the Streaming VC. If your camera is off, you will be moved out, repeated violations may result in longer timeouts.\n"
    "2. Control skipping and more for the Omegle Stream Bot https://discord.com/channels/{GUILD_ID}/{COMMAND_CHANNEL_ID} GC.\n"
    "3. Please be sure to !stop the bot when no one is using it (prevents ban).\n\n"
    "Thank you for your cooperation!"
)
