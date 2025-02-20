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
