# SkipCord-2: Omegle Streaming Bot for Discord

SkipCord-2 is a powerful Discord bot designed for streamers who use Omegle or similar platforms. It allows streamers to share their Omegle experience with others in a Discord voice channel, giving everyone the ability to control the stream using simple commands.

## Stream Control & Browser Automation
- **!skip**:  
  Skips the current Omegle session by sending an ESC key event via Selenium.

- **!refresh**:  
  Refreshes the Omegle page to resolve connection issues and then skips to the next session.

- **!start**:  
  Initiates the stream by navigating to the Omegle video page and triggering a skip.

- **!pause**:  
  Pauses the stream by refreshing the page.

- **Sound Effects**:  
  Plays a configured audio file (e.g., `skip.mp3`) in the Streaming VC whenever one of the stream control commands is executed.  
  *(Implemented in functions like `selenium_skip`, `selenium_refresh`, and `play_sound_in_vc`.)*

## Camera Enforcement & Automated Moderation
- **Camera Enforcement**:  
  - Monitors users in the Streaming VC and checks if their cameras are on.  
  - Non-allowed users without an active camera trigger a timer.
  - On the **first violation**, the user is moved to the “Hell VC” and receives a DM notification.

- **Automated Timeouts**:  
  - **Second violation**: The user is timed out for a short period (e.g., 60 seconds).  
  - **Subsequent violations**: Longer timeouts are applied (e.g., 300 seconds).  
  *(Implemented in the `timeout_unauthorized_users` task.)*

## Interactive Help Menu & User Guidance
- **Help Menu**:  
  - Periodically sends a help menu in the command channel displaying key commands.
  - Utilizes interactive buttons (via Discord UI components) for quick execution of stream commands.

- **Button Cooldowns**:  
  - Prevents rapid reuse of help menu buttons by enforcing a 5-second cooldown per user.  
  *(See the `HelpView` and `HelpButton` classes.)*

- **VC Join/Leave Logging & Welcome Messages**:  
  - Logs when users join or leave the Streaming VC with timestamps.
  - Sends a welcome message (and a DM with rules) when a new member joins the server.  
  *(Implemented in the `on_voice_state_update` and `on_member_join` events.)*


## Moderation Commands

- **!rtimeouts**:  
  Removes all active timeouts from members and lists the affected usernames.

- **!rmutes**:  
  Unmutes all muted members in the voice channels.

- **!rdeafens**:  
  Removes the deafen status from any deafened members.

- **!hush**:  
  Server mutes everyone in the Streaming VC (excluding allowed users) and logs the impacted users.

- **!secret**:  
  Server mutes and deafens everyone in the Streaming VC (excluding allowed users) for stricter control.

- **!rhush**:  
  Lifts the mute status from all members in the Streaming VC.

- **!rsecret**:  
  Removes both mute and deafen statuses from everyone in the Streaming VC.

- **!join**:  
  Sends a join invite DM to all members with the Admin role.

## Rate Limiting & Cooldowns
- **Command Cooldowns**:  
  Enforces a 5-second cooldown per command per user to prevent spam.

- **Button Cooldowns**:  
  Interactive help menu buttons are similarly rate-limited to 5 seconds between uses.

## Logging & Error Handling
- **Activity Logging**:  
  Logs all major events (e.g., command executions, user join/leave, moderation actions) both to a log file and to the command window.

- **Error Reporting**:  
  Any errors during command execution or moderation are logged for troubleshooting.



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

--------------------------------------------------------------------------------
3) Installing Dependencies
--------------------------------------------------------------------------------
Open Command Prompt in your bot’s folder (Shift + Right-click → “Open PowerShell window here” or “Open Command window here”) and run:

   pip install -U discord.py python-dotenv selenium webdriver-manager

This ^ installs the core libraries:
- `discord.py` for Discord bot functionality
- `python-dotenv` for reading environment variables from `.env`
- `selenium` for browser automation
- `webdriver-manager` for automatic EdgeDriver management

--------------------------------------------------------------------------------
4) Configure Your Bot
--------------------------------------------------------------------------------

### Set Your .env / Environment Variable
Create a file named `.env` (in the same folder as `bot.py`) with contents like:

   BOT_TOKEN=YOUR_BOT_TOKEN_HERE


### Adjust config.py
- **GUILD_ID**: Replace `YourDiscordID` with your Discord Server ID.
- **COMMAND_CHANNEL_ID**, **CHAT_CHANNEL_ID**, **STREAMING_VC_ID**, **HELL_VC_ID**: 
  Put your actual channel or voice channel IDs as integers. 
  Right-click your channels in Discord (Developer Mode enabled) to copy IDs.
- **ALLOWED_USERS**: A set of usernames#discriminator who can bypass camera checks or run powerful commands. 
- **OMEGLE_VIDEO_URL**: https://website.com/video # Replace with omegle URL.
- **EDGE_USER_DATA_DIR**: "C:\\Users\\UserName\\AppData\\Local\\Microsoft\\Edge\\User Data"  # Edge browser user data directory.
  
--------------------------------------------------------------------------------
5) Running the Bot
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
6) Troubleshooting
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
