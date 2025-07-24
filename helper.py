# helper.py
# This file contains the implementation for many of the bot's commands and event handlers.
# It is designed to keep the main `bot.py` file cleaner and more focused on the core bot structure.

import asyncio
import discord
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional, Union, List
from collections import namedtuple

from discord.ext import commands
from loguru import logger

# Import shared tools and data structures
from tools import (
    BotState,
    BotConfig,
    get_discord_age,
    record_command_usage,
    record_command_usage_by_user,
    handle_errors, # Import handle_errors
    format_duration,
)

def format_departure_time(duration: timedelta) -> str:
    """
    Formats the duration of a member's stay into a human-readable string (e.g., '1y 2d 3h').
    This calls the universal format_duration function from tools.
    """
    return format_duration(duration)


def create_message_chunks(
    entries: List[Any],
    title: str,
    process_entry: Callable[[Any], str],
    max_chunk_size: int = 50,
    max_length: int = 4000, # Increased for embed descriptions
    as_embed: bool = False,
    embed_color: Optional[discord.Color] = None
) -> Union[List[str], List[discord.Embed]]:
    """
    A utility function to split a long list of text entries into multiple messages or embeds.
    This is essential for avoiding Discord's character limits.
    """
    if as_embed and embed_color is None:
        raise ValueError("embed_color must be provided when as_embed=True")

    chunks = []
    current_chunk = []
    current_length = 0

    # Embeds don't need a separate title string in the content
    title_length = 0 if as_embed else len(f"**{title} ({len(entries)} total)**\n")

    for entry in entries:
        processed_list = process_entry(entry)
        # Ensure process_entry always returns a list of strings
        if not isinstance(processed_list, list):
            processed_list = [processed_list]
        
        for processed in processed_list:
            if processed:
                entry_length = len(processed) + 1  # +1 for the newline

                if (current_length + entry_length > max_length and current_chunk) or \
                   (len(current_chunk) >= max_chunk_size):
                    if as_embed:
                        embed = discord.Embed(title=title, description="\n".join(current_chunk), color=embed_color)
                        chunks.append(embed)
                    else:
                        chunks.append(f"**{title} ({len(entries)} total)**\n" + "\n".join(current_chunk))
                    current_chunk = []
                    current_length = 0

                current_chunk.append(processed)
                current_length += entry_length

    if current_chunk:
        if as_embed:
            embed = discord.Embed(title=title, description="\n".join(current_chunk), color=embed_color)
            chunks.append(embed)
        else:
            chunks.append(f"**{title} ({len(entries)} total)**\n" + "\n".join(current_chunk))

    return chunks

