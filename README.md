# SkipCord-2: Omegle Streaming Bot for Discord  

SkipCord-2 is a powerful Discord bot designed for streamers who use Omegle or similar platforms. It allows streamers to share their Omegle experience with others in a Discord voice channel, giving everyone the ability to control the stream using a button menu / or commands. The bot includes advanced moderation features, detailed logging, and automated enforcement of streaming rules.

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

### Admin/Allowed Commands 
- **!timeouts** - Lists current timeouts/untimeouts
- **!times** - Shows VC User Time Stats
- **!roles** - Lists all roles and their members
- **!rtimeouts** - Removes all active timeouts

### Allowed Users Only Commands 
- **!whois** - List of recent actions (timeouts/kicks/bans)
- **!stats** - Lists VC Time / Command usage Stats
- **!purge** - Purges messages from channel
- **!top** - Lists top 10 oldest Discord accounts
- **!bans / !banned** - Lists banned users with reasons
- **!join** - Sends join invite DMs to admins
- **!clear** - Clears VC time/command usage data
- **!hush** - Server mutes everyone in Streaming VC
- **!secret** - Server mutes+deafens everyone in VC
- **!rhush** - Removes mute status from VC
- **!rsecret** - Removes mute+deafen from VC
- **!modoff** - Temporarily disables VC moderation
- **!modon** - Re-enables VC moderation
- **!shutdown** - Safely shuts down the bot

### Enhanced Features 
- **VC Time Tracking**:  
  - Tracks time spent in streaming VC
  - Daily auto-stats with top 10 users
- **Auto-Pause**: Automatically pauses when last user turns off camera
- **Multiple VC Support**: Monitors both Streaming VC and Alt VC
- **Global Hotkey**: Skip command via keyboard shortcut
- **State Persistence**: All data saved/restored on restart

### Automated Systems 
- **Camera Enforcement**:  
  - Non-allowed users without cameras are muted/deafened
  - 1st violation: Moved to punishment VC
  - 2nd violation: Short timeout
  - 3rd+ violations: Longer timeout
- **Daily Auto-Stats**:
  - Posts top 10 VC users daily
  - Automatically clears statistics
- **Activity Logging**:  
  - Detailed logs of all commands and events
  - Welcome messages for new members
  - Role change notifications
  - Join/leave tracking with durations

![v4](https://github.com/user-attachments/assets/1a19be16-a22c-4d34-a909-ad79172d7bb0)

---

# SkipCord-2: Setup & Configuration  

## 1) Prerequisites
- **Edge** - Keep (msedge.exe) up to date
- **Python 3.9+** - "Install python to path" (google it) from [python.org](https://www.python.org/downloads/)
- **Dependencies**: Open cmd.exe as admin run: `pip install -U discord.py python-dotenv selenium webdriver-manager keyboard`

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
- `.env` (contains `BOT_TOKEN=your_token_here`)

## 4) Configure config.py
Replace with your info:
```python
GUILD_ID = 1234567890                # Your server ID
COMMAND_CHANNEL_ID = 1234567890      # Channel for commands
CHAT_CHANNEL_ID = 1234567890         # General chat channel
STREAMING_VC_ID = 1234567890         # Main streaming voice channel
ALT_VC_ID = 1234567890               # Alternate voice channel
PUNISHMENT_VC_ID = 1234567890        # Timeout voice channel
AUTO_STATS_CHAN = 1234567890         # Channel for auto-stats
AUTO_STATS_HOUR_UTC = 0              # UTC hour for auto-stats (0-23)
AUTO_STATS_MINUTE_UTC = 0            # UTC minute for auto-stats (0-59)
ALLOWED_USERS = [1234567890]         # Full Bot Access / Server Owner ID
ADMIN_ROLE_NAME = ["Admin"]          # Name of Role for Admin Command Access
MUSIC_BOT = 1234567890               # ID of music bot to exempt
STATS_EXCLUDED_USERS = set()         # Users to exclude from stats
OMEGLE_VIDEO_URL = "https://omegle.com/"
EDGE_USER_DATA_DIR = "C:/Path/To/Edge/User Data"
```
## 5) Running the Bot
1. Close all Edge browser instances
2. Run the bot: `python bot.py`
   - The bot will: 
     - Launch Edge with Omegle 
     - Start all monitoring systems 
3. Troubleshooting: 
   - If Edge doesn't launch, check EDGE_USER_DATA_DIR path
   - Check logs for specific error messages
4. Enjoy your fully automated Omegle streaming community management!
