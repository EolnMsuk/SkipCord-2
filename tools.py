import logging
from dataclasses import dataclass
import time
import discord
from discord.ext import commands
from typing import Any
from datetime import datetime, timezone  # Added for embed creation functions

def handle_errors(func: Any) -> Any:
    """Decorator to wrap functions with centralized error handling."""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logging.error(f"Error in {func.__name__}: {e}", exc_info=True)
            # If the first argument has a "send" attribute (e.g. a Context or Message), attempt to send a notice.
            if args and hasattr(args[0], "send"):
                await args[0].send("An unexpected error occurred.")
    return wrapper

def send_message_both(ctx, message: str):
    """
    Sends a message in the current channel and as a DM to the user.
    If DM fails (for example, due to privacy settings), a warning is logged.
    """
    async def _send():
        try:
            await ctx.send(message)
        except Exception as e:
            logging.error(f"Failed to send message in channel: {e}")
        try:
            await ctx.author.send(message)
        except discord.Forbidden:
            logging.warning(f"Could not send DM to {ctx.author.name} (DMs disabled).")
        except Exception as e:
            logging.error(f"Failed to send DM: {e}")
    return _send()

def ordinal(n: int) -> str:
    """
    Returns an ordinal string representation of an integer (e.g., 1st, 2nd).
    """
    if 10 <= n % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return str(n) + suffix

def get_discord_age(created_at) -> str:
    """
    Calculates the Discord account age from a given datetime.
    Returns a human-readable string.
    """
    now = datetime.now(timezone.utc)
    delta = now - created_at
    years = delta.days // 365
    months = (delta.days % 365) // 30
    days = (delta.days % 365) % 30
    parts = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if not parts:
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        if hours:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return ", ".join(parts) if parts else "Just now"

# Allowed commands for stats tracking:
ALLOWED_STATS_COMMANDS = {
    "!skip", "!refresh", "!pause", "!start", "!paid",
    "!rules", "!about", "!info", "!whois", "!rtimeouts",
    "!roles", "!join", "!top", "!commands", "!admin",
    "!admins", "!owner", "!owners"
}

def record_command_usage(analytics, command_name: str) -> None:
    """
    Increments the global usage count for a command if it is in the allowed list.
    """
    if command_name not in ALLOWED_STATS_COMMANDS:
        return
    analytics["command_usage"][command_name] = analytics["command_usage"].get(command_name, 0) + 1

def record_command_usage_by_user(analytics, user_id: int, command_name: str) -> None:
    """
    Increments the usage count for a command by a specific user if it is in the allowed list.
    """
    if command_name not in ALLOWED_STATS_COMMANDS:
        return
    if user_id not in analytics["command_usage_by_user"]:
        analytics["command_usage_by_user"][user_id] = {}
    analytics["command_usage_by_user"][user_id][command_name] = analytics["command_usage_by_user"][user_id].get(command_name, 0) + 1

