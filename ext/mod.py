from discord.ext import commands
import discord
import asyncio
import json
import typing
import urllib

### TODO: Merge hackyinfo into info
### TODO: Merge hackban into ban

	
class Mod(commands.Cog):
	""" Guild Moderation Commands """
	def __init__(self, bot):
		self.bot = bot
		self.bot.loop.create_task(self.update_cache())
		self.bot.loop.create_task(self.update_prefixes())
		self.bot.command_prefix = self.get_prefix
	
	def get_prefix(self,bot,message):
		try:
			pref = self.bot.prefix_cache[message.guild.id]
		except KeyError:
			pref = [".tb"]
		except AttributeError:
			pref = [".tb","!","-","`","!","?"]

		return commands.when_mentioned_or(*pref)(self.bot, message)		
	
	def me_or_mod():
		def predicate(ctx):
			if ctx.author.id == 210582977493598208:
				return True
			return ctx.author.permissions_in(ctx.channel).manage_channels
		return commands.check(predicate)
	
	async def update_prefixes(self):
		self.bot.prefix_cache = {}
		connection = await self.bot.db.acquire()
		async with connection.transaction():
			records =  await connection.fetch("""
				SELECT * FROM prefixes
			""")
		await self.bot.db.release(connection)
		
		for r in records:
			guild_id = r["guild_id"]
			prefix = r["prefix"]
			try:
				self.bot.prefix_cache[guild_id].append(prefix)
			except KeyError:
				self.bot.prefix_cache.update({guild_id : [prefix]})	
	
	async def update_cache(self):
		self.bot.disabled_cache = {}
		connection = await self.bot.db.acquire()
		async with connection.transaction():
			records =  await connection.fetch("""
				SELECT * FROM ignored_commands
			""")
		await self.bot.db.release(connection)
		
		for r in records:
			guild_id = r["guild_id"]
			command = r["command"]
			try:
				self.bot.disabled_cache[guild_id].append(command)
			except KeyError:
				self.bot.disabled_cache.update({guild_id : [command]})
	
	@commands.command(aliases=['nick'])
	@commands.has_permissions(manage_nicknames=True)
	async def name(self,ctx,*,newname: str):
		""" Rename the bot for your server. """
		await ctx.me.edit(nick=newname)	
	
	@commands.command(usage = "say <Channel (optional)< <what you want the bot to say>")
	@me_or_mod()
	async def say(self,ctx,destin:typing.Optional[discord.TextChannel] = None,*,tosay):
		""" Say something as the bot in specified channel """
		if destin is None:
			destin = ctx.channel
		try:
			await ctx.message.delete()
		except discord.Forbidden:
			pass
		await destin.send(tosay)

	@commands.command(usage = "topic <New Channel Topic>")
	@commands.has_permissions(manage_channels=True)
	@commands.bot_has_permissions(manage_channels=True)
	async def topic(self,ctx,*,newtopic):
		""" Set the topic for the current channel """
		await ctx.channel.edit(topic=newtopic)
		await ctx.send(f"Topic changed to: '{newtopic}'")
		
	@commands.command(usage = "pin <(Message ID you want pinned) or (new message to pin.)>")
	@commands.has_permissions(manage_channels=True)
	@commands.bot_has_permissions(manage_channels=True)
	async def pin(self,ctx,*,msg):
		""" Pin a message to the current channel """
		try:
			m = await ctx.channel.fetch_message(int(msg))
		except ValueError:
			topin = await ctx.send(f":pushpin: {ctx.author.mention}: {msg}")
			await topin.pin()
			await ctx.message.delete()
	
	@commands.command(usage = "rename <member> <new name>")
	@commands.has_permissions(manage_nicknames=True)
	@commands.bot_has_permissions(manage_nicknames=True)
	async def rename(self,ctx,member:discord.Member,nickname:commands.clean_content):
		""" Rename a member """
		try:
			await member.edit(nick=nickname)
		except discord.Forbidden:
			await ctx.send("⛔ I can\'t change that member's nickname.")
		except discord.HTTPException:
			await ctx.send("❔ Member edit failed.")
		else:
			await ctx.send(f"{member.mention} has been renamed.")
		await ctx.message.delete()

	@commands.command(usage= "delete_empty_roles")
	@commands.has_permissions(manage_roles=True)
	@commands.bot_has_permissions(manage_roles=True)
	async def delete_empty_roles(self,ctx):
		""" Delete any unused roles on the server """
		count = 0
		deleted = []
		for i in ctx.guild.roles:
			# protected roles.
			if i.name.lower() == "muted":
				continue
			if len(i.members) == 0:
				count += 1
				await i.delete()
				deleted.append(i.name)	
		await ctx.send(f'Found and deleted {count} empty roles: {", ".join(deleted)}')
	
	@commands.command(usage = "kick <@member1  @member2 @member3> <reason>")
	@commands.has_permissions(kick_members=True)
	@commands.bot_has_permissions(kick_members=True)
	async def kick(self,ctx,members : commands.Greedy[discord.Member],*,reason = "unspecified reason."):
		""" Kicks the user from the server """
		for i in members:
			try:
				await i.kick(reason=f"{ctx.author.name}: {reason}")
			except discord.Forbidden:
				await i.send(f"⛔ Sorry {ctx.author.name} I can't kick {user.mention}.")
			except discord.HTTPException:
				await i.send(f'❔ Kicking failed for {ctx.author.name}.')
			else:
				await ctx.send(f"👢 {user.mention} was kicked by {ctx.author.mention} for: \"{reason}\".")
	
	@commands.command(usage = "ban <@member1  @member2 @member3> <reason>")
	@commands.has_permissions(ban_members=True)
	@commands.bot_has_permissions(ban_members=True)
	async def ban(self,ctx,members : commands.Greedy[discord.Member],delete_days: typing.Optional[int] = 0,*,reason="Not specified"):
		""" Bans a list of members from the server, deletes all messages for the last x days """
		for i in members:
			try:
				await i.ban(reason=f"{ctx.author.name}: {reason}",delete_message_days=delete_days)
			except discord.Forbidden:
				await ctx.send(f"⛔ Sorry, I can't ban {i.mention}.")
			except discord.HTTPException:
				await ctx.send(f"❔ Banning failed for {i.mention}.")
			else:
				await ctx.send(f"☠ {i.mention} was banned by {ctx.author.mention} for: \"{reason}\".")
	
	@commands.command(usage = "hackban <memberid1  @memberid2 @memberid3> <reason>")
	@commands.has_permissions(ban_members=True)
	@commands.bot_has_permissions(ban_members=True)
	async def hackban(self, ctx, *member_ids: int):
		"""Bans a list of members via their ID."""
		for member_id in member_ids:
			try:
				await self.bot.http.ban(member_id, ctx.message.guild.id)
			except discord.HTTPException:
				pass
		await ctx.send(f'☠ Did some bans. Showing new banlist. {ctx.author.mention}')
		await ctx.invoke(self.banlist)
	
	@commands.command()
	@commands.has_permissions(ban_members=True)
	@commands.bot_has_permissions(ban_members=True)
	async def unban(self,ctx,*,who):
		""" Unbans a user from the server (use name#discrim or userid)"""
		# Try to get by userid. 
		if who.isdigit():
			who = self.bot.get_user(int(who))
			try:
				await self.bot.http.unban(who.id, ctx.guild.id)
			except discord.Forbidden:
				await ctx.send("⛔ I cab't unban that user.")
			except discord.HTTPException:
				await ctx.send("❔ Unban failed.")
			else:
				await ctx.send(f"🆗 {who} was unbanned")	
		else:				
			try:
				un,discrim = who.split('#')
				for i in await ctx.guild.bans():
					if i.user.display_name == un:
						if i.discriminator == discrim:
							try:
								await self.bot.http.unban(i.user.id, ctx.guild.id)
							except discord.Forbidden:
								await ctx.send("⛔ I can\'t unban that user.")
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
	@commands.has_permissions(ban_members=True)
	@commands.bot_has_permissions(view_audit_log=True)
	async def banlist(self,ctx):
		""" Show the banlist for the server """
		banlist = await ctx.guild.bans()

		banpage = ""
		banpages = []
		banembeds = []
		if len(banlist) == 0:
			banpage = "☠ No bans found!"
		else:
			for x in banlist:
				a = x.user.name
				b = x.user.discriminator
				if len("\💀 {a}#{b}: {x.reason}\n") + len(banpage) > 1200:
					banpages.append(banpage)
					banpage = ""
				banpage += urllib.parse.unquote(f"\💀 {a}#{b}: {x.reason}\n")
			banpages.append(banpage)
		thispage = 1
		for i in banpages:
			e = discord.Embed(color=0x111)
			n = f"≡ {ctx.guild.name} discord ban list"
			e.set_author(name=n,icon_url=ctx.guild.icon_url)
			e.set_thumbnail(url="https://i.ytimg.com/vi/eoTDquDWrRI/hqdefault.jpg")
			e.title = "User (Reason)"
			e.description = i
			e.set_footer(text=f"Page {thispage} of {len(banpages)}")
			thispage += 1
			banembeds.append(e)
		
		m = await ctx.send(embed=banembeds[0])
		if len(banembeds) == 1:
			return
		if len(banembeds) > 2:
			await m.add_reaction("⏮") # first
		if len(banembeds) > 1:
			await m.add_reaction("◀") # prev
		if len(banembeds) > 1:
			await m.add_reaction("▶") # next
		if len(banembeds) > 2:
			await m.add_reaction("⏭") # last
		
		def check(reaction,user):
			if reaction.message.id == m.id and user == ctx.author:
				e = str(reaction.emoji)
				return e.startswith(('⏮','◀','▶','⏭'))
		
		page = 0			
		# Reaction Logic Loop.
		while True:
			try:
				res = await self.bot.wait_for("reaction_add",check=check,timeout=120)
			except asyncio.TimeoutError:
				await m.clear_reactions()
				break
			res = res[0]
			if res.emoji == "⏮": #first
				page = 1
				await m.remove_reaction("⏮",ctx.message.author)
			elif res.emoji == "◀": #prev
				await m.remove_reaction("◀",ctx.message.author)
				if page > 1:
					page = page - 1
			elif res.emoji == "▶": #next	
				await m.remove_reaction("▶",ctx.message.author)
				if page < len(banembeds):
					page = page + 1
			elif res.emoji == "⏭": #last
				page = len(banembeds)
				await m.remove_reaction("⏭",ctx.message.author)
			await m.edit(embed=banembeds[page - 1])
		
	### Mutes & Blocks
	@commands.command()
	@commands.has_permissions(manage_channels=True)
	@commands.bot_has_permissions(manage_channels=True)
	async def block(self,ctx,member:discord.Member):
		""" Block a user from this channel (cannot be used on guild default channel) """
		try:
			mutechan = self.bot.get_channel(self.bot.notif_cache[ctx.guild.id]["mute_channel_id"])
		except:
			mutechan = None
		
		# Check if already muted
		ows = ctx.channel.overwrites
		ows = [i[0] for i in ows if isinstance(i[0],discord.Member)]
		
		if member in ows:
			try:
				await ctx.channel.set_permissions(member, overwrite=None)
			except Exception as e:
				return await ctx.send(f"Could not unblock member from channel, Error: \n```{e}```")
			else:
				if mutechan:
					await mutechan.send(f"{member.mention} was unblocked from {ctx.channel.mention} by {ctx.author}")	
				return await ctx.send(f"Unblocked {member.mention} from {ctx.channel.mention}")		
		
		ow = discord.PermissionOverwrite()
		# Cannot block from default channel.
		ow.read_messages = False
		ow.send_messages = False
		
		try:
			await ctx.channel.set_permissions(member,overwrite=ow)
		except Exception as e:
			return await ctx.send(f"Could not block user from channel, error:\n ```{e}```")
		else:
			await ctx.send(f"{member.mention} has been blocked from {ctx.channel.mention} by {ctx.author}")
			if mutechan:
				await mutechan.send(f"{member.mention} has been blocked from {ctx.channel.mention} by {ctx.author}")
				
	@commands.has_permissions(manage_roles=True)
	@commands.bot_has_permissions(manage_roles=True)
	@commands.command(usage = "mute <@user1 @user2 @user3> <reason>")
	async def mute(self,ctx,members : commands.Greedy[discord.Member],*,reason="No reason given."):
		""" Toggle a list of users having the "Muted" role."""
		try:
			mutechan = self.bot.get_channel(self.bot.notif_cache[ctx.guild.id]["mute_channel_id"])
		except:
			mutechan = None
		
		mrole = discord.utils.get(ctx.guild.roles, name='Muted')
			
		if not mrole:
			mrole = await ctx.guild.create_role(name="Muted") # Read Messages / Read mesasge history.
		
		# Unmute if currently muted.
		for i in members:
			if mrole in i.roles:
				await i.remove_roles(*[mrole],reason="unmuted.")
				await ctx.send(f"{i.mention} was unmuted.")
				await mutechan.send(f"{member.mention} was unmuted by {ctx.author}.")
				# Get Mod channel.
				if mutechan:
					await mutechan.send()
			else:
				await i.add_roles(*[mrole],reason=f"{ctx.author}: {reason}")
				await ctx.send(f"{i.mention} was muted.")
				await mutechan.send(f"{member.mention} was muted by {ctx.author} for {reason}.")
		
		# Reapply muted role overrides.
		
		await mrole.edit(position=ctx.me.top_role.position - 1)		
		moverwrite = discord.PermissionOverwrite()
		moverwrite.add_reactions = False
		moverwrite.send_messages = False		
		for i in ctx.guild.text_channels:
			await i.set_permissions(mrole,overwrite=moverwrite)
	
	@commands.command(aliases=["clear"])
	@commands.has_permissions(manage_messages=True)
	@commands.bot_has_permissions(manage_messages=True)
	async def clean(self,ctx,number : int = 100):
		""" Deletes my messages from the last x messages in channel"""
		try:
			prefixes = tuple(self.bot.prefix_cache[ctx.guild.id])
		except KeyError:
			prefixes = ctx.prefix
		
		def is_me(m):
			return m.author == ctx.me or m.content.startswith(prefixes)

		deleted = await ctx.channel.purge(limit=number, check=is_me)
		s = "s" if len(deleted) > 1 else ""
		await ctx.send(f'♻️ {ctx.author.mention}: Deleted {len(deleted)} bot and command messages{s}',delete_after=10)	

	@commands.command(usage = "Normal user: List all prefixes for the server \n"
							+ "Moderators: prefix <'yourprefix'> to toggle a bot prefix for the server")
	@commands.guild_only()
	async def prefix(self,ctx,*,prefix=""):
		""" Add, remove, or List bot prefixes for this server."""
		prefix = prefix.replace("add ","").replace("remove ","")
		try:
			prefixes = self.bot.prefix_cache[ctx.guild.id]
		except KeyError:
			prefixes = ['.tb']
			connection = await self.bot.db.acquire()
			async with connection.transaction():
				records =  await connection.execute("""
					INSERT INTO prefixes (guild_id,prefix) VALUES ($1,$2) 
				""",ctx.guild.id,prefix)
			await self.bot.db.release(connection)		
		
		if prefix:
			# Server Admin only.
			if  ctx.channel.permissions_for(ctx.author).manage_guild:				
				if prefix not in prefixes:
					connection = await self.bot.db.acquire()
					async with connection.transaction():
						records =  await connection.execute("""
							INSERT INTO prefixes (guild_id,prefix) VALUES ($1,$2) 
						""",ctx.guild.id,prefix)
					await self.bot.db.release(connection)
					await ctx.send(f'Added "{prefix}" to {ctx.guild.name}\'s prefixes list.')
				else:
					if prefix == ".tb":
						return await ctx.send("The .tb prefix cannot be removed.")
					connection = await self.bot.db.acquire()	
					async with connection.transaction():
						records =  await connection.execute("""
							DELETE FROM prefixes WHERE (guild_id,prefix) = ($1,$2) 
						""",ctx.guild.id,prefix)
					await self.bot.db.release(connection)
					await ctx.send(f'Removed "{prefix}" from {ctx.guild.name}\'s prefix list.')
		
		await self.update_prefixes()
		prefixes = ', '.join(["'{i}'" for i in self.bot.prefix_cache[ctx.guild.id]])
		await ctx.send(f"Current Command prefixes for this server: ```{prefixes}```")

	@commands.command(aliases=["enable"],usage= "<'disable' or 'enable'> <command name>")
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
						DELETE FROM ignored_commands WHERE (guild_id,command) = ($1,$2)
						""",ctx.guild.id,command)
				await self.bot.db.release(connection)			
				await self.update_cache()
				return await ctx.send(f"The {command} command was re-enabled for {ctx.guild.name}")

		if command in ('disable','enable'):
			return await ctx.send('Cannot disable the disable command.')
		elif command not in [i.name for i in list(self.bot.commands)]:
			return await ctx.send('Unrecognised command name.')
		
		connection = await self.bot.db.acquire()
		async with connection.transaction():
			await connection.execute(""" 
				INSERT INTO ignored_commands (guild_id,command) VALUES ($1,$2)
				""",ctx.guild.id,command)
		await self.bot.db.release(connection)			
		await self.update_cache()
		return await ctx.send(f"The {command} command was disabled for {ctx.guild.name}")

	@commands.command(usage = "disabled")
	@commands.has_permissions(manage_guild=True)
	async def disabled(self,ctx):
		""" Check which commands are disabled on this server """
		try:
			commands = self.bot.disabled_cache[ctx.guild.id]
			await ctx.send(f"The following commands are disabled on this server: ```{' ,'.join(commands)}```")
		except KeyError:
			return await ctx.send(f'No commands are currently disabled on {ctx.guild.name}')
		
			
def setup(bot):
	bot.add_cog(Mod(bot))