# SkipCord-2

A Discord bot that integrates with the [Uhmegle](https://uhmegle.com/video) site to provide a semi-automated Omegle-style streaming experience in a designated voice channel. It enforces a camera-on policy, auto-manages users in the voice channel, and provides commands for skipping, refreshing, starting, and stopping the stream.

---

## Features

- **Selenium Integration**  
  Uses Microsoft Edge (Chromium) with Selenium to open and control the Uhmegle video chat site, allowing skip, refresh, and start/stop functionalities from Discord commands.

- **Camera Enforcement**  
  Automatically checks if a user in the **Streaming** voice channel has their camera turned on. If not, the user is moved or timed out after repeated violations.

- **Configurable Bot Prefix & Channels**  
  Configure your desired command channel, chat channel, streaming channel, etc., using environment variables and the settings in `config.py`.

- **Auto-Purge and Help Menu**  
  The bot periodically purges the command channel to keep it tidy and reposts a help menu.
