# config.py
# This is the central configuration file for the SkipCord-2 bot.
# Fill in the placeholder values below with your specific server and user information.
# To get IDs for servers, channels, and users, enable Developer Mode in Discord
# (Settings -> Advanced -> Developer Mode), then right-click on the item and select "Copy ID".

# --- Essential Discord IDs ---
# These IDs are required for the bot to function correctly.

GUILD_ID = 123456789012345678              # The unique ID of your Discord server (guild).
COMMAND_CHANNEL_ID = 123456789012345678    # The ID of the text channel where the !help menu will be posted and commands are expected.
CHAT_CHANNEL_ID = 123456789012345678       # The ID of the main text channel for general announcements (joins, leaves, bans, etc.).
STREAMING_VC_ID = 123456789012345678       # The ID of the primary voice channel where the stream will be "watched" and moderated.
PUNISHMENT_VC_ID = 123456789012345678      # The ID of the voice channel where users are moved for their first camera-off violation.
ALT_VC_ID = None                           # (Optional) The ID of a second voice channel to monitor for camera enforcement.

# --- Statistics & Analytics ---
# Configure the daily automated statistics reporting.

AUTO_STATS_CHAN = 123456789012345678       # The ID of the channel where daily VC time reports will be posted.
AUTO_STATS_HOUR_UTC = 5                    # The UTC hour (0-23) when the daily stats report is posted and data is cleared. (e.g., 5 = 5:00 AM UTC).
AUTO_STATS_MINUTE_UTC = 0                  # The UTC minute (0-59) for the daily stats report.


# A set of user IDs to exclude from all statistical tracking (VC time, command usage, etc.).
# Useful for bots or alternate accounts.
# Example: STATS_EXCLUDED_USERS = {333333333333333333}
STATS_EXCLUDED_USERS = set()

# The user ID of any music bot you use. This will prevent the moderation system
# from taking action against it.
MUSIC_BOT = 123456789012345678

# --- Global Hotkey ---
# (Optional) Configure a system-wide hotkey on the host machine to trigger a skip.

ENABLE_GLOBAL_HOTKEY = True                 # Set to True to enable the hotkey, False to disable.
GLOBAL_HOTKEY_COMBINATION = "alt+grave"     # The key combination to trigger the skip. Note: grave = ~ key  (e.g., "alt+s", "ctrl+shift+f12")

# --- User Permissions ---
# Control who has administrative access to the bot.

# A set of user IDs that have full, unrestricted access to all bot commands.
# These users bypass all permission checks, cooldowns, and channel restrictions.
# Example: ALLOWED_USERS = {111111111111111111, 222222222222222222}
ALLOWED_USERS = {123456789012345678}

# A list of role names that grant access to admin-level commands (e.g., !purge, !modon).
# Users with these roles can use sensitive commands but are still subject to channel restrictions.
# Example: ADMIN_ROLE_NAME = ["Moderator", "Stream Admin"]
ADMIN_ROLE_NAME = ["Admin", "Mod"]

# --- Browser & Stream Automation ---
# Settings for controlling the Selenium-driven web browser.

OMEGLE_VIDEO_URL = "https://www.omegle.com/video"  # The URL the bot will navigate to for streaming.
# SKIP_COMMAND_KEY = ["Escape", "Escape"] # (Optional) You can uncomment and customize the keys used for the skip command's browser automation.

# (Optional) Provide a direct path to your msedgedriver.exe if you want to manage it manually.
# If set to None, the bot will attempt to download and manage the correct driver automatically.
# Example: EDGE_DRIVER_PATH = "C:/WebDrivers/msedgedriver.exe"
EDGE_DRIVER_PATH = None

# The path to your Microsoft Edge user data directory. This allows the browser to remember
# logins, cookies, and settings, which can be useful.
# To find this on Windows, go to `edge://version/` in your Edge browser and copy the "Profile path".
# IMPORTANT: Remove the `Default` part from the end of the path.
# Example: EDGE_USER_DATA_DIR = "C:/Users/YourUsername/AppData/Local/Microsoft/Edge/User Data"
EDGE_USER_DATA_DIR = "C:/Users/YourUser/AppData/Local/Microsoft/Edge/User Data"

# --- Moderation Settings ---
# Fine-tune the automated moderation features.

CAMERA_OFF_ALLOWED_TIME = 15               # Time in seconds a non-admin user can have their camera off in a moderated VC before a violation is triggered.
TIMEOUT_DURATION_SECOND_VIOLATION = 60     # Duration in seconds for the timeout on a user's 2nd camera-off violation (e.g., 300 = 5 minutes).
TIMEOUT_DURATION_THIRD_VIOLATION = 300     # Duration in seconds for the timeout on a user's 3rd (and subsequent) violations (e.g., 1800 = 30 minutes).

# --- Bot Behavior & Messages ---
# Customize messages and cooldowns.

COMMAND_COOLDOWN = 5                       # The number of seconds a user must wait between using omegle commands.
HELP_COOLDOWN = 5                          # The number of seconds a user must wait between using the help menu commands.

# The message sent to users via DM when they join the streaming VC for the first time.
RULES_MESSAGE = "Welcome! Please be respectful and follow Discord's ToS. Camera is required for non-admins in the streaming VC."

# A flexible list of messages sent for the !info command. Add as many as you like.
INFO_MESSAGES = [
    "**Welcome to the server!** This is an automated message.",
    "**Rules:** Be respectful, follow Discord ToS, and have fun.",
    "**Commands:** Use `!help` in the command channel to see the controls."
]

# The message sent via DM to admins when the !join command is used.
JOIN_INVITE_MESSAGE = "You've been invited to join the stream!"
