# config.py
# This is a template configuration file for the SkipCord-2 bot.
# Replace the placeholder values (like 0, None, or "path/to/...") with your actual server and user information.

# --- ⚙️ DISCORD SERVER CONFIGURATION ⚙️ ---
# These IDs are ESSENTIAL. The bot will not work without them.
# How to get IDs: In Discord, go to User Settings > Advanced > enable Developer Mode.
# Then, right-click on your server icon or a channel name and select "Copy ID".

# (Required)
GUILD_ID = 0                 # PASTE YOUR SERVER'S ID HERE.
CHAT_CHANNEL_ID = 0          # PASTE the ID of your main chat channel. The bot will post announcements here (joins, bans, etc.).
COMMAND_CHANNEL_ID = 0       # PASTE the ID of the text channel where users will type commands like !skip.
STREAMING_VC_ID = 0          # PASTE the ID of the voice channel where the Omegle stream happens and camera rules are enforced.
PUNISHMENT_VC_ID = 0         # PASTE the ID of a "jail" voice channel. Users are moved here for their first camera violation.

# (Optional)
ALT_VC_ID = None             # (Optional) PASTE the ID of a SECOND voice channel where camera rules should also be enforced. Set to None if you don't have one.
AUTO_STATS_CHAN = None       # (Optional) PASTE the ID of a channel for daily automatic VC time reports. Set to None to have it post in CHAT_CHANNEL.
MEDIA_ONLY_CHANNEL_ID = None # (Optional) PASTE the ID of a channel where the bot will delete non-media messages. Set to None to disable.

# --- 👑 SERVER OWNER PERMISSIONS 👑 ---
# Controls who can use the most powerful bot commands (e.g., !shutdown, !ban).
# Add ONLY Server Owner USER ID (unless you know what you are doing).
# To get a user ID, right-click their name and "Copy ID".
# Example: ALLOWED_USERS = {987654321098765432} or {98765432109776546, 123456788932464}
ALLOWED_USERS = {0}

# --- 🛡️ ROLE CONFIGURATION 🛡️ ---
# List the EXACT names of roles that should have semi-admin-level command access.
# Case-sensitive! Example: ADMIN_ROLE_NAME = ["Moderator", "Server Admin"]
ADMIN_ROLE_NAME = ["Owner"]

# A set of user IDs to completely exclude from all statistical tracking (VC time, command usage).
# NOTE: All bots are automatically excluded by the code. This setting is for excluding the omegle host.
STATS_EXCLUDED_USERS = {0}

# --- 🌐 BROWSER AUTOMATION (SELENIUM) 🌐 ---
# These settings control the web browser that runs the Omegle stream.
# The URL the bot will open. Change only if you use a different Omegle mirror.
OMEGLE_VIDEO_URL = "https://uhmegle.com/video"

# (Optional but Recommended) The FULL file path to your msedgedriver.exe.
# If you leave this as None, the bot will try to download it automatically, which can sometimes fail.
# Example: EDGE_DRIVER_PATH = "C:/Users/YourUser/Downloads/msedgedriver.exe"
EDGE_DRIVER_PATH = "C:/Users/YourUser/Downloads/msedgedriver.exe"

# The FULL path to your Microsoft Edge "User Data" folder.
# This is crucial for the browser to remember settings and appear less like a bot.
# To find it: Open Edge, go to `edge://version/`, and copy the "Profile path".
# Then, remove the "Default" or "Profile X" part from the end of the path.
# Example: "C:/Users/YourUser/AppData/Local/Microsoft/Edge/User Data"
EDGE_USER_DATA_DIR = "C:/Users/YourUser/AppData/Local/Microsoft/Edge/User Data"

# --- ⏰ AUTOMATED STATS SCHEDULE (UTC TIME) ⏰ ---
# This determines when the daily stats report is posted and stats are reset.
# Uses 24-hour format. You can use a UTC time converter online to find the right time for your timezone.
AUTO_STATS_HOUR_UTC = 0                    # The hour (0-23) in UTC. Example: 14 for 2 PM UTC.
AUTO_STATS_MINUTE_UTC = 0                  # The minute (0-59) in UTC.

# --- ⚙️ GENERAL BOT SETTINGS ⚙️ ---
# If True, the bot will delete any message in the MEDIA_ONLY_CHANNEL_ID that isn't a picture, video, or link.
MOD_MEDIA = False

# If True, the bot will automatically pause/refresh the Omegle stream when the last user with a camera leaves the STREAMING_VC_ID.
EMPTY_VC_PAUSE = True

# --- ⌨️ GLOBAL HOTKEY ⌨️ ---
# Allows you to trigger a !skip from anywhere on your computer.
ENABLE_GLOBAL_HOTKEY = False

# The key combination. See the `keyboard` library documentation for format.
# Examples: "alt+s", "ctrl+shift+f12", "alt+`"
GLOBAL_HOTKEY_COMBINATION = "alt+grave"

# --- 👮 VOICE CHANNEL MODERATION 👮 ---
# The global cooldown in seconds between using Omegle commands (!skip, !refresh).
COMMAND_COOLDOWN = 5

# How long (in seconds) a user can have their camera off in a moderated VC before punishment.
CAMERA_OFF_ALLOWED_TIME = 30

# The timeout duration (in seconds) for a user's SECOND camera-off violation.
TIMEOUT_DURATION_SECOND_VIOLATION = 60      # 1 minute

# The timeout duration (in seconds) for a user's THIRD (and any subsequent) violation.
TIMEOUT_DURATION_THIRD_VIOLATION = 300      # 5 minutes

# --- 📝 CUSTOM MESSAGES 📝 ---
# The message DMed to users with an ADMIN_ROLE_NAME when the `!join` command is used.
JOIN_INVITE_MESSAGE = """
The stream is starting! Join the voice channel here: [Paste Invite Link or Channel Link]
"""

# The message for the `!rules` command and DMed to new users. Supports Discord markdown.
RULES_MESSAGE = """
## Welcome to the Server!
**Rule 1:** Be respectful.
**Rule 2:** Keep your camera on in the streaming voice channel.
**Rule 3:** No hateful or inappropriate content.
"""

# A list of messages for the `!info` command. Each string is sent as a separate message.
INFO_MESSAGES = [
"This is an example info message. You can add more strings to this list to send multiple messages.",
"Use this to share server details, links, or other important information."
]

# (Optional) You can customize the keys used for the skip command's browser automation.
# The default is ["Escape", "Escape"].
SKIP_COMMAND_KEY = None
