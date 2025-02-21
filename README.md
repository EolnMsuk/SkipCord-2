# SkipCord-2: Omegle Streaming Bot for Discord

SkipCord-2 is a powerful Discord bot designed for streamers who use Omegle or similar platforms. It allows streamers to share their Omegle experience with others in a Discord voice channel, giving everyone the ability to control the stream using simple commands.

## Features:
- **Stream Control**: Users can skip, refresh, start, or pause the Omegle stream using commands like `!skip`, `!refresh`, `!start`, and `!pause`.
- **Camera Enforcement**: The bot enforces rules in the streaming voice channel, requiring users to have their cameras on. Violators are moved to a "Hell VC" or timed out.
- **Help Menu**: A periodic help menu is sent to the command channel, making it easy for users to learn how to use the bot.
- **Sound Effects**: The bot plays a sound effect when a skip or refresh command is executed, adding to the fun.
- **Automated Timeouts**: Users who repeatedly violate the camera policy are automatically timed out, with increasing durations for each offense.
- **Purge Command**: Allowed users can purge messages in the chat or command channels to keep things clean.

## How It Works:
The bot uses Selenium to control the Omegle stream in a browser window. It listens for commands in a designated Discord channel and performs actions like skipping or refreshing the stream. The bot also monitors the voice channel to ensure users follow the rules, and it sends welcome messages to new members.

## Why Use SkipCord-2?
If you're an Omegle streamer who wants to share your experience with friends or a community, SkipCord-2 makes it easy to manage the stream and keep everyone engaged. The bot's automated features ensure that the rules are followed, so you can focus on streaming.


SkipCord-2: Windows Setup & Configuration

Below is a step-by-step guide to installing and running SkipCord-2 on Windows:

--------------------------------------------------------------------------------
1) Prerequisites
--------------------------------------------------------------------------------
- **Python 3.9+** (preferably the latest stable 3.x version). 
  - Download from https://www.python.org/downloads/ if you don’t have it already.
  - Check installation: open Command Prompt (cmd) and run: python --version

- **pip** (usually bundled with Python).
  - Check by running: pip --version

- **Git** (optional, but helpful for version control).
  - Download from https://git-scm.com/ if needed.

- **Microsoft Edge** (latest) + **WebDriver** 
  - Our bot uses the ‘webdriver_manager’ library to auto-download the appropriate Edge driver. 
  - Make sure Edge is installed and up to date.

- **Discord Bot Token** 
  - Create a bot via https://discord.com/developers/applications
  - Enable “Message Content Intent” and “Server Members Intent” under the “Bot” tab if you need to read messages or track members.
  - Copy your bot token (you’ll store this in an environment variable or a `.env` file).

--------------------------------------------------------------------------------
2) Project Folder & Files
--------------------------------------------------------------------------------
- Place the following files together in one folder (or in a dedicated Git repository):
   1. **bot.py** (the main bot code)
   2. **config.py** (your server IDs and settings) 
   3. **.env** (storing your BOT_TOKEN)
   4. Any “mp3” or media files your bot needs to play in Discord (e.g., “skip.mp3”).

Example `requirements.txt` contents:

-----------------------------------
discord.py
python-dotenv
selenium
webdriver-manager
-----------------------------------

--------------------------------------------------------------------------------
3) Installing Dependencies
--------------------------------------------------------------------------------
Open Command Prompt in your bot’s folder (Shift + Right-click → “Open PowerShell window here” or “Open Command window here”) and run:

   pip install -U discord.py python-dotenv selenium webdriver-manager

This installs the core libraries:
- `discord.py` for Discord bot functionality
- `python-dotenv` for reading environment variables from `.env`
- `selenium` for browser automation
- `webdriver-manager` for automatic EdgeDriver management

--------------------------------------------------------------------------------
4) Configure Your Bot
--------------------------------------------------------------------------------

### (a) Set Your .env / Environment Variable
Create a file named `.env` (in the same folder as `bot.py`) with contents like:

   BOT_TOKEN=YOUR_BOT_TOKEN_HERE


### (b) Adjust config.py
- **GUILD_NAME**: Replace `"YourDiscordServerName"` with the exact name of your Discord server (case-sensitive).
- **COMMAND_CHANNEL_ID**, **CHAT_CHANNEL_ID**, **STREAMING_VC_ID**, **HELL_VC_ID**: 
  Put your actual channel or voice channel IDs as integers. 
  Right-click your channels in Discord (Developer Mode enabled) to copy IDs.
- **ALLOWED_USERS**: A set of usernames#discriminator who can bypass camera checks or run powerful commands. 
- **UHMEGLE_VIDEO_URL**: If not using Uhmegle, replace with your desired site link.

--------------------------------------------------------------------------------
5) Edit Selenium Edge Profile Path
--------------------------------------------------------------------------------
In `bot.py`, there is a function `init_selenium()` that includes:
Replace `"C:\\users\\NAME\\Edge\\UserData"` with an actual local path if you want to preserve cookies/logins for Omegle or Uhmegle. If you leave it blank, Selenium will create a temporary profile each time.

--------------------------------------------------------------------------------
6) Running the Bot
--------------------------------------------------------------------------------
From the Command Prompt (in the bot folder), run:

   python bot.py

If the bot successfully starts, you should see log info in your console:
   Bot is online as <YourBotNameHere>

Your bot will:
- Connect to Discord
- Launch (or attempt to launch) Microsoft Edge for Selenium
- Begin enforcing camera rules and waiting for commands like !skip, !refresh, !start, !pause, etc.

--------------------------------------------------------------------------------
7) Troubleshooting
--------------------------------------------------------------------------------
- **Edge or WebDriver Issues**: 
  Ensure Edge is updated, and let `webdriver_manager` handle the driver automatically. If there are version mismatches, try updating the “webdriver-manager” package: 
    pip install -U webdriver-manager
- **Bot Token Invalid**: 
  Double-check your `.env` or environment variable for typos.
- **Permissions**: 
  Make sure your bot’s role in Discord has permission to connect to voice channels, move members, time out members, read messages, etc. 
  Under “Server Settings → Roles”, confirm the bot’s role is set properly.

--------------------------------------------------------------------------------
That’s it! Once it’s set up, your bot will run on Windows, automatically controlling Omegle (or Uhmegle) through Selenium, allowing you and your camera-enabled friends to skip or refresh quickly without manually touching the browser every time.
