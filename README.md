# SkipCord 2

SkipCord 2 is a Discord bot designed to manage and automate interactions within a streaming voice channel (VC) on a Discord server. The bot is particularly useful for communities that use platforms like Omegle or Uhmegle for video chatting. It enforces rules, manages user interactions, and provides commands to control the streaming experience.

## Features

- **Streaming VC Management**: Automatically enforces rules such as requiring users to have their cameras on while in the streaming VC.
- **Command Controls**: Provides commands like `!skip`, `!refresh`, `!start`, and `!stop` to manage the streaming session.
- **Cooldown System**: Implements cooldowns to prevent command spamming.
- **User Violation Tracking**: Tracks user violations and applies appropriate actions such as moving users to a "Hell VC" or timing them out.
- **Selenium Integration**: Uses Selenium to interact with the Uhmegle website for skipping and refreshing the video chat.
- **Sound Notifications**: Plays sound notifications in the VC for certain actions like skipping or refreshing.

## Requirements

- Python 3.8 or higher
- Discord.py library
- Selenium
- FFmpeg (for sound playback)
- A Discord bot token


# Uhmegle Discord Bot Setup

## Overview

This bot uses [Discord.py](https://pypi.org/project/discord.py/) and [Selenium](https://www.selenium.dev/) to control [Uhmegle](https://uhmegle.com/) (similar to Omegle). It can:
1. Join your voice channel (VC) to play skip/refresh sounds.
2. Intercept chat commands in a specific Discord channel to skip, refresh, start, or stop the Uhmegle session.
3. Automatically time out or move people who don’t have their camera on in the configured “Streaming VC.”

This guide will explain how to set up everything, from creating the bot on Discord to configuring your environment and launching the bot.

--------------------------------------------------------------------------------

## 1. Prerequisites

1. Python 3.8+ (Check with `python --version`).
2. Git (optional but recommended).
3. Edge (Chromium-based) installed on your system (the bot code uses Microsoft Edge WebDriver).
4. A Discord bot token from the Discord Developer Portal. Create an application, add a bot, then copy the bot token.
5. The following Python libraries:
   - discord.py
   - python-dotenv
   - selenium
   - webdriver-manager
   - (Optional) msedge-selenium-tools if you run into Edge-specific issues.

You can install them all at once with:
pip install discord.py python-dotenv selenium webdriver-manager

--------------------------------------------------------------------------------

## 2. Discord Setup

1. Create a Server or use an existing one. The server (guild) name in config.py is set to “OmegleStream (18+)”. You can rename your server or update the GUILD_NAME in config.py to match your actual server name.
2. Create or Identify Channels:
   - A Command Channel (where only commands like !skip, !refresh, etc. are used).
   - A Chat Channel (for normal chat / welcomes).
   - A Streaming Voice Channel (where people with cameras on can join).
   - A Hell VC (for users who break camera rules).
3. Retrieve the Channel and Role IDs:
   In your Discord app, enable Developer Mode (User Settings → Advanced → Developer Mode). Right-click the channels and select Copy ID.
   - COMMAND_CHANNEL_ID → The text channel for the commands.
   - CHAT_CHANNEL_ID → The general chat channel.
   - STREAMING_VC_ID → The voice channel for streaming.
   - HELL_VC_ID → The voice channel for disobedient users.
4. Invite Your Bot to the Server:
   In the Discord Developer Portal, under OAuth2 → URL Generator, select bot. Then choose the bot permissions your bot needs (e.g., Administrator or at least “View Channels”, “Send Messages”, “Manage Messages”, “Move Members”, “Mute Members”, “Deafen Members”, etc.). Copy the generated invite link and paste it in a browser to invite the bot to your server.

--------------------------------------------------------------------------------

## 3. File Descriptions

Your repository contains two main files:

### config.py

Defines various configurations and constants. Important parts:

GUILD_NAME = "OmegleStream (18+)"  # Must match your server's name
COMMAND_CHANNEL_ID = 1334294218826453072  # Replace with the actual ID
CHAT_CHANNEL_ID = 1207213216849985596     # Replace with the actual ID
STREAMING_VC_ID = 1131770315740024966     # Replace with the actual ID
HELL_VC_ID = 1134660138955980820          # Replace with the actual ID

ALLOWED_USERS = {
    "elonmusk4334", 
    "elonmuskalt4334", 
    "Jockie Music#8158", 
    "Omegle Bot#0081"
}

Update these values with:
- Your own server name for GUILD_NAME.
- Channel IDs for COMMAND_CHANNEL_ID, CHAT_CHANNEL_ID, STREAMING_VC_ID, HELL_VC_ID.
- Allowed user names in ALLOWED_USERS if you want to allow them to bypass camera checks or have more privileges.

### bot.py

The main bot script. It does the following:
- Loads environment variables (for your bot token).
- Initializes Selenium with Edge WebDriver to automate Uhmegle.
- Listens for commands (!skip, !refresh, !start, !stop) in your defined command channel.
- Manages rules enforcement in the Streaming VC (auto-move or time out users who do not turn on their camera).

Important: The bot expects:
- A .env file or environment variable named BOT_TOKEN containing your Discord bot token.
- The Uhmegle URL in config.UHMEGLE_VIDEO_URL (defaults to "https://uhmegle.com/video").

--------------------------------------------------------------------------------

## 4. Setting Up Environment Variables

In your project folder, create a file named .env:
BOT_TOKEN=YOUR_BOT_TOKEN_HERE

Replace YOUR_BOT_TOKEN_HERE with the token copied from the Discord Developer Portal.

--------------------------------------------------------------------------------

## 5. Selenium & Edge WebDriver

- The script uses webdriver_manager to automatically fetch the correct version of Edge WebDriver.
- Make sure you have Microsoft Edge (Chromium-based) installed on your system.
- The code sets up the driver in init_selenium() like this:
service = EdgeService(EdgeChromiumDriverManager().install())
options = webdriver.EdgeOptions()
driver = webdriver.Edge(service=service, options=options)

When you run the script, a real browser window for Edge will appear and navigate to UHMEGLE_VIDEO_URL.

--------------------------------------------------------------------------------

## 6. Basic Installation & Running the Bot

1. Clone or Download this repository to your local machine.
2. Install Python Dependencies:
pip install discord.py python-dotenv selenium webdriver-manager
3. Set Up the .env File:
echo "BOT_TOKEN=YOUR_BOT_TOKEN_HERE" > .env
4. Configure config.py:
   - Update GUILD_NAME to match your Discord Server name exactly.
   - Update channel IDs (COMMAND_CHANNEL_ID, CHAT_CHANNEL_ID, etc.) with the ones you copied from Developer Mode.
   - (Optional) Update ALLOWED_USERS with any user names you want to bypass camera checks.
5. Run the bot:
python bot.py
6. Watch the Console:
   - On the first run, webdriver_manager will download the correct Microsoft Edge WebDriver for you.
   - You should see a new Edge browser window open and navigate to https://uhmegle.com/video.

When the bot is connected, you should see messages like:
INFO:root:Bot is online as YourBotName#XXXX
INFO:root:Selenium: Opened Uhmegle video page.

--------------------------------------------------------------------------------

## 7. Usage

### Bot Commands

All the commands are used in the command channel you specified in config.py. They are also behind a 5-second cooldown per user.

1. !skip
   - Skips the current stranger on Uhmegle (actually presses ESC twice, 1 second apart).
   - Plays a skip sound in the Streaming VC (if configured with skip.mp3).

2. !refresh
   - Refreshes the Uhmegle page to fix any “Disconnected” issues.
   - Waits a couple of seconds, then attempts a skip.
   - Plays the skip sound.

3. !start
   - Reloads the Uhmegle page to “start” the session.
   - Automatically performs a skip after 3 seconds.
   - Plays the skip sound.

4. !stop
   - Refreshes the Uhmegle page to effectively pause or stop.
   - Plays the skip sound.

5. !help
   - Sends an embedded help menu in the command channel.
   - Also presents clickable buttons for each command.

### Camera Enforcement

- If a user joins the Streaming VC without their camera on, the bot starts a 60-second timer.
- After 60 seconds with no camera, the user is moved to the Hell VC (first violation).
- On second violation, they get timed out for 60 seconds.
- On third violation and beyond, they get timed out for 300 seconds.
- You can configure these behaviors in the timeout_unauthorized_users background task (in bot.py).

### Mod Commands

- !purge (in the command or chat channel): Purges up to 5000 messages from that channel. Only works for ALLOWED_USERS.
- !rtimeouts: Removes all active timeouts from everyone in the server. For ALLOWED_USERS only.
- !wtimeouts: Shows a list of who is currently timed out, how much time is left, and why. Also restricted to ALLOWED_USERS.

--------------------------------------------------------------------------------

## 8. Customization & Tips

1. Change the Bot’s Command Prefix
   In bot.py, find bot = commands.Bot(command_prefix="!", ...). Change the command_prefix to something else if you prefer.

2. Update the Sound File
   By default, SOUND_FILE = "skip.mp3" in config.py. You can change this to any local .mp3 path for your skip/refresh beep.

3. Discord Permissions
   Your bot role must have permission to move members, timeout members (or moderate members), manage messages (for purge), etc.

4. Keep .env Secret
   Never commit your actual BOT_TOKEN to public repos. Make sure .env is in your .gitignore.

5. Camera Detection
   The bot checks if user.voice.self_video is True. For some people, Discord might not always report camera states accurately. Test with multiple users to confirm behavior.

--------------------------------------------------------------------------------

## 9. Troubleshooting

1. Edge Browser Not Opening or Crashing
   Verify you have Microsoft Edge (Chromium) installed. If you’re on a different OS or version, ensure webdriver_manager can find the right driver.

2. Bot Doesn’t Respond
   Confirm the bot token is correct in your .env.
   Make sure the bot has permission to read/send messages in the specified channels.
   Ensure the GUILD_NAME in config.py matches your Discord server’s exact name (case sensitive).

3. User Camera Not Detected
   Some system or hardware issues might cause Discord not to flag self_video=True. This is a known quirk for certain configurations. Consider simplifying or removing camera checks if needed.

4. Timeout / Move / Mute Permission Errors
   Your bot’s role must be above the roles of any users you want to move or time out. Check your server’s role hierarchy.

--------------------------------------------------------------------------------

## 10. Contributing

1. Fork this repository or create your own branch.
2. Open pull requests with clear descriptions.
3. Test changes before merging or opening a PR to ensure stability.

--------------------------------------------------------------------------------

## 11. License

You can include any license you prefer here, for instance MIT, GPL, etc.

--------------------------------------------------------------------------------

Enjoy your new Uhmegle control bot! If you have issues, double-check each step above. Feel free to open an issue in your repository if you’d like more support.
