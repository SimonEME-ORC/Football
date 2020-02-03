from copy import deepcopy
from urllib.parse import unquote
from discord.ext import commands
import discord
import typing

from ext.utils.embed_paginator import paginate


def get_prefix(bot, message):
    try:
        pref = bot.prefix_cache[message.guild.id]
    except KeyError:
        pref = [".tb "]
    except AttributeError:
        pref = [".tb ", "!", "-", "`", "!", "?", ""]  # Use all prefixes (or none) for DM help.
    return commands.when_mentioned_or(*pref)(bot, message)


class Mod(commands.Cog):
    """ Guild Moderation Commands """
    
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.update_cache())
        self.bot.loop.create_task(self.update_prefixes())
        self.bot.command_prefix = get_prefix
    
    def me_or_mod():
        def predicate(ctx):
            return ctx.author.permissions_in(ctx.channel).manage_channels or ctx.author.id == ctx.bot.owner_id
        
        return commands.check(predicate)
    
    # Listeners
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        connection = await self.bot.db.acquire()
        await connection.execute("""
        with gid as (
                INSERT INTO guild_settings (guild_id) VALUES ($1)
        RETURNING guild_id
        )
        INSERT INTO prefixes (prefix, guild_id)
        VALUES
        ( $2, (SELECT guild_id FROM gid)
        );
        """, guild.id,  '.tb ')
        await self.bot.db.release(connection)
        print(f"Guild Join: Default prefix set for {guild.id}")
        await self.update_prefixes()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        connection = await self.bot.db.acquire()
        await connection.execute("""DELETE FROM guild_settings WHERE guild_id = $1""", guild.id)
        await self.bot.db.release(connection)
        print(f"Guild Remove: Cascade delete for {guild.id}")
        
    async def update_prefixes(self):
        self.bot.prefix_cache = {}
        connection = await self.bot.db.acquire()
        records = await connection.fetch("""SELECT * FROM prefixes""")
        await self.bot.db.release(connection)
        
        for r in records:
            guild_id = r["guild_id"]
            prefix = r["prefix"]
            try:
                self.bot.prefix_cache[guild_id].append(prefix)
            except KeyError:
                self.bot.prefix_cache.update({guild_id: [prefix]})
    
    async def update_cache(self):
        self.bot.disabled_cache = {}
        connection = await self.bot.db.acquire()
        records = await connection.fetch("""SELECT * FROM disabled_commands""")
        await self.bot.db.release(connection)
        
        for r in records:
            try:
                self.bot.disabled_cache[r["guild_id"]].append(r["command"])
            except KeyError:
                self.bot.disabled_cache.update({r["guild_id"]: [r["command"]]})
    
    @commands.command(aliases=['nick'])
    @commands.has_permissions(manage_nicknames=True)
    async def name(self, ctx, *, new_name: str):
        """ Rename the bot for your server. """
        await ctx.me.edit(nick=new_name)
    
    @commands.command(usage="say <Channel (optional)< <what you want the bot to say>")
    @me_or_mod()
    async def say(self, ctx, destination: typing.Optional[discord.TextChannel] = None, *, msg):
        """ Say something as the bot in specified channel """
        if destination is None:
            destination = ctx.channel
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        await destination.send(msg)
    
    @commands.command(usage="topic <New Channel Topic>")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def topic(self, ctx, *, new_topic):
        """ Set the topic for the current channel """
        await ctx.channel.edit(topic=new_topic)
        await ctx.send(f"Topic changed to: '{new_topic}'")
    
    @commands.command(usage="pin <(Message ID you want pinned) or (new message to pin.)>")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def pin(self, ctx, *, message: typing.Union[discord.Message, int, str]):
        """ Pin a message to the current channel """
        if isinstance(message, int):
            message = await ctx.channel.fetch_message(message)
        elif isinstance(message, str):
            message = await ctx.send(message)
        await message.pin()
        await ctx.message.delete()
    
    @commands.command(usage="rename <member> <new name>")
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def rename(self, ctx, member: discord.Member, nickname: commands.clean_content):
        """ Rename a member """
        try:
            await member.edit(nick=nickname)
        except discord.Forbidden:
            await ctx.send("⛔ I can't change that member's nickname.")
        except discord.HTTPException:
            await ctx.send("❔ Member edit failed.")
        else:
            await ctx.send(f"{member.mention} has been renamed.")
    
    @commands.command(usage="delete_empty_roles")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def delete_empty_roles(self, ctx):
        """ Delete any unused roles on the server """
        targets = [i for i in ctx.guild.roles if i.name.lower() != "muted" and not i.members]
        deleted = []
        for i in targets:
            deleted.append(i.name)
            await i.delete()
        await ctx.send(f'Found and deleted {len(deleted)} empty roles: {", ".join(deleted)}')
    
    @commands.command(usage="kick <@member1  @member2 @member3> <reason>")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, members: commands.Greedy[discord.Member], *, reason="unspecified reason."):
        """ Kicks the user from the server """
        replies = []
        for i in members:
            try:
                await i.kick(reason=f"{ctx.author.name}: {reason}")
            except discord.Forbidden:
                replies.append(f"⛔ I can't kick {i.mention}.")
            except discord.HTTPException:
                replies.append(f'⚠ Kicking failed for {ctx.author.name}.')
            else:
                replies.append(f"✅ {i.mention} was kicked by {ctx.author} for: \"{reason}\".")
        await ctx.send("\n".join(replies))
    
    @commands.command(usage="ban <@member1 user_id2 @member3 @member4> "
                            "<(Optional: Days to delete messages from)> <(Optional: reason)>",
                      aliases=["hackban"])
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, targets: commands.Greedy[typing.Union[discord.Member, int]],
                  delete_days: typing.Optional[int] = 0, *, reason="Not specified"):
        """ Bans a list of members (or User IDs) from the server, deletes all messages for the last x days """
        replies = []
        for i in targets:
            if isinstance(i, discord.Member):
                try:
                    await i.ban(reason=f"{ctx.author.name}: {reason}", delete_message_days=delete_days)
                except discord.Forbidden:
                    replies.append(f"⛔ Sorry, I can't ban {i.mention}.")
                except discord.HTTPException:
                    replies.append(f"⚠ Banning failed for {i.mention}.")
                else:
                    replies.append(f"☠ {i.mention} was banned by {ctx.author} for: \"{reason}\".")
            else:
                try:
                    await self.bot.http.ban(i, ctx.message.guild.id)
                    target = await self.bot.fetch_user(i)
                    replies.append(f"☠ UserID {i} {target} was banned")
                except discord.HTTPException:
                    replies.append(f"⚠ Banning failed for UserID# {i}.")
                except Exception as e:
                    print(e)
                    print("Failed while banning ID#.")
        await ctx.send("\n".join(replies))
    
    @commands.command()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, *, who):
        """ Unbans a user from the server (use name#discrim or userid)"""
        # Try to get by user_id.
        if who.isdigit():
            who = self.bot.get_user(int(who))
            try:
                await self.bot.http.unban(who.id, ctx.guild.id)
            except discord.Forbidden:
                await ctx.send("⛔ I can't unban that user.")
            except discord.HTTPException:
                await ctx.send("❔ Unban failed.")
            else:
                await ctx.send(f"🆗 {who} was unbanned")
        else:
            try:
                un, discrim = who.split('#')
                for i in await ctx.guild.bans():
                    if i.user.display_name == un:
                        if i.discriminator == discrim:
                            try:
                                await self.bot.http.unban(i.user.id, ctx.guild.id)
                            except discord.Forbidden:
                                await ctx.send("⛔ I can't unban that user.")
                            except discord.HTTPException:
                                await ctx.send("❔ Unban failed.")
                            else:
                                await ctx.send(f"🆗 {who} was unbanned")
            except ValueError:
                for i in await ctx.guild.bans():
                    if i.user.name == who:
                        try:
                            await self.bot.http.unban(i.user.id, ctx.guild.id)
                        except discord.Forbidden:
                            await ctx.send("⛔ I can\'t unban that user.")
                        except discord.HTTPException:
                            await ctx.send("❔ Unban failed.")
                        else:
                            await ctx.send(f"🆗 {who} was unbanned")
    
    @commands.command(aliases=['bans'])
    @commands.has_permissions(view_audit_log=True)
    @commands.bot_has_permissions(view_audit_log=True)
    async def banlist(self, ctx):
        """ Show the banlist for the server """
        banlist = await ctx.guild.bans()
        banpages = []
        banembeds = []
        if len(banlist) == 0:
            banpages = "☠ No bans found!"
        else:
            this_page = ""
            for x in banlist:
                a = x.user.name
                b = x.user.discriminator
                if len(unquote("\💀 {a}#{b}: {x.reason}\n")) + len(this_page) > 1200:
                    banpages.append(this_page)
                    this_page = ""
                this_page += unquote(f"\💀 {a}#{b}: {x.reason}\n")
            banpages.append(this_page)
        page_number = 1
        for i in banpages:
            e = discord.Embed(color=0x111)
            n = f"≡ {ctx.guild.name} discord ban list"
            e.set_author(name=n, icon_url=ctx.guild.icon_url)
            e.set_thumbnail(url="https://i.ytimg.com/vi/eoTDquDWrRI/hqdefault.jpg")
            e.title = "User (Reason)"
            e.description = i
            e.set_footer(text=f"Page {page_number} of {len(banpages)}")
            page_number += 1
            banembeds.append(deepcopy(e))
        await paginate(ctx, banpages)
    
    ### Mutes & Blocks
    @commands.command()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def block(self, ctx, member: discord.Member):
        """ Block a user from seeing this channel (cannot be used on guild default channel) """
        try:
            mute_channel = self.bot.get_channel(self.bot.notif_cache[ctx.guild.id]["mute_channel_id"])
        except:
            mute_channel = None
        
        # Check if already muted
        ows = ctx.channel.overwrites
        ows = [i[0] for i in ows if isinstance(i[0], discord.Member)]
        
        if member in ows:
            try:
                await ctx.channel.set_permissions(member, overwrite=None)
            except Exception as e:
                return await ctx.send(f"Could not unblock member from channel, Error: \n```{e}```")
            else:
                if mute_channel:
                    await mute_channel.send(
                        f"{member.mention} was unblocked from {ctx.channel.mention} by {ctx.author}")
                return await ctx.send(f"Unblocked {member.mention} from {ctx.channel.mention}")
        
        ow = discord.PermissionOverwrite(read_messages=False, send_messages=False)
        
        # Cannot block from default channel.
        try:
            await ctx.channel.set_permissions(member, overwrite=ow)
        except Exception as e:
            return await ctx.send(f"Could not block user from channel, error:\n ```{e}```")
        else:
            await ctx.send(f"{member.mention} has been blocked from {ctx.channel.mention} by {ctx.author}")
            if mute_channel:
                await mute_channel.send(f"{member.mention} has been blocked from {ctx.channel.mention} by "
                                        f"{ctx.author}")
    
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.command(usage="mute <@user1 @user2 @user3> <reason>")
    async def mute(self, ctx, members: commands.Greedy[discord.Member], *, reason="No reason given."):
        """ Toggle a list of users having the "Muted" role."""
        try:
            mute_channel = self.bot.get_channel(self.bot.notif_cache[ctx.guild.id]["mute_channel_id"])
        except:
            mute_channel = None
        
        muted_role = discord.utils.get(ctx.guild.roles, name='Muted')
        
        if not muted_role:
            muted_role = await ctx.guild.create_role(name="Muted")  # Read Messages / Read mesasge history.
            await muted_role.edit(position=ctx.me.top_role.position - 1)
            moverwrite = discord.PermissionOverwrite(add_reactions=False, send_messages=False)
            
            for i in ctx.guild.text_channels:
                await i.set_permissions(muted_role, overwrite=moverwrite)
        
        # Unmute if currently muted.
        for i in members:
            if muted_role in i.roles:
                await i.remove_roles(*[muted_role], reason="unmuted.")
                await ctx.send(f"{i.mention} was unmuted.")
                await mute_channel.send(f"{i.mention} was unmuted by {ctx.author}.")
                # Get Mod channel.
                if mute_channel:
                    await mute_channel.send()
            else:
                await i.add_roles(*[muted_role], reason=f"{ctx.author}: {reason}")
                await ctx.send(f"{i.mention} was muted.")
                await mute_channel.send(f"{i.mention} was muted by {ctx.author} for {reason}.")
    
    @commands.command(aliases=["clear"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clean(self, ctx, number: int = 100):
        """ Deletes my messages from the last x messages in channel"""
        try:
            prefixes = tuple(self.bot.prefix_cache[ctx.guild.id])
        except KeyError:
            prefixes = ctx.prefix
        
        def is_me(m):
            return m.author == ctx.me or m.content.startswith(prefixes)
        
        deleted = await ctx.channel.purge(limit=number, check=is_me)
        s = "s" if len(deleted) > 1 else ""
        await ctx.send(f'♻ Deleted {len(deleted)} bot and command messages{s}', delete_after=10)
    
    @commands.group(invoke_without_command=True, usage='prefix: List all prefixes for the server')
    @commands.guild_only()
    async def prefix(self, ctx):
        """ Add, remove, or List bot prefixes for this server."""
        try:
            prefixes = self.bot.prefix_cache[ctx.guild.id]
        except KeyError:
            prefixes = ['.tb ']
            connection = await self.bot.db.acquire()
            await connection.execute("""INSERT INTO prefixes (guild_id,prefix) VALUES ($1,$2)""", ctx.guild.id, '.tb ')
            await self.bot.db.release(connection)
            await self.update_prefixes()
        
        prefixes = ', '.join([f"'{i}'" for i in prefixes])
        await ctx.send(f"Current Command prefixes for this server: ```{prefixes}```")
    
    @prefix.command(name="add", aliases=["set"])
    @commands.has_permissions(manage_guild=True)
    async def pref_add(self, ctx, prefix):
        try:
            prefixes = self.bot.prefix_cache[ctx.guild.id]
        except KeyError:
            prefixes = ['.tb ']
        
        if prefix not in prefixes:
            connection = await self.bot.db.acquire()
            await connection.execute("""INSERT INTO prefixes (guild_id,prefix) VALUES ($1,$2) """, ctx.guild.id,
                                     prefix)
            await self.bot.db.release(connection)
            await ctx.send(f"Added '{prefix}' to {ctx.guild.name}'s prefixes list.")
            await self.update_prefixes()
        else:
            await ctx.send(f"'{prefix}' was already in {ctx.guild.name}'s prefix list")
        
        prefixes = ', '.join([f"'{i}'" for i in self.bot.prefix_cache[ctx.guild.id]])
        await ctx.send(f"Current Command prefixes for this server: ```{prefixes}```")
    
    @prefix.command(name="remove", aliases=["delete"])
    @commands.has_permissions(manage_guild=True)
    async def pref_del(self, ctx, prefix):
        try:
            prefixes = self.bot.prefix_cache[ctx.guild.id]
        except KeyError:
            prefixes = ['.tb ']
        if prefix in prefixes:
            connection = await self.bot.db.acquire()
            await connection.execute("""DELETE FROM prefixes WHERE (guild_id,prefix) = ($1,$2) """, ctx.guild.id,
                                     prefix)
            await self.bot.db.release(connection)
            await ctx.send(f"Deleted '{prefix}' from {ctx.guild.name}'s prefixes list.")
            await self.update_prefixes()
        else:
            await ctx.send(f"'{prefix}' was not in {ctx.guild.name}'s prefix list")
        
        prefixes = ', '.join([f"'{i}'" for i in self.bot.prefix_cache[ctx.guild.id]])
        await ctx.send(f"Current Command prefixes for this server: ```{prefixes}```")
    
    @commands.command(aliases=["enable"], usage="<'disable' or 'enable'> <command name>")
    @commands.has_permissions(manage_guild=True)
    async def disable(self, ctx, command: str):
        """Disables a command for this server."""
        command = command.lower()
        
        if ctx.invoked_with == "enable":
            if command not in self.bot.disabled_cache[ctx.guild.id]:
                return await ctx.send("That command isn't disabled on this server.")
            else:
                connection = await self.bot.db.acquire()
                async with connection.transaction():
                    await connection.execute("""
                        DELETE FROM disabled_commands WHERE (guild_id,command) = ($1,$2)
                        """, ctx.guild.id, command)
                await self.bot.db.release(connection)
                await self.update_cache()
                return await ctx.send(f"The {command} command was re-enabled for {ctx.guild.name}")
        
        if command in ('disable', 'enable'):
            return await ctx.send('Cannot disable the disable command.')
        elif command not in [i.name for i in list(self.bot.commands)]:
            return await ctx.send('Unrecognised command name.')
        
        connection = await self.bot.db.acquire()
        await connection.execute(""" INSERT INTO disabled_commands (guild_id,command) VALUES ($1,$2) """,
                                 ctx.guild.id, command)
        await self.bot.db.release(connection)
        await self.update_cache()
        return await ctx.send(f"The {command} command was disabled for {ctx.guild.name}")
    
    @commands.command(usage="disabled")
    @commands.has_permissions(manage_guild=True)
    async def disabled(self, ctx):
        """ Check which commands are disabled on this server """
        try:
            commands = self.bot.disabled_cache[ctx.guild.id]
            await ctx.send(f"The following commands are disabled on this server: ```{' ,'.join(commands)}```")
        except KeyError:
            return await ctx.send(f'No commands are currently disabled on {ctx.guild.name}')


def setup(bot):
    bot.add_cog(Mod(bot))
