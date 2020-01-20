from discord.ext import commands
import discord
from typing import Union,Optional

class Notifications(commands.Cog):
	""" Guild Moderation Commands """
	def __init__(self, bot):
		self.bot = bot
		self.bot.notif_cache = {}
		self.bot.loop.create_task(self.update_cache())

	### TODO: Code Bot notifications messages. (db columns exist)
	### TODO: On Channel Delete - Cascades!
	### TODO: Port on_message_delete
	### TODO: Custom Reactions.
	### TODO: on member name change

	async def update_cache(self):
		self.bot.notif_cache = {}
		connection = await self.bot.db.acquire()
		async with connection.transaction():
			records =  await connection.fetch("""
				SELECT * FROM guild_settings
			""")
		await self.bot.db.release(connection)
	
		for r in records:
			guild_id = r["guild_id"]
			self.bot.notif_cache.update({guild_id:{}})
			for k,v in r.items():
				if k == "guild_id":
					continue
				if v is not None:
					self.bot.notif_cache[guild_id].update({k:v})
	
	# Listeners
	@commands.Cog.listener()
	async def on_guild_join(self,guild):
		connection = await self.bot.db.acquire()
		async with connection.transaction():
			await connection.execute(""" 
				INSERT INTO guild_settings (guild_id) VALUES ($1)
				""",guild.id)
			await connection.execute(""" 
				INSERT INTO prefixes (guild_id,prefix) VALUES ($1,$2)
				""",guild.id)				
		await self.bot.db.release(connection)
	
	@commands.Cog.listener()
	async def on_guild_remove(self,guild):
		connection = await self.bot.db.acquire()
		async with connection.transaction():
			await connection.execute("""DELETE FROM guild_settings WHERE guild_id = $1""",guild.id)
		await self.bot.db.release(connection)

	@commands.Cog.listener()
	async def on_member_unban(self,guild,user):
		try:
			c = guild.get_channel(self.notif_cache[new_member.guild.id]["unbans_channel_id"])
		except (KeyError,AttributeError):
			return
		
		await c.send(f"🆗 {user} (ID: {user.id}) was unbanned.")

	### TODO : Colour-Code Member Creation Date
	@commands.Cog.listener()			
	async def on_member_join(self,new_member):
		
		if new_member.id == 272722118192529409:
			try:
				await new_member.edit(nick=random.choice(self.bot.girls).title())
			except:
				pass
		try:
			j = new_member.guild.get_channel(self.notif_cache[new_member.guild.id]["join_channel_id"])
		except (AttributeError,TypeError):
			return
			
		e = discord.Embed()
		e.color = 0x7289DA
		s = sum(1 for m in self.bot.get_all_members() if m.id == new_member.id)
		e.title = str(new_member)
		e.add_field(name="Status",value=str(mem.status).title(),inline=True)
		e.add_field(name='User ID', value=new_member.id,inline=True)
		e.add_field(name='Mutual Servers', value=f'{s} shared',inline=True)
		if new_member.bot:
			e.description = '**This is a bot account**'
		e.set_footer(text='Account Creation date: ')
		e.timestamp = new_member.created_at
		e.set_thumbnail(url=new_member.avatar_url)
		await j.send(embed=e)
	
	
	@commands.Cog.listener()
	async def on_member_remove(self,member):
		# Check if in mod.	
		try:
			async for x in member.guild.audit_logs(limit=1):
				if str(x.target) == str(member):
					if x.action == discord.AuditLogAction.kick:
						if x.reason is not None:
							if x.reason in ["roulete","Asked to be"]:
								return
						try:
							kc = member.guild.get_channel(self.notif_cache[member.guild.id]["kicks_channel_id"])
						except (AttributeError,TypeError):
							return		
						return await kc.send(f"👢 {member.mention} was kicked by {x.user} for {x.reason}.")
					elif x.action == discord.AuditLogAction.ban:
						try:
							bc = member.guild.get_channel(self.notif_cache[member.guild.id]["bans_channel_id"])
						except (AttributeError,TypeError):
							return
						return await bc.send(f"☠ {member.mention} was banned by {x.user} for {x.reason}.")
				else:
					try:
						lc = member.guild.get_channel(self.notif_cache[member.guild.id]["leaves_channel_id"])
						await lc.send(f"⬅ {member.mention} left the server.")
					except (AttributeError,TypeError):
						return
		except discord.Forbidden:
			try:
				lc = member.guild.get_channel(self.notif_cache[member.guild.id]["leaves_channel_id"])
				await lc.send(f"⬅ {member.mention} left the server.")
			except (AttributeError,TypeError):
				pass

	### Emoji update information
	@commands.Cog.listener()
	async def on_guild_emojis_update(self,guild,before,after):
		try:
			c = guild.get_channel(self.notif_cache[new_member.guild.id]["emoji_channel_id"])
		except (KeyError,AttributeError):
			return
		
		# Find if it was addition or removal.
		newemoji = [i for i in after if i not in before]
		if not newemoji:
			try:
				removedemoji = [i for i in before if i not in after][0]
				await c.send(f"The '{removedemoji.name}' emoji was removed")
			except IndexError:
				await c.send("An emoji was removed.")
		else:
			await c.send(f"The {newemoji[0]} emoji was created.")
		
	# Commands.
	@commands.group(invoke_without_command=True,usage = "mod")
	@commands.has_permissions(manage_guild=True)
	@commands.guild_only()
	async def mod(self,ctx):
		""" Shows the status of various mod tools."""
		# Get settings.
		e = discord.Embed(color=0x7289DA)
		e.description = ""
		e.title = f"Config settings for {ctx.guild.name}"
		
		for key,value in self.bot.notif_cache[ctx.guild.id].items():
			e.description += f"{key}: {value} \n"

		e.set_thumbnail(url=ctx.guild.icon_url)
		await ctx.send(embed=e)

	@commands.has_permissions(manage_guild=True)
	@commands.command(usage = "joins <(#channel) or (the word 'None') or leave blank to show current setting>")
	async def joins(self,ctx,channel: Optional[Union[discord.TextChannel,str]]):
		""" Send member information to a channel on join. """
		# Give current info
		if isinstance(channel,discord.TextChannel):
			ch = channel.id
		elif channel is None or channel.lower() != "none":
			try:
				ch = self.bot.get_channel(self.bot.notif_cache[ctx.guild.id]["joins_channel_id"])
				return await ctx.send(f'Join information is currently being output to {ch.mention}')
			except (KeyError):
				return await ctx.send(f'Join information is not currently being output.')
		else:
			ch = None
			
		connection = await self.bot.db.acquire()
		async with connection.transaction():
			await connection.execute(""" 
				UPDATE guild_settings SET joins_channel_id = $2 WHERE guild_id = $1
				""",ctx.guild.id,ch)
		await self.bot.db.release(connection)			
		await self.update_cache()
		
		if ch is None:
			await ctx.send('Join notifications will no longer be output.')
		else:
			await ctx.send(f'Information about users will  be sent to {channel.mention} when they join.')

	@commands.has_permissions(manage_guild=True)
	@commands.command(usage = "leaves <(#channel) or (the word 'None') or leave blank to show current setting>")
	async def leaves(self,ctx,channel: Optional[Union[discord.TextChannel,str]]):
		""" Set a channel to show information about new member joins """
		# Give current info
		if isinstance(channel,discord.TextChannel):
			ch = channel.id
		elif channel is None or channel.lower() != "none":
			try:
				ch = self.bot.get_channel(self.bot.notif_cache[ctx.guild.id]["leaves_channel_id"])
				return await ctx.send(f'Member leave information is currently being output to {ch.mention}')
			except (KeyError):
				return await ctx.send(f'Member leaves are not currently being output.')
		else:
			ch = None
			
		connection = await self.bot.db.acquire()
		async with connection.transaction():
			await connection.execute(""" 
				UPDATE guild_settings SET leaves_channel_id = $2 WHERE guild_id = $1
				""",ctx.guild.id,ch)
		await self.bot.db.release(connection)			
		await self.update_cache()
		
		if ch is None:
			await ctx.send('Leave notifications will no longer be output.')
		else:
			await ctx.send(f'Notifications will be sent to {ch.mention} when users leave.')
	
	@commands.has_permissions(manage_guild=True)
	@commands.command(usage = "mutes <(#channel) or (the word 'None') or leave blank to show current setting>")
	async def mutes(self,ctx,channel: Optional[Union[discord.TextChannel,str]]):
		""" Set a channel to show messages about user mutings """
		if isinstance(channel,discord.TextChannel):
			ch = channel.id
		elif channel is None or channel.lower() != "none":
			try:
				ch = self.bot.get_channel(self.bot.notif_cache[ctx.guild.id]["mutes_channel_id"])
				return await ctx.send(f'Mute notifications are currently being output to {ch.mention}')
			except (KeyError):
				return await ctx.send(f'Mute notifications are not currently being output.')
		else:
			ch = None
			
		connection = await self.bot.db.acquire()
		async with connection.transaction():
			await connection.execute(""" 
				UPDATE guild_settings SET mutes_channel_id = $2 WHERE guild_id = $1
				""",ctx.guild.id,ch)
		await self.bot.db.release(connection)
		await self.update_cache()
		if ch is None:
			await ctx.send('Mute notifications will no longer be output.')
		else:
			await ctx.send(f"Notifications will be output to {channel.mention} when a member is muted.")		
	
	@commands.has_permissions(manage_guild=True)
	@commands.command(usage = "emojis <(#channel) or (the word 'None') or leave blank to show current setting>")
	async def emojis(self,ctx,channel: Optional[Union[discord.TextChannel,str]]):
		""" Set a channel to show when emojis are changed. """
		if isinstance(channel,discord.TextChannel):
			ch = channel.id
		elif channel is None or channel.lower() != "none":
			try:
				ch = self.bot.get_channel(self.bot.notif_cache[ctx.guild.id]["emojis_channel_id"])
				return await ctx.send(f'Emoji change notifications are currently being output to {ch.mention}')
			except (KeyError):
				return await ctx.send(f'Emoji change notifications are not currently being output.')
		else:
			ch = None
			
		connection = await self.bot.db.acquire()
		async with connection.transaction():
			await connection.execute(""" 
				UPDATE guild_settings SET emojis_channel_id = $2 WHERE guild_id = $1
				""",ctx.guild.id,ch)
		await self.bot.db.release(connection)
		await self.update_cache()
		if ch is None:
			await ctx.send('Emoji change notifications will no longer be output.')
		else:
			await ctx.send(f"Notifications will be output to {channel.mention} when a emojis are changed.")
	
def setup(bot):
	bot.add_cog(Notifications(bot))