class BotHelper:
    """
    A class that encapsulates the logic for various bot commands and event notifications.
    This promotes modularity by separating command implementation from the event listeners in `bot.py`.
    """
    def __init__(self, bot: commands.Bot, state: BotState, bot_config: BotConfig, save_func: Optional[Callable] = None):
        self.bot = bot
        self.state = state
        self.bot_config = bot_config
        self.save_state = save_func # A function to save the bot's state, passed from bot.py

    async def _log_timeout_in_state(self, member: discord.Member, duration_seconds: int, reason: str, moderator_name: str, moderator_id: Optional[int] = None):
        """
        A centralized, thread-safe method for recording a member's timeout information into the bot's state.
        
        Args:
            member: The member who was timed out.
            duration_seconds: The duration of the timeout in seconds.
            reason: The reason for the timeout.
            moderator_name: The name of the moderator who issued the timeout.
            moderator_id: The ID of the moderator.
        """
        async with self.state.moderation_lock:
            self.state.active_timeouts[member.id] = {
                "timeout_end": time.time() + duration_seconds,
                "reason": reason,
                "timed_by": moderator_name,
                "timed_by_id": moderator_id,
                "start_timestamp": time.time()
            }

    async def _create_departure_embed(self, member_or_user: Union[discord.Member, discord.User], moderator: Union[discord.User, str], reason: str, action: str, color: discord.Color) -> discord.Embed:
        """
        Creates a standardized, rich embed for member departure events like kicks and bans.
        This ensures consistent formatting for all such notifications.
        
        Args:
            member_or_user: The user/member who departed. Can be a real object or a mock object.
            moderator: The moderator responsible for the action.
            reason: The reason for the departure.
            action: The type of action (e.g., "KICKED", "BANNED").
            color: The color for the embed's side bar.
        
        Returns:
            A fully constructed discord.Embed object ready to be sent.
        """
        # Handle both real objects and mock (namedtuple) objects
        mention = getattr(member_or_user, 'mention', f"<@{member_or_user.id}>")
        author_name = getattr(member_or_user, 'name', 'Unknown User')
        avatar_url = member_or_user.display_avatar.url if hasattr(member_or_user, 'display_avatar') and member_or_user.display_avatar else None

        # Adjust wording for kicks
        if action.upper() == "KICKED":
            description = f"{mention} **was {action.upper()}**"
        else:
            description = f"{mention} **{action.upper()}**"

        embed = discord.Embed(description=description, color=color)
        if avatar_url:
            embed.set_author(name=author_name, icon_url=avatar_url)
            embed.set_thumbnail(url=avatar_url)

        # Attempt to fetch the user's banner for a more visually appealing embed.
        try:
            user_obj = await self.bot.fetch_user(member_or_user.id)
            if user_obj.banner:
                embed.set_image(url=user_obj.banner.url)
        except Exception:
            pass  # Ignore if the banner can't be fetched (e.g., user has none).

        moderator_mention = getattr(moderator, 'mention', str(moderator))
        embed.add_field(name="Moderator", value=moderator_mention, inline=True)

        # Add details like time in server and roles if the data is available
        if hasattr(member_or_user, 'joined_at') and member_or_user.joined_at:
            duration = datetime.now(timezone.utc) - member_or_user.joined_at
            duration_str = format_departure_time(duration)
            embed.add_field(name="Time in Server", value=duration_str, inline=True)

        if hasattr(member_or_user, 'roles'):
            # For real members, get mentions. For mock members, the list already contains mentions.
            if isinstance(member_or_user, discord.Member):
                roles = [role.mention for role in member_or_user.roles if role.name != "@everyone"]
            else:
                roles = member_or_user.roles # This is now a list of mention strings

            if roles:
                roles.reverse() # Show highest roles first
                embed.add_field(name="Roles", value=" ".join(roles), inline=True)


        embed.add_field(name="Reason", value=reason, inline=False)
        return embed

    @handle_errors
    async def handle_member_join(self, member: discord.Member) -> None:
        """
        Handles the logic for when a new member joins the server.
        It sends a welcome message and logs the join event.
        """
        if member.guild.id != self.bot_config.GUILD_ID:
            return

        chat_channel = member.guild.get_channel(self.bot_config.CHAT_CHANNEL_ID)
        if chat_channel:
            embed = discord.Embed(
                description=f"{member.mention} **JOINED the SERVER**!",
                color=discord.Color.green())

            embed.set_author(name=member.name, icon_url=member.display_avatar.url)
            embed.set_thumbnail(url=member.display_avatar.url)

            if member.banner:
                embed.set_image(url=member.banner.url)

            embed.add_field(
                name="Account Age",
                value=get_discord_age(member.created_at),
                inline=True)

            await chat_channel.send(embed=embed)

        async with self.state.moderation_lock:
            self.state.recent_joins.append((
                member.id,
                member.name,
                member.display_name,
                datetime.now(timezone.utc)
            ))
        logger.info(f"{member.name} joined the server {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")

    @handle_errors
    async def send_timeout_notification(self, member: discord.Member, moderator: discord.User, duration: int, reason: str = None) -> None:
        """
        Sends a rich, formatted notification to the chat channel when a member is timed out.
        """
        chat_channel = member.guild.get_channel(self.bot_config.CHAT_CHANNEL_ID)
        if not chat_channel:
            return

        duration_str = format_duration(duration)

        # Create the base embed
        embed = discord.Embed(
            description=f"{member.mention} **was TIMED OUT**",
            color=discord.Color.orange())

        embed.set_author(name=f"{member.name}", icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)

        try:
            user_obj = await self.bot.fetch_user(member.id)
            if user_obj.banner:
                embed.set_image(url=user_obj.banner.url)
        except Exception:
            pass
        
        embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        embed.add_field(name="Duration", value=duration_str, inline=True)

        roles = [role.mention for role in member.roles if role.name != "@everyone"]
        if roles:
            roles.reverse()
            roles_str = " ".join(roles)
            embed.add_field(name="Roles", value=roles_str, inline=True)

        final_reason = reason or "No reason provided"
        embed.add_field(name="Reason", value=final_reason, inline=False)

        await chat_channel.send(embed=embed)

    @handle_errors
    async def send_timeout_removal_notification(self, member: discord.Member, duration: int, reason: str = "Expired Naturally") -> None:
        """
        Sends a rich, formatted notification when a member's timeout is removed or expires.
        """
        chat_channel = member.guild.get_channel(self.bot_config.CHAT_CHANNEL_ID)
        if not chat_channel: return

        duration_str = format_duration(duration)

        embed = discord.Embed(
            description=f"{member.mention} **TIMEOUT REMOVED**",
            color=discord.Color.orange())

        embed.set_author(name=f"{member.name}", icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)

        try:
            user_obj = await self.bot.fetch_user(member.id)
            if user_obj.banner: embed.set_image(url=user_obj.banner.url)
        except Exception: pass

        embed.add_field(name="Original Duration", value=duration_str, inline=True)

        if "manually removed by" in reason.lower() or "Timeout removed by" in reason:
            try:
                parts = reason.rsplit("by", 1)
                reason_text = parts[0].strip()
                mod_name = parts[1].strip().lstrip('🛡️').strip()
                mod_member = discord.utils.find(lambda m: m.name == mod_name or m.display_name == mod_name, member.guild.members)
                mod_display = mod_member.mention if mod_member else mod_name
                reason = f"{reason_text} by {mod_display}"
            except Exception as e:
                logger.warning(f"Error processing moderator name for timeout removal: {e}")

        embed.add_field(name="Reason", value=f"{reason}", inline=False)
        await chat_channel.send(embed=embed)

    @handle_errors
    async def send_unban_notification(self, user: discord.User, moderator: discord.User) -> None:
        """Sends a notification when a user is unbanned."""
        chat_channel = self.bot.get_guild(self.bot_config.GUILD_ID).get_channel(self.bot_config.CHAT_CHANNEL_ID)
        if chat_channel:
            embed = discord.Embed(description=f"{user.mention} **UNBANNED**", color=discord.Color.green())
            embed.set_author(name=user.name, icon_url=user.display_avatar.url)
            embed.set_thumbnail(url=user.display_avatar.url)

            try:
                user_obj = await self.bot.fetch_user(user.id)
                if user_obj.banner: embed.set_image(url=user_obj.banner.url)
            except Exception: pass

            embed.add_field(name="Moderator", value=moderator.mention, inline=True)
            await chat_channel.send(embed=embed)

            async with self.state.moderation_lock:
                self.state.recent_unbans.append((
                    user.id, user.name, user.display_name, datetime.now(timezone.utc), moderator.name
                ))
                if len(self.state.recent_unbans) > 100: self.state.recent_unbans.pop(0)

    @handle_errors
    async def handle_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        """
        Handles the on_member_ban event. This now acts as the primary source for ban info.
        """
        if guild.id != self.bot_config.GUILD_ID: return
        
        chat_channel = guild.get_channel(self.bot_config.CHAT_CHANNEL_ID)
        if not chat_channel: return

        reason, moderator = "No reason provided", "Unknown"
        try:
            # Look for the specific ban action in the audit log
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
                if entry.target and entry.target.id == user.id:
                    moderator, reason = entry.user, entry.reason or "No reason provided"
                    break
        except Exception as e:
            logger.error(f"Could not fetch audit log for ban: {e}")
        
        embed = await self._create_departure_embed(user, moderator, reason, "BANNED", discord.Color.red())
        await chat_channel.send(embed=embed)
        
        async with self.state.moderation_lock:
            # Mark this user as banned so on_member_remove knows to ignore them
            self.state.recently_banned_ids.add(user.id)
            self.state.recent_bans.append((user.id, user.name, getattr(user, 'display_name', user.name), datetime.now(timezone.utc), reason))

    @handle_errors
    async def handle_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        """Handles the on_member_unban event, finding the moderator from the audit log."""
        if guild.id != self.bot_config.GUILD_ID: return

        await asyncio.sleep(2)
        async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
            if entry.target.id == user.id:
                await self.send_unban_notification(user, entry.user)
                return
        logger.warning(f"Unban for {user.name} detected, but audit log entry not found.")
        await self.send_unban_notification(user, self.bot.user)

    @handle_errors
    async def handle_member_remove(self, member: discord.Member) -> None:
        """
        FIX: Handles member departure by deterministically checking for a ban or kick first,
        then processing as a leave. This removes the old race condition.
        """
        if member.guild.id != self.bot_config.GUILD_ID: return

        guild = member.guild
        chat_channel = guild.get_channel(self.bot_config.CHAT_CHANNEL_ID)
        if not chat_channel: return

        # Give the on_member_ban event a moment to fire and add the user to the banned set
        await asyncio.sleep(2)

        async with self.state.moderation_lock:
            if member.id in self.state.recently_banned_ids:
                # This departure was a ban and was already handled by on_member_ban.
                self.state.recently_banned_ids.remove(member.id) # Clean up the entry
                logger.info(f"Departure of {member.name} confirmed as a ban, skipping further processing.")
                return

        # If it wasn't a ban, check if it was a kick.
        try:
            # Check the audit log for a kick within the last 30 seconds.
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.kick, after=datetime.now(timezone.utc) - timedelta(seconds=30)):
                if entry.target and entry.target.id == member.id:
                    reason = entry.reason or "No reason provided"
                    embed = await self._create_departure_embed(member, entry.user, reason, "KICKED", discord.Color.orange())
                    await chat_channel.send(embed=embed)
                    logger.info(f"Processed departure for {member.name} as a KICK.")
                    async with self.state.moderation_lock:
                        roles = [role.mention for role in member.roles if role.name != "@everyone"]
                        self.state.recent_kicks.append((member.id, member.name, member.display_name, datetime.now(timezone.utc), reason, entry.user.mention, " ".join(roles)))
                    return # Kick handled, we are done.
        except discord.Forbidden:
            logger.warning("Missing permissions to check audit log for kicks.")
        except Exception as e:
            logger.error(f"Error checking audit log for kick: {e}")

        # If it was neither a ban nor a kick, it must be a leave.
        join_time = member.joined_at or datetime.now(timezone.utc)
        duration = datetime.now(timezone.utc) - join_time
        duration_str = format_departure_time(duration)

        embed = discord.Embed(color=discord.Color.red(), description=f"{member.mention} **LEFT the SERVER**")
        embed.set_author(name=member.name, icon_url=member.display_avatar.url)
        embed.add_field(name="Time in Server", value=duration_str, inline=True)
        
        roles = [role.mention for role in member.roles if role.name != "@everyone"]
        if roles:
            roles.reverse()
            embed.add_field(name="Roles", value=" ".join(roles), inline=True)
        
        await chat_channel.send(embed=embed)
        logger.info(f"Processed departure for {member.name} as a LEAVE.")
        async with self.state.moderation_lock:
            self.state.recent_leaves.append((member.id, member.name, member.display_name, datetime.now(timezone.utc), " ".join(roles)))

    @handle_errors
    async def show_bans(self, ctx) -> None:
        """(Command) Lists all banned users in the server."""
        record_command_usage(self.state.analytics, "!bans")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!bans")

        ban_entries = [entry async for entry in ctx.guild.bans()]
        if not ban_entries:
            await ctx.send("No users are currently banned.")
            return

        def process_ban(entry):
            user = entry.user
            reason = entry.reason or "No reason provided"
            return f"• `{user.name}` (`{user.id}`) | Reason: *{reason}*"

        embeds = create_message_chunks(
            entries=ban_entries,
            title=f"Banned Users (Total: {len(ban_entries)})",
            process_entry=process_ban,
            as_embed=True,
            embed_color=discord.Color.red()
        )

        for embed in embeds: await ctx.send(embed=embed)

    @handle_errors
    async def show_top_members(self, ctx) -> None:
        """(Command) Lists the top 10 oldest server members and top 10 oldest Discord accounts."""
        await ctx.send("Gathering member data, this may take a moment...")
        
        members = list(ctx.guild.members)
        joined_members = sorted([m for m in members if m.joined_at], key=lambda m: m.joined_at)[:10]
        created_members = sorted(members, key=lambda m: m.created_at)[:10]

        async def create_member_embed(member, rank, color, show_join_date=True):
            user_obj = member
            try:
                # Fetch full user object to get banner, but don't fail if it doesn't work
                fetched_user = await self.bot.fetch_user(member.id)
                if fetched_user:
                    user_obj = fetched_user
            except Exception:
                pass # Fallback to the member object if fetch fails

            embed = discord.Embed(title=f"#{rank} - {member.display_name}", description=f"{member.mention}", color=color)
            embed.set_author(name=f"{member.name}#{member.discriminator}", icon_url=member.display_avatar.url)
            embed.set_thumbnail(url=member.display_avatar.url)
            if hasattr(user_obj, 'banner') and user_obj.banner:
                embed.set_image(url=user_obj.banner.url)

            embed.add_field(name="Account Created", value=f"{member.created_at.strftime('%Y-%m-%d')}\n({get_discord_age(member.created_at)} old)", inline=True)
            if show_join_date and member.joined_at:
                embed.add_field(name="Joined Server", value=f"{member.joined_at.strftime('%Y-%m-%d')}\n({get_discord_age(member.joined_at)} ago)", inline=True)
            
            roles = [role.mention for role in member.roles if role.name != "@everyone"]
            if roles:
                role_str = " ".join(roles)
                if len(role_str) > 1024:
                    role_str = "Too many roles to display."
                embed.add_field(name=f"Roles ({len(roles)})", value=role_str, inline=False)
            
            return embed

        await ctx.send("**🏆 Top 10 Oldest Server Members (by join date)**")
        if not joined_members:
            await ctx.send("No members with join dates found in the server.")
        else:
            for i, member in enumerate(joined_members, 1):
                embed = await create_member_embed(member, i, discord.Color.gold())
                await ctx.send(embed=embed)

        await ctx.send("**🕰️ Top 10 Oldest Discord Accounts (by creation date)**")
        for i, member in enumerate(created_members, 1):
            embed = await create_member_embed(member, i, discord.Color.blue())
            await ctx.send(embed=embed)

    @handle_errors
    async def show_info(self, ctx) -> None:
        """(Command) Sends the pre-configured info messages to the channel."""
        command_name = f"!{ctx.invoked_with}"
        record_command_usage(self.state.analytics, command_name)
        record_command_usage_by_user(self.state.analytics, ctx.author.id, command_name)
        for msg in self.bot_config.INFO_MESSAGES: await ctx.send(msg)

    @handle_errors
    async def list_roles(self, ctx) -> None:
        """(Command) Lists all roles in the server and the members in each role."""
        record_command_usage(self.state.analytics, "!roles")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!roles")

        for role in sorted(ctx.guild.roles, key=lambda r: r.position, reverse=True):
            if role.name != "@everyone" and role.members:
                def process_member(member): return f"{member.display_name} ({member.name}#{member.discriminator})"
                
                embeds = create_message_chunks(
                    entries=role.members, title=f"Role: {role.name}", process_entry=process_member,
                    as_embed=True, embed_color=role.color or discord.Color.default()
                )
                for i, embed in enumerate(embeds):
                    if len(embeds) > 1: embed.title = f"{embed.title} (Part {i + 1})"
                    embed.set_footer(text=f"Total members: {len(role.members)}")
                    await ctx.send(embed=embed)

    @handle_errors
    async def show_admin_list(self, ctx) -> None:
        """(Command) Lists all configured bot owners and server admins."""
        from tools import build_embed
        record_command_usage(self.state.analytics, "!admin")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!admin")
        guild = ctx.guild
        if not guild: return

        owners_list = []
        for user_id in self.bot_config.ALLOWED_USERS:
            member = guild.get_member(user_id)
            if member: owners_list.append(f"{member.name} ({member.display_name})")
            else:
                try:
                    user = await self.bot.fetch_user(user_id)
                    owners_list.append(f"{user.name} (Not in server, ID: {user_id})")
                except discord.NotFound: owners_list.append(f"Unknown User (ID: {user_id})")

        admins_set = set()
        admin_roles = [role for role in guild.roles if role.name in self.bot_config.ADMIN_ROLE_NAME]
        for role in admin_roles:
            for member in role.members:
                if member.id not in self.bot_config.ALLOWED_USERS: admins_set.add(f"{member.name} ({member.display_name})")

        owners_text = "\n".join(sorted(owners_list)) if owners_list else "👑 No owners found."
        admins_text = "\n".join(sorted(list(admins_set))) if admins_set else "🛡️ No admins found."

        embed_owners = build_embed("👑 Owners", owners_text, discord.Color.gold())
        embed_admins = build_embed("🛡️ Admins", admins_text, discord.Color.red())

        await ctx.send(embed=embed_owners)
        await ctx.send(embed=embed_admins)

    @handle_errors
    async def show_commands_list(self, ctx) -> None:
        """(Command) Displays a formatted list of all available bot commands, sorted by permission level."""
        from tools import build_embed
        record_command_usage(self.state.analytics, "!commands")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!commands")
        user_commands = (
            "`!skip/!start` - Skips or starts Omegle.\n`!refresh/!pause` - Refreshes the Omegle page.\n"
            "`!info/!about` - Lists Server Info and Rules.\n`!times` - Shows top 10 voice channel user times."
        )
        admin_commands = (
            "`!timeouts` - Lists current timeouts / removals.\n`!rtimeouts` - Removes timeouts from ALL members.\n"
            "`!help` - Displays Omegle controls with buttons.\n`!roles` - Lists roles and their members.\n"
            "`!rules` - Lists Server rules.\n`!admin/!owner` - Lists Admins and Owners.\n"
            "`!commands` - Full list of all bot commands."
        )
        allowed_commands = (
            "`!purge [number]` - Purges messages from the channel.\n`!modoff/!modon` - Disables VC Moderation.\n"
            "`!banned/!bans` - Lists all users who are server banned.\n`!top` - Lists the top 10 longest members of the server.\n"
            "`!join` - Sends a join invite DM to admin role members.\n`!whois` - Lists timeouts, untimeouts, joins, leaves, kicks.\n"
            "`!stats` - Lists VC Time / Command usage Stats.\n`!clear` - Clears the VC / Command usage data.\n"
            "`!hush` - Server mutes everyone in the Streaming VC.\n`!rhush` - Removes mute status from everyone in Streaming VC.\n"
            "`!secret` - Server mutes + deafens everyone in Streaming VC.\n`!rsecret` - Removes mute and deafen statuses from Streaming VC."
        )
        await ctx.send(embed=build_embed("👤 User Commands", user_commands, discord.Color.blue()))
        await ctx.send(embed=build_embed("🛡️ Admin/Allowed Commands", admin_commands, discord.Color.red()))
        await ctx.send(embed=build_embed("👑 Allowed Users Only Commands", allowed_commands, discord.Color.gold()))

    @handle_errors
    async def show_whois(self, ctx) -> None:
        """(Command) Displays a comprehensive report of recent moderation and member activities."""
        record_command_usage(self.state.analytics, "!whois")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!whois")

        now = datetime.now(timezone.utc)
        reports = {}
        has_data = False

        # --- Data Gathering ---
        async with self.state.moderation_lock:
            time_filter = now - timedelta(hours=24)
            timed_out_members = [member for member in ctx.guild.members if member.is_timed_out()]
            untimeout_list = [e for e in self.state.recent_untimeouts if e[3] >= time_filter and (len(e) > 5 and e[5] and e[5] != "System")]
            kick_list = [e for e in self.state.recent_kicks if e[3] >= time_filter]
            ban_list = [e for e in self.state.recent_bans if e[3] >= time_filter]
            unban_list = [e for e in self.state.recent_unbans if e[3] >= time_filter]
            join_list = [e for e in self.state.recent_joins if e[3] >= time_filter]
            leave_list = [e for e in self.state.recent_leaves if e[3] >= time_filter]
            role_change_list = [e for e in self.state.recent_role_changes if e[4] >= time_filter]


        # --- User Info Mapping ---
        user_ids_to_map = {entry[0] for data_list in [untimeout_list, kick_list, ban_list, unban_list, join_list, leave_list, role_change_list] for entry in data_list}
        user_map = {}
        if user_ids_to_map:
            cached_ids = set()
            for user_id in user_ids_to_map:
                if member := ctx.guild.get_member(user_id):
                    user_map[user_id] = member
                    cached_ids.add(user_id)
            for user_id in (user_ids_to_map - cached_ids):
                try: user_map[user_id] = await self.bot.fetch_user(user_id)
                except discord.NotFound: user_map[user_id] = None

        # --- Helper Functions ---
        def get_clean_mention(identifier):
            if identifier is None: return "Unknown"
            if isinstance(identifier, int):
                if member := ctx.guild.get_member(identifier): return member.mention
            if member := discord.utils.find(lambda m: m.name == str(identifier) or m.display_name == str(identifier), ctx.guild.members): return member.mention
            return str(identifier)

        def get_user_display_info(user_id, stored_username=None, stored_display_name=None):
            user = user_map.get(user_id)
            if user: return f"{user.mention} ({user.name})"
            name = stored_username or "Unknown User"
            return f"`{name}` <@{user_id}>"

        # --- Report Generation ---
        if timed_out_members:
            has_data = True
            def process_timeout(member):
                data = self.state.active_timeouts.get(member.id, {})
                timed_by = data.get("timed_by_id", data.get("timed_by", "Unknown"))
                reason = data.get("reason", "No reason provided")
                start_ts = data.get("start_timestamp")
                
                line = f"• {member.mention} - by {get_clean_mention(timed_by)}"
                if reason and reason != "No reason provided":
                    line += f" for *{reason}*"
                
                if start_ts:
                    line += f" | <t:{int(start_ts)}:R>"
                return line
            reports["⏳ Timed Out Members"] = create_message_chunks(timed_out_members, "⏳ Timed Out Members", process_timeout, as_embed=True, embed_color=discord.Color.orange())

        if untimeout_list:
            has_data = True
            def process_untimeout(entry):
                uid, _, _, ts, _, mod_name, mod_id = entry
                mod_mention = get_clean_mention(mod_id or mod_name)
                return f"• <@{uid}> - by {mod_mention} <t:{int(ts.timestamp())}:R>"
            reports["🔓 Recent Untimeouts"] = create_message_chunks(untimeout_list, "🔓 Recent Untimeouts (24h)", process_untimeout, as_embed=True, embed_color=discord.Color.from_rgb(173, 216, 230))

        if kick_list:
            has_data = True
            def process_kick(entry):
                uid, name, dname, ts, reason, mod, _ = entry
                user_info = get_user_display_info(uid, name, dname)
                line = f"• {user_info} - by {mod}"
                if reason and reason != "No reason provided":
                    line += f" for *{reason}*"
                line += f" <t:{int(ts.timestamp())}:R>"
                return line
            reports["👢 Recent Kicks"] = create_message_chunks(kick_list, "👢 Recent Kicks (24h)", process_kick, as_embed=True, embed_color=discord.Color.orange())

        if ban_list:
            has_data = True
            def process_ban(entry):
                uid, name, dname, ts, reason = entry
                user_info = get_user_display_info(uid, name, dname)
                line = f"• {user_info}"
                if reason and reason != "No reason provided":
                    line += f" - for *{reason}*"
                line += f" <t:{int(ts.timestamp())}:R>"
                return line
            reports["🔨 Recent Bans"] = create_message_chunks(ban_list, "🔨 Recent Bans (24h)", process_ban, as_embed=True, embed_color=discord.Color.dark_red())

        if unban_list:
            has_data = True
            def process_unban(entry):
                uid, name, dname, ts, mod = entry
                user_info = get_user_display_info(uid, name, dname)
                return f"• {user_info} - by {mod} <t:{int(ts.timestamp())}:R>"
            reports["🔓 Recent Unbans"] = create_message_chunks(unban_list, "🔓 Recent Unbans (24h)", process_unban, as_embed=True, embed_color=discord.Color.dark_green())
            
        if role_change_list:
            has_data = True
            def process_role_change(entry):
                uid, name, gained, lost, ts = entry
                user_info = get_user_display_info(uid, name)
                parts = [f"• {user_info} <t:{int(ts.timestamp())}:R>"]
                if gained: parts.append(f"  - **Gained**: {', '.join(gained)}")
                if lost: parts.append(f"  - **Lost**: {', '.join(lost)}")
                return parts
            reports["🎭 Recent Role Changes"] = create_message_chunks(role_change_list, "🎭 Recent Role Changes (24h)", process_role_change, as_embed=True, embed_color=discord.Color.purple())

        if join_list:
            has_data = True
            def process_join(entry):
                uid, name, dname, ts = entry
                user_info = get_user_display_info(uid, name, dname)
                return f"• {user_info} <t:{int(ts.timestamp())}:R>"
            reports["🎉 Recent Joins"] = create_message_chunks(join_list, "🎉 Recent Joins (24h)", process_join, as_embed=True, embed_color=discord.Color.green())

        if leave_list:
            has_data = True
            def process_leave(entry):
                uid, name, dname, ts, _ = entry
                user_info = get_user_display_info(uid, name, dname)
                return f"• {user_info} <t:{int(ts.timestamp())}:R>"
            reports["🚪 Recent Leaves"] = create_message_chunks(leave_list, "🚪 Recent Leaves (24h)", process_leave, as_embed=True, embed_color=discord.Color.red())

        # --- Displaying Reports ---
        if not has_data:
            await ctx.send("📭 No recent activity found in the last 24 hours.")
            return

        report_order = ["⏳ Timed Out Members", "🔓 Recent Untimeouts", "👢 Recent Kicks", "🔨 Recent Bans", "🔓 Recent Unbans", "🎭 Recent Role Changes", "🎉 Recent Joins", "🚪 Recent Leaves"]
        for report_type in report_order:
            if report_type in reports:
                for embed in reports[report_type]:
                    await ctx.send(embed=embed)
                    await asyncio.sleep(0.5)

    @handle_errors
    async def remove_timeouts(self, ctx) -> None:
        """(Command) Removes all active timeouts from members in the server."""
        record_command_usage(self.state.analytics, "!rtimeouts")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!rtimeouts")

        timed_out_members = [m for m in ctx.guild.members if m.is_timed_out()]
        if not timed_out_members:
            await ctx.send("No users are currently timed out.")
            return

        confirm_msg = await ctx.send(f"⚠️ **WARNING:** This will remove timeouts from {len(timed_out_members)} members!\nReact with ✅ to confirm or ❌ to cancel within 30 seconds.")
        for emoji in ["✅", "❌"]: await confirm_msg.add_reaction(emoji)

        def check(reaction, user): return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id
        try:
            reaction, _ = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
            if str(reaction.emoji) == "❌": await ctx.send("Command cancelled."); return
        except asyncio.TimeoutError:
            await ctx.send("⌛ Command timed out. No changes were made."); return

        removed, failed = [], []
        for member in timed_out_members:
            try:
                await member.timeout(None, reason=f"Timeout removed by {ctx.author.name} ({ctx.author.id})")
                removed.append(member.name)
                async with self.state.moderation_lock:
                    if member.id in self.state.active_timeouts:
                        self.state.recent_untimeouts.append((member.id, member.name, member.display_name, datetime.now(timezone.utc), f"Manually removed by {ctx.author.name}", ctx.author.name, ctx.author.id))
                        del self.state.active_timeouts[member.id]
                logger.info(f"Removed timeout from {member.name} by {ctx.author.name}")
            except discord.Forbidden: failed.append(f"{member.name} (Missing Permissions)")
            except discord.HTTPException as e: failed.append(f"{member.name} (Error: {e})")

        result_msg = []
        if removed: result_msg.append(f"**✅ Removed timeouts from:**\n- " + "\n".join(removed))
        if failed: result_msg.append(f"\n**❌ Failed to remove timeouts from:**\n- " + "\n".join(failed))
        if result_msg: await ctx.send("\n".join(result_msg))

        if chat_channel := ctx.guild.get_channel(self.bot_config.CHAT_CHANNEL_ID):
            await chat_channel.send(f"⏰ **Mass Timeout Removal**\nExecuted by {ctx.author.mention}\nRemoved: {len(removed)} | Failed: {len(failed)}")

    @handle_errors
    async def show_rules(self, ctx) -> None:
        """(Command) Posts the server rules to the channel."""
        record_command_usage(self.state.analytics, "!rules")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!rules")
        await ctx.send("📋 **Server Rules:**\n" + self.bot_config.RULES_MESSAGE)

    @handle_errors
    async def show_timeouts(self, ctx) -> None:
        """(Command) Displays a report of current timeouts and a history of manual untimeouts."""
        record_command_usage(self.state.analytics, "!timeouts")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!timeouts")

        reports, has_data = {}, False

        def get_clean_mention(identifier):
            if identifier is None: return "Unknown"
            if isinstance(identifier, int):
                if member := ctx.guild.get_member(identifier): return member.mention
            if member := discord.utils.find(lambda m: m.name == str(identifier) or m.display_name == str(identifier), ctx.guild.members): return member.mention
            return str(identifier)

        timed_out_members = [member for member in ctx.guild.members if member.is_timed_out()]
        if timed_out_members:
            has_data = True
            async def process_timeout(member):
                async with self.state.moderation_lock:
                    data = self.state.active_timeouts.get(member.id, {})
                timed_by = data.get("timed_by_id", data.get("timed_by"))
                reason = data.get("reason")
                start_ts = data.get("start_timestamp")
                
                line = f"• {member.mention}"
                if timed_by and timed_by != "Unknown":
                    line += f" - by {get_clean_mention(timed_by)}"
                if reason and reason != "No reason provided":
                    line += f" for *{reason}*"
                
                if start_ts:
                    line += f" | <t:{int(start_ts)}:R>"
                return line
            processed_timeouts = await asyncio.gather(*(process_timeout(m) for m in timed_out_members))
            reports["⏳ Currently Timed Out"] = create_message_chunks(processed_timeouts, "⏳ Currently Timed Out", lambda x: x, as_embed=True, embed_color=discord.Color.orange())

        async with self.state.moderation_lock:
            untimeout_entries = [e for e in self.state.recent_untimeouts if len(e) > 5 and e[5] and e[5] != "System"]
        if untimeout_entries:
            has_data = True
            processed_users = set()

            def process_untimeout(entry):
                user_id = entry[0]
                ts = entry[3]  # The datetime object for the untimeout event
                mod_name = entry[5]
                mod_id = entry[6] if len(entry) > 6 else None
                mod_mention = get_clean_mention(mod_id) if mod_id else get_clean_mention(mod_name)
                
                line = f"• <@{user_id}>"
                if mod_mention and mod_mention != "Unknown":
                    line += f" - Removed by: {mod_mention}"
                
                # Add the relative timestamp, just like in !whois
                line += f" <t:{int(ts.timestamp())}:R>"
                return line

            unique_untimeout_entries = []
            for entry in reversed(untimeout_entries):
                if entry[0] not in processed_users:
                    unique_untimeout_entries.append(entry)
                    processed_users.add(entry[0])

            processed_untimeouts = [process_untimeout(e) for e in reversed(unique_untimeout_entries)]
            reports["🔓 All Untimeouts"] = create_message_chunks(processed_untimeouts, "🔓 All Untimeouts", lambda x: x, as_embed=True, embed_color=discord.Color.blue())

        for report_type in ["⏳ Currently Timed Out", "🔓 All Untimeouts"]:
            if report_type in reports and reports[report_type]:
                for embed in reports[report_type]:
                    await ctx.send(embed=embed)
        if not has_data:
            await ctx.send("📭 No active timeouts or untimeouts found")

    async def _send_vc_time_report(self, destination: discord.abc.Messageable) -> None:
        """
        An internal helper function to generate and send the voice channel time report.
        This is used by both the `!times` command and the daily auto-stats task.
        """
        guild = destination.guild if hasattr(destination, 'guild') else self.bot.get_guild(self.bot_config.GUILD_ID)

        async def get_user_display_info(user_id, data):
            """Gets a user's display info, trying the live member object first then falling back to stored data."""
            if member := guild.get_member(user_id):
                roles = [role for role in member.roles if role.name != "@everyone"]
                highest_role = max(roles, key=lambda r: r.position) if roles else None
                role_display = f"**[{highest_role.name}]**" if highest_role else ""
                return f"{member.mention} {role_display} ({member.name})"
            username = data.get("username", "Unknown User")
            return f"`{username}` (Left/Not Found) <@{user_id}>"

        def is_excluded(user_id): return user_id in self.bot_config.STATS_EXCLUDED_USERS

        async def get_vc_time_data():
            """Calculates total VC time for all users, including current active sessions."""
            async with self.state.vc_lock:
                current_time = time.time()
                combined_data = {uid: d.copy() for uid, d in self.state.vc_time_data.items() if not is_excluded(uid)}
                total_time_all_users = sum(d.get("total_time", 0) for d in combined_data.values())

                for user_id, start_time in self.state.active_vc_sessions.items():
                    if is_excluded(user_id): continue
                    active_duration = current_time - start_time
                    if user_id in combined_data: combined_data[user_id]["total_time"] += active_duration
                    else:
                        member = guild.get_member(user_id)
                        combined_data[user_id] = { "total_time": active_duration, "username": member.name if member else "Unknown", "display_name": member.display_name if member else "Unknown" }
                    total_time_all_users += active_duration
            
            sorted_users = sorted(combined_data.items(), key=lambda item: item[1].get("total_time", 0), reverse=True)[:10]
            return total_time_all_users, sorted_users

        total_tracking_seconds = 0
        async with self.state.vc_lock:
            if self.state.vc_time_data:
                all_sessions = [s["start"] for d in self.state.vc_time_data.values() for s in d.get("sessions", [])]
                if all_sessions:
                    total_tracking_seconds = time.time() - min(all_sessions)

        tracking_time_str = format_duration(total_tracking_seconds)
        await destination.send(f"⏳ **Tracking Started:** {tracking_time_str} ago\n")

        total_time_all_users, top_vc_users = await get_vc_time_data()

        if top_vc_users:
            async def process_vc_entry(entry):
                uid, data = entry
                total_s = data.get('total_time', 0)
                time_str = format_duration(total_s)
                display_info = await get_user_display_info(uid, data)
                return f"• {display_info}: {time_str}"
            processed_entries = await asyncio.gather(*(process_vc_entry(entry) for entry in top_vc_users))
            for chunk in create_message_chunks(processed_entries, "🏆 Top 10 VC Members", lambda x: x, 10, as_embed=True, embed_color=discord.Color.gold()):
                await destination.send(embed=chunk)
        else: await destination.send("No VC time data available yet.")

        total_time_str = format_duration(total_time_all_users)
        await destination.send(f"⏱ **Total VC Time (All Users):** {total_time_str}")

    @handle_errors
    async def show_times_report(self, destination: Union[commands.Context, discord.TextChannel]) -> None:
        """(Command) Public-facing function to show the VC time report."""
        if isinstance(destination, commands.Context):
            record_command_usage(self.state.analytics, "!times")
            record_command_usage_by_user(self.state.analytics, destination.author.id, "!times")
        await self._send_vc_time_report(destination.channel if isinstance(destination, commands.Context) else destination)

    @handle_errors
    async def show_analytics_report(self, ctx) -> None:
        """(Command) Shows a detailed report of VC time, command usage, and moderation events."""
        record_command_usage(self.state.analytics, "!stats")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!stats")

        await self._send_vc_time_report(ctx.channel)
        await ctx.send("\n" + "─"*50 + "\n")

        async def get_user_display_info(user_id):
            """Helper to get a rich display name for a user in the stats report."""
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                if member := ctx.guild.get_member(user_id):
                    roles = [role for role in member.roles if role.name != "@everyone"]
                    highest_role = max(roles, key=lambda r: r.position) if roles else None
                    role_display = f"**[{highest_role.name}]**" if highest_role else ""
                    return f"{member.mention} {role_display} ({member.name})"
                return f"{user.mention} ({user.name})"
            except Exception: return f"<@{user_id}> (Unknown User)"

        def is_excluded(user_id): return user_id in self.bot_config.STATS_EXCLUDED_USERS

        has_stats_data = False
        async with self.state.analytics_lock:
            if self.state.analytics.get("command_usage"):
                has_stats_data = True
                commands = sorted(self.state.analytics["command_usage"].items(), key=lambda x: x[1], reverse=True)
                for chunk in create_message_chunks(commands, "📊 Overall Command Usage", lambda cmd: f"• `{cmd[0]}`: {cmd[1]} times", as_embed=True, embed_color=discord.Color.blue()):
                    await ctx.send(embed=chunk)

            if self.state.analytics.get("command_usage_by_user"):
                has_stats_data = True
                filtered_users = [(uid, cmds) for uid, cmds in self.state.analytics["command_usage_by_user"].items() if not is_excluded(uid)]
                sorted_users = sorted(filtered_users, key=lambda item: sum(item[1].values()), reverse=True)[:10]
                async def process_user_usage(entry):
                    uid, cmds = entry
                    usage = ", ".join([f"{c}: {cnt}" for c, cnt in sorted(cmds.items(), key=lambda x: x[1], reverse=True)])
                    return f"• {await get_user_display_info(uid)}: {usage}"
                processed_entries = await asyncio.gather(*(process_user_usage(entry) for entry in sorted_users))
                for chunk in create_message_chunks(processed_entries, "👤 Top 10 Command Users", lambda x: x, as_embed=True, embed_color=discord.Color.green()):
                    await ctx.send(embed=chunk)

        async with self.state.moderation_lock:
            if self.state.user_violations:
                has_stats_data = True
                filtered_violations = [(uid, count) for uid, count in self.state.user_violations.items() if not is_excluded(uid)]
                sorted_violations = sorted(filtered_violations, key=lambda item: item[1], reverse=True)[:10]
                async def process_violation(entry):
                    uid, count = entry
                    if member := ctx.guild.get_member(uid):
                        user_display_str = f"`{member.name}` (`{member.display_name}`)" if member.name != member.display_name else f"`{member.name}`"
                    else:
                        try: user_display_str = f"`{(await self.bot.fetch_user(uid)).name}` (Left Server)"
                        except discord.NotFound: user_display_str = f"Unknown User (ID: `{uid}`)"
                    return f"• {user_display_str}: {count} violation(s)"
                processed_entries = await asyncio.gather(*(process_violation(entry) for entry in sorted_violations))
                for chunk in create_message_chunks(processed_entries, "⚠️ No-Cam Detected Report", lambda x: x, as_embed=True, embed_color=discord.Color.orange()):
                    await ctx.send(embed=chunk)

        if not has_stats_data: await ctx.send("📊 No command/violation statistics available yet.")

    @handle_errors
    async def send_join_invites(self, ctx) -> None:
        """(Command) Sends a pre-configured DM to all users with an admin role."""
        record_command_usage(self.state.analytics, "!join")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!join")

        guild = ctx.guild
        admin_role_names = self.bot_config.ADMIN_ROLE_NAME
        join_message = self.bot_config.JOIN_INVITE_MESSAGE

        admin_roles = [role for role in guild.roles if role.name in admin_role_names]
        if not admin_roles:
            await ctx.send("No admin roles found with the specified names."); return

        members_to_dm = {member for role in admin_roles for member in role.members}
        if not members_to_dm:
            await ctx.send("No members with the specified admin roles found to DM."); return

        await ctx.send(f"Sending invites to {len(members_to_dm)} member(s) with the role(s): {', '.join(admin_role_names)}. This may take a moment...")

        impacted = []
        for member in members_to_dm:
            if member.bot: continue
            try:
                await member.send(join_message)
                impacted.append(member.name)
                logger.info(f"Sent join invite to {member.name}.")
                await asyncio.sleep(1)
            except discord.Forbidden: logger.warning(f"Could not DM {member.name} (DMs are disabled or bot is blocked).")
            except Exception as e: logger.error(f"Error DMing {member.name}: {e}")

        if impacted:
            msg = "Finished sending invites. Sent to: " + ", ".join(impacted)
            logger.info(msg)
            await ctx.send(msg)
        else: await ctx.send("Finished processing. No invites were successfully sent.")

    @handle_errors
    async def clear_stats(self, ctx) -> None:
        """(Command) Resets all statistical data after a confirmation prompt."""
        confirm_msg = await ctx.send("⚠️ This will reset ALL statistics data (VC times, command usage, violations).\nReact with ✅ to confirm or ❌ to cancel.")
        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")

        def check(reaction, user): return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id
        try:
            reaction, _ = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
            if str(reaction.emoji) == "✅":
                guild = ctx.guild
                streaming_vc = guild.get_channel(self.bot_config.STREAMING_VC_ID)
                alt_vc = guild.get_channel(self.bot_config.ALT_VC_ID)
                current_members = []
                if streaming_vc: current_members.extend([m for m in streaming_vc.members if not m.bot])
                if alt_vc: current_members.extend([m for m in alt_vc.members if not m.bot])

                async with self.state.vc_lock, self.state.analytics_lock, self.state.moderation_lock:
                    self.state.vc_time_data = {}
                    self.state.active_vc_sessions = {}
                    self.state.analytics = {"command_usage": {}, "command_usage_by_user": {}, "violation_events": 0}
                    self.state.user_violations = {}
                    self.state.camera_off_timers = {}

                    if current_members:
                        current_time = time.time()
                        for member in current_members:
                            self.state.active_vc_sessions[member.id] = current_time
                            self.state.vc_time_data[member.id] = {"total_time": 0, "sessions": [], "username": member.name, "display_name": member.display_name}
                        logger.info(f"Restarted VC tracking for {len(current_members)} current members")
                await ctx.send("✅ All statistics data has been reset.")
                logger.info(f"Statistics cleared by {ctx.author.name} (ID: {ctx.author.id})")
                if self.save_state:
                    await self.save_state()
            else: await ctx.send("❌ Statistics reset cancelled.")
        except asyncio.TimeoutError: await ctx.send("⌛ Command timed out. No changes were made.")
        finally:
            try: await confirm_msg.delete()
            except Exception: pass
