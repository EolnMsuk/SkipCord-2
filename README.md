# SkipCord-2: Omegle Streaming Bot for Discord  

SkipCord-2 is a powerful Discord bot designed for streamers who use Omegle or similar platforms. It allows streamers to share their Omegle experience with others in a Discord voice channel, giving everyone the ability to control the stream using simple commands. The bot includes advanced moderation features, detailed logging, and automated enforcement of streaming rules.

## Key Features

### User Commands 
- **!skip** - Skips the current stranger on Omegle
- **!refresh** - Refreshes page (fix disconnected)
- **!pause** - Pauses Omegle temporarily
- **!start** - Re-initiates Omegle by skipping
- **!paid** - Redirects after someone pays for unban
- **!rules** - Posts and DMs the server rules
- **!help** - Displays help menu with buttons
- **!info / !about** - Posts and DMs server information
- **!owner / !admin** - Lists Admins and Owners
- **!commands** - Lists all available commands

### Moderation Commands 
- **!whois** - List of recently timedout / kicked / banned users (Admin Users)
- **!stats** - Shows command usage statistics and violations (Admin Users)
- **!roles** - Lists all roles and their members (Admin Users)
- **!rtimeouts** - Removes all active timeouts (Admin Users)
- **!purge** - Purges messages from channel (Allowed Users)
- **!hush** - Server mutes everyone in Streaming VC (Allowed Users)
- **!secret** - Server mutes+deafens everyone in Streaming VC (Allowed Users)
- **!rhush** - Removes mute status from Streaming VC (Allowed Users)
- **!rsecret** - Removes mute+deafen from Streaming VC (Allowed Users)
- **!modoff** - Temporarily disables VC moderation (Allowed Users)
- **!modon** - Re-enables VC moderation (Allowed Users)
- **!join** - Sends join invite DMs to admin role members (Allowed Users)
- **!top** - Lists top 5 oldest Discord accounts (Allowed Users)
- **!bans / !banned** - Lists all banned users with reasons (Allowed Users)
- **!shutdown** - Safely shuts down the bot (Allowed Users)

### Enhanced Features 
- **Auto-Pause**: Automatically pauses when last user turns off camera
- **Multiple VC Support**: Monitors both Streaming VC and Alt VC
- **Global Hotkey**: Skip command can be triggered via keyboard shortcut
- **State Persistence**: All data is saved and restored on restart++

### Automated Systems 
- **Camera Enforcement**:  
  - Non-allowed users without cameras are muted/deafened
  - 1st violation: Moved to punishment VC
  - 2nd violation: Short timeout
  - 3rd+ violations: Longer timeout

- **Activity Logging**:  
  - Detailed logs of all commands and events
  - Welcome messages for new members
  - Role change notifications
  - Join/leave tracking with durations

- **Help Menu**:  
  - Periodic UI refresh with interactive buttons
  - Cooldown system to prevent spam

![v3](https://github.com/user-attachments/assets/036bee1f-eb68-4b31-b429-8fdc4c220eca)

---

# SkipCord-2: Setup & Configuration  

## 1) Prerequisites
- **Python 3.9+** - Install from [python.org](https://www.python.org/downloads/)
- **FFmpeg** - Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH
- **Microsoft Edge** - Must be up to date
- **Dependencies**: Run `pip install -U discord.py python-dotenv selenium webdriver-manager keyboard`

## 2) Create Discord Bot
1. Create bot at [Discord Developer Portal](https://discord.com/developers/applications)
2. Enable these intents:
   - Message Content Intent
   - Server Members Intent
   - Presence Intent
3. Save your bot token
4. Invite bot using https://discordapi.com/permissions.html#1088840794048

## 3) File Setup
Required files in your project folder:
- `bot.py` (main bot file)
- `tools.py` (supporting functions)
- `config.py` (configuration)
- `skip.mp3` (sound file)
- `.env` (contains `BOT_TOKEN=your_token_here`)


## 4) Configure config.py
Essential settings to configure:
```python
GUILD_ID = 1234567890                # Your server ID
COMMAND_CHANNEL_ID = 1234567890      # Channel for commands
CHAT_CHANNEL_ID = 1234567890         # General chat channel
STREAMING_VC_ID = 1234567890         # Main streaming voice channel
ALT_VC_ID = 1234567890               # Alternate voice channel
PUNISHMENT_VC_ID = 1234567890        # Timeout voice channel

ALLOWED_USERS = [1234567890]         # Full Bot Access / Server Owner ID
ADMIN_ROLE_NAME = ["Admin"]          # Name of Role for Admin Command Access
MUSIC_BOT = 1234567890               # ID of music bot to exempt

OMEGLE_VIDEO_URL = "https://omegle.com/"
EDGE_USER_DATA_DIR = "C:/Users/YOURNAME/AppData/Local/Microsoft/Edge/User Data"
```

## 5) Running the Bot
1. Close all Edge browser instances
2. Run the bot: `python bot.py`
   - The bot will: 
     - Launch Edge with Omegle 
     - Connect to voice channel 
     - Start all monitoring systems 
3. Troubleshooting 
   - If Edge doesn't launch, check EDGE_USER_DATA_DIR path
   - For voice issues, verify FFmpeg is installed correctly
   - Check logs for specific error messages
4. That's it! Your SkipCord-2 bot is ready to manage your Omegle streaming community with powerful moderation and automation features.
