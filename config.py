# config.py

GUILD_NAME = "YourServerName"
COMMAND_CHANNEL_ID = 123456789012345678  # Discord channel ID for bot commands
CHAT_CHANNEL_ID = 987654321098765432    # Discord chat channel ID
STREAMING_VC_ID = 135791357913579135    # Discord voice channel for the stream
HELL_VC_ID = 246802468024680246         # "Hell" voice channel for moving offenders

ALLOWED_USERS = {
    "YourDiscordUsername#1234",
    "AnotherAllowedUser#9999",
    # ...
}

COMMAND_COOLDOWN = 5  # (seconds) Wait time between commands
HELP_COOLDOWN = 5     # (seconds) Not widely used in the current version
PURGE_DELAY = 5       # (seconds) Delay between purge actions

UHMEGLE_VIDEO_URL = "https://uhmegle.com/video"

RULES_MESSAGE = (
    "Welcome to the **Streaming VC**!\n\n"
    "**Rules:**\n"
    "1. Keep your camera on.\n"
    "2. Use the bot commands responsibly.\n"
    "3. No harassing or abusive behavior.\n\n"
    "Thank you for your cooperation!"
)
