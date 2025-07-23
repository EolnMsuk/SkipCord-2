# SkipCord-2: Omegle Streaming Bot for Discord (v6)

SkipCord-2 is a powerful, fully modular Discord bot designed for streamers who use Omegle or similar platforms. It allows streamers to share their Omegle experience with others in a Discord voice channel, giving everyone the ability to control the stream using a button menu or commands. The bot includes advanced moderation features, detailed logging, automated enforcement of streaming rules, and a fully asynchronous architecture for rock-solid performance.

## Key Features

### User-Facing Commands (Camera On or Allowed User)
* `!skip` / `!start` - Skips the current stranger or starts a new chat.
* `!refresh` / `!pause` - Refreshes the Omegle page to fix disconnections or pause the stream.
* `!info` / `!about` - Shows server information and rules.
* `!times` - Shows the top 10 most active voice channel users.
* `!rules` - Displays the server rules.

### Admin & Allowed User Commands
* `!help` - Displays the interactive Omegle control menu.
* `!timeouts` - Lists current timeouts and recent manual timeout removals.
* `!rtimeouts` - Removes all active timeouts from users.
* `!admin` / `!owner` - Lists configured Admins and Owners.
* `!roles` - Lists all server roles and their members.
* `!commands` - Shows a complete list of all available bot commands.
* `!bans` / `!banned` - Lists all banned users with reasons.
* `!top` - Lists the top 10 oldest Discord accounts and server members.
* `!join` - Sends a join invite DM to all users with an admin role.
* `!whois` - Shows a detailed 24-hour report of all user activities (joins, leaves, kicks, bans, role changes, etc.).
* `!stats` - Lists detailed statistics for VC time and command usage.
* `!clear` - Resets all statistical data after confirmation.
* `!modon` / `!modoff` - Enables or disables the automated VC moderation system.
* `!hush` - Server-mutes all non-admin users in the Streaming VC.
* `!rhush` - Removes server-mutes.
* `!secret` - Server-mutes and deafens all non-admin users.
* `!rsecret` - Removes server-mutes and deafens.
* `!purge [number]` - Purges a specified number of messages from a channel.
* `!shutdown` - Safely shuts down the bot, saving all data.

### 🚀 Enhanced Features
* **Asynchronous Browser Control**: All Selenium browser tasks run in a separate thread, preventing the bot from freezing or lagging during web operations.
* **Robust Driver Management**: The bot automatically checks browser health and attempts to relaunch it if it crashes.
* **VC Time Tracking**: Tracks the cumulative time users spend in moderated voice channels, with daily leaderboards.
* **Auto-Pause**: Automatically refreshes (pauses) the stream when the last user with their camera on leaves the VC or turns their camera off.
* **Global Hotkey**: A keyboard shortcut can be configured to trigger the `!skip` command from anywhere on the host machine.
* **State Persistence**: All critical data (stats, violations, timeouts, event history) is saved to a `data.json` file and reloaded on startup, ensuring no data is lost on restart or crash.

### 🤖 Automated Systems
* **Camera Enforcement**:
    * Non-admin users without cameras in a moderated VC are automatically muted/deafened.
    * **1st Violation**: User is moved to a designated punishment VC.
    * **2nd Violation**: User receives a short timeout.
    * **3rd+ Violations**: User receives a longer timeout.
* **Media-Only Channel**: Automatically deletes any messages in a designated channel that do not contain an image, video, link embed, or other media attachment.
* **Daily Auto-Stats**: Posts the top 10 most active VC users daily at a configured UTC time, then automatically clears all statistics for the next day.
* **Comprehensive Logging**: Uses `loguru` for detailed, color-coded logs of all commands, moderation actions, and server events (joins, leaves, bans, role changes).

---

# SkipCord-2: Setup & Configuration (v6)

## 1) Prerequisites
* **Microsoft Edge**: Ensure the Edge browser is installed and up-to-date.
* **Python 3.9+**: Install from [python.org](https://www.python.org/downloads/). Make sure to check "Add Python to PATH" during installation.
* **Dependencies**: Open Command Prompt (cmd.exe) as an administrator and run:
    `pip install -U discord.py python-dotenv selenium webdriver-manager keyboard loguru`

## 2) Create a Discord Bot
1.  Go to the [Discord Developer Portal](https://discord.com/developers/applications) and create a new application/bot.
2.  Navigate to the "Bot" tab and enable the following **Privileged Gateway Intents**:
    * **Message Content Intent**
    * **Server Members Intent**
3.  Copy your **Bot Token** and keep it secret.
4.  Go to the "OAuth2" -> "URL Generator" tab. Select the `bot` and `applications.commands` scopes.
5.  In the "Bot Permissions" section below, select `Administrator`.
6.  Copy the generated URL at the bottom and use it to invite your bot to your server.

## 3) File Setup
Create a folder for your bot and place the following files inside:
* `bot.py` (main bot file)
* `omegle.py` (handles browser automation)
* `helper.py` (handles command logic and event notifications)
* `tools.py` (contains supporting functions and data classes)
* `config.py` (your server's configuration)
* `.env` (a new file you will create)

Create the `.env` file and add the following line, replacing `your_token_here` with your actual bot token:
`BOT_TOKEN=your_token_here`

## 4) Configure `config.py`
Open `config.py` and replace the placeholder values with your server's specific IDs and settings. You can get these IDs by enabling Developer Mode in Discord, then right-clicking on a server, channel, or user and selecting "Copy ID".

```python
# Example config.py
GUILD_ID = 1234567890                # Your Discord Server ID
COMMAND_CHANNEL_ID = 1234567890      # Channel for bot commands and help menu
CHAT_CHANNEL_ID = 1234567890         # Channel for join/leave/ban notifications
STREAMING_VC_ID = 1234567890         # Main streaming voice channel
PUNISHMENT_VC_ID = 1234567890        # VC where users are moved for a first violation
AUTO_STATS_CHAN = 1234567890         # Channel for daily auto-stats reports
MEDIA_ONLY_CHANNEL_ID = None         # (Optional) Channel where only media is allowed
ALT_VC_ID = None                     # (Optional) A second voice channel to moderate
AUTO_STATS_HOUR_UTC = 5              # UTC hour for auto-stats (0-23)
AUTO_STATS_MINUTE_UTC = 0            # UTC minute for auto-stats (0-59)

# A set of user IDs with full bot access (bypasses all permissions checks)
ALLOWED_USERS = {1234567890, 9876543210}
# A list of role names that grant access to admin-level commands
ADMIN_ROLE_NAME = ["Admin", "Moderator"]

OMEGLE_VIDEO_URL = "[https://omegle.com/video](https://omegle.com/video)"   # URL for the streaming website
# (Optional) Provide a direct path to msedgedriver.exe if you want to manage it manually.
# If set to None, the bot will download and manage it automatically.
EDGE_DRIVER_PATH = None # e.g., "C:/WebDrivers/msedgedriver.exe"
# Path to your Edge browser's user data directory (for saved logins, etc.)
EDGE_USER_DATA_DIR = "C:/Users/YourUser/AppData/Local/Microsoft/Edge/User Data"

# A flexible list of messages to be sent for the !info command
INFO_MESSAGES = [
    "**Welcome to the server!** Here is some basic info.",
    "Rule 1: Be respectful.",
    "Rule 2: Follow Discord's ToS."
]
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
