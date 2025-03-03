# SkipCord-2: Omegle Streaming Bot for Discord

SkipCord-2 is a powerful Discord bot designed for streamers who use Omegle or similar platforms. It allows streamers to share their Omegle experience with others in a Discord voice channel, giving everyone the ability to control the stream using simple commands. If you're an Omegle streamer who wants to share your experience with friends or a community, SkipCord-2 makes it easy to manage the stream and keep everyone engaged. The bot's automated features ensure that the rules are followed, so you can focus on streaming.

## User Commands
- **!skip**  
  Skips the current Omegle session by sending an ESC key event via Selenium.

- **!refresh**  
  Refreshes the Omegle page to resolve connection issues and then skips to the next session.

- **!pause**  
  Pauses the stream by refreshing the page.

- **!start**  
  Initiates the stream by navigating to the Omegle video page and triggering a skip.

- **!paid**  
  Redirects the browser to OMEGLE_VIDEO_URL after someone pays for unban using ID.

- **!help**  
  Displays the help menu with buttons for the above commands.

## Moderation Commands (allowed users only)
- **!purge [count]**  
  Purges a specified number of messages from the channel (default is 5 if not specified).

- **!rtimeouts**  
  Removes all active timeouts from members and lists the affected usernames.

- **!hush**  
  Server mutes everyone in the Streaming VC (excluding allowed users) and logs the impacted users.

- **!secret**  
  Server mutes and deafens everyone in the Streaming VC (excluding allowed users) for stricter control.

- **!rhush**  
  Lifts the mute status from all members in the Streaming VC.

- **!rsecret**  
  Removes both mute and deafen statuses from everyone in the Streaming VC.

- **!join**  
  Sends a join invite DM to all members with the Admin role.

## Camera Enforcement & Automated Moderation
- **Camera Enforcement**:  
  - Monitors users in the Streaming VC and checks if their cameras are on.  
  - Non-allowed users without an active camera trigger a timer.
  - On the 1st violation, the user is moved to the “Hell VC” and receives a DM notification.
  - **seccond violation** The user is timed out for a short period (e.g., 60 seconds).  
  - **Subsequent violations**: Longer timeouts are applied (e.g., 300 seconds).  
  *(Implemented in the `timeout_unauthorized_users` task.)*

- **Sound Effect**:  
  - Plays a configured audio file (e.g., `skip.mp3`) in the Streaming VC whenever one of the stream control commands is executed.  

- **Activity Logging**:  
  - Logs all major events (e.g., command executions, user join/leave, moderation actions) both to a log file and to the command window.

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

- **Error Reporting**:  
  - Any errors during command execution or moderation are logged for troubleshooting.
 
--------------------------------------------------------------------------------
 
# SkipCord-2: Windows Setup & Configuration
## 1) Getting Ready
- **Python 3.9+** (preferably the latest stable 3.x version). 
  - Download from https://www.python.org/downloads/ if you don’t have it already.
  - Check installation: open Command Prompt (cmd) and run: python --version

- **pip** (usually bundled with Python).
  - Check by running: pip --version

- **Microsoft Edge** (latest) + **WebDriver** 
  - Our bot uses the ‘webdriver_manager’ library to auto-download the appropriate Edge driver. 
  - Make sure Edge is installed and up to date.

- **Discord Bot Token** 
  - Create a discord bot via https://discord.com/developers/applications
  - Enable “Message Content Intent” and “Server Members Intent” and "Presence Intent" under the “Bot” tab.
  - Copy your bot token (you’ll store this in the `.env` file in your bot folder).
  - Go to https://discordapi.com/permissions.html#1088840794048 and replace Client ID to use link to invite bot to your server.


## 2) Project Folder & Files
Create a file named `.env` with contents like:

   BOT_TOKEN=YOUR_BOT_TOKEN_HERE

- Save the .env file in the same folder as the following:
   1. **bot.py** (the main bot code)
   2. **config.py** (your server IDs and settings) 
   3. **.env** (storing your BOT_TOKEN)
   4. **skip.mp3** (media file your bot is to play)

## 3) Install Dependencies
Open Command Prompt in your bot’s folder (Shift + Right-click → “Open PowerShell window here” or “Open Command window here”) and run:

   pip install -U discord.py python-dotenv selenium webdriver-manager keyboard

This ^ installs the core libraries:
- `discord.py` for Discord bot functionality
- `python-dotenv` for reading environment variables
- `selenium` for browser automation
- `webdriver-manager` for automatic EdgeDriver management
- `keyboard` for keyboard emulation


## 4) Adjust config.py
- **GUILD_ID**: Replace `YourDiscordID` with your Discord Server ID.
- **COMMAND_CHANNEL_ID**, **CHAT_CHANNEL_ID**, **STREAMING_VC_ID**, **HELL_VC_ID**: Put your actual channel or voice channel IDs as integers.
- **ADMIN_ROLE_NAME**: Role name for members to be DMed
- **JOIN_INVITE_MESSAGE**: MSG to send to Admins to join
- **VC_MODERATION_PERMANENTLY_DISABLED**: Keep as False to use VC moderation normally.
- **ALLOWED_USERS**: A set of user IDs who can bypass camera checks and run powerful commands. 
- **OMEGLE_VIDEO_URL**: https://omegle.com/video # Replace with omegle URL.
- **EDGE_USER_DATA_DIR**: "C:\\Users\\UserName\\AppData\\Local\\Microsoft\\Edge\\User Data"  # Replace UserName with your windows username.
- **WELCOME_MESSAGE**: A msg to post in the GC when a new user joins the server.
- **RULES_MESSAGE**: A welcome msg for new members joining the Streaming VC - Rules etc.
  
## 5) Running the Bot
Close all instances of Edge - then right click the bot.py and select open with Python (or simply double click) 

If the bot successfully starts, you should see log info in your console:
   Bot is online as YourBotNameHere and...
   
- Connect to Discord
- Launch Microsoft Edge for Selenium in the VIDEO URL designated by config 
- Begin enforcing camera rules and waiting for commands like !skip, !refresh, !start, !pause, etc.

--------------------------------------------------------------------------------

That’s it! Once it’s set up, your bot will run on Windows, automatically controlling Omegle through Selenium, allowing you and your camera-enabled friends to skip or refresh quickly without manually touching the browser every time.

## Troubleshooting
- **Edge or WebDriver Issues**: 
  Ensure Edge is updated, and let `webdriver_manager` handle the driver automatically. If there are version mismatches, try updating the “webdriver-manager” package: 
    pip install -U webdriver-manager
- **Bot Token Invalid**: 
  Double-check your `.env` or environment variable for typos.
- **Permissions**: 
  Make sure your bot’s role in Discord has permission to connect to voice channels, move members, time out members, read messages, etc. 
  Under “Server Settings → Roles”, confirm the bot’s role is set properly.
