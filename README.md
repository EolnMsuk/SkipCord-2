# SkipCord-2: Omegle Streaming Bot for Discord  

SkipCord-2 is a powerful Discord bot designed for streamers who use Omegle or similar platforms. It allows streamers to share their Omegle experience with others in a Discord voice channel, giving everyone the ability to control the stream using simple commands. If you're an Omegle streamer who wants to share your experience with friends or a community, SkipCord-2 makes it easy to manage the stream and keep everyone engaged. The bot's automated features ensure that the rules are followed, so you can focus on streaming.

## User Commands (Users in VC + Cam on)  
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

- **!rules**  
 Posts and DMs the server rules defined by config.

- **!info / !about**  
 Posts and DMs the server information defined by config.

- **!help**  
  Displays help menu with buttons.

## Moderation Commands (Allowed Users / Admin Role)
- **!commands**  
  Lists all of the commands and who can use them (Admin Role)

- **!roles**  
  Lists the names role title of all members with roles in the server (Admin Role)

- **!join**  
  Sends a join invite DM to all members with the Admin role (Admin Role)

- **!whois**  
  Lists names of members who are timed out / recently left / joined the server (Admin Role)

- **!rtimeouts**  
  Removes all active timeouts from members and lists the affected usernames (Admin Role)

- **!analytics**  
  Lists command usage information, including ID and amount (Admin Role)

- **!top**  
  Lists the top 5 Oldest Discord accounts on the current server (Admin Role)
  
- **!purge**  
  Purges a specified number of messages from the GC (default is 5) (Allowed Users)

- **!hush**  
  Server mutes everyone in the Streaming VC (excluding allowed users) (Allowed Users)

- **!secret**  
  Server mutes and deafens everyone in the Streaming VC (excluding allowed users) (Allowed Users)

- **!rhush**  
  Removes the mute status from all members in the Streaming VC (Allowed Users)

- **!rsecret**  
  Removes both mute and deafen statuses from everyone in the Streaming VC (Allowed Users)

- **!modoff**  
  Temporarily disables VC moderation (auto-mute/deafen) for non-allowed users (Allowed Users)

- **!modon**  
  Re-enables VC moderation after it has been disabled (Allowed Users)

