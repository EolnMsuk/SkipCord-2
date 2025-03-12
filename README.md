![Untitled](https://github.com/user-attachments/assets/95027fcf-f81a-4379-8179-d014920ad2f7)

# SkipCord-2: Omegle Streaming Bot for Discord  

SkipCord-2 is a powerful Discord bot designed for streamers who use Omegle or similar platforms. It allows streamers to share their Omegle experience with others in a Discord voice channel, giving everyone the ability to control the stream using simple commands. If you're an Omegle streamer who wants to share your experience with friends or a community, SkipCord-2 makes it easy to manage the stream and keep everyone engaged. The bot's automated features ensure that the rules are followed, so you can focus on streaming.

## User Commands (Streaming VC + cam on)  
- **!skip**  
  Skips the current stranger on Omegle.

- **!refresh**  
  Refreshes page (fix disconnected).

- **!pause**  
  Pauses Omegle temporarily.

- **!start**  
  Re-initiates Omegle by skipping.

- **!paid**  
  Redirects after someone pays for unban.

- **!help**  
  Displays help menu with buttons.

## Moderation Commands (Allowed Users)
- **!purge [count]**  
  Purges a specified number of messages from the GC (default is 5).

- **!whois**  
  Lists the names of current Discord members who are timed out / recently left / joined the server.

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

- **!modoff**  
  Temporarily disables VC moderation (auto-mute/deafen) for non-allowed users.

- **!modon**  
  Re-enables VC moderation after it has been disabled.

## Camera Enforcement & Automated Moderation  
- **Camera Enforcement**:  
  - Monitors users in the Streaming VC and checks if their cameras are on.
  - Non-allowed users without an active camera are server muted and deafened + trigger a timer.
  - On the 1st violation, the user is moved to the “Hell VC” and receives a DM notification.
  - 2nd violation the user is timed out for a short period (e.g., 60 seconds).  
  - 3rd+ violations have longer timeouts (e.g., 300 seconds).

- **VC Join/Leave Logging & Welcome Messages**:  
  - Logs when users join or leave the Streaming VC with timestamps.
  - Sends a welcome message (and a DM with rules) when a new member joins the server. 

- **Activity Logging**:  
  - Logs all major events (e.g., command executions, user join/leave, moderation actions) both to a log file and to the command window.

- **Help Menu**:  
  - Periodically sends a help menu in the command channel displaying key commands.
  - Utilizes interactive buttons (via Discord UI components) for quick execution of stream commands.

- **Button Cooldowns**:  
  - Prevents rapid reuse of help menu buttons by enforcing a 5-second cooldown per user.  
  *(See the `HelpView` and `HelpButton` classes.)*

- **Sound Effect**:  
  - Plays a configured audio file (e.g., `skip.mp3`) in the Streaming VC whenever one of the stream control commands is executed.  

--------------------------------------------------------------------------------
 
# SkipCord-2: Windows Setup & Configuration  
## 1) Getting Started
- **Install Python 3.9+** (preferably the latest stable 3.x version). 
  - Download from https://www.python.org/downloads/ if you don’t have it already.
  - Check installation: open Command Prompt (cmd) and run: `python --version`
  - PIP (came with python) - Check by running: `pip --version`

- **Install FFmpeg**  
  - Download the latest static build of FFmpeg for Windows from [ffmpeg.org](https://ffmpeg.org/download.html) or from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/). Extract the archive and add the folder containing `ffmpeg.exe` to your system's PATH environment variable: https://phoenixnap.com/kb/ffmpeg-windows - You can verify the installation by running `ffmpeg -version` in your Command Prompt.

- **Microsoft Edge**  
  - Our bot uses the `webdriver_manager` library to auto-download the appropriate Edge driver, so make sure Edge is up to date.

- **Create Discord Bot**  
  - Create a discord bot via https://discord.com/developers/applications
  - Enable “Message Content Intent”, “Server Members Intent” and "Presence Intent" under the “Bot” tab.
  - Save your bot token and Client ID (you’ll need these).

- **Invite your Bot** 
  - Go to https://discordapi.com/permissions.html#1088840794048 and replace Client ID with your own.
  - Use the new link (at bottom) to invite your bot to the server.

## 2) Project Folder & Files
Create a new text file named `.env` with contents your token:

   BOT_TOKEN=YOUR_BOT_TOKEN_HERE

- Save the .env file in the same folder as the rest:
   1. **bot.py** (bot code) 
   2. **config.py** (settings) 
   3. **.env** (stores BOT_TOKEN) 
   4. **skip.mp3** (skip sound mp3) 

## 3) Install Dependencies  
Open Command Prompt (cmd as admin) and run: 

`pip install -U discord.py python-dotenv selenium webdriver-manager keyboard`

After it finishes installing, a restart is recomended.

## 4) Adjusting the config.py File  
- **GUILD_ID**: Replace with your Discord Server ID.
- **COMMAND_CHANNEL_ID**, **CHAT_CHANNEL_ID**, **STREAMING_VC_ID**, **HELL_VC_ID**: Put your actual channel or voice channel IDs as integers.
- **ADMIN_ROLE_NAME**: Role name for members to be DMed.
- **JOIN_INVITE_MESSAGE**: Message to send to Admins to join.
- **VC_MODERATION_PERMANENTLY_DISABLED**: Keep as False to use VC moderation normally.
- **ALLOWED_USERS**: A set of user IDs who can bypass camera checks and run powerful commands.
- **WHOIS_ALLOWED_ROLE_NAMES**: A list of role names permitted to run the **!whois** command (defaults to `["Admin", "Admen"]`).
- **OMEGLE_VIDEO_URL**: https://omegle.com/video Replace with the appropriate URL.
- **EDGE_USER_DATA_DIR**: "C:\\Users\\YOUR_USERNAME\\AppData\\Local\\Microsoft\\Edge\\User Data" Replace with your actual username.
- **WELCOME_MESSAGE**: A message to post in the GC when a new user joins the server.
- **RULES_MESSAGE**: A welcome message for new members joining the Streaming VC - Rules, etc.
- **CAMERA_OFF_ALLOWED_TIME**: The number of seconds a non-allowed user's camera can be off before a violation.
- **TIMEOUT_DURATION_SECOND_VIOLATION**: The timeout duration (in seconds) for a 2nd violation.
- **TIMEOUT_DURATION_THIRD_VIOLATION**: The timeout duration (in seconds) for a 3rd+ violation.

## 5) Running the Bot  

- Close all instances of Edge - then right click the bot.py and select "Open with Python" (or simply double click). 
- At this point the bot should open an instance of Edge (Omegle), and the commands will only work for that tab/instance.

--------------------------------------------------------------------------------

That’s it! Once it’s set up, your bot will run automatically controlling Omegle through Selenium, allowing you and your camera-enabled friends to skip or refresh quickly without manually touching the browser every time.
