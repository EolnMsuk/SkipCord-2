# SkipCord-2

SkipCord-2 is a Discord bot designed to manage a video streaming channel. It integrates with Selenium to automate skipping and refreshing an Omegle-like service called “Uhmegle.” It also enforces rules for streaming participants through automatic checks for camera usage and provides commands for bot control.

## Features

- **Automated Skipping**: Use commands like `!skip`, `!refresh`, `!start`, and `!pause` to control the Uhmegle video page via Selenium.
- **Voice Channel Enforcement**: Automatically moves or times out users who do not comply with camera-on requirements.
- **Cooldown System**: Prevents command spamming by applying a cooldown to users for each command.
- **Selenium Integration**: Launches Microsoft Edge to interact with Uhmegle, skipping or refreshing as requested.

## Commands

- `!skip`: Skips the current Uhmegle stream twice and plays a skip sound in the VC.
- `!refresh`: Refreshes the Uhmegle page and then skips once automatically.
- `!start`: Navigates to Uhmegle and starts the stream.
- `!pause`: Pauses the stream by refreshing the page.
- `!purge`: Deletes a large number of recent messages in the channel (admin/allowed users only).
- `!help`: Displays a button-based help menu within the commands channel.
- `!rtimeouts`: Removes all active timeouts in the server (admin/allowed users only).

## Configuration

- **Guild/Channel IDs**: Modify `config.py` to match your Discord server (guild) name and channel IDs.
- **Allowed Users**: Add or remove usernames in the `ALLOWED_USERS` set to grant them additional privileges.
- **Environment Variables**: Store your `BOT_TOKEN` in an `.env` file.
- **Selenium Profile**: Adjust the `edge_profile_path` in `bot.py` to your own Microsoft Edge profile path.

See [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md) for full instructions on setting up SkipCord-2 in Windows.


# Detailed Installation Guide for SkipCord-2 on Windows

This guide will walk you through creating your own version of SkipCord-2, a Discord bot that uses Selenium to automate a streaming/omegle-like service and enforces camera rules in a specified voice channel.

---

## 1. Create and Configure a Discord Application

1. **Go to the Discord Developer Portal**  
   Visit [https://discord.com/developers/applications](https://discord.com/developers/applications) and log in.

2. **Create a New Application**  
   - Click on **New Application**.
   - Enter a name (e.g., “SkipCord-2”).

3. **Create a Bot**  
   - In the left sidebar, click **Bot**.
   - Click **Add Bot**. Confirm any prompts.
   - Under **Token**, click **Reset Token** and copy the **Bot Token**. You’ll need this shortly.
   - Under **Privileged Gateway Intents**, make sure at least **MESSAGE CONTENT INTENT** is turned on if you intend to manage content. Also enable other intents if your code needs them (like **SERVER MEMBERS INTENT** for member joins).

4. **Invite the Bot to Your Server**  
   - In the left sidebar, click **OAuth2** → **URL Generator**.
   - Select **bot** as a scope.
   - Under **Bot Permissions**, select the permissions your bot will need (e.g., Administrator or specific permissions).
   - Copy the generated invite link, paste it into a browser, and select the server to invite your bot.

---

## 2. Install Python

1. **Download Python**  
   - Visit [https://www.python.org/downloads/](https://www.python.org/downloads/) and download the latest Python 3.x version for Windows.

2. **Install Python**  
   - Run the installer.  
   - **Important**: Check the box **“Add Python to PATH”** during installation.

---

## 3. Set Up the Project Files

1. **Clone or Download the Repository**  
   - You can use `git clone <repo-link>` or download a ZIP file of SkipCord-2’s source code and extract it into a folder.

2. **(Optional) Create a Virtual Environment**  
   - Open **Command Prompt** or **PowerShell** in your project folder.
   - Run:
     ```bash
     python -m venv venv
     ```
   - Activate your virtual environment:
     ```bash
     venv\Scripts\activate
     ```

3. **Install Dependencies**  
   - Inside your project folder, install all Python dependencies:
     ```bash
     pip install -r requirements.txt
     ```
     If you do not have a `requirements.txt`, manually install the packages mentioned in the code:
     - `discord.py`
     - `selenium`
     - `webdriver_manager`
     - `python-dotenv`
   - Example:
     ```bash
     pip install discord.py selenium webdriver_manager python-dotenv
     ```

---

## 4. Microsoft Edge and WebDriver Setup

SkipCord-2 uses **Selenium** with **Microsoft Edge** to automate skipping and refreshing. The code employs the `webdriver_manager` library, which typically handles driver installation automatically. However, here are some notes if you need manual setup:

1. **Ensure Microsoft Edge is Installed**  
   - SkipCord-2 is configured to use Edge. Make sure you have the latest stable version of Microsoft Edge on your system.

2. **Driver Manager (Automatic)**  
   - `webdriver_manager.microsoft` will download and manage the correct Edge driver automatically when you run the bot. Usually, no additional steps are required.

3. **(Optional) Manual EdgeDriver Installation**  
   - If automatic download fails, visit the [Microsoft Edge Driver](https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/) page, download the matching driver, and place it in your project folder or in a folder that’s in your system PATH.

---

## 5. Configuration and Environment Variables

1. **Discord Bot Token (.env file)**  
   - In the root of your project folder, create a new file named `.env`.
   - Add your bot token:
     ```
     BOT_TOKEN=YOUR_BOT_TOKEN_HERE
     ```
   - Replace `YOUR_BOT_TOKEN_HERE` with the token you copied from the Discord Developer Portal.

2. **Update `config.py`**  
   - Open `config.py`.
   - Edit `GUILD_NAME` to match the exact name of your Discord server.
   - Update channel IDs with the ones from your Discord server:
     - `COMMAND_CHANNEL_ID`
     - `CHAT_CHANNEL_ID`
     - `STREAMING_VC_ID`
     - `HELL_VC_ID`
   - Adjust `ALLOWED_USERS` to include the usernames (exactly as they appear on Discord) of users who have advanced permissions.

3. **Edge Profile Path (`bot.py`)**  
   - Within `bot.py`, look for `edge_profile_path` inside the `init_selenium()` function.
   - Update it to your own Edge profile path. Typically:
     ```
     edge_profile_path = "C:\\Users\\YourUsername\\AppData\\Local\\Microsoft\\Edge\\User Data"
     ```
   - If you have multiple Edge profiles, you might specify a profile directory like `--profile-directory="Profile 1"` or similar.

---

## 6. Running the Bot

1. **Activate Virtual Environment** (if you created one):
   ```bash
   venv\Scripts\activate