## Camera Enforcement & Automated Moderation  
- **Help Menu**:  
  - Periodically sends a help menu in the command channel displaying key commands.
  - Utilizes interactive buttons (via Discord UI components) for quick execution of stream commands.

  ![help](https://github.com/user-attachments/assets/257da27a-1fa6-4eef-8df5-596d90175b41)
  
- **Camera Enforcement**:  
  - Monitors users in the Streaming VC and checks if their cameras are on.
  - Non-allowed users without an active camera are server muted and deafened, and a timer is started.
  - On the 1st violation, the user is moved to the “Hell VC” and receives a DM notification.
  - On the 2nd violation, the user is timed out for a short period (e.g., 60 seconds).  
  - On 3rd+ violations, the user receives a longer timeout (e.g., 300 seconds).

  ![mod](https://github.com/user-attachments/assets/a2ce7f96-aaa7-4edb-af9d-1607a5d63d86)

- **VC Join/Leave Logging & Welcome Messages**:  
  - Logs when users join or leave the Streaming VC with timestamps.
  - Sends a welcome message (and a DM with rules) when a new member joins the server or VC for first time.

  ![joinleave](https://github.com/user-attachments/assets/7b6a222a-716f-4d7c-97a7-560ff9fb4115)

- **Activity Logging**:  
  - Logs all major events (e.g., command executions, user join/leave, moderation actions) both to a log file and to the command window.
  - Logs all Admin commands ready to be called by !analytics which lists member ID / command / amount.

  ![analytics](https://github.com/user-attachments/assets/1afe1c24-4f32-49d3-b81c-34cbc82bdb48)
  ![5](https://github.com/user-attachments/assets/f1ba39fc-72e0-40ba-aeec-ef235d67b339)

- **Button Cooldowns**:  
  - Prevents rapid reuse of help menu buttons by enforcing a 5-second cooldown per user.  
  *(See the `HelpView` and `HelpButton` classes.)*

  ![commands](https://github.com/user-attachments/assets/71fff4be-7d31-4f13-b7ec-31c7165a19dd)

- **Sound Effect**:  
  - Plays a configured audio file (e.g., `skip.mp3`) in the Streaming VC whenever one of the stream control commands is executed.

--------------------------------------------------------------------------------
 
# SkipCord-2: Windows Setup & Configuration  
## 1) Getting Started
- **Install Python 3.9+** (preferably the latest stable 3.x version). 
  - Download from https://www.python.org/downloads/ if you don’t have it already.
  - Check installation: open Command Prompt (cmd) and run: `python --version`
  - PIP (comes with Python) - Check by running: `pip --version`

- **Install FFmpeg**  
  - Download the latest static build of FFmpeg for Windows from [ffmpeg.org](https://ffmpeg.org/download.html) or from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) - Extract the archive and add the folder containing `ffmpeg.exe` to your system's PATH environment variable: https://phoenixnap.com/kb/ffmpeg-windows - You can verify the installation by running `ffmpeg -version` in your Command Prompt.

- **Microsoft Edge**  
  - The bot uses the `webdriver_manager` library to auto-download the appropriate Edge driver, so make sure Edge is up to date.

- **Create Discord Bot**  
  - Create a Discord bot via https://discord.com/developers/applications
  - Enable “Message Content Intent”, “Server Members Intent” and "Presence Intent" under the “Bot” tab.
  - Save your bot token and Client ID (you’ll need these).

- **Invite your Bot** 
  - Go to https://discordapi.com/permissions.html#1088840794048 and replace the Client ID with your own.
  - Use the new link (at bottom) to invite your bot to the server.

## 2) Project Folder & Files
Create a new text file named `.env` with the following content (replace YOUR_BOT_TOKEN_HERE with your bot token):

   BOT_TOKEN=YOUR_BOT_TOKEN_HERE

- Save the .env file in the same folder as the rest:
   1. **bot.py** (bot code) 
   2. **config.py** (settings) 
   3. **.env** (stores BOT_TOKEN) 
   4. **skip.mp3** (skip sound mp3) 

## 3) Install Dependencies  
Open Command Prompt (cmd as admin) and run: 

`pip install -U discord.py python-dotenv selenium webdriver-manager keyboard`

After it finishes installing, a restart is recommended.

## 4) Adjusting the config.py File  
Before launching bot, update the values in **config.py** with your own server’s details. Specifically:
- **GUILD_ID**, **COMMAND_CHANNEL_ID**, **CHAT_CHANNEL_ID**, **STREAMING_VC_ID**, **HELL_VC_ID**: Replace the placeholder numeric values with your actual channel or voice channel IDs (as integers).
- **ADMIN_ROLE_NAME**: Replace with the actual role names that should receive join invites.
- **SKIP_COMMAND_KEY**: Set to a list of keys to be sent sequentially when !skip command is sent.
- **JOIN_INVITE_MESSAGE**: Update the Discord channel URLs with your own server’s IDs.
- **EDGE_USER_DATA_DIR**: Replace “YOUR_USERNAME” with your actual Windows username.
- **ALLOWED_USERS**: Replace the example user IDs with your actual allowed user IDs.
- **WHOIS_ALLOWED_ROLE_NAMES**: Roles that can run !whois command.
- **OMEGLE_VIDEO_URL**: The active omegle video URL.
- **RULES_MESSAGE**: Modify the rules as desired.
- **CAMERA_OFF_ALLOWED_TIME**, **TIMEOUT_DURATION_SECOND_VIOLATION**, **TIMEOUT_DURATION_THIRD_VIOLATION**: Adjust timing values if necessary.

## 5) Running the Bot  

- Close all instances of Edge, then double click bot.py (or open cmd and type python path/to/bot.py).
- The bot should launch an instance of Edge (navigating to the specified Omegle page), and commands will work for that instance.

--------------------------------------------------------------------------------

That’s it! Once it’s set up and all placeholders in **config.py** are updated, your bot will be ready to run while keeping your personal details private.