@dataclass
class BotConfig:
    """
    A typed configuration class for the bot.
    All configuration values are typed and validated here.
    """
    GUILD_ID: int
    COMMAND_CHANNEL_ID: int
    CHAT_CHANNEL_ID: int
    STREAMING_VC_ID: int
    HELL_VC_ID: int
    ALLOWED_USERS: set
    OMEGLE_VIDEO_URL: str
    EDGE_USER_DATA_DIR: str
    SOUND_FILE: str
    ADMIN_ROLE_NAME: list
    JOIN_INVITE_MESSAGE: str
    ENABLE_GLOBAL_HOTKEY: bool
    GLOBAL_HOTKEY_COMBINATION: str
    VC_MODERATION_PERMANENTLY_DISABLED: bool
    COMMAND_COOLDOWN: int
    HELP_COOLDOWN: int
    RULES_MESSAGE: str
    INFO_MESSAGES: list
    CAMERA_OFF_ALLOWED_TIME: int
    TIMEOUT_DURATION_SECOND_VIOLATION: int
    TIMEOUT_DURATION_THIRD_VIOLATION: int
    MUSIC_BOT: int

    @staticmethod
    def from_config_module(config_module: Any) -> 'BotConfig':
        """
        Creates a BotConfig object from a module.
        Aggregates INFO1_MESSAGE through INFO5_MESSAGE into a list.
        """
        info_msgs = []
        for i in range(1, 6):
            info = getattr(config_module, f"INFO{i}_MESSAGE", None)
            if info:
                info_msgs.append(info)
        return BotConfig(
            GUILD_ID = config_module.GUILD_ID,
            COMMAND_CHANNEL_ID = config_module.COMMAND_CHANNEL_ID,
            CHAT_CHANNEL_ID = config_module.CHAT_CHANNEL_ID,
            STREAMING_VC_ID = config_module.STREAMING_VC_ID,
            HELL_VC_ID = config_module.HELL_VC_ID,
            ALLOWED_USERS = config_module.ALLOWED_USERS,
            OMEGLE_VIDEO_URL = config_module.OMEGLE_VIDEO_URL,
            EDGE_USER_DATA_DIR = config_module.EDGE_USER_DATA_DIR,
            SOUND_FILE = config_module.SOUND_FILE,
            ADMIN_ROLE_NAME = config_module.ADMIN_ROLE_NAME,
            JOIN_INVITE_MESSAGE = config_module.JOIN_INVITE_MESSAGE,
            ENABLE_GLOBAL_HOTKEY = config_module.ENABLE_GLOBAL_HOTKEY,
            GLOBAL_HOTKEY_COMBINATION = config_module.GLOBAL_HOTKEY_COMBINATION,
            VC_MODERATION_PERMANENTLY_DISABLED = config_module.VC_MODERATION_PERMANENTLY_DISABLED,
            COMMAND_COOLDOWN = config_module.COMMAND_COOLDOWN,
            HELP_COOLDOWN = config_module.HELP_COOLDOWN,
            RULES_MESSAGE = config_module.RULES_MESSAGE,
            INFO_MESSAGES = info_msgs,
            CAMERA_OFF_ALLOWED_TIME = config_module.CAMERA_OFF_ALLOWED_TIME,
            TIMEOUT_DURATION_SECOND_VIOLATION = config_module.TIMEOUT_DURATION_SECOND_VIOLATION,
            TIMEOUT_DURATION_THIRD_VIOLATION = config_module.TIMEOUT_DURATION_THIRD_VIOLATION,
            MUSIC_BOT = config_module.MUSIC_BOT
        )

def build_embed(title: str, description: str, color: discord.Color) -> discord.Embed:
    """
    Creates and returns a discord.Embed with the specified title, description, and color.
    """
    return discord.Embed(title=title, description=description, color=color)

async def build_role_update_embed(member: discord.Member, roles_gained, roles_lost) -> discord.Embed:
    """
    Asynchronously builds and returns an embed for role update events.
    The embed includes the member's profile picture, banner (if available),
    join date, account age, user ID, and lists of roles gained and lost.
    """
    try:
        # Attempt to fetch the user to get updated banner information.
        user = await member._state.fetch_user(member.id)
    except Exception as e:
        logging.error(f"Failed to fetch user for role update embed: {e}")
        user = member
    banner_url = user.banner.url if getattr(user, "banner", None) else None
    embed = discord.Embed(
        title=f"Role Update for {member.display_name}",
        description=f"{member.mention} had a role change.",
        color=discord.Color.purple(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    if banner_url:
        embed.set_image(url=banner_url)
    embed.add_field(name="Joined at", value=member.joined_at.strftime('%Y-%m-%d') if member.joined_at else "Unknown", inline=True)
    embed.add_field(name="Account Age", value=get_discord_age(member.created_at), inline=True)
    embed.add_field(name="User ID", value=str(member.id), inline=True)
    roles_gained_str = ", ".join([role.name for role in roles_gained]) if roles_gained else "None"
    roles_lost_str = ", ".join([role.name for role in roles_lost]) if roles_lost else "None"
    embed.add_field(name="Roles Gained", value=roles_gained_str, inline=False)
    embed.add_field(name="Roles Lost", value=roles_lost_str, inline=False)
    return embed

class BotState:
    """
    Encapsulates the global state of the bot.
    """
    def __init__(self) -> None:
        self.voice_client = None
        self.driver = None
        self.cooldowns = {}
        self.button_cooldowns = {}
        self.camera_off_timers = {}
        self.user_violations = {}
        self.users_received_rules = set()
        self.users_with_dms_disabled = set()
        self.active_timeouts = {}
        self.user_last_join = {}
        self.vc_moderation_active = True
        self.hush_override_active = False
        self.recent_joins = []
        self.recent_leaves = []
        self.analytics = {
            "command_usage": {},
            "command_usage_by_user": {},
            "violation_events": 0
        }
