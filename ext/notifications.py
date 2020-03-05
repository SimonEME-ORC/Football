import asyncio
from collections import defaultdict

from discord.ext import commands
import discord
import typing

from ext.utils import codeblocks


class Notifications(commands.Cog):
    """ Guild Moderation Commands """
    
    def __init__(self, bot):
        self.bot = bot
        self.notif_cache = defaultdict(dict)
        self.bot.loop.create_task(self.update_cache())
    
    # TODO: On Channel Delete - Cascades!
    # TODO: Custom welcome message
    # TODO: Port on_message_delete
    # TODO: Custom Reactions.
    
    async def update_cache(self):
        self.notif_cache.clear()
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            records = await connection.fetch("""SELECT * FROM guild_settings""")
        await self.bot.db.release(connection)
        
        for r in records:
            guild_id = r["guild_id"]
            for k, v in r.items():
                if k == "guild_id":
                    continue
                self.notif_cache[guild_id].update({k: v})
    
    # Master info command.
    @commands.has_permissions(manage_guild=True)
    @commands.group(invoke_without_command=True, usage="mod")
    async def mod(self, ctx):
        """ Shows the status of various mod tools."""
        # Get settings.
        e = discord.Embed(color=0x7289DA)
        e.description = ""
        e.title = f"Config settings for {ctx.guild.name}"
        
        for key, value in self.notif_cache[ctx.guild.id].items():
            e.description += f"{key}: {value} \n"
        
        e.set_thumbnail(url=ctx.guild.icon_url)
        await ctx.send(embed=e)
    
    @commands.has_permissions(manage_channels=True)
    @commands.group(usage="joins <#channel> to set a new channel, or leave blank to show current information.")
    async def joins(self, ctx, channel: typing.Optional[discord.TextChannel]):
        """ Send member information to a channel on join. """
        if channel is None:  # Give current info
            ch = self.bot.get_channel(self.notif_cache[ctx.guild.id]["joins_channel_id"])
            if ch is None:
                return await ctx.send(f'Join information is not currently being output.')
            else:
                return await ctx.send(f'Join information is currently being output to {ch.mention}')
        
        connection = await self.bot.db.acquire()
        await connection.execute(""" UPDATE guild_settings SET joins_channel_id = $2 WHERE guild_id = $1""",
                                 ctx.guild.id, channel.id)
        await self.bot.db.release(connection)
        await self.update_cache()
        
        await ctx.send(f'Information about new users will be sent to {channel.mention} when they join.')
    
    @commands.has_permissions(manage_channels=True)
    @joins.command(name="off", alaises=["none", "disable"], usages="joins off")
    async def joins_off(self, ctx):
        connection = await self.bot.db.acquire()
        await connection.execute(""" UPDATE guild_settings SET joins_channel_id = $2 WHERE guild_id = $1""",
                                 ctx.guild.id, None)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send('Information about new users will no longer be output.')
    
    @commands.has_permissions(manage_guild=True)
    @commands.group(usage="leaves <#channel> to set a new channel, or leave blank to show current setting")
    async def leaves(self, ctx, channel: typing.Optional[discord.TextChannel] = None):
        """ Set a channel to show information about new member joins """
        if channel is None:  # Show current info
            ch = self.bot.get_channel(self.notif_cache[ctx.guild.id]["leaves_channel_id"])
            if ch is None:
                return await ctx.send(f'Member leaves are not currently being output.')
            else:
                return await ctx.send(f'Member leave information is currently being output to {ch.mention}')
        
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute("""
                UPDATE guild_settings SET leaves_channel_id = $2 WHERE guild_id = $1
                """, ctx.guild.id, channel.id)
        await self.bot.db.release(connection)
        await self.update_cache()
        
        await ctx.send(f'Notifications will be sent to {channel.mention} when users leave.')
    
    @commands.has_permissions(manage_channels=True)
    @leaves.command(name="off", alaises=["none", "disable"], usage="leaves off")
    async def leaves_off(self, ctx):
        connection = await self.bot.db.acquire()
        await connection.execute(""" UPDATE guild_settings SET joins_channel_id = $2 WHERE guild_id = $1""",
                                 ctx.guild.id, None)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send('Leave notifications will no longer be output.')
    
    @commands.has_permissions(manage_channels=True)
    @commands.group(usage="mutes <#channel> to set a new channel or leave blank to show current setting>")
    async def mutes(self, ctx, channel: typing.Optional[discord.TextChannel] = None):
        """ Set a channel to show messages about user mutings """
        if channel is None:  # Show current info
            ch = self.bot.get_channel(self.notif_cache[ctx.guild.id]["mutes_channel_id"])
            if ch is None:
                return await ctx.send(f'Mute notifications are not currently being output.')
            else:
                return await ctx.send(f'Mute notifications are currently being output to {ch.mention}')
        
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute(""" UPDATE guild_settings SET mutes_channel_id = $2 WHERE guild_id = $1""",
                                     ctx.guild.id, channel.id)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send(f"Notifications will be output to {channel.mention} when a member is muted.")

    @commands.has_permissions(manage_channels=True)
    @mutes.command(name="off", alaises=["none", "disable"], usage="leaves off")
    async def mutes_off(self, ctx):
        connection = await self.bot.db.acquire()
        await connection.execute(""" UPDATE guild_settings SET mutes_channel_id = $2 WHERE guild_id = $1""",
                                 ctx.guild.id, None)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send('Mute and block notifications will no longer be output.')
    
    @commands.has_permissions(manage_channels=True)
    @commands.group(usage="emojis <#channe> to set a new channel or leave blank to show current setting>")
    async def emojis(self, ctx, channel: typing.Optional[discord.TextChannel] = None):
        """ Set a channel to show when emojis are changed. """
        if channel is None:
            ch = self.bot.get_channel(self.notif_cache[ctx.guild.id]["emojis_channel_id"])
            if ch is None:
                return await ctx.send(f'Emoji change notifications are not currently being output.')
            else:
                return await ctx.send(f'Emoji change notifications are currently being output to {ch.mention}')
        
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute("""
                UPDATE guild_settings SET emojis_channel_id = $2 WHERE guild_id = $1
                """, ctx.guild.id, channel.id)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send(f"Notifications will be output to {channel.mention} when emojis are changed.")

    @emojis.command()
    @commands.has_permissions(manage_channels=True)
    async def emojis_off(self, ctx):
        connection = await self.bot.db.acquire()
        await connection.execute(""" UPDATE guild_settings SET emojis_channel_id = $2 WHERE guild_id = $1""",
                                 ctx.guild.id, None)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send('Emoji update notifications will no longer be output.')

    # Listeners
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await asyncio.sleep(10)  # Time for other cogs to do their shit.
        await self.update_cache()
        
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        connection = await self.bot.db.acquire()
        await connection.execute("""DELETE FROM guild_settings WHERE guild_id = $1""", guild.id)
        await self.bot.db.release(connection)
    
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        matches = [k for k, v in self.notif_cache.items() if v == channel.id]
        if not matches:
            return
        
        connection = await self.bot.db.acquire()
        async with connection.transaction:
            for i in matches:
                await connection.execute("""UPDATE guild_settings SET ($1 = NULL) WHERE $1 = $2""", i, channel.id)
        await connection.release()

    # TODO: Blocked
    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        pass

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        # Notify about member mute/un-mute.
        muted_role = discord.utils.find(lambda r: r.name.lower() == 'muted', before.guild.roles)
        if muted_role is None:
            return
        try:
            notif_channel = self.bot.get_channel(self.notif_cache[before.guild.id]['mutes_channel_id'])
        except KeyError:
            return  # Not set
        
        if notif_channel is None:
            return
        
        if muted_role in before.roles and muted_role not in after.roles:
            content = f"🙊 {before.mention} was unmuted"
        elif muted_role not in before.roles and muted_role in after.roles:
            content = f"🙊 {before.mention} was muted"
        else:
            return  # No muting occurred.
        
        try:
            async for entry in before.guild.audit_logs(action=discord.AuditLogAction.member_role_update, limit=1):
                content += f" by {entry.user} for {entry.reason}"
        except discord.Forbidden:
            pass  # Missing permissions to get reason.
        
        await notif_channel.send(content)
            
    @commands.Cog.listener()
    async def on_member_join(self, new_member):
        j = new_member.guild.get_channel(self.notif_cache[new_member.guild.id]["joins_channel_id"])
        if j is None:
            return
        
        # Extended member join information.
        e = discord.Embed()
        e.colour = 0x7289DA
        s = sum(1 for m in self.bot.get_all_members() if m.id == new_member.id)
        e.title = str(new_member)
        e.add_field(name="Status", value=str(new_member.status).title(), inline=True)
        e.add_field(name='User ID', value=new_member.id, inline=True)
        e.add_field(name='Mutual Servers', value=f'{s} shared', inline=True)
        if new_member.bot:
            e.description = '**This is a bot account**'
        
        coloured_time = codeblocks.time_to_colour(new_member.created_at)
        
        e.add_field(name="Account Created", value=coloured_time)
        e.set_thumbnail(url=new_member.avatar_url)
        await j.send(embed=e)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        # Check if in mod.
        try:
            async for x in member.guild.audit_logs(limit=1):
                if str(x.target) == str(member):
                    try:
                        if x.action == discord.AuditLogAction.kick:
                            kc = member.guild.get_channel(self.notif_cache[member.guild.id]["kicks_channel_id"])
                            return await kc.send(f"👢 {member.mention} was kicked by {x.user} for {x.reason}.")
                        elif x.action == discord.AuditLogAction.ban:
                            bc = member.guild.get_channel(self.notif_cache[member.guild.id]["bans_channel_id"])
                            return await bc.send(f"☠ {member.mention} was banned by {x.user} for {x.reason}.")
                    except (AttributeError, TypeError):
                        pass  # No kick/ban channel set, default to leaves.
        except discord.Forbidden:
            pass  # We cannot see audit logs.
        
        try:
            lc = member.guild.get_channel(self.notif_cache[member.guild.id]["leaves_channel_id"])
            await lc.send(f"⬅ {member.mention} left the server.")
        except (AttributeError, TypeError):
            pass
        
    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        try:
            c = guild.get_channel(self.notif_cache[guild.id]["emojis_channel_id"])
        except KeyError:
            return  # No channel set.
        
        if not c:
            return
            
        if c is None:
            print(self.notif_cache[guild.id]["emojis_channel_id"], "Dead channel?", "emoji update.")
        
        # Find if it was addition or removal.
        new_emoji = [i for i in after if i not in before]
        if not new_emoji:
            try:
                removed_emoji = [i for i in before if i not in after][0]
                await c.send(f"The '{removed_emoji}' emoji was removed")
            except IndexError:
                await c.send("An emoji was removed.")
        else:
            notif = f"The {new_emoji[0]} emoji was created"
            if guild.me.permissions_in(c).manage_emojis:
                emoji = await guild.fetch_emoji(new_emoji[0].id)
                notif += " by " + emoji.user.mention
            await c.send(notif)

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        try:
            c = guild.get_channel(self.notif_cache[guild.id]["unbans_channel_id"])
        except KeyError:
            return
        await c.send(f"🆗 {user} (ID: {user.id}) was unbanned.")
        
        
def setup(bot):
    bot.add_cog(Notifications(bot))
