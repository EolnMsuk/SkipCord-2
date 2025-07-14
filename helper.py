# helper.py

import asyncio
import discord
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional, Union, List

from discord.ext import commands

from tools import (
    BotState,
    BotConfig,
    get_discord_age,
    record_command_usage,
    record_command_usage_by_user,
)

def create_message_chunks(
    entries: List[Any], 
    title: str, 
    process_entry: Callable[[Any], str], 
    max_chunk_size: int = 50,
    max_length: int = 1900,
    as_embed: bool = False,
    embed_color: Optional[discord.Color] = None
) -> Union[List[str], List[discord.Embed]]:
    """
    Creates message chunks from entries while respecting both count and length limits.
    Can return either text chunks or embed chunks.
    """
    if as_embed and embed_color is None:
        raise ValueError("embed_color must be provided when as_embed=True")
        
    chunks = []
    current_chunk = []
    current_length = 0
    
    title_text = f"**{title} ({len(entries)} total)**\n"
    title_length = len(title_text)
    
    for entry in entries:
        processed = process_entry(entry)
        if processed:
            entry_length = len(processed) + 1  # +1 for newline
            
            if (current_length + entry_length + title_length > max_length and current_chunk) or \
               (len(current_chunk) >= max_chunk_size):
                if as_embed:
                    embed = discord.Embed(
                        title=title,
                        description="\n".join(current_chunk),
                        color=embed_color
                    )
                    chunks.append(embed)
                else:
                    chunks.append(title_text + "\n".join(current_chunk))
                current_chunk = []
                current_length = 0
                
            current_chunk.append(processed)
            current_length += entry_length
    
    if current_chunk:
        if as_embed:
            embed = discord.Embed(
                title=title,
                description="\n".join(current_chunk),
                color=embed_color
            )
            chunks.append(embed)
        else:
            chunks.append(title_text + "\n".join(current_chunk))
    
    return chunks

