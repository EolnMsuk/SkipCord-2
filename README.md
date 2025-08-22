# SkipCord-2: Omegle Streaming Bot for Discord (v7)

SkipCord-2 is a powerful, fully modular Discord bot designed for streamers who use Omegle or similar platforms. It allows streamers to share their Omegle experience with others in a Discord voice channel, giving everyone the ability to control the stream using an interactive button menu. The bot includes advanced moderation features, detailed logging, automated enforcement of streaming rules, and a fully asynchronous architecture for rock-solid performance.

## Key Features

### **Stream Controls & User Experience**

* **Interactive Button Menu**: Users can control the stream (`!skip`, `!info`, `!refresh` etc.) with a clean, persistent button menu.
* **VC Time Tracking**: Tracks the cumulative time users spend in moderated voice channels, with daily leaderboards via `!times`.
* **Auto-Pause**: Automatically refreshes (pauses) the stream when the last user with their camera on leaves the VC or turns their camera off. This can be disabled in the config.
* **Global Hotkey**: A keyboard shortcut can be configured to trigger the `!skip` command from anywhere on the host machine.
* **State Persistence**: All critical data (stats, violations, timeouts, event history) is saved to a `data.json` file and reloaded on startup, ensuring no data is lost on restart or crash.

### **Advanced Moderation & Automation**

* **Camera Enforcement**:
    * Non-admin users without cameras in a moderated VC are automatically muted/deafened.
    * **1st Violation**: User is moved to a designated punishment VC.
    * **2nd Violation**: User receives a short timeout.
    * **3rd+ Violations**: User receives a longer timeout.
* **Media-Only Channel**: Automatically deletes any messages in a designated channel that do not contain an image, video, link embed, or other media attachment.
* **Daily Auto-Stats**: Posts a full analytics report (VC time, command usage, etc.) daily at a configured UTC time, then automatically clears all statistics for the next day.
* **Comprehensive Logging**: Uses `loguru` for detailed, color-coded logs of all commands, moderation actions, and server events (joins, leaves, bans, role changes).

### **Comprehensive Event Notifications**

The bot ensures administrators are always informed with a robust, event-driven notification system. Using rich, detailed embeds sent to a designated chat channel, it provides real-time updates for all significant server activities.

* **Member Activity**: Joins, Leaves, Kicks, Bans, and Unbans.
* **Moderation Actions**: Timeouts Added/Removed and Role Changes.
* **Bot & Stream Status**: Bot Online, Stream Auto-Pause, and Browser Health notifications.

---

## Command List

### 👤 User Commands

*(Requires being in the Streaming VC with camera on)*

* `!skip` / `!start`: Skips the current Omegle user.
* `!refresh` / `!pause`: Refreshes the Omegle page.
* `!info` / `!about`: Shows server information and rules.
* `!rules`: Displays the server rules.
* `!times`: Shows the top 10 most active VC users.

### 🛡️ Admin Commands

*(Requires Admin Role or being an Allowed User + Camera On)*

* `!help`: Sends the interactive help menu.
* `!bans` / `!banned`: Lists all banned users.
* `!timeouts`: Shows currently timed-out users.
* `!rtimeouts`: Removes all active timeouts.
* `!display <user>`: Shows a detailed profile for a user.
* `!commands`: Shows this list of all commands.

### 👑 Owner Commands (Allowed Users Only)

*(No channel or VC restrictions)*

* `!purge <count>`: Deletes a specified number of messages.
* `!shutdown`: Safely shuts down the bot.
* `!hush` / `!secret`: Server-mutes (and deafens) all non-admin users.
* `!rhush` / `!rsecret`: Removes server-mutes (and deafens).
* `!modon` / `!modoff`: Toggles automated VC moderation.
* `!disablenotifications`: Toggles event notifications OFF.
* `!enablenotifications`: Toggles event notifications ON.
* `!disable <user>`: Prevents a user from using commands.
* `!enable <user>`: Re-enables a disabled user from using commands.
* `!ban <user>`: Interactively bans user(s).
* `!unban <user_id>`: Interactively unbans a user by ID.
* `!unbanall`: Interactively unbans all users.
* `!top`: Lists the top 10 oldest server members and Discord accounts.
* `!roles`: Lists all server roles and their members.
* `!admin` / `!owner`: Lists configured owners and admins.
* `!whois`: Shows a 24-hour report of all server activity.
* `!stats`: Shows a detailed analytics report.
* `!join`: DMs a join invite to all users with an admin role.
* `!clearstats`: Clears all statistical data.
* `!clearwhois`: Clears all historical event data.

---

# Setup & Configuration (v7.0)

## 1) Prerequisites

