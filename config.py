# config.py

# Replace with the ID of your Discord server (guild).
# To find your server ID, enable Developer Mode in Discord settings, right-click your server name, and select "Copy ID".
GUILD_ID = "YOUR_GUILD_ID_HERE"

# Replace with the IDs of your Discord channels.
# To find a channel ID, enable Developer Mode, right-click the channel name, and select "Copy ID".
COMMAND_CHANNEL_ID = "YOUR_COMMAND_CHANNEL_ID_HERE"  # Channel where bot commands are allowed
CHAT_CHANNEL_ID = "YOUR_CHAT_CHANNEL_ID_HERE"        # General chat channel for welcome messages
STREAMING_VC_ID = "YOUR_STREAMING_VC_ID_HERE"        # Voice channel for streaming (camera required)
HELL_VC_ID = "YOUR_HELL_VC_ID_HERE"                  # Voice channel for users who violate rules

# Add usernames of users who are allowed to use commands without being in the Streaming VC.
# Format: "username" or "username#discriminator" (e.g., "elonmusk4334" or "Jockie Music#8158").
ALLOWED_USERS = {
    "USERNAME_1",
    "USERNAME_2",
    "USERNAME_3"
}

# Cooldown settings (in seconds)
COMMAND_COOLDOWN = 5  # Cooldown between commands for non-allowed users
HELP_COOLDOWN = 5     # Cooldown between help menu uses
PURGE_DELAY = 5       # Delay between purge actions

# Path to the sound file played when skipping or refreshing Omegle.
# Place your sound file in the same directory as the bot or provide the full path.
SOUND_FILE = "skip.mp3"

# URL of the Uhmegle site (video page).
# Replace with the URL of the Omegle-like service you're using.
UHMEGLE_VIDEO_URL = "https://uhmegle.com/video"

# Welcome message sent to new members when they join the server.
# Use {mention} to mention the new member.
WELCOME_MESSAGE = (
    "Welcome to the Discord {mention}! 🎉\n"
    f"Go to https://discord.com/channels/{GUILD_ID}/{COMMAND_CHANNEL_ID} then type !help"
)

# Rules message sent to users when they join the Streaming VC.
# Customize this message to match your server's rules.
RULES_MESSAGE = (
    "Welcome to the **Streaming  📷** VC!\n\n"
    "**Rules:**\n"
    "1. Please have your camera on while in the Streaming VC. If your camera is off, you will be moved out, repeated violations may result in longer timeouts.\n"
    "2. Control skipping and more for the Omegle Stream Bot https://discord.com/channels/YOUR_GUILD_ID/YOUR_COMMAND_CHANNEL_ID GC.\n"
    "3. Please be sure to !stop the bot when no one is using it (prevents ban).\n\n"
    "Thank you for your cooperation!"
)
