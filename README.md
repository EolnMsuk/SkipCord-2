# SkipCord-2: Modular Omegle Streaming Bot for Discord

SkipCord-2 is a powerful, now fully modular, Discord bot designed for streamers who use Omegle or similar platforms. It allows streamers to share their Omegle experience with others in a Discord voice channel, giving everyone the ability to control the stream using a button menu or commands. The bot includes advanced moderation features, detailed logging, automated enforcement of streaming rules, and a new asynchronous architecture for improved performance.

## Key Features

### User Commands

* **!skip** - Skips the current stranger on Omegle.
* **!refresh** - Refreshes the page (to fix disconnection issues).
* **!pause** - Pauses Omegle temporarily.
* **!start** - Re-initiates the Omegle stream by skipping.
* **!paid** - Redirects after someone pays for an unban.
* **!rules** - Posts and DMs the server rules.
* **!help** - Displays the interactive help menu with buttons.
* **!info** / !about - Posts and DMs server information.
* **!owner / !admin** - Lists Admins and Owners.
* **!commands** - Lists all available commands.

### Admin/Allowed Commands

* **!timeouts** - Lists current timeouts and recent timeout removals.
* **!times** - Shows voice channel user time statistics.
* **!roles** - Lists all roles and their members.
* **!rtimeouts** - Removes all active timeouts from users.

### Allowed Users Only Commands

* **!whois** - Lists recent actions (timeouts, kicks, bans, joins, leaves).
* **!stats** - Lists detailed VC Time and command usage statistics.
* **!purge** - Purges a specified number of messages from a channel.
* **!top** - Lists the top 10 oldest Discord accounts in the server.
* **!bans** / !banned - Lists all banned users with reasons.
* **!join** - Sends a join invite DM to all users with an admin role.
* **!clear** - Clears all VC time and command usage data.
* **!hush** - Server-mutes everyone in the Streaming VC.
* **!secret** - Server-mutes and deafens everyone in the Streaming VC.
* **!rhush** - Removes mute status from everyone in the Streaming VC.
* **!rsecret** - Removes mute and deafen status from everyone in the Streaming VC.
* **!modoff** - Temporarily disables VC moderation.
* **!modon** - Re-enables VC moderation.
* **!shutdown** - Safely shuts down the bot.

### Enhanced Features

* **Asynchronous Browser Control**: Selenium tasks now run in a separate thread, preventing the bot from freezing during browser operations.
* **VC Time Tracking**: Tracks time users spend in the streaming VC, with daily auto-stats for top users.
* **Auto-Pause**: Automatically pauses the stream when the last user with a camera on leaves or turns it off.
* **Multiple VC Support**: Monitors both a primary Streaming VC and an Alternate VC for camera enforcement.
* **Global Hotkey**: A keyboard shortcut can be configured to trigger the skip command from anywhere on the host machine.
* **State Persistence**: All critical data (stats, violations, timeouts) is saved on shutdown and reloaded on startup.

### Automated Systems

* **Camera Enforcement**:
    * Non-allowed users without cameras are automatically muted/deafened.
    * 1st violation: Moved to a designated punishment VC.
    * 2nd violation: Short timeout.
    * 3rd+ violations: Longer timeout.
* **Media-Only Channel**: Automatically deletes any messages in a designated channel that do not contain an image, video, or other media attachment.
* **Daily Auto-Stats**: Posts the top 10 most active VC users daily at a configured time, then automatically clears the statistics.
* **Activity Logging**: Detailed logs for all commands, events, new members, role changes, and join/leave notifications.

![v4](https://github.com/user-attachments/assets/b860ca2d-5b4b-4525-b4a3-5a7da112358a)

---

# SkipCord-2: Setup & Configuration (v5)

## 1) Prerequisites

* **Microsoft Edge**: Ensure Edge is installed and up to date.
* **Python 3.9+**: Install from [python.org](https://www.python.org/downloads/). Make sure to check "Add Python to PATH".
* **Dependencies**: Open Command Prompt (cmd.exe) as an administrator and run:
    `pip install -U discord.py python-dotenv selenium webdriver-manager keyboard`

## 2) Create a Discord Bot

1.  Go to the [Discord Developer Portal](https://discord.com/developers/applications) and create a new application/bot.
2.  Under the "Bot" tab, enable the following **Privileged Gateway Intents**:
    * Message Content Intent
    * Server Members Intent
    * Presence Intent
3.  Copy your **Bot Token** and keep it safe.
4.  Go to https://discordapi.com/permissions.html#1088840794048 and replace the Client ID with your own.
5.  Use the new link (at bottom) to invite your bot to the server.

<img width="563" height="229" alt="perms" src="https://github.com/user-attachments/assets/45c9d335-3e3b-4866-82ef-a3d143eab00d" />

## 3) File Setup

Create a folder for your bot and place the following files inside it:

* `bot.py` (the main bot file)
* `omegle.py` (handles Omegle browser automation)
* `helper.py` (handles command logic and event notifications)
* `tools.py` (contains supporting functions and data classes)
* `config.py` (your server's configuration)
* `.env` (a file containing your bot token)

Edit / Create the `.env` file (rename it). Open it and add the following line, replacing `your_token_here` with your actual token:
`BOT_TOKEN=your_token_here`

## 4) Configure `config.py`

Open `config.py` and replace the placeholder values with your server's specific IDs and settings.

```python
# Example config.py
GUILD_ID = 1234567890                # Your server ID
COMMAND_CHANNEL_ID = 1234567890      # Channel for commands
CHAT_CHANNEL_ID = 1234567890         # General chat channel
STREAMING_VC_ID = 1234567890         # Main streaming voice channel
ALT_VC_ID = 1234567890               # Alternate voice channel
PUNISHMENT_VC_ID = 1234567890        # Timeout voice channel
MEDIA_ONLY_CHANNEL_ID = 1234567890   # (Optional) Channel where only media is allowed
AUTO_STATS_CHAN = 1234567890         # Channel for daily auto-stats
AUTO_STATS_HOUR_UTC = 5              # UTC hour for auto-stats (0-23)
AUTO_STATS_MINUTE_UTC = 0            # UTC minute for auto-stats (0-59)

ALLOWED_USERS = {1234567890}          # Set of user IDs with full bot access
ADMIN_ROLE_NAME = ["Admin", "Mod"]   # List of role names for admin command access

OMEGLE_VIDEO_URL = "[https://omegle.com/](https://omegle.com/)"
EDGE_USER_DATA_DIR = "C:/Path/To/Your/Edge/User Data" # e.g., C:/Users/YourUser/AppData/Local/Microsoft/Edge/User Data

# Example of the flexible INFO_MESSAGES list
INFO_MESSAGES = [
    "**Welcome to the server!** Here is some basic info.",
    "Rule 1: Be respectful.",
    "Rule 2: Follow Discord's ToS."
]
```

## 5) Running the Bot

1.  **Important**: Close all running instances of the Microsoft Edge browser.
2.  Open your command prompt, navigate to the bot's folder, and run the bot using:
    `python bot.py`
3.  The bot will launch Edge, navigate to Omegle, and start all monitoring systems.
4.  **Troubleshooting**:
    * If Edge doesn't launch, double-check that the `EDGE_USER_DATA_DIR` path in `config.py` is correct.
    * Check the `bot.log` file for any specific error messages.
