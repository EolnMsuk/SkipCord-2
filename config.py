# -----------------------------------------------------------------------------
# SkipCord-2 (v2) Configuration File
# -----------------------------------------------------------------------------
# Instructions:
# 1. Replace all placeholder values (like 123456789012345678) with your actual IDs.
# 2. To get IDs, right-click on a server, channel, user, or role in Discord
#    and select "Copy ID". You must have Developer Mode enabled in your
#    Discord settings (Settings > Advanced > Developer Mode).
# 3. Ensure all paths use forward slashes (/), even on Windows.
# -----------------------------------------------------------------------------

# -- Server & Channel IDs --
# These IDs link the bot to your specific Discord server and channels.

GUILD_ID = 123456789012345678
# The unique ID of your Discord server (guild).

COMMAND_CHANNEL_ID = 123456789012345678
# The ID of the text channel where users should use bot commands.

CHAT_CHANNEL_ID = 123456789012345678
# The ID of your main chat channel, where the bot will post notifications
# (joins, leaves, bans, timeouts, etc.).

STREAMING_VC_ID = 123456789012345678
# The ID of the primary voice channel where you will be streaming and where
# camera enforcement is active.

ALT_VC_ID = 123456789012345678
# The ID of a secondary voice channel to monitor for camera enforcement.
# Users in this VC will also be subject to the camera-on rules.

PUNISHMENT_VC_ID = 123456789012345678
# The ID of the voice channel where users are moved for their first
# camera-off violation.

MEDIA_ONLY_CHANNEL_ID = 123456789012345678
# (Optional) The ID of a channel where the bot should enforce a "media-only"
# rule, deleting any messages that don't contain an image, video, or file.
# Set to None or 0 if you don't want to use this feature.


# -- User Permissions & Roles --
# Define who has administrative control over the bot.

ALLOWED_USERS = {123456789012345678, 987654321098765432}
# A set of user IDs that have full, unrestricted access to all bot commands.
# This should typically include the server owner and trusted administrators.
# Use a set with curly braces {} and separate multiple IDs with commas.

ADMIN_ROLE_NAME = ["Admin", "Moderator", "Stream Mod"]
# A list of role names that grant access to admin-level commands (like !timeouts).
# Users with these roles can use admin commands but not owner-only commands
# (like !shutdown or !clear). The names must match your server's roles exactly.

MUSIC_BOT = 123456789012345678
# The user ID of any music bot you use. This exempts the bot from camera
# enforcement and other moderation actions. Set to 0 if not needed.

STATS_EXCLUDED_USERS = {123456789012345678}
# A set of user IDs to exclude from all statistics tracking (!stats, !times).
# Useful for alt accounts or other bots.


# -- Automation & Moderation Settings --
# Configure the bot's automated behaviors.

VC_MODERATION_PERMANENTLY_DISABLED = False
# Set to True to completely disable all automated VC moderation (camera checks,
# mutes, etc.). This cannot be overridden by the !modon command.

CAMERA_OFF_ALLOWED_TIME = 15
# The number of seconds a user can have their camera off in a monitored VC
# before a violation is triggered.

TIMEOUT_DURATION_SECOND_VIOLATION = 300
# The duration in seconds for a user's timeout on their 2nd camera-off violation.
# 300 seconds = 5 minutes.

TIMEOUT_DURATION_THIRD_VIOLATION = 900
# The duration in seconds for a user's timeout on their 3rd (and subsequent)
# camera-off violations. 900 seconds = 15 minutes.

AUTO_STATS_CHAN = 123456789012345678
# The ID of the channel where the bot will automatically post the daily
# VC time report before clearing the stats.

AUTO_STATS_HOUR_UTC = 5
# The UTC hour (0-23) when the daily auto-stats report will be posted and
# statistics will be cleared. E.g., 5 for 5:00 AM UTC.

AUTO_STATS_MINUTE_UTC = 0
# The UTC minute (0-59) for the daily auto-stats task.


# -- Browser & Hotkey Settings --
# Configure the Selenium browser automation.

OMEGLE_VIDEO_URL = "https://www.omegle.com/"
# The URL the bot will navigate to when using !start, !refresh, or !paid.

EDGE_USER_DATA_DIR = "C:/Users/YourUsername/AppData/Local/Microsoft/Edge/User Data"
# The absolute path to your Microsoft Edge user data directory. This allows the
# bot to use your existing Edge profile, potentially bypassing captchas.
# To find it, go to `edge://version` in your Edge browser and copy the "Profile path".
# IMPORTANT: Replace the final `/Default` part with `/` and use forward slashes.

ENABLE_GLOBAL_HOTKEY = True
# Set to True to enable the global keyboard hotkey for the skip command.
# Set to False to disable it.

GLOBAL_HOTKEY_COMBINATION = "ctrl+alt+s"
# The key combination for the global skip hotkey.
# See the 'keyboard' library documentation for format examples.

SKIP_COMMAND_KEY = ["Escape", "Escape"]
# The key(s) the bot will simulate pressing in the browser to skip.
# For Omegle, pressing Escape twice is the standard way to disconnect.


# -- Messages & Cooldowns --
# Customize the bot's text responses and command timing.

COMMAND_COOLDOWN = 3
# The number of seconds a user must wait between using commands.

HELP_COOLDOWN = 120
# The number of seconds a user must wait between using the !help command.

RULES_MESSAGE = (
    "1. Be respectful to everyone.\n"
    "2. No hate speech, racism, or harassment.\n"
    "3. Follow Discord's Terms of Service.\n"
    "4. Keep discussions in the appropriate channels."
)
# The message content for the !rules command. Use \n for new lines.

JOIN_INVITE_MESSAGE = "The stream is starting! Come join us in the voice channel."
# The DM sent to admins when an allowed user uses the !join command.

INFO_MESSAGES = [
    "**Welcome to the server!** This is an automated Omegle streaming community.",
    "Use the buttons or commands in the designated channel to control the stream.",
    "Please read the #rules channel for community guidelines.",
    "If you have any issues, please contact an Admin."
]
# A list of messages sent by the !info or !about command. The bot will send
# each string in this list as a separate message.
