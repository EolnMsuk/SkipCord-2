# config.py

# All your bot's configuration and constants go here
GUILD_NAME = "YourGuildNameHere"  # Replace with your guild name

# Replace channel names with their IDs
COMMAND_CHANNEL_ID = 123456789012345678  # Replace with the actual ID of the command channel
CHAT_CHANNEL_ID = 123456789012345678     # Replace with the actual ID of the chat channel
STREAMING_VC_ID = 123456789012345678     # Replace with the actual ID of the Streaming VC
HELL_VC_ID = 123456789012345678          # Replace with the actual ID of the Hell VC

ALLOWED_USERS = {
    "User1", 
    "User2", 
    "User3#1234", 
    "BotName#1234"
}
COMMAND_COOLDOWN = 5  # Seconds
HELP_COOLDOWN = 5     # Seconds
PURGE_DELAY = 5       # Delay between purge actions in seconds

# This is no longer used for Selenium, but we keep it for reference
BROWSER_WINDOW_TITLE = "Uhmegle: Video Chat - Instant Messaging Worldwide as Omegle Alternative - Profile 1 - Microsoft​ Edge"

SOUND_FILE = "skip.mp3"  # Path to your sound file

# URL of the Uhmegle site (video page)
UHMEGLE_VIDEO_URL = "https://uhmegle.com/video"

# Welcome message (for on_member_join)
WELCOME_MESSAGE = (
    "Welcome to the Discord {mention}! 🎉\n"
    "Go to https://discord.com/channels/123456789012345678/123456789012345678 then type !help"
)

# Rules message
RULES_MESSAGE = (
    "Welcome to the **Streaming  📷** VC!\n\n"
    "**Rules:**\n"
    "1. Please have your camera on while in the Streaming VC. If your camera is off, you will be moved out, repeated violations may result in longer timeouts.\n"
    "2. Control skipping and more for the Omegle Stream Bot https://discord.com/channels/123456789012345678/123456789012345678 GC.\n"
    "3. Please be sure to !stop the bot when no one is using it (prevents ban).\n\n"
    "Thank you for your cooperation!"
)
