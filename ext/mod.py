from discord.ext.commands.cooldowns import BucketType
from discord.ext import commands
import discord
import asyncio
import json
import urllib

class Mod(commands.Cog):
	''' Guild Moderation Commands '''
	def __init__(self, bot):
		self.bot = bot
		
	@commands.command()
	@commands.is_owner()
	async def say(self,ctx,destin:discord.TextChannel = None,*,tosay):
		""" Say something as the bot in specified channel """
		try:
			await ctx.message.delete()
		except:
			pass
		if destin is None:
			destin = ctx
		await destin.send(tosay)

	@commands.command()
	@commands.has_permissions(manage_messages=True)
	async def topic(self,ctx,*,newtopic):
		""" Set the topic for the current channel """
		await ctx.channel.edit(topic=newtopic)
		await ctx.send(f"Topic changed to: '{newtopic}'")
		
		
	@commands.command()
	@commands.has_permissions(manage_messages=True)
	@commands.bot_has_permissions(manage_messages=True)
	async def pin(self,ctx,*,msg):
		""" Pin a message to the current channel """
		try:
			m = await self.bot.fetch_message(int(msg))
			await m.pin()
		except:
			await ctx.message.delete()
			topin = await ctx.send(f":pushpin: {ctx.author.mention}: {msg}")
			await topin.pin()
	
	@commands.command()
	@commands.has_permissions(manage_nicknames=True)
	async def rename(self,ctx,member:discord.Member,nickname:str):
		""" Rename a member """
		try:
			await member.edit(nick=nickname)
		except discord.Forbidden:
			await ctx.send("⛔ I can\'t change that member's nickname.")
		except discord.HTTPException:
			await ctx.send("❔ Member edit failed.")
		else:
			await ctx.send(f"{member.mention} has been renamed.")	

	@commands.command()
	@commands.is_owner()
	async def delete_empty_roles(self,ctx):
		""" Delete any unused roles on the server """
		count = 0
		for i in ctx.guild.roles:
			# protected roles.
			if i.name in ["muted","Moderator"]:
				continue
			if len(i.members) == 0:
				print(f"Empty role: {i.name}")
				count += 1
				try:
					await i.delete()
				except discord.Forbidden:
					continue
		await ctx.send(f'Found and deleted {count} empty roles.')
	
	@commands.command()
	@commands.has_permissions(kick_members=True)
	async def kick(self,ctx,user : discord.Member,*,reason = "unspecified reason."):
		""" Kicks the user from the server """
		await ctx.message.delete()
		try:
			await user.kick(reason=f"{ctx.author.name}: {reason}")
		except discord.Forbidden:
			await ctx.send(f"⛔ Sorry {ctx.author.name} I can't kick {user.mention}.")
		except discord.HTTPException:
			await ctx.send('❔ Kicking failed.')
		else:
			await ctx.send(f"👢 {user.mention} was kicked by {ctx.author.mention} for: \"{reason}\".")
	
	@commands.command()
	@commands.has_permissions(ban_members=True)
	@commands.bot_has_permissions(ban_members=True)
	async def ban(self,ctx,member : discord.Member,*,reason="Not specified",days = 0):
		""" Bans the member from the server """
		await ctx.message.delete()
		try:
			await member.ban(reason=f"{ctx.author.name}: {reason}",delete_message_days=days)
		except discord.Forbidden:
			await ctx.send(f"⛔ Sorry, I can't ban {member.mention}.")
		except discord.HTTPException:
			await ctx.send("❔ Banning failed.")
		else:
			await ctx.send(f"☠ {member.mention} was banned by {ctx.author.mention} for: \"{reason}\".")
	
	@commands.command()
	@commands.has_permissions(ban_members=True)
	@commands.bot_has_permissions(ban_members=True)
	async def hackban(self, ctx, *member_ids: int):
		"""Bans a member via their ID."""
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
	@commands.guild_only()
	@commands.has_permissions(ban_members=True)
	async def banlist(self,ctx):
		""" Show the banlist for the server """
		try:
			banlist = await ctx.guild.bans()
		except discord.Forbidden:
			return await ctx.send('I don\'t have permission to view the banlist on this server.')
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
		
	## Mod logs.
	async def _save(self):
		with await self.bot.configlock:
			with open('config.json',"w",encoding='utf-8') as f:
				json.dump(self.bot.config,f,ensure_ascii=True,
				sort_keys=True,indent=4, separators=(',',':'))
	
	async def get_mod_channel(self,ctx,id):
		try: 
			d = self.bot.config[id]["mod"]
		except KeyError:
			d = self.bot.config[id]["mod"] = {}
		
		try:
			c = d["channel"]
			mc = self.bot.get_channel(c)
		except KeyError:
			d["channel"] = None
			await self._save()
			mc = None
			
		if mc is None:
			await ctx.send(f"Mod channel not set, please use"\
				f"`{ctx.prefix}mod set` in desired channel to set it first")
		
		return mc
	
	async def check_mod_config(self,guild):
	# Check if in mod.
		id = guild.id
		try: 
			d = self.bot.config[id]["mod"]
		except KeyError:
			d = self.bot.config[id]["mod"] = {}
			await self._save()
	
	@commands.command()
	@commands.has_permissions(manage_guild=True)
	@commands.guild_only()
	async def mod(self,ctx,*,set=""):
		""" Shows the status of various mod tools."""
		if set == "set":
			self.bot.config.update({f"{ctx.guild.id}":{"mod":{"channel":f"{ctx.channel.id}"}}})
			cf = f"Mod Channel for {ctx.guild.name} set to {ctx.channel.name}"
			await ctx.send(cf)
			await self._save()
		
		# Check mod is set.
		mc = await self.get_mod_channel(ctx,id)
		
		if not mc:
			return
		
		e = discord.Embed(color=0x7289DA)
		e.description = f"Mod Channel: {mc.mention}\n"
		e.title = f"Config settings for {ctx.guild.name}"
		
		for i in ['joins','leaves','unbans','emojis','mutes']:
			try:
				c[i]
			except KeyError:
				c[i] = "Off"
		e.description += f"Joins: `{c['joins']}`\n"
		e.description += f"Leaves: `{c['leaves']}`\n"
		e.description += f"Unbans: `{c['unbans']}`\n"
		e.description += f"Emojis: `{c['emojis']}`\n"
		e.description += f"Mutes: `{c['mutes']}`"
		e.set_thumbnail(url=ctx.guild.icon_url)
		await ctx.send(embed=e)

	### Mutes & Blocks
	@commands.has_permissions(kick_members=True)
	@commands.command()
	async def block(self,ctx,member:discord.Member):
		""" Block a user from this channel (cannot be used on guild default channel) """
		# Check if already muted
		ows = ctx.channel.overwrites
		ows = [i[0] for i in ows if isinstance(i[0],discord.Member)]
		if member in ows:
			try:
				await ctx.channel.set_permissions(member, overwrite=None)
			except Exception as e:
				await ctx.send(f"Could not unblock member from channel, Error: \n```{e}```")
				print(e)
			else:
				try:
					if self.bot.config[f"{ctx.guild.id}"]["mod"]["mutes"]:
						# Get Mod channel.
						mc = await self.get_mod_channel(ctx,id)
						
						if not mc:
							return
							
						await mc.send(f"{member.mention} was unmuted by {ctx.author}")	
				except KeyError:
					self.bot.config[f"{ctx.guild.id}"]["mod"]["mutes"] == False			
				return await ctx.send(f"Unblocked {member.mention} from {ctx.channel.mention}")		
		
		ow = discord.PermissionOverwrite()
		# Cannot block from default channel.
		ow.read_messages = False
		ow.send_messages = False
		try:
			await ctx.channel.set_permissions(member,overwrite=ow)
		except Exception as e:
			print(e)
			return await ctx.send(f"Could not block user from channel, error:\n ```{e}```")
		else:
			await ctx.send(f"{member.mention} has been blocked from {ctx.channel.mention}")
			# Get Mod channel.
			mc = await self.get_mod_channel(ctx,id)
			
			if not mc:
				return
				
			await mc.send(f"{member.mention} was unmuted by {ctx.author}")	
			
	
	@commands.has_permissions(manage_messages=True)
	@commands.command()
	@commands.guild_only()
	async def mute(self,ctx,member:discord.Member,*,reason="No reason given."):
		""" Toggle a user having the "Muted" role."""
		mrole = discord.utils.get(ctx.guild.roles, name='Muted')
				
		# Unmute if currently muted.
		if mrole in member.roles:
			await member.remove_roles(*mrole)
			await ctx.send(f"{member.mention} was unmuted.")
			
			# Get Mod channel.
			mc = await self.get_mod_channel(ctx,id)
			if not mc:
				return
				
			try:
				if self.bot.config[f"{ctx.guild.id}"]["mod"]["mutes"]:
					await mc.send(f"{member.mention} was unmuted by {ctx.author}")	
			except KeyError:
				self.bot.config[f"{ctx.guild.id}"]["mod"]["mutes"] == False
			return
			
		# Else Mute
		if not mrole:
			m = await ctx.send("Could not find a 'Muted' Role. Create one now?")
			for i in ['✅','❌']:
				await m.add_reaction(i)
			
			try:
				def check(r,u):
					if r.message.id == m.id and u == ctx.author:
						e = str(r.emoji)
						return e in ['✅','❌']		
				wf = "reaction_add"
				r = await self.bot.wait_for(wf,check=check,timeout=120)
			except asyncio.TimeoutError:
				try:
					await m.clear_reactions()
				except discord.Forbidden:
					pass
				
			r = r[0]
			if r.emoji == "✅": #Check
				mrole = await ctx.guild.create_role(name="Muted") # Read Messages / Read mesasge history.
				await mrole.edit(position=ctx.me.top_role.position + 1) # Move the role to the highest position under the bot, to override everything else.
				
				moverwrite = discord.PermissionOverwrite()
				moverwrite.add_reactions = False
				moverwrite.send_messages = False
				
				for i in ctx.guild.text_channels:
					await i.set_permissions(mrole,overwrite=moverwrite)
					
			if r.emoji == "❌": #Cross
				return await m.edit(f"Did not mute {member.mention}, \"Muted\" role does not exist and creation was cancelled.")
		
		await member.add_roles(*mrole)
		
		# Reapply muted role overrides.
		moverwrite = discord.PermissionOverwrite()
		moverwrite.add_reactions = False
		moverwrite.send_messages = False		
		for i in ctx.guild.text_channels:
			await i.set_permissions(mrole,overwrite=moverwrite)
		await ctx.send(f"{member.mention} was Muted.")
		
		try:
			if self.bot.config[f"{ctx.guild.id}"]["mod"]["mutes"]:
				await self.bot.get_channel(c["channel"]).send(f"{member.mention} was muted by {ctx.author}: {reason}")
		except KeyError:
			self.bot.config[f"{ctx.guild.id}"]["mod"]["mutes"] == False
	
	@commands.has_permissions(manage_guild=True)
	@commands.command()
	@commands.guild_only()
	async def mutes(self,ctx,*,toggle=None):
		""" Show or hide member mutings and blockings from channel, toggle with mutes "on" or "off" """
		# Check mod channel is set.
		mc = await self.get_mod_channel(ctx,id)
		
		if not mc:
			return
		
		# Give current info
		if toggle is None:
			try: 
				m = self.bot.config[f"{ctx.guild.id}"]["mod"]["mutes"]
			except KeyError:
				self.bot.config[f"{ctx.guild.id}"]["mod"]["mutes"] = False
				await self._save()
			
			m = self.bot.config[f"{ctx.guild.id}"]["mod"]["mutes"]
			if j:
				return await ctx.send(f"Messages will be output to {mc.mention}"\
					f"when a member is muted. Toggle with `{ctx.prefix}mutes off`")
			else:
				return await ctx.send("Messages will not be output when a member is muted.."\
					f"Toggle with `{ctx.prefix}mutes on`")

		# Or update guild preference
		elif toggle.lower() == "on":
			await self.check_mod_config(ctx.guild)
			self.bot.config[f"{ctx.guild.id}"]["mod"]["joins"] = True
			await self._save()
			return await ctx.send(f"A notification will be sent to {mc.mention} when a member is muted.")
			
		elif toggle.lower() == "off":
			await self.check_mod_config(ctx.guild)
			self.bot.config[f"{ctx.guild.id}"]["mod"]["joins"] = False
			await self._save()
			return await ctx.send(f"Notifications will no longer be sent to {mc.mention} when members are muted.")		

	### Extended Member Join Information
	@commands.Cog.listener()			
	async def on_member_join(self,mem):
		
		await self.check_mod_config(mem.guild)
		
		# Check if in config.
		try: 
			d = self.bot.config[id]["mod"]
		except KeyError:
			d = self.bot.config[id]["mod"] = {}
			await self._save()
			
		try:
			j = self.bot.config[f"{mem.guild.id}"]["mod"]["joins"]
		except KeyError:
			self.bot.config[f"{mem.guild.id}"]["mod"]["joins"] =  False
			await self._save()
		try:	
			c = self.bot.config[f"{mem.guild.id}"]["mod"]["channel"]
			c = self.bot.get_channel(c)
		except KeyError:
			return
		if j:
			e = discord.Embed()
			e.color = 0x7289DA
			s = sum(1 for m in self.bot.get_all_members() if m.id == mem.id)
			e.set_author(name=str(mem), icon_url=mem.avatar_url)
			status = str(mem.status).title()
			e.add_field(name="Status",value=status,inline=True)
			e.add_field(name='ID', value=mem.id,inline=True)
			e.add_field(name='Servers', value=f'{s} shared',inline=True)
			if mem.bot:
				e.description = '**This is a bot account**'
			e.add_field(name='Account Created', value=mem.created_at,inline=True)
			e.set_thumbnail(url=mem.avatar_url)
			await c.send(embed=e)
			
	@commands.has_permissions(manage_guild=True)
	@commands.command()
	@commands.guild_only()
	async def joins(self,ctx,*,toggle=None):
		""" Show or hide extended member information upon joining. (Toggle with 'on' and 'off')"""
		# Check mod channel is set.
		mc = await self.get_mod_channel(ctx,id)
		
		if not mc:
			return
		
		# Give current info
		if toggle is None:
			try: 
				j = self.bot.config[f"{ctx.guild.id}"]["mod"]["joins"]
			except KeyError:
				self.bot.config[f"{ctx.guild.id}"]["mod"]["joins"] = False
				await self._save()
			
			j = self.bot.config[f"{ctx.guild.id}"]["mod"]["joins"]
			if j:
				return await ctx.send(f"Extended information is currently output to {mc.mention}"\
					f"when a member joins this server. Toggle with `{ctx.prefix}joins off`")
			else:
				return await ctx.send("Extended information will not be output when a member joins this server."\
					f"Toggle with `{ctx.prefix}joins on`")

		# Or update guild preference
		elif toggle.lower() == "on":
			self.bot.config[f"{ctx.guild.id}"]["mod"]["joins"] = True
			await self._save()
			return await ctx.send(f"Extended information will be output to {mc.mention} when a member joins this server.")
			
		elif toggle.lower() == "off":
			self.bot.config[f"{ctx.guild.id}"]["mod"]["joins"] = False
			await self._save()
			return await ctx.send(f"Extended information will no longer be output to {mc.mention} when members joins this server.")
	
	### Kick, Ban/Unban, and Leave information
	@commands.Cog.listener()
	async def on_member_unban(self,guild,user):
		
		await self.check_mod_config(guild)
		
		# Check if in mod.
		try: 
			d = self.bot.config[id]["mod"]
		except KeyError:
			d = self.bot.config[id]["mod"] = {}
			await self._save()
			
		try:
			l = self.bot.config[f"{guild.id}"]["mod"]["leaves"]
		except KeyError:
			l = self.bot.config[f"{guild.id}"]["mod"]["leaves"] = False
			await self._save()
		
		try:
			c = self.bot.config[f"{guild.id}"]["mod"]["channel"]			
			c = self.bot.get_channel(c)
		except KeyError:
			c = self.bot.config[f"{guild.id}"]["mod"]["channel"] = None
			await self._save()
		
		if l:
			await c.send(f"🆗 {user.name}#{user.discrim} (ID: {user.id}) was unbanned.")
	
	
	@commands.Cog.listener()
	async def on_member_remove(self,member):
		# Check if in mod.
		await self.check_mod_config(member.guild)
			
		try:
			l = self.bot.config[f"{member.guild.id}"]["mod"]["leaves"]
		except KeyError:
			l = self.bot.config[f"{member.guild.id}"]["mod"]["leaves"] = False
			await self._save()
			
		try:
			c = self.bot.config[f"{member.guild.id}"]["mod"]["channel"]
			c = self.bot.get_channel(c)
		except KeyError:
			c = self.bot.config[f"{member.guild.id}"]["mod"]["channel"] = None
			await self._save()
		
		if not l or c is None:
			return
		
		async for i in member.guild.audit_logs(limit=1):
			x = i
			if str(x.target) == str(member):
				if x.action.name == "kick":
					if x.reason is not None:
						if x.reason in ["roulete","Asked to be"]:
							return
					return await c.send(f"👢 **Kick**: {member.mention} by {x.user.mention} for {x.reason}.")
				elif x.action.name == "ban":
					return await c.send(f"☠ **Ban**: {member.mention} by {x.user.mention} for {x.reason}.")
			else:
				await c.send(f"⬅ {member.mention} left the server.")
				
	@commands.has_permissions(manage_guild=True)
	@commands.command()
	@commands.guild_only()
	async def leaves(self,ctx,*,toggle=None):
		""" Show or hide a message when a member is kicked/banned or leaves """
		
		await self.check_mod_config(ctx.channel.guild)
		# Check mod is set.
		mc = await self.get_mod_channel(ctx,id)
		
		if not mc:
			return
		
		# Give current info
		if toggle is None:
			try: 
				l = self.bot.config[f"{ctx.guild.id}"]["mod"]["leaves"]
			except KeyError:
				self.bot.config[f"{ctx.guild.id}"]["mod"]["leaves"] = False
				await self._save()
			
			l = self.bot.config[f"{ctx.guild.id}"]["mod"]["leaves"]
			if l:
				return await ctx.send(f"Messages are currently output to {mc.mention}"\
					f"when a member leaves this server. Toggle with `{ctx.prefix}leaves off`")
			else:
				return await ctx.send("Messages are not being output when a member leaves this server."\
					f"Toggle with `{ctx.prefix}leaves on`")

		# Or update guild preference			
		elif toggle.lower() == "on":
			self.bot.config[f"{ctx.guild.id}"]["mod"]["leaves"] = True
			await self._save()
			return await ctx.send(f"A message will be output to {mc.mention} when a member leaves this server.")
			
		elif toggle.lower() == "off":
			self.bot.config[f"{ctx.guild.id}"]["mod"]["leaves"] = False
			await self._save()
			return await ctx.send(f"Messages will no longer be output to {mc.mention} when members leave this server.")
	
	### Emoji update information
	@commands.Cog.listener()
	async def on_guild_emojis_update(self,guild,before,after):
		
		# Check if in mod.
		try: 
			d = self.bot.config[id]["mod"]
		except KeyError:
			d = self.bot.config[id]["mod"] = {}
			await self._save()
	
		# Check config to see if outputting.
		try:
			l = self.bot.config[f"{member.guild.id}"]["mod"]["emojis"]
		except KeyError:
			l = self.bot.config[f"{member.guild.id}"]["mod"]["emojis"] = False
			await self._save()
			
		try:
			c = self.bot.config[f"{member.guild.id}"]["mod"]["channel"]
			c = self.bot.get_channel(c)
		except KeyError:
			c = self.bot.config[f"{member.guild.id}"]["mod"]["channel"] = None
			await self._save()
		
		if not l or c is None:
			return		
		
		# Find if it was addition or removal.
		newemoji = [i for i in after if i not in before]
		if not newemoji:
			removedemoji = [i for i in before if i not in after][0]
			return await c.send(f"The '{removedemoji.name}' emoji was removed")
		else:
			await c.send(f"The {newemoji[0]} emoji was created.")
	
	@commands.has_permissions(manage_guild=True)
	@commands.command()
	@commands.guild_only()
	async def emojis(self,ctx,*,toggle=None):
		""" Show or hide messages when guild emojis are updated. Toggle with mod emojis on/off """
		# Check mod is set.
		mc = await self.get_mod_channel(ctx,id)
		
		if not mc:
			return
			
		# Give current info
		if toggle is None:
			try: 
				l = self.bot.config[f"{ctx.guild.id}"]["mod"]["emojis"]
			except KeyError:
				self.bot.config[f"{ctx.guild.id}"]["mod"]["emojis"] = False
				await self._save()
			
			l = self.bot.config[f"{ctx.guild.id}"]["mod"]["emojis"]
			if l:
				return await ctx.send(f"Messages are currently output to {mc.mention}"\
					f"when an emojis are updated on this server. Toggle with ``emojis off`")
			else:
				return await ctx.send("Messages are not being output when an emojis are updated on this server."\
					f"Toggle with `{ctx.prefix}emojis on`")
					
		# Or update guild preference		
		elif toggle.lower() == "on":
			self.bot.config[f"{ctx.guild.id}"]["mod"]["emojis"] = True
			await self._save()
			return await ctx.send(f"A message will be output to {mc.mention} when emojis are updated on this server.")
			
		elif toggle.lower() == "off":
			self.bot.config[f"{ctx.guild.id}"]["mod"]["emojis"] = False
			await self._save()
			return await ctx.send(f"Messages will no longer be output to {mc.mention} when emojis are updated on this server.")
		
def setup(bot):
	bot.add_cog(Mod(bot))