* **Microsoft Edge**: Ensure the Edge browser is installed and up-to-date.
* **Python 3.9+**: Install from [python.org](https://www.python.org/downloads/). Make sure to check "Add Python to PATH" during installation.
* **Dependencies**: Open cmd.exe as Admin then run: 

`pip install discord.py python-dotenv selenium webdriver-manager loguru keyboard pyautogui`

## 2) Create a Discord Bot

1.  Go to the [Discord Developer Portal](https://discord.com/developers/applications) and create a new application/bot.
2.  Navigate to the "Bot" tab and enable the following **Privileged Gateway Intents**:
    * **Message Content Intent**
    * **Server Members Intent**
3.  Copy your **Bot Token** and keep it secret.
4.  Go to the "OAuth2" -> "URL Generator" tab. Select the `bot` and `applications.commands` scopes.
5.  In the "Bot Permissions" section below, select `Administrator`.
6.  Copy the generated URL and use it to invite your bot to your server.

## 3) File Setup

1.  Create a folder for your bot and place the python files (`bot.py`, `helper.py`, `omegle.py`, `tools.py`), your `config.py`, and `requirements.txt` inside.
2.  Create a new file named `.env` in the same folder.
3.  Add the following line to the `.env` file, replacing `your_token_here` with your actual bot token:
    `BOT_TOKEN=your_token_here`

## 4) Configure `config.py`

Open `config.py` and replace the placeholder values with your server's specific IDs and settings. You can get these IDs by enabling Developer Mode in Discord, then right-clicking on a server, channel, or user and selecting "Copy ID".

```python
# Example config.py

# --- REQUIRED SETTINGS ---
GUILD_ID = 123456789012345678                # Your Discord Server ID
COMMAND_CHANNEL_ID = 123456789012345678      # Channel for bot commands and help menu
CHAT_CHANNEL_ID = 123456789012345678         # Channel for join/leave/ban notifications
STREAMING_VC_ID = 123456789012345678         # Main streaming voice channel
PUNISHMENT_VC_ID = 123456789012345678        # VC where users are moved for a first violation
OMEGLE_VIDEO_URL = "[https://omegle.com/video](https://omegle.com/video)" # URL for the streaming website
# Path to your Edge browser's user data directory (for saved logins, etc.)
# Find it by going to edge://version/ in your browser and copying the "Profile path"
EDGE_USER_DATA_DIR = "C:/Users/YourUser/AppData/Local/Microsoft/Edge/User Data"

# --- PERMISSIONS ---
# A set of user IDs with full bot access (bypasses all permissions checks)
ALLOWED_USERS = {123456789012345678, 987654321098765432}
# A list of role names that grant access to admin-level commands
ADMIN_ROLE_NAME = ["Admin", "Moderator"]

# --- OPTIONAL FEATURES ---
# (Set to None to disable)
ALT_VC_ID = None                     # A second voice channel to moderate
AUTO_STATS_CHAN = 123456789012345678 # Channel for daily auto-stats reports
MEDIA_ONLY_CHANNEL_ID = None         # Channel where only media is allowed
MOD_MEDIA = True                     # Enable/disable media-only channel moderation
EMPTY_VC_PAUSE = True                # If true, auto-pauses stream when VC is empty

# --- TIMING & MESSAGES ---
AUTO_STATS_HOUR_UTC = 5              # UTC hour for auto-stats (0-23)
AUTO_STATS_MINUTE_UTC = 0            # UTC minute for auto-stats (0-59)
CAMERA_OFF_ALLOWED_TIME = 30         # Seconds a user can have camera off before punishment
TIMEOUT_DURATION_SECOND_VIOLATION = 60  # Seconds for 2nd violation timeout
TIMEOUT_DURATION_THIRD_VIOLATION = 300 # Seconds for 3rd+ violation timeout

# A list of messages for the `!info` command. Each string is sent as a separate message.
INFO_MESSAGES = [
"This is an example info message. You can add more strings to this list to send multiple messages.",
"Use this to share server details, links, or other important information."
]

# Message sent via !join command
JOIN_INVITE_MESSAGE = "An admin has requested your presence in the stream! Join here: <#CHANNEL_ID>"
```

## 5) Running the Bot

1.  **Important**: Close all currently running instances of the Microsoft Edge browser.
2.  Open your command prompt, navigate to the bot's folder (`cd path/to/your/bot`), and run the bot using:
    `python bot.py`
3.  The bot will launch the Edge browser, navigate to the configured URL, and start all monitoring systems.
4.  **Troubleshooting**:
    * If the bot fails to start with a token error, ensure your `.env` file is correct and in the same folder.
    * If Edge doesn't launch, double-check that the `EDGE_USER_DATA_DIR` path in `config.py` is correct.
    * Check the `bot.log` file for any specific error messages.