class BotHelper:
    def __init__(self, bot: commands.Bot, state: BotState, bot_config: BotConfig, save_func: Optional[Callable] = None):
        self.bot = bot
        self.state = state
        self.bot_config = bot_config
        self.save_state = save_func

    async def _log_timeout_in_state(self, member: discord.Member, duration_seconds: int, reason: str, moderator_name: str, moderator_id: Optional[int] = None):
        """Centralized function to log timeout data to the bot's state."""
        async with self.state.moderation_lock:
            self.state.active_timeouts[member.id] = {
                "timeout_end": time.time() + duration_seconds,
                "reason": reason,
                "timed_by": moderator_name,
                "timed_by_id": moderator_id,
                "start_timestamp": time.time()
            }

    async def handle_member_join(self, member: discord.Member) -> None:
        """
        Logs new member joins and triggers a state save for data durability.
        """
        try:
            if member.guild.id == self.bot_config.GUILD_ID:
                chat_channel = member.guild.get_channel(self.bot_config.CHAT_CHANNEL_ID)
                if chat_channel:
                    embed = discord.Embed(
                        description=f"{member.mention} **JOINED the SERVER**!",
                        color=discord.Color.green())
                    
                    avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
                    embed.set_author(name=member.name, icon_url=avatar_url)
                    embed.set_thumbnail(url=avatar_url)
                    
                    try:
                        user = await self.bot.fetch_user(member.id)
                        if user.banner:
                            embed.set_image(url=user.banner.url)
                    except Exception:
                        pass # Ignore if banner cannot be fetched
                    
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
                      
                logging.info(f"{member.name} joined the server {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
                
        except Exception as e:
            logging.error(f"Error in on_member_join: {e}", exc_info=True)

    async def send_timeout_notification(self, member: discord.Member, moderator: discord.User, duration: int, reason: str = None) -> None:
        """Sends a notification when a member is timed out with proper @mentions."""
        try:
            chat_channel = member.guild.get_channel(self.bot_config.CHAT_CHANNEL_ID)
            if not chat_channel:
                return

            hours, remainder = divmod(duration, 3600)
            minutes, seconds = divmod(remainder, 60)
            duration_str = ""
            if hours > 0:
                duration_str += f"{hours} hour{'s' if hours != 1 else ''} "
            if minutes > 0:
                duration_str += f"{minutes} minute{'s' if minutes != 1 else ''} "
            if seconds > 0 or not duration_str:
                duration_str += f"{seconds} second{'s' if seconds != 1 else ''}"

            embed = discord.Embed(
                description=f"{member.mention} **was TIMED OUT**",
                color=discord.Color.orange())
       
            embed.set_author(
                name=f"{member.name}",
                icon_url=member.display_avatar.url
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            
            try:
                user_obj = await self.bot.fetch_user(member.id)
                if user_obj.banner:
                    embed.set_image(url=user_obj.banner.url)
            except Exception:
                pass
            
            embed.add_field(
                name="", 
                value=f"⏱️ {duration_str.strip()}",
                inline=True
            )
            embed.add_field(
                name="", 
                value=f"🛡️ {moderator.name}",
                inline=True
            )
            
            if reason and reason.strip() and reason.lower() != "no reason provided":
                embed.add_field(
                    name="", 
                    value=f"📝 {reason.strip()}",
                    inline=False
                )
            
            await chat_channel.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Error sending timeout notification: {e}", exc_info=True)

    async def send_timeout_removal_notification(self, member: discord.Member, duration: int, reason: str = "Expired Naturally") -> None:
        """Sends a notification when a member's timeout is removed with proper @mentions."""
        try:
            chat_channel = member.guild.get_channel(self.bot_config.CHAT_CHANNEL_ID)
            if not chat_channel:
                return

            hours, remainder = divmod(duration, 3600)
            minutes, seconds = divmod(remainder, 60)
            duration_str = ""
            if hours > 0:
                duration_str += f"{hours} hour{'s' if hours != 1 else ''} "
            if minutes > 0:
                duration_str += f"{minutes} minute{'s' if minutes != 1 else ''} "
            if seconds > 0 or not duration_str:
                duration_str += f"{seconds} second{'s' if seconds != 1 else ''}"

            embed = discord.Embed(
                description=f"{member.mention} **TIMEOUT REMOVED**",
                color=discord.Color.orange())
            
            embed.set_author(
                name=f"{member.name}",
                icon_url=member.display_avatar.url
            )
            embed.set_thumbnail(url=member.display_avatar.url)

            try:
                user_obj = await self.bot.fetch_user(member.id)
                if user_obj.banner:
                    embed.set_image(url=user_obj.banner.url)
            except Exception:
                pass

            embed.add_field(
                name="", 
                value=f"⏱️ {duration_str.strip()}",
                inline=True
            )

            if "manually removed by" in reason.lower() or "Timeout removed by" in reason:
                try:
                    parts = reason.rsplit("by", 1)
                    reason_text = parts[0].strip()
                    mod_name = parts[1].strip().lstrip('🛡️').strip()
                    
                    mod_member = discord.utils.find(
                        lambda m: m.name == mod_name or m.display_name == mod_name,
                        member.guild.members
                    )
                    
                    mod_display = mod_member.name if mod_member else mod_name
                    reason = f"{reason_text} by {mod_display}"
                except Exception as e:
                    logging.warning(f"Error processing moderator name for timeout removal: {e}")

            embed.add_field(
                name="", 
                value=f"📝 {reason}",
                inline=False
            )

            await chat_channel.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Error sending timeout removal notification: {e}", exc_info=True)

    async def send_unban_notification(self, user: discord.User, moderator: discord.User) -> None:
        """Sends a notification when a user is unbanned."""
        try:
            chat_channel = self.bot.get_guild(self.bot_config.GUILD_ID).get_channel(self.bot_config.CHAT_CHANNEL_ID)
            if chat_channel:
                embed = discord.Embed(
                    description=f"{user.mention} **UNBANNED**",
                    color=discord.Color.green())
                
                embed.set_author(name=user.name, icon_url=user.display_avatar.url)
                embed.set_thumbnail(url=user.display_avatar.url)
                
                try:
                    user_obj = await self.bot.fetch_user(user.id)
                    if user_obj.banner:
                        embed.set_image(url=user_obj.banner.url)
                except Exception:
                    pass
                
                embed.add_field(name="Moderator", value=moderator.mention, inline=True)
                
                await chat_channel.send(embed=embed)
                
                async with self.state.moderation_lock:
                    self.state.recent_unbans.append((
                        user.id,
                        user.name,
                        user.display_name,
                        datetime.now(timezone.utc),
                        moderator.name
                    ))
                    
                    if len(self.state.recent_unbans) > 100:
                        self.state.recent_unbans.pop(0)

        except Exception as e:
            logging.error(f"Error sending unban notification: {e}", exc_info=True)

    async def handle_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        """
        Logs when a user is banned. This now acts as a fallback for bans of non-members
        and a de-duplication checker, as on_member_remove handles primary announcements.
        """
        # Give on_member_remove a moment to acquire the lock and set the flag.
        # A short sleep handles near-simultaneous events without causing major delays.
        await asyncio.sleep(2)

        # Check if the ban announcement was already handled by on_member_remove
        async with self.state.moderation_lock:
            if hasattr(self.state, 'announced_bans') and user.id in self.state.announced_bans:
                # It was handled. Clean up the flag and exit.
                self.state.announced_bans.remove(user.id)
                logging.info(f"Ban for {user.name} already handled by on_member_remove. De-duplication successful.")
                return

        # If the flag was not set, it's likely a ban of a user not currently in the server.
        # Proceed with the original fallback logic.
        try:
            chat_channel = guild.get_channel(self.bot_config.CHAT_CHANNEL_ID)
            if not chat_channel:
                return
                
            reason = "No reason provided"
            moderator = "Unknown"
            
            # No need for an extra sleep here, the initial one is enough
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                    if entry.target.id == user.id:
                        moderator = entry.user.mention
                        if entry.reason:
                            reason = entry.reason
                        break
            except Exception as e:
                logging.error(f"Could not fetch audit log for ban: {e}")

            embed = discord.Embed(
                description=f"{user.mention} **BANNED**",
                color=discord.Color.red())
            
            embed.set_author(name=user.name, icon_url=user.display_avatar.url)
            embed.set_thumbnail(url=user.display_avatar.url)
            
            try:
                user_obj = await self.bot.fetch_user(user.id)
                if user_obj.banner:
                    embed.set_image(url=user_obj.banner.url)
            except Exception:
                pass
            
            embed.add_field(name="Moderator", value=moderator, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            
            await chat_channel.send(embed=embed)
        
            async with self.state.moderation_lock:
                self.state.recent_bans.append((
                    user.id,
                    user.name,
                    user.display_name if hasattr(user, 'display_name') else user.name,
                    datetime.now(timezone.utc),
                    reason
                ))
                
                if len(self.state.recent_bans) > 100:
                    self.state.recent_bans.pop(0)
                
            logging.info(f"{user.name} was banned from the server (handled by on_member_ban). Reason: {reason}")
            
        except Exception as e:
            logging.error(f"Error in on_member_ban: {e}", exc_info=True)

    async def handle_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        """Logs when a user is unbanned from the server."""
        try:
            # Brief delay to allow audit log to populate
            await asyncio.sleep(2)
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
                if entry.target.id == user.id:
                    await self.send_unban_notification(user, entry.user)
                    return
            # Fallback if audit log is not found quickly
            logging.warning(f"Unban for {user.name} detected, but audit log entry not found.")
            await self.send_unban_notification(user, self.bot.user)

        except Exception as e:
            logging.error(f"Error in on_member_unban: {e}", exc_info=True)

    async def handle_member_remove(self, member: discord.Member) -> None:
        """
        Logs departures. Checks for bans, kicks vs. leaves more reliably.
        """
        try:
            guild = member.guild
            current_time = datetime.now(timezone.utc)
            was_kicked = False
            
            # 1. Check if the user was banned. This is the new primary handler for bans of existing members.
            try:
                await guild.fetch_ban(member)
                # If the above line doesn't throw discord.NotFound, the user was banned.
                
                # Set the flag immediately to prevent a race condition with on_member_ban
                async with self.state.moderation_lock:
                    if hasattr(self.state, 'announced_bans'):
                        self.state.announced_bans.add(member.id)

                # Handle the ban announcement here where we have the `member` object and its roles.
                logging.info(f"Departure of {member.name} detected as a ban. Handling announcement...")

                reason = "No reason provided"
                moderator = "Unknown"

                # Brief delay to allow audit log to populate
                await asyncio.sleep(2)
                try:
                    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                        if entry.target.id == member.id:
                            moderator = entry.user.mention
                            if entry.reason:
                                reason = entry.reason
                            break
                except Exception as e:
                    logging.error(f"Could not fetch audit log for ban in on_member_remove: {e}")
                
                chat_channel = guild.get_channel(self.bot_config.CHAT_CHANNEL_ID)
                if chat_channel:
                    embed = discord.Embed(
                        description=f"{member.mention} **BANNED**",
                        color=discord.Color.red())

                    embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                    embed.set_thumbnail(url=member.display_avatar.url)

                    try:
                        user_obj = await self.bot.fetch_user(member.id)
                        if user_obj.banner:
                            embed.set_image(url=user_obj.banner.url)
                    except Exception:
                        pass
                    
                    # Add Time in Server
                    if member.joined_at:
                        duration = datetime.now(timezone.utc) - member.joined_at
                        duration_str = f"{duration.days}d {duration.seconds//3600}h {(duration.seconds%3600)//60}m"
                        embed.add_field(name="Time in Server", value=duration_str, inline=True)

                    embed.add_field(name="Moderator", value=moderator, inline=True)
                    
                    # Fetch and add roles
                    roles = [role.name for role in member.roles if role.name != "@everyone"]
                    if roles:
                        embed.add_field(
                            name="Roles",
                            value=", ".join(roles),
                            inline=True
                        )

                    embed.add_field(name="Reason", value=reason, inline=False)
                    await chat_channel.send(embed=embed)

                # Log the ban to the state
                async with self.state.moderation_lock:
                    self.state.recent_bans.append((
                        member.id,
                        member.name,
                        member.display_name,
                        datetime.now(timezone.utc),
                        reason
                    ))
                    if len(self.state.recent_bans) > 100:
                        self.state.recent_bans.pop(0)

                logging.info(f"{member.name} was banned from the server (handled by on_member_remove). Reason: {reason}")
                return # The departure is fully handled, so we exit.

            except discord.NotFound:
                pass # Not banned, proceed to check for kicks or leaves.
            except Exception as e:
                logging.error(f"Error fetching ban for {member.name} in on_member_remove: {e}")

            # 2. Check for a kick by polling the audit log.
            kick_entry = None
            # Poll for a few seconds to account for audit log delays.
            for _ in range(4): # Poll for up to 4 seconds (4 * 1s)
                try:
                    # Check for a kick that happened recently.
                    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.kick, after=current_time - timedelta(seconds=30)):
                        if entry.target.id == member.id:
                            kick_entry = entry
                            break # Found the entry
                    if kick_entry:
                        break # Exit the polling loop
                except Exception as e:
                    logging.error(f"Error polling kick audit log for {member.name}: {e}")
                    break # Stop polling on error
                await asyncio.sleep(1) # Wait 1 second before the next poll

            if kick_entry:
                was_kicked = True
                entry = kick_entry
                self.state.recent_kick_timestamps[member.id] = current_time
                
                chat_channel = guild.get_channel(self.bot_config.CHAT_CHANNEL_ID)
                if chat_channel:
                    roles = [role for role in member.roles if role.name != "@everyone"]
                    
                    embed = discord.Embed(
                        description=f"{member.mention} **KICKED**",
                        color=discord.Color.orange(),
                        timestamp=current_time)
                    
                    avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
                    embed.set_author(name=member.name, icon_url=avatar_url)
                    embed.set_thumbnail(url=avatar_url)
                    
                    try:
                        user = await self.bot.fetch_user(member.id)
                        if user.banner:
                            embed.set_image(url=user.banner.url)
                    except Exception:
                        pass
                    
                    # Add Time in Server
                    if member.joined_at:
                        duration = datetime.now(timezone.utc) - member.joined_at
                        duration_str = f"{duration.days}d {duration.seconds//3600}h {(duration.seconds%3600)//60}m"
                        embed.add_field(name="Time in Server", value=duration_str, inline=True)

                    embed.add_field(name="Kicked by", value=entry.user.mention, inline=True)
                    
                    if roles:
                        embed.add_field(
                            name="Roles", 
                            value=", ".join([role.name for role in roles]),
                            inline=True
                        )

                    embed.add_field(name="Reason", value=entry.reason or "No reason provided", inline=False)

                    await chat_channel.send(embed=embed)
                
                async with self.state.moderation_lock:
                    self.state.recent_kicks.append((
                        member.id, member.name, member.nick, current_time,
                        entry.reason or "No reason provided",
                        entry.user.mention,
                        ", ".join([role.name for role in member.roles if role.name != "@everyone"]) or None
                    ))
                    if len(self.state.recent_kicks) > 100:
                        self.state.recent_kicks.pop(0)
                
                logging.info(f"{member.name} was kicked. Reason: {entry.reason}")
                return # Kick is handled, exit the function

            # 3. If not a ban or a kick, it was a voluntary leave.
            if not was_kicked:
                if guild.id == self.bot_config.GUILD_ID:
                    chat_channel = guild.get_channel(self.bot_config.CHAT_CHANNEL_ID)
                    if chat_channel:
                        join_time = member.joined_at or current_time
                        duration = current_time - join_time
                        duration_str = f"{duration.days}d {duration.seconds//3600}h {(duration.seconds%3600)//60}m"
                        avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
                        roles = [role for role in member.roles if role.name != "@everyone"]
                        
                        embed = discord.Embed(color=discord.Color.red())
                        embed.set_author(name=member.name, icon_url=avatar_url)
                        embed.description = f"{member.mention} **LEFT the SERVER**"
                        embed.set_thumbnail(url=avatar_url)
                        embed.add_field(name="Time in Server", value=duration_str, inline=True)
                        if roles:
                            embed.add_field(
                                name="Roles", 
                                value=", ".join([role.name for role in roles]),
                                inline=True
                            )
                        await chat_channel.send(embed=embed)
                    
                    logging.info(f"{member.name} left the server voluntarily.")
                
                async with self.state.moderation_lock:
                    self.state.recent_leaves.append((
                        member.id, member.name, member.nick, current_time,
                        ", ".join([role.name for role in member.roles if role.name != "@everyone"]) or None
                    ))
                    if len(self.state.recent_leaves) > 100:
                        self.state.recent_leaves.pop(0)

        except Exception as e:
            logging.error(f"Error in on_member_remove: {e}", exc_info=True)

    async def show_bans(self, ctx) -> None:
        """Lists all banned users in compact format."""
        if ctx.author.id not in self.bot_config.ALLOWED_USERS:
            await ctx.send("⛔ You do not have permission to use this command.")
            return

        record_command_usage(self.state.analytics, "!bans")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!bans")

        try:
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

            for embed in embeds:
                await ctx.send(embed=embed)
                
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to view bans.")
        except Exception as e:
            logging.error(f"Error in !bans command: {e}", exc_info=True)
            await ctx.send("⚠️ An error occurred while fetching bans.")

    async def show_top_members(self, ctx) -> None:
        """Lists top members based on server join date and account creation date."""
        if ctx.author.id not in self.bot_config.ALLOWED_USERS:
            await ctx.send("⛔ You do not have permission to use this command.")
            return
        
        record_command_usage(self.state.analytics, "!top")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!top")
        
        try:
            # Prepare lists of members
            joined_members = sorted(
                [m for m in ctx.guild.members if m.joined_at],
                key=lambda m: m.joined_at
            )[:10]
            created_members = sorted(ctx.guild.members, key=lambda m: m.created_at)[:10]

            # Gather all unique user IDs to fetch them efficiently
            user_ids_to_fetch = {m.id for m in joined_members} | {m.id for m in created_members}
            
            user_fetch_tasks = [self.bot.fetch_user(uid) for uid in user_ids_to_fetch]
            fetched_users_list = await asyncio.gather(*[t for t in user_fetch_tasks if t], return_exceptions=True)
            
            user_map = {user.id: user for user in fetched_users_list if isinstance(user, discord.User)}

            # --- Top 10 Oldest Server Members ---
            await ctx.send("**🏆 Top 10 Oldest Server Members (by join date)**")
            if not joined_members:
                await ctx.send("No members with join dates found in the server.")
            else:
                for i, member in enumerate(joined_members, 1):
                    user = user_map.get(member.id, member) # Fallback to member object
                    embed = discord.Embed(title=f"#{i} - {member.display_name}", description=f"{member.mention}", color=discord.Color.gold())
                    embed.set_author(name=f"{member.name}#{member.discriminator}", icon_url=member.display_avatar.url)
                    embed.set_thumbnail(url=member.display_avatar.url)
                    
                    if hasattr(user, 'banner') and user.banner:
                        embed.set_image(url=user.banner.url)
                    
                    embed.add_field(name="Account Created", value=f"{member.created_at.strftime('%Y-%m-%d')}\n({get_discord_age(member.created_at)} old)", inline=True)
                    embed.add_field(name="Joined Server", value=f"{member.joined_at.strftime('%Y-%m-%d')}\n({get_discord_age(member.joined_at)} ago)", inline=True)
                    
                    roles = [role.mention for role in member.roles if role.name != "@everyone"]
                    if roles:
                        embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles) if len(", ".join(roles)) < 1024 else "Too many roles", inline=False)
                    
                    await ctx.send(embed=embed)

            # --- Top 10 Oldest Discord Accounts ---
            await ctx.send("**🕰️ Top 10 Oldest Discord Accounts (by creation date)**")
            for i, member in enumerate(created_members, 1):
                user = user_map.get(member.id, member) # Fallback to member object
                embed = discord.Embed(title=f"#{i} - {member.display_name}", description=f"{member.mention}", color=discord.Color.blue())
                embed.set_author(name=f"{member.name}#{member.discriminator}", icon_url=member.display_avatar.url)
                embed.set_thumbnail(url=member.display_avatar.url)
                
                if hasattr(user, 'banner') and user.banner:
                    embed.set_image(url=user.banner.url)
                
                embed.add_field(name="Account Created", value=f"{member.created_at.strftime('%Y-%m-%d')}\n({get_discord_age(member.created_at)} old)", inline=True)
                if member.joined_at:
                    embed.add_field(name="Joined Server", value=f"{member.joined_at.strftime('%Y-%m-%d')}\n({get_discord_age(member.joined_at)} ago)", inline=True)
                
                roles = [role.mention for role in member.roles if role.name != "@everyone"]
                if roles:
                    embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles) if len(", ".join(roles)) < 1024 else "Too many roles", inline=False)
                
                await ctx.send(embed=embed)

        except Exception as e:
            logging.error(f"Error in !top command: {e}", exc_info=True)
            await ctx.send("⚠️ An error occurred while processing the command.")

    async def show_info(self, ctx) -> None:
        """Sends the info messages in the channel only."""
        command_name = f"!{ctx.invoked_with}"
        record_command_usage(self.state.analytics, command_name)
        record_command_usage_by_user(self.state.analytics, ctx.author.id, command_name)
        
        for msg in self.bot_config.INFO_MESSAGES:
            await ctx.send(msg)

    async def list_roles(self, ctx) -> None:
        """Lists each role and its members."""
        if ctx.author.id not in self.bot_config.ALLOWED_USERS:
            await ctx.send("You do not have permission to use this command.")
            return
        
        record_command_usage(self.state.analytics, "!roles")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!roles")
        
        for role in sorted(ctx.guild.roles, key=lambda r: r.position, reverse=True):
            if role.name != "@everyone" and role.members:
                def process_member(member):
                    return f"{member.display_name} ({member.name}#{member.discriminator})"

                embeds = create_message_chunks(
                    entries=role.members,
                    title=f"Role: {role.name}",
                    process_entry=process_member,
                    as_embed=True,
                    embed_color=role.color or discord.Color.default()
                )

                for i, embed in enumerate(embeds):
                    if len(embeds) > 1:
                        embed.title = f"{embed.title} (Part {i + 1})"
                    embed.set_footer(text=f"Total members: {len(role.members)}")
                    await ctx.send(embed=embed)

    async def show_admin_list(self, ctx) -> None:
        """Lists all current admins and owners."""
        from tools import build_embed
        record_command_usage(self.state.analytics, "!admin")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!admin")
        guild = ctx.guild
        if not guild:
            return

        # Fetch owners/allowed users directly by ID
        owners_list = []
        for user_id in self.bot_config.ALLOWED_USERS:
            member = guild.get_member(user_id)
            if member:
                owners_list.append(f"{member.name} ({member.display_name})")
            else:
                try:
                    user = await self.bot.fetch_user(user_id)
                    owners_list.append(f"{user.name} (Not in server, ID: {user_id})")
                except discord.NotFound:
                    owners_list.append(f"Unknown User (ID: {user_id})")

        # Fetch admins by role using a set for efficiency and automatic deduplication
        admins_set = set()
        admin_roles = [role for role in guild.roles if role.name in self.bot_config.ADMIN_ROLE_NAME]
        for role in admin_roles:
            for member in role.members:
                # Avoid listing owners/allowed users twice
                if member.id not in self.bot_config.ALLOWED_USERS:
                    admins_set.add(f"{member.name} ({member.display_name})")

        owners_text = "\n".join(sorted(owners_list)) if owners_list else "👑 No owners found."
        admins_text = "\n".join(sorted(list(admins_set))) if admins_set else "🛡️ No admins found."
        
        embed_owners = build_embed("👑 Owners", owners_text, discord.Color.gold())
        embed_admins = build_embed("🛡️ Admins", admins_text, discord.Color.red())
        
        await ctx.send(embed=embed_owners)
        await ctx.send(embed=embed_admins)

    async def show_commands_list(self, ctx) -> None:
        """Lists all available bot commands."""
        from tools import build_embed
        record_command_usage(self.state.analytics, "!commands")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!commands")
        user_commands = (
            "**!skip** - Skips the current stranger on Omegle.\n"
            "**!refresh** - Refreshes page.\n"
            "**!pause** - Pauses Omegle.\n"
            "**!start** - Starts Omegle.\n"
            "**!paid** - Redirects back to Omegle URL.\n"
            "**!help** - Displays Omegle controls with buttons.\n"
            "**!rules** - Lists and DMs Server rules.\n"
            "**!admin** - Lists Admins and Owners.\n"
            "**!owner** - Lists Admins and Owners.\n"
            "**!info** - Lists Server Info.\n"
            "**!about** - Lists Server Info.\n"
            "**!commands** - Full list of all bot commands."
        )
        admin_commands = (
            "**!timeouts** - Lists current timeouts / removals.\n"
            "**!times** - Shows VC User Time Stats.\n"
            "**!roles** - Lists roles and their members.\n"
            "**!rtimeouts** - Removes timeouts from ALL members."
        )
        allowed_commands = (
            "**!purge [number]** - Purges messages from the channel.\n"
            "**!top** - Lists the top 10 longest members of the server.\n"
            "**!join** - Sends a join invite DM to admin role members.\n"
            "**!bans** - Lists all users who are server banned.\n"
            "**!whois** - Lists timeouts, untimeouts, joins, leaves, kicks.\n"
            "**!stats** - Lists VC Time / Command usage Stats.\n"
            "**!banned** - Lists all users who are server banned.\n"
            "**!clear** - Clears the VC / Command usage data.\n"
            "**!hush** - Server mutes everyone in the Streaming VC.\n"
            "**!secret** - Server mutes + deafens everyone in Streaming VC.\n"
            "**!rhush** - Removes mute status from everyone in Streaming VC.\n"
            "**!rsecret** - Removes mute and deafen statuses from Streaming VC.\n"
            "**!modoff** - Temporarily disables VC moderation for non-allowed users.\n"
            "**!modon** - Re-enables VC moderation after it has been disabled."
        )
        user_embed = build_embed("👤 User Commands", user_commands, discord.Color.blue())
        admin_embed = build_embed("🛡️ Admin/Allowed Commands", admin_commands, discord.Color.red())
        allowed_embed = build_embed("👑 Allowed Users Only Commands", allowed_commands, discord.Color.gold())
        await ctx.send(embed=user_embed)
        await ctx.send(embed=admin_embed)
        await ctx.send(embed=allowed_embed)

    async def show_whois(self, ctx) -> None:
        """Displays a report with all user actions in a clean, optimized format."""
        if ctx.author.id not in self.bot_config.ALLOWED_USERS:
            await ctx.send("⛔ You do not have permission to use this command.")
            return

        record_command_usage(self.state.analytics, "!whois")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!whois")

        now = datetime.now(timezone.utc)
        reports = {}
        has_data = False

        # --- Data Gathering ---
        async with self.state.moderation_lock:
            timed_out_members = [member for member in ctx.guild.members if member.is_timed_out()]
            untimeout_list = [e for e in self.state.recent_untimeouts if now - e[3] <= timedelta(hours=24) and (len(e) > 5 and e[5] and e[5] != "System")]
            kick_list = [e for e in self.state.recent_kicks if now - e[3] <= timedelta(hours=24)]
            ban_list = [e for e in self.state.recent_bans if now - e[3] <= timedelta(hours=24)]
            unban_list = [e for e in self.state.recent_unbans if now - e[3] <= timedelta(hours=24)]
            join_list = [e for e in self.state.recent_joins if now - e[3] <= timedelta(hours=24)]
            leave_list = [e for e in self.state.recent_leaves if now - e[3] <= timedelta(hours=24)]

        # --- Batch User Fetching ---
        user_ids_to_fetch = set()
        for data_list in [untimeout_list, kick_list, ban_list, unban_list, join_list, leave_list]:
            for entry in data_list:
                user_ids_to_fetch.add(entry[0])

        user_map = {}
        if user_ids_to_fetch:
            tasks = [self.bot.fetch_user(uid) for uid in user_ids_to_fetch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for user in results:
                if isinstance(user, discord.User):
                    user_map[user.id] = user

        # --- Helper Functions using the user_map ---
        def get_clean_mention(identifier):
            if identifier is None: return "Unknown"
            if isinstance(identifier, int):
                member = ctx.guild.get_member(identifier)
                if member: return member.mention
            member = discord.utils.find(lambda m: m.name == str(identifier) or m.display_name == str(identifier), ctx.guild.members)
            return member.mention if member else str(identifier)
        
        def get_left_user_display_info(user_id, stored_username=None):
            user = user_map.get(user_id)
            if user:
                return f"{user.name} [ID: {user_id}]"
            # Fallback to stored name if user couldn't be fetched (e.g., deleted account)
            return f"{stored_username or 'Unknown User'} [ID: {user_id}]"

        # --- Report Generation ---
        if timed_out_members:
            has_data = True
            def process_timeout(member):
                data = self.state.active_timeouts.get(member.id, {})
                timed_by = data.get("timed_by_id", data.get("timed_by"))
                reason = data.get("reason")
                line = f"• {member.mention}"
                if timed_by and timed_by != "Unknown": line += f" - TimedOut by: {get_clean_mention(timed_by)}"
                if reason and reason != "No reason provided": line += f" | Reason: {reason}"
                return line
            reports["⏳ Timed Out Members"] = create_message_chunks(timed_out_members, "⏳ Timed Out Members", process_timeout, max_length=1800)

        if untimeout_list:
            has_data = True
            processed_users = set()
            def process_untimeout(entry):
                user_id, mod_name, mod_id = entry[0], entry[5], entry[6] if len(entry) > 6 else None
                if user_id in processed_users: return None
                processed_users.add(user_id)
                mod_mention = get_clean_mention(mod_id) if mod_id else get_clean_mention(mod_name)
                line = f"• <@{user_id}>"
                if mod_mention and mod_mention != "Unknown": line += f" - Removed by: {mod_mention}"
                return line
            reports["🔓 Recent Untimeouts"] = create_message_chunks(untimeout_list, "🔓 Recent Untimeouts", process_untimeout, max_length=1800)

        if kick_list:
            has_data = True
            def process_kick(entry):
                user_id, s_name, reason, kicker = entry[0], entry[1], entry[4], entry[5] if len(entry) > 5 else None
                user_display = get_left_user_display_info(user_id, s_name)
                line = f"• {user_display}"
                if kicker and kicker != "Unknown": line += f" - Kicked by: {get_clean_mention(kicker)}"
                if reason and reason != "No reason provided": line += f" | Reason: {reason}"
                return line
            reports["👢 Recent Kicks"] = create_message_chunks(kick_list, "👢 Recent Kicks", process_kick, max_length=1800)

        if ban_list:
            has_data = True
            def process_ban(entry):
                user_id, s_name, reason = entry[0], entry[1], entry[4]
                user_mention = f"<@{user_id}>"
                user_display = get_left_user_display_info(user_id, s_name)
                line = f"• {user_mention} ({user_display})"
                if reason and reason != "No reason provided":
                    if " by " in reason.lower():
                        reason_text, mod_name = reason.rsplit(" by ", 1)
                        line += f" - Reason: {reason_text} by {get_clean_mention(mod_name)}"
                    else:
                        line += f" - Reason: {reason}"
                return line
            reports["🔨 Recent Bans"] = create_message_chunks(ban_list, "🔨 Recent Bans", process_ban, max_length=1800)

        if unban_list:
            has_data = True
            def process_unban(entry):
                user_id, mod_name = entry[0], entry[4]
                line = f"• <@{user_id}>"
                if mod_name and mod_name != "Unknown": line += f" - Unbanned by: {get_clean_mention(mod_name)}"
                return line
            reports["🔓 Recent Unbans"] = create_message_chunks(unban_list, "🔓 Recent Unbans", process_unban, max_length=1800)

        if join_list:
            has_data = True
            def process_join(entry):
                user_id, s_name = entry[0], entry[1]
                member = ctx.guild.get_member(user_id)
                if member:
                    return f"• {member.name} ({member.display_name}) [ID: {user_id}]" if member.display_name != member.name else f"• {member.name} [ID: {user_id}]"
                return f"• {get_left_user_display_info(user_id, s_name)} (left server)"
            reports["🎉 Recent Joins"] = create_message_chunks(join_list, "🎉 Recent Joins", process_join, max_length=1800)

        if leave_list:
            has_data = True
            def process_leave(entry):
                user_id, s_name = entry[0], entry[1]
                return f"• {get_left_user_display_info(user_id, s_name)}"
            reports["🚪 Recent Leaves"] = create_message_chunks(leave_list, "🚪 Recent Leaves", process_leave, max_length=1800)

        report_order = ["⏳ Timed Out Members", "🔓 Recent Untimeouts", "👢 Recent Kicks", "🔨 Recent Bans", "🔓 Recent Unbans", "🎉 Recent Joins", "🚪 Recent Leaves"]
        for report_type in report_order:
            if report_type in reports and reports[report_type]:
                for chunk in reports[report_type]:
                    await ctx.send(chunk)
        
        if not has_data:
            await ctx.send("📭 No recent activity data available")

    async def remove_timeouts(self, ctx) -> None:
        """Removes timeouts from all members."""
        if not (ctx.author.id in self.bot_config.ALLOWED_USERS or any(role.name in self.bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles)):
            await ctx.send("⛔ You do not have permission to use this command.")
            return
        
        record_command_usage(self.state.analytics, "!rtimeouts")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!rtimeouts")
        
        timed_out_members = [m for m in ctx.guild.members if m.is_timed_out()]
        if not timed_out_members:
            await ctx.send("No users are currently timed out.")
            return
        
        confirm_msg = await ctx.send(f"⚠️ **WARNING:** This will remove timeouts from {len(timed_out_members)} members!\nReact with ✅ to confirm or ❌ to cancel within 30 seconds.")
        for emoji in ["✅", "❌"]: await confirm_msg.add_reaction(emoji)
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id
        
        try:
            reaction, _ = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
            if str(reaction.emoji) == "❌":
                await ctx.send("Command cancelled.")
                return
        except asyncio.TimeoutError:
            await ctx.send("⌛ Command timed out. No changes were made.")
            return
        
        removed, failed = [], []
        for member in timed_out_members:
            try:
                await member.timeout(None, reason=f"Timeout removed by {ctx.author.name} ({ctx.author.id})")
                removed.append(member.name)
                async with self.state.moderation_lock:
                    if member.id in self.state.active_timeouts:
                        self.state.recent_untimeouts.append((member.id, member.name, member.display_name, datetime.now(timezone.utc), f"Manually removed by {ctx.author.name}", ctx.author.name, ctx.author.id))
                        del self.state.active_timeouts[member.id]
                logging.info(f"Removed timeout from {member.name} by {ctx.author.name}")
            except discord.Forbidden:
                failed.append(f"{member.name} (Missing Permissions)")
            except discord.HTTPException as e:
                failed.append(f"{member.name} (Error: {e})")

        result_msg = []
        if removed: result_msg.append(f"**✅ Removed timeouts from:**\n- " + "\n- ".join(removed))
        if failed: result_msg.append(f"\n**❌ Failed to remove timeouts from:**\n- " + "\n- ".join(failed))
        
        if result_msg:
            await ctx.send("\n".join(result_msg))
        
        chat_channel = ctx.guild.get_channel(self.bot_config.CHAT_CHANNEL_ID)
        if chat_channel:
            await chat_channel.send(f"⏰ **Mass Timeout Removal**\nExecuted by {ctx.author.mention}\nRemoved: {len(removed)} | Failed: {len(failed)}")

    async def show_rules(self, ctx) -> None:
        """Lists the server rules in the channel."""
        record_command_usage(self.state.analytics, "!rules")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!rules")
        await ctx.send("📜 **Server Rules:**\n" + self.bot_config.RULES_MESSAGE)

    async def show_timeouts(self, ctx) -> None:
        """Displays a report of currently timed out members and all untimeouts."""
        if not (ctx.author.id in self.bot_config.ALLOWED_USERS or any(role.name in self.bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles)):
            await ctx.send("⛔ You do not have permission to use this command.")
            return

        record_command_usage(self.state.analytics, "!timeouts")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!timeouts")

        reports = {}
        has_data = False

        def get_clean_mention(identifier):
            if identifier is None: return "Unknown"
            if isinstance(identifier, int):
                member = ctx.guild.get_member(identifier)
                if member: return member.mention
            member = discord.utils.find(lambda m: m.name == str(identifier) or m.display_name == str(identifier), ctx.guild.members)
            return member.mention if member else str(identifier)

        # Currently Timed Out Members
        timed_out_members = [member for member in ctx.guild.members if member.is_timed_out()]
        if timed_out_members:
            has_data = True
            async def process_timeout(member):
                data = self.state.active_timeouts.get(member.id, {})
                timed_by = data.get("timed_by_id", data.get("timed_by"))
                reason = data.get("reason")
                line = f"• {member.mention}"
                if timed_by and timed_by != "Unknown": line += f" - Timed out by: {get_clean_mention(timed_by)}"
                if reason and reason != "No reason provided": line += f" | Reason: {reason}"
                return line
            
            timeout_tasks = [process_timeout(m) for m in timed_out_members]
            processed_timeouts = await asyncio.gather(*timeout_tasks)
            reports["⏳ Currently Timed Out"] = create_message_chunks(processed_timeouts, "⏳ Currently Timed Out", lambda x: x, max_length=1800)

        # All Untimeouts (no time limit) - Filter for known mods only
        async with self.state.moderation_lock:
            untimeout_entries = [e for e in self.state.recent_untimeouts if len(e) > 5 and e[5] and e[5] != "System"]
        
        if untimeout_entries:
            has_data = True
            processed_users = set()
            
            # This can remain synchronous as it doesn't await anything
            def process_untimeout(entry):
                user_id, mod_name, mod_id = entry[0], entry[5], entry[6] if len(entry) > 6 else None
                # Duplication check is tricky here without async context, moved to a simple filter
                mod_mention = get_clean_mention(mod_id) if mod_id else get_clean_mention(mod_name)
                line = f"• <@{user_id}>"
                if mod_mention and mod_mention != "Unknown": line += f" - Removed by: {mod_mention}"
                return line
            
            # Filter out duplicate users before processing
            unique_untimeout_entries = []
            for entry in reversed(untimeout_entries):
                if entry[0] not in processed_users:
                    unique_untimeout_entries.append(entry)
                    processed_users.add(entry[0])
            
            processed_untimeouts = [process_untimeout(e) for e in reversed(unique_untimeout_entries)]
            reports["🔓 All Untimeouts"] = create_message_chunks(processed_untimeouts, "🔓 All Untimeouts", lambda x: x, max_length=1800)

        report_order = ["⏳ Currently Timed Out", "🔓 All Untimeouts"]
        for report_type in report_order:
            if report_type in reports and reports[report_type]:
                for chunk in reports[report_type]:
                    await ctx.send(chunk)
        
        if not has_data:
            await ctx.send("📭 No active timeouts or untimeouts found")

    async def _send_vc_time_report(self, destination: discord.abc.Messageable) -> None:
        """Helper function to calculate and send VC time reports."""
        guild = destination.guild if hasattr(destination, 'guild') else self.bot.get_guild(self.bot_config.GUILD_ID)

        async def get_user_display_info(user_id, data):
            """Gets user display info, preferring live data but falling back to stored data."""
            try:
                member = guild.get_member(user_id)
                # This doesn't need fetch_member as get_member is sufficient for online members
                if member:
                    roles = [role for role in member.roles if role.name != "@everyone"]
                    highest_role = max(roles, key=lambda r: r.position) if roles else None
                    role_display = f"**[{highest_role.name}]**" if highest_role else ""
                    return f"{member.mention} {role_display} ({member.name})"
            except Exception as e:
                 logging.warning(f"Could not get live member info for {user_id}, falling back. Error: {e}")

            # Fallback for offline/left users
            username = data.get("username", "Unknown User")
            return f"`{username}` (Left/Not Found) <@{user_id}>"


        def is_excluded(user_id):
            return user_id in self.bot_config.STATS_EXCLUDED_USERS

        async def get_vc_time_data():
            async with self.state.vc_lock:
                current_time = time.time()
                combined_data = {uid: d.copy() for uid, d in self.state.vc_time_data.items() if not is_excluded(uid)}
                total_time_all_users = sum(d.get("total_time", 0) for d in combined_data.values())

                for user_id, start_time in self.state.active_vc_sessions.items():
                    if is_excluded(user_id): continue
                    active_duration = current_time - start_time
                    if user_id in combined_data:
                        combined_data[user_id]["total_time"] += active_duration
                    else:
                        member = guild.get_member(user_id)
                        combined_data[user_id] = {
                            "total_time": active_duration,
                            "username": member.name if member else "Unknown",
                            "display_name": member.display_name if member else "Unknown"
                        }
                    total_time_all_users += active_duration
            
            sorted_users = sorted(combined_data.items(), key=lambda item: item[1].get("total_time", 0), reverse=True)[:10]
            return total_time_all_users, sorted_users

        total_tracking_seconds = 0
        async with self.state.vc_lock:
            if self.state.vc_time_data:
                all_sessions = [s["start"] for d in self.state.vc_time_data.values() for s in d.get("sessions", [])]
                if all_sessions:
                    earliest_session = min(all_sessions)
                    total_tracking_seconds = time.time() - earliest_session
        
        h, m, s = int(total_tracking_seconds // 3600), int((total_tracking_seconds % 3600) // 60), int(total_tracking_seconds % 60)
        tracking_time_str = ' '.join(p for p in [f"{h}h" if h else "", f"{m}m" if m else "", f"{s}s" if s or not any([h, m]) else ""] if p)
        await destination.send(f"⏳ **Tracking Started:** {tracking_time_str} ago\n")

        total_time_all_users, top_vc_users = await get_vc_time_data()
        
        if top_vc_users:
            async def process_vc_entry(entry):
                uid, data = entry
                total_s = data.get('total_time', 0)
                h, m, s = int(total_s // 3600), int((total_s % 3600) // 60), int(total_s % 60)
                time_str = ' '.join(p for p in [f"{h}h" if h else "", f"{m}m" if m else "", f"{s}s"] if p)
                display_info = await get_user_display_info(uid, data)
                return f"• {display_info}: {time_str}"

            processed_entries = await asyncio.gather(*(process_vc_entry(entry) for entry in top_vc_users))
            for chunk in create_message_chunks(processed_entries, "🏆 Top 10 VC Members", lambda x: x, 10):
                await destination.send(chunk)
        else:
            await destination.send("No VC time data available yet.")

        h, m, s = int(total_time_all_users // 3600), int((total_time_all_users % 3600) // 60), int(total_time_all_users % 60)
        total_time_str = ' '.join(p for p in [f"{h}h" if h else "", f"{m}m" if m else "", f"{s}s"] if p)
        await destination.send(f"⏱ **Total VC Time (All Users):** {total_time_str}")

    async def show_times_report(self, destination: Union[commands.Context, discord.TextChannel]) -> None:
        """Shows VC time tracking information."""
        # For commands, check permissions. For channels (tasks), skip check.
        if isinstance(destination, commands.Context):
            ctx = destination
            if not (ctx.author.id in self.bot_config.ALLOWED_USERS or any(role.name in self.bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles)):
                await ctx.send("⛔ You do not have permission to use this command.")
                return
            record_command_usage(self.state.analytics, "!times")
            record_command_usage_by_user(self.state.analytics, ctx.author.id, "!times")
        
        await self._send_vc_time_report(destination)


    async def show_analytics_report(self, ctx) -> None:
        """Shows command usage statistics and violation events."""
        if ctx.author.id not in self.bot_config.ALLOWED_USERS:
            await ctx.send("⛔ You do not have permission to use this command.")
            return

        record_command_usage(self.state.analytics, "!stats")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!stats")

        # Use the refactored helper for the VC time portion
        await self._send_vc_time_report(ctx)
        await ctx.send("\n" + "─"*50 + "\n") # Separator

        async def get_user_display_info(user_id):
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                member = ctx.guild.get_member(user_id)
                if member:
                    roles = [role for role in member.roles if role.name != "@everyone"]
                    highest_role = max(roles, key=lambda r: r.position) if roles else None
                    role_display = f"**[{highest_role.name}]**" if highest_role else ""
                    return f"{member.mention} {role_display} ({member.name})"
                return f"{user.mention} ({user.name})"
            except Exception:
                return f"<@{user_id}> (Unknown User)"

        def is_excluded(user_id):
            return user_id in self.bot_config.STATS_EXCLUDED_USERS
        
        has_stats_data = False
        async with self.state.analytics_lock:
            if self.state.analytics.get("command_usage"):
                has_stats_data = True
                commands = sorted(self.state.analytics["command_usage"].items(), key=lambda x: x[1], reverse=True)
                for chunk in create_message_chunks(commands, "📊 Overall Command Usage", lambda cmd: f"• `{cmd[0]}`: {cmd[1]} times"):
                    await ctx.send(chunk)
            
            if self.state.analytics.get("command_usage_by_user"):
                has_stats_data = True
                filtered_users = [(uid, cmds) for uid, cmds in self.state.analytics["command_usage_by_user"].items() if not is_excluded(uid)]
                sorted_users = sorted(filtered_users, key=lambda item: sum(item[1].values()), reverse=True)[:10]
                
                async def process_user_usage(entry):
                    uid, cmds = entry
                    usage = ", ".join([f"{c}: {cnt}" for c, cnt in sorted(cmds.items(), key=lambda x: x[1], reverse=True)])
                    return f"• {await get_user_display_info(uid)}: {usage}"
                
                processed_entries = await asyncio.gather(*(process_user_usage(entry) for entry in sorted_users))
                for chunk in create_message_chunks(processed_entries, "👤 Top 10 Command Users", lambda x: x):
                    await ctx.send(chunk)
        
        async with self.state.moderation_lock:
            if self.state.user_violations:
                has_stats_data = True
                filtered_violations = [(uid, count) for uid, count in self.state.user_violations.items() if not is_excluded(uid)]
                sorted_violations = sorted(filtered_violations, key=lambda item: item[1], reverse=True)[:10]

                async def process_violation(entry):
                    uid, count = entry
                    return f"• {await get_user_display_info(uid)}: {count} violation(s)"

                processed_entries = await asyncio.gather(*(process_violation(entry) for entry in sorted_violations))
                for chunk in create_message_chunks(processed_entries, "⚠️ No-Cam Detected Report", lambda x: x):
                    await ctx.send(chunk)
        
        if not has_stats_data:
            await ctx.send("📊 No command/violation statistics available yet.")

    async def send_join_invites(self, ctx) -> None:
        """Sends a join invite DM to all members with an admin role."""
        if ctx.author.id not in self.bot_config.ALLOWED_USERS:
            await ctx.send("⛔ You do not have permission to use this command.")
            return
        
        record_command_usage(self.state.analytics, "!join")
        record_command_usage_by_user(self.state.analytics, ctx.author.id, "!join")
            
        guild = ctx.guild
        admin_role_names = self.bot_config.ADMIN_ROLE_NAME
        join_message = self.bot_config.JOIN_INVITE_MESSAGE
        
        admin_roles = [role for role in guild.roles if role.name in admin_role_names]
        if not admin_roles:
            await ctx.send("No admin roles found with the specified names.")
            return

        impacted = []
        members_to_dm = set()
        for role in admin_roles:
            for member in role.members:
                members_to_dm.add(member)

        if not members_to_dm:
            await ctx.send("No members with the specified admin roles found to DM.")
            return

        await ctx.send(f"Sending invites to {len(members_to_dm)} member(s) with the role(s): {', '.join(admin_role_names)}. This may take a moment...")

        for member in members_to_dm:
            try:
                # Avoid sending DMs to bots
                if member.bot:
                    continue
                await member.send(join_message)
                impacted.append(member.name)
                logging.info(f"Sent join invite to {member.name}.")
                await asyncio.sleep(1) # Rate limit DMs
            except discord.Forbidden:
                logging.warning(f"Could not DM {member.name} (DMs are disabled or bot is blocked).")
            except Exception as e:
                logging.error(f"Error DMing {member.name}: {e}")
                    
        if impacted:
            msg = "Finished sending invites. Sent to: " + ", ".join(impacted)
            logging.info(msg)
            await ctx.send(msg)
        else:
            await ctx.send("Finished processing. No invites were successfully sent.")

    async def clear_stats(self, ctx) -> None:
        """Resets all statistics data."""
        if ctx.author.id not in self.bot_config.ALLOWED_USERS:
            await ctx.send("⛔ You do not have permission to use this command.")
            return

        confirm_msg = await ctx.send("⚠️ This will reset ALL statistics data (VC times, command usage, violations).\nReact with ✅ to confirm or ❌ to cancel.")
        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id

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
                        logging.info(f"Restarted VC tracking for {len(current_members)} current members")
                
                await ctx.send("✅ All statistics data has been reset.")
                logging.info(f"Statistics cleared by {ctx.author.name} (ID: {ctx.author.id})")
            else:
                await ctx.send("❌ Statistics reset cancelled.")
                
        except asyncio.TimeoutError:
            await ctx.send("⌛ Command timed out. No changes were made.")
        finally:
            try:
                await confirm_msg.delete()
            except Exception:
                pass
