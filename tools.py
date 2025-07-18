import logging
import logging.config
from dataclasses import dataclass
import time
import discord
from discord.ext import commands
from typing import Any, Optional, Set, List, Tuple, Dict, Union
from datetime import datetime, timezone, timedelta
import sys
import asyncio
from functools import wraps

# Custom stream handler for Unicode-safe logging
class UnicodeSafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            # Encode/decode to handle Unicode characters safely
            stream.write(msg.encode('utf-8', errors='replace').decode('utf-8') + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

# Clear existing logging handlers
logging.root.handlers = []

# Configure logging settings
logging_config = {
    "version": 1,
    "formatters": {
        "detailed": {
            "format": "%(asctime)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        }
    },
    "handlers": {
        "console": {
            "()": UnicodeSafeStreamHandler,  # Use custom Unicode handler
            "formatter": "detailed",
            "level": "INFO",
            "stream": sys.stdout
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": "bot.log",
            "formatter": "detailed",
            "level": "INFO",
            "encoding": "utf-8"
        }
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO"
    }
}

# Apply logging configuration
logging.config.dictConfig(logging_config)

# Global state reference for tools
_bot_state_instance = None

def set_bot_state_instance(state_instance: 'BotState') -> None:
    """Set the global bot state instance for tools.py functions."""
    global _bot_state_instance
    _bot_state_instance = state_instance

def get_bot_state() -> 'BotState':
    """Get the global bot state instance."""
    if _bot_state_instance is None:
        raise RuntimeError("BotState instance not initialized")
    return _bot_state_instance

def sanitize_channel_name(channel_name: str) -> str:
    """Sanitizes channel names by removing non-ASCII characters."""
    return ''.join(char for char in channel_name if ord(char) < 128)

def log_command_usage(ctx_or_interaction: Any, command_name: str) -> None:
    """Logs command usage with duplicate prevention."""
    try:
        # Determine context type (command vs interaction)
        if isinstance(ctx_or_interaction, commands.Context):  # Regular command context
            user = ctx_or_interaction.author
            channel = getattr(ctx_or_interaction.channel, 'name', 'DM')
            source = 'command'
        elif isinstance(ctx_or_interaction, discord.Interaction):  # Interaction context
            user = ctx_or_interaction.user
            channel = getattr(ctx_or_interaction.channel, 'name', 'DM')
            source = 'button'
        else: # Fallback for messages
            user = ctx_or_interaction.author
            channel = getattr(ctx_or_interaction.channel, 'name', 'DM')
            source = 'message'


        # Create unique log identifier
        timestamp = int(time.time())
        log_id = f"{user.id}-{command_name}-{timestamp//10}"  # Group by 10-second windows
        
        state = get_bot_state()
        if state.is_command_logged(log_id):
            return
            
        state.log_command_usage(log_id)

        # Format and log command usage
        safe_channel = sanitize_channel_name(channel)
        human_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        
        logging.info(
            f"COMMAND USED: '{command_name}' by {user} (ID: {user.id}) "
            f"in #{safe_channel} at {human_time} [via {source}]"
        )
    except Exception as e:
        logging.error(f"Error logging command usage: {e}", exc_info=True)

# Decorator for error handling and command logging
def handle_errors(func: Any) -> Any:
    @wraps(func)
    async def wrapper(*args, **kwargs):
        ctx = None
        if args:
            if isinstance(args[0], commands.Context):
                ctx = args[0]
            elif hasattr(args[0], 'channel'): # Heuristic for interaction-like objects
                ctx = args[0]

        if ctx and hasattr(ctx, 'command') and ctx.command:
            log_command_usage(ctx, ctx.command.name)
        elif ctx and not hasattr(ctx, 'command'): # Handle cases where it's not a full context
            pass # Logging should happen at point of call
        
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logging.error(f"Error in {func.__name__}: {e}", exc_info=True)
            if ctx and hasattr(ctx, "send"):
                try:
                    await ctx.send("An unexpected error occurred while running that command.")
                except Exception as send_e:
                    logging.error(f"Failed to send error message to context: {send_e}")
    return wrapper

def ordinal(n: int) -> str:
    """Returns ordinal string (1st, 2nd, etc.)."""
    if 10 <= n % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return str(n) + suffix

def get_discord_age(created_at) -> str:
    """Calculates Discord account age in human-readable format."""
    now = datetime.now(timezone.utc)
    delta = now - created_at
    # Calculate time components
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
    # Handle cases with no days
    if not parts:
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        if hours:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return ", ".join(parts) if parts else "Just now"

# Commands allowed in statistics tracking
ALLOWED_STATS_COMMANDS = {
    "!stats", "!skip", "!refresh", "!pause", "!start", "!paid",
    "!rules", "!about", "!info", "!whois", "!rtimeouts",
    "!roles", "!join", "!top", "!commands", "!admin",
    "!admins", "!owner", "!owners", "!timeouts", "!times"
}

def record_command_usage(analytics, command_name: str) -> None:
    """Records command usage in analytics if allowed."""
    if command_name not in ALLOWED_STATS_COMMANDS:
        return
    analytics["command_usage"][command_name] = analytics["command_usage"].get(command_name, 0) + 1

def record_command_usage_by_user(analytics, user_id: int, command_name: str) -> None:
    """Records command usage by user in analytics if allowed."""
    if command_name not in ALLOWED_STATS_COMMANDS:
        return
    if user_id not in analytics["command_usage_by_user"]:
        analytics["command_usage_by_user"][user_id] = {}
    analytics["command_usage_by_user"][user_id][command_name] = (
        analytics["command_usage_by_user"][user_id].get(command_name, 0) + 1
    )

# Bot configuration dataclass
@dataclass
class BotConfig:
    """Bot configuration dataclass."""
    GUILD_ID: int
    COMMAND_CHANNEL_ID: int
    CHAT_CHANNEL_ID: int
    STREAMING_VC_ID: int
    PUNISHMENT_VC_ID: int
    ALT_VC_ID: int
    ALLOWED_USERS: set
    OMEGLE_VIDEO_URL: str
    EDGE_USER_DATA_DIR: str
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
    STATS_EXCLUDED_USERS: set
    AUTO_STATS_CHAN: int
    AUTO_STATS_HOUR_UTC: int
    AUTO_STATS_MINUTE_UTC: int
    MEDIA_ONLY_CHANNEL_ID: Optional[int]

    @staticmethod
    def from_config_module(config_module: Any) -> 'BotConfig':
        """Creates BotConfig from config module."""
        info_msgs = []
    
        if hasattr(config_module, 'INFO_MESSAGES') and isinstance(config_module.INFO_MESSAGES, list):
            info_msgs = config_module.INFO_MESSAGES
        else:
            for i in range(1, 6):
                attr_name = f"INFO{i}_MESSAGE"
                if hasattr(config_module, attr_name):
                    info = getattr(config_module, attr_name)
                    if info:
                        info_msgs.append(info)
    
        return BotConfig(
            GUILD_ID=config_module.GUILD_ID,
            COMMAND_CHANNEL_ID=config_module.COMMAND_CHANNEL_ID,
            CHAT_CHANNEL_ID=config_module.CHAT_CHANNEL_ID,
            STREAMING_VC_ID=config_module.STREAMING_VC_ID,
            PUNISHMENT_VC_ID=config_module.PUNISHMENT_VC_ID,
            ALT_VC_ID=config_module.ALT_VC_ID,
            ALLOWED_USERS=config_module.ALLOWED_USERS,
            OMEGLE_VIDEO_URL=config_module.OMEGLE_VIDEO_URL,
            EDGE_USER_DATA_DIR=config_module.EDGE_USER_DATA_DIR,
            ADMIN_ROLE_NAME=config_module.ADMIN_ROLE_NAME,
            JOIN_INVITE_MESSAGE=config_module.JOIN_INVITE_MESSAGE,
            ENABLE_GLOBAL_HOTKEY=config_module.ENABLE_GLOBAL_HOTKEY,
            GLOBAL_HOTKEY_COMBINATION=config_module.GLOBAL_HOTKEY_COMBINATION,
            VC_MODERATION_PERMANENTLY_DISABLED=config_module.VC_MODERATION_PERMANENTLY_DISABLED,
            COMMAND_COOLDOWN=config_module.COMMAND_COOLDOWN,
            HELP_COOLDOWN=config_module.HELP_COOLDOWN,
            RULES_MESSAGE=config_module.RULES_MESSAGE,
            INFO_MESSAGES=info_msgs,
            CAMERA_OFF_ALLOWED_TIME=config_module.CAMERA_OFF_ALLOWED_TIME,
            TIMEOUT_DURATION_SECOND_VIOLATION=config_module.TIMEOUT_DURATION_SECOND_VIOLATION,
            TIMEOUT_DURATION_THIRD_VIOLATION=config_module.TIMEOUT_DURATION_THIRD_VIOLATION,
            MUSIC_BOT=config_module.MUSIC_BOT,
            STATS_EXCLUDED_USERS=getattr(config_module, 'STATS_EXCLUDED_USERS', set()),
            AUTO_STATS_CHAN=config_module.AUTO_STATS_CHAN,
            AUTO_STATS_HOUR_UTC=config_module.AUTO_STATS_HOUR_UTC,
            AUTO_STATS_MINUTE_UTC=config_module.AUTO_STATS_MINUTE_UTC,
            MEDIA_ONLY_CHANNEL_ID=getattr(config_module, 'MEDIA_ONLY_CHANNEL_ID', None)
        )

def build_embed(title: str, description: str, color: discord.Color) -> discord.Embed:
    """Builds a Discord embed with title and description."""
    return discord.Embed(title=title, description=description, color=color)

async def build_role_update_embed(member: discord.Member, roles_gained, roles_lost) -> discord.Embed:
    """Builds embed for role updates with user information."""
    user = member # Default to member object
    try:
        # Fetching the user object may provide the banner
        user = await member.guild.fetch_member(member.id)
    except discord.NotFound:
        logging.warning(f"Could not fetch full member object for {member.name} during role update.")
    except Exception as e:
        logging.error(f"Failed to fetch user for role update embed: {e}")

    banner_url = user.banner.url if hasattr(user, 'banner') and user.banner else None
    
    embed = discord.Embed(
        title=f"Role Update for {member.name}",
        description=f"{member.mention} had a role change.",
        color=discord.Color.purple()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    if banner_url:
        embed.set_image(url=banner_url)
    
    if member.joined_at:
        embed.add_field(name="Joined at", value=member.joined_at.strftime('%Y-%m-%d'), inline=True)
    else:
        embed.add_field(name="Joined at", value="Unknown", inline=True)
    
    embed.add_field(name="Account Age", value=get_discord_age(member.created_at), inline=True)
    embed.add_field(name="User ID", value=str(member.id), inline=True)
    
    if roles_gained:
        roles_gained_str = ", ".join([role.name for role in roles_gained])
        embed.add_field(name="Roles Gained", value=roles_gained_str, inline=False)
    
    if roles_lost:
        roles_lost_str = ", ".join([role.name for role in roles_lost])
        embed.add_field(name="Roles Lost", value=roles_lost_str, inline=False)
    
    return embed

# Bot state management class
class BotState:
    def __init__(self, config) -> None:
        self.config = config
        
        # Concurrency locks to prevent race conditions
        self.vc_lock = asyncio.Lock()
        self.analytics_lock = asyncio.Lock()
        self.moderation_lock = asyncio.Lock()
        self.cooldown_lock = asyncio.Lock()
        
        # Cooldown trackers
        self.cooldowns: Dict[int, Tuple[float, bool]] = {}
        self.button_cooldowns: Dict[int, Tuple[float, bool]] = {}
        
        # Voice channel moderation
        self.camera_off_timers: Dict[int, float] = {}
        self.user_violations: Dict[int, int] = {}
        self.vc_moderation_active = True
        self.hush_override_active = False
        
        # User management
        self.users_received_rules: Set[int] = set()
        self.users_with_dms_disabled: Set[int] = set()
        self.user_last_join: Dict[int, bool] = {}
        self.failed_dm_users = set()
        
        # Moderation actions
        self.active_timeouts: Dict[int, Dict[str, Any]] = {}
        self.pending_timeout_removals: Dict[int, bool] = {} # Now just a simple flag
        self.recent_kick_timestamps: Dict[int, datetime] = {}
        self.announced_bans: Set[int] = set() # FIX: Add this line to initialize the set
        
        # Event tracking
        self.recent_joins: List[Tuple[int, str, Optional[str], datetime]] = []
        self.recent_leaves: List[Tuple[int, str, Optional[str], datetime, Optional[str]]] = []
        self.recent_bans: List[Tuple[int, str, Optional[str], datetime, str]] = []
        self.recent_kicks: List[Tuple[int, str, Optional[str], datetime, str, Optional[str], Optional[str]]] = []
        self.recent_unbans: List[Tuple[int, str, Optional[str], datetime, str]] = []
        self.recent_untimeouts: List[Tuple[int, str, Optional[str], datetime, str, Optional[str], Optional[int]]] = []
        
        # Analytics
        self.analytics = {
            "command_usage": {},
            "command_usage_by_user": {},
            "violation_events": 0
        }
        self.recently_logged_commands: Set[str] = set()
        
        # Voice time tracking
        self.last_auto_pause_time = 0
        self.vc_time_data: Dict[int, Dict[str, Any]] = {}
        self.active_vc_sessions: Dict[int, float] = {}

    def is_command_logged(self, log_id: str) -> bool:
        """Check if a command was recently logged."""
        return log_id in self.recently_logged_commands

    def log_command_usage(self, log_id: str) -> None:
        """Record a command usage."""
        self.recently_logged_commands.add(log_id)

    async def clean_old_entries(self) -> None:
        """Unified cleanup maintaining 7-day history and entry limits"""
        current_time = time.time()
        now = datetime.now(timezone.utc)
        seven_days_ago_dt = now - timedelta(days=7)
    
        async with self.cooldown_lock:
            self.cooldowns = {k: v for k, v in self.cooldowns.items() if current_time - v[0] < (self.config.COMMAND_COOLDOWN * 2)}
            self.button_cooldowns = {k: v for k, v in self.button_cooldowns.items() if current_time - v[0] < (self.config.COMMAND_COOLDOWN * 2)}

        async with self.moderation_lock:
            self.active_timeouts = {k: v for k, v in self.active_timeouts.items() if v.get('timeout_end', float('inf')) > current_time}
            self.pending_timeout_removals = {k: v for k, v in self.pending_timeout_removals.items() if current_time - v.get('timestamp', 0) < 604800}
            self.recent_kick_timestamps = {k: v for k, v in self.recent_kick_timestamps.items() if current_time - v.timestamp() < 604800}
            self.user_violations = {k: v for k, v in self.user_violations.items() if v > 0}
            for dataset in [self.failed_dm_users, self.users_with_dms_disabled, self.users_received_rules]:
                if len(dataset) > 1000:
                    dataset.clear() # Simple clear on large sets

        async with self.vc_lock:
            self.camera_off_timers = {k: v for k, v in self.camera_off_timers.items() if current_time - v < (self.config.CAMERA_OFF_ALLOWED_TIME * 2)}
            
            # **BUG FIX**: Removed incorrect cleanup logic for `user_last_join` which holds booleans, not timestamps.
            # This dictionary does not need time-based cleanup. It will be managed by events.

            seven_days_ago_ts = current_time - (7 * 24 * 3600)
            self.vc_time_data = {
                user_id: {
                    **data,
                    "sessions": [s for s in data.get("sessions", []) if s.get("end", 0) > seven_days_ago_ts]
                }
                for user_id, data in self.vc_time_data.items()
                if any(s.get("end", 0) > seven_days_ago_ts for s in data.get("sessions", []))
            }

        async with self.analytics_lock:
            if len(self.analytics["command_usage_by_user"]) > 1000:
                user_usage_sorted = sorted(self.analytics["command_usage_by_user"].items(), key=lambda x: sum(x[1].values()), reverse=True)
                self.analytics["command_usage_by_user"] = dict(user_usage_sorted[:1000])
    
            if len(self.analytics["command_usage"]) > 100:
                commands_sorted = sorted(self.analytics["command_usage"].items(), key=lambda x: x[1], reverse=True)
                self.analytics["command_usage"] = dict(commands_sorted[:100])

        list_specs = {
            'recent_joins': (3, 200), 'recent_leaves': (3, 200),
            'recent_bans': (3, 200), 'recent_kicks': (3, 200),
            'recent_unbans': (3, 200), 'recent_untimeouts': (3, 200)
        }
    
        for list_name, (time_idx, max_entries) in list_specs.items():
            async with self.moderation_lock:
                lst = getattr(self, list_name)
                cleaned = [entry for entry in lst if len(entry) > time_idx and entry[time_idx] > seven_days_ago_dt][-max_entries:]
                setattr(self, list_name, cleaned)

        if len(self.recently_logged_commands) > 5000:
            self.recently_logged_commands.clear()
