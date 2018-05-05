import discord,os,datetime,re,asyncio,copy,unicodedata,inspect,psutil,sys
from discord.ext.commands.cooldowns import BucketType
from collections import OrderedDict, deque, Counter
from discord.ext import commands
import json

class Meta:
	"""Commands for utilities related to the Bot itself."""
	def __init__(self, bot):
		self.bot = bot
	
	async def _save(self):
		with await self.bot.configlock:
			with open('config.json',"w",encoding='utf-8') as f:
				json.dump(self.bot.config,f,ensure_ascii=True,
				sort_keys=True,indent=4, separators=(',',':'))
	
	@commands.command(aliases=['botstats',"uptime"])
	async def about(self,ctx):
		"""Tells you information about the bot itself."""
		e = discord.Embed(colour = 0x111111,timestamp = self.bot.user.created_at)

		owner = self.bot.get_user((await self.bot.application_info()).owner.id)
		e.set_author(name=f"Owner: {owner}", icon_url=owner.avatar_url)
		
		# statistics
		total_members = sum(len(s.members) for s in self.bot.guilds)
		total_online  = sum(1 for m in self.bot.get_all_members() if m.status != discord.Status.offline)
		voice = sum(len(g.text_channels) for g in self.bot.guilds)
		text = sum(len(g.voice_channels) for g in self.bot.guilds)
		memory_usage = psutil.Process().memory_full_info().uss / 1024**2
		
		members = f"{total_members} Members\n{total_online} Online\n{len(self.bot.users)} unique"
		e.add_field(name='Members', value=members)
		e.add_field(name='Channels', value=f'{text + voice} total\n{text} text\n{voice} voice')
		e.add_field(name='Servers', value=len(self.bot.guilds))
		e.add_field(name='Uptime', value=self.get_bot_uptime(),inline=False)
		e.add_field(name='Commands Run', value=sum(self.bot.commands_used.values()))
		e.add_field(name='Memory Usage', value='{:.2f} MiB'.format(memory_usage))
		e.add_field(name='Python Version',value=sys.version)
		e.set_footer(text='Made with discord.py', icon_url='http://i.imgur.com/5BFecvA.png')

		m = await ctx.send(embed=e)
		await m.edit(content=" ",embed=e)
		time = f"{str((m.edited_at - m.created_at).microseconds)[:3]}ms"
		e.add_field(name="Ping",value=time)
		await m.edit(content=None,embed=e)
	
	@commands.command(aliases=["invite"])
	async def inviteme(self,ctx):
		await ctx.send("Use this link to invite me, without moderation accesss. <https://discordapp.com/oauth2/authorize?client_id=250051254783311873&permissions=67488768&scope=bot>")
	
	@commands.group()
	@commands.guild_only()
	async def prefix(self,ctx):
		""" Lists the bot prefixes for this server """
		try:
			prefixes = self.bot.config[f"{ctx.guild.id}"]["prefix"]
		except KeyError:
			self.bot.config[f"{ctx.guild.id}"]["prefix"] = ['$','!','`','.','-','?']
			await self._save()
			prefixes = self.bot.config[f"{ctx.guild.id}"]["prefix"]
		await ctx.send(f"Command prefixes for this server: ```{' '.join(prefixes)}```")
		
	@prefix.command(name="add")
	@commands.has_permissions(manage_guild=True)
	async def _add(self,ctx,*,prefix):
		""" Add a bot prefix for the server """
		prefixes = self.bot.config[f"{ctx.guild.id}"]["prefix"]
		if not prefixes:
			self.bot.config[f"{ctx.guild.id}"]["prefix"] = ['$','!','`','.','-','?',prefix]
			await self._save()
			return await ctx.send(f"{prefix} added to prefix list.")
		if prefix in prefixes:
			return await ctx.send("Already in prefix list")
		else:
			self.bot.config[f"{ctx.guild.id}"]["prefix"].append(prefix)
			await self._save()
			return await ctx.send(f"{prefix} added to prefix list.")
			
	@prefix.command(name="remove",aliases=["del"])
	@commands.has_permissions(manage_guild=True)
	async def _remove(self,ctx,*,prefix):
		""" Add a bot prefix for the server """
		prefixes = self.bot.config[f"{ctx.guild.id}"]["prefix"]
		if not prefixes:
			return await ctx.send(f"Unable to find existing prefix list.")
		if prefix in prefixes:
			self.bot.config[f"{ctx.guild.id}"]["prefix"].remove(prefix)
			await self._save()
			return await ctx.send(f"{prefix} removed from prefix list.")
		else:
			return await ctx.send(f"{prefix} was not in the existing prefix list.")
	
	
	@prefix.command()
	@commands.has_permissions(manage_guild=True)
	async def default(self,ctx):
		""" Resets the guild's prefixes to default ['$','!','`','.','-','?']"""
		self.bot.config[f"{ctx.guild.id}"]["prefix"] = ['$','!','`','.','-','?']
		await self._save()
		await ctx.send("Server prefixes reset to ['$','!','`','.','-','?']")
	
	@commands.command()
	@commands.has_permissions(manage_guild=True)
	async def disable(self, ctx, *, command: str):
		"""Disables a command for this server."""
		command = command.lower()
		if command in ('enable', 'disable'):
			return await ctx.send('Cannot disable that command.')
		if command not in [i.name for i in list(self.bot.commands)]:
			return await ctx.send('Unrecognised command name.')
		if "disabled" in self.bot.config[f"{ctx.guild.id}"]:
			self.bot.config[f"{ctx.guild.id}"]["disabled"].append(command)
		else:
			self.bot.config[f"{ctx.guild.id}"]["disabled"] = [command]
		await self._save()
		await ctx.send(f'The "{command}" command has been disabled for this server.')

	@commands.command()
	@commands.has_permissions(manage_guild=True)
	async def disabled(self,ctx):
		disabledcmds = self.bot.config[f"{ctx.guild.id}"]["disabled"]
		if disabledcmds:
			await ctx.send(f"Disabled commands for this server: ```{disabledcmds}```")
		else:
			await ctx.send("No commands are currently disabled on this server")
			
	@commands.command()
	@commands.has_permissions(manage_guild=True)
	async def enable(self, ctx, *, command: str):
		"""Enables a command for this server."""
		command = command.lower()
		if command not in [i.name for i in list(self.bot.commands)]:
			return await ctx.send('Unrecognised command name.')
		try:
			self.bot.config[f"{ctx.guild.id}"]["disabled"].remove(command)
		except ValueError:
			await ctx.send('The command does not exist or is not disabled.')
		else:
			await ctx.send(f'The "{command}" command has been enabled for this server.')
			await self._save()
	
	@commands.command()
	@commands.has_permissions(manage_messages=True)
	async def clean(self,ctx,number : int = 100):
		""" Deletes my messages from last x in channel"""
		preflist = await self.bot.command_prefix(self.bot,ctx.message)
		def is_me(m):
			return m.author.id == self.bot.user.id or m.content[0] in preflist
		try:
			mc = self.bot.config[str(ctx.guild.id)]['mod']['channel']
			mc = self.bot.get_channel(mc)
		except KeyError:
			mc = "N/A"
		if ctx.channel == mc:
			await ctx.send("🚫 'Clean' has been disabled for the moderator channel.",delete_after=10)
		else:
			deleted = await ctx.channel.purge(limit=number, check=is_me)
			s = "s" if len(deleted) > 1 else ""
			await ctx.send(f'♻️ {ctx.author.mention}: Deleted {len(deleted)} bot and command messages{s}',delete_after=10)
	
	@commands.command()
	async def source(self, ctx, *, command: str = None):
		"""Displays my full source code or for a specific command.
		To display the source code of a subcommand you can separate it by
		periods, e.g. tag.create for the create subcommand of the tag command
		or by spaces.
		"""
		source_url = 'https://github.com/Painezor/Toonbot'
		if command is None:
			return await ctx.send(source_url)

		obj = self.bot.get_command(command.replace('.', ' '))
		if obj is None:
			return await ctx.send('Could not find command.')

		# since we found the command we're looking for, presumably anyway, let's
		# try to access the code itself
		src = obj.callback.__code__
		lines, firstlineno = inspect.getsourcelines(src)
		if not obj.callback.__module__.startswith('discord'):
			# not a built-in command
			location = os.path.relpath(src.co_filename).replace('\\', '/')
		else:
			location = obj.callback.__module__.replace('.', '/') + '.py'
			source_url = 'https://github.com/Painezor/Toonbot'

		final_url = f'<{source_url}/blob/master/{location}#L{firstlineno}-L{firstlineno + len(lines) - 1}>'
		await ctx.send(final_url)
	
	@commands.command()
	@commands.is_owner()
	async def version(self,ctx):
		""" Get Python version """
		await ctx.send(f"Running on python versino {sys.version}")
	
	@commands.command()
	async def hello(self,ctx):
		"""Say hello."""
		await ctx.send(f"Hi {ctx.author.mention}, I'm {ctx.me.display_name}, "
		f"Painezor#8489 coded me to do some football stuff. If you think you've spotted a bug, ping him\n"
		f"Type {self.bot.config[str(ctx.guild.id)]['prefix'][0]}help to be DM'd a list of my commands."
		)

	async def say_permissions(self, ctx, member, channel):
		permissions = channel.permissions_for(member)
		await formats.entry_to_code(ctx, permissions)

	@commands.command(aliases=['setavatar'])
	@commands.is_owner()
	async def picture(self,ctx,newpic : str):
		""" Change the bot's avatar """
		async with self.bot.session.get(newpic) as resp:
			if resp.status != 200:
				await ctx.send(f"HTTP Error: Status Code {resp.status}")
				return None
			profileimg = await resp.read()
			await self.bot.user.edit(avatar=profileimg)
		
	@commands.command()
	@commands.has_permissions(manage_roles=True)
	@commands.bot_has_permissions(manage_roles=True)
	async def permissions(self, ctx, *, member : discord.Member = None):
		"""Shows a member's permissions."""
		if member is None:
			member = ctx.author
		permissions = ctx.channel.permissions_for(member)
		permissions = "\n".join([f"{i[0]} : {i[1]}" for i in permissions])
		await ctx.send(f"```py\n{permissions}```")
		
		
	@commands.command()
	@commands.has_permissions(manage_roles=True)
	@commands.bot_has_permissions(manage_roles=True)
	async def botpermissions(self, ctx):
		"""Shows the bot's permissions.
		This is a good way of checking if the bot has the permissions needed
		to execute the commands it wants to execute.
		To execute this command you must have Manage Roles permissions or
		have the Bot Admin role. You cannot use this in private messages.
		"""
		channel = ctx.channel
		member = ctx.me
		await self.say_permissions(ctx, member, channel)
		
	@commands.command(aliases=['nick'])
	@commands.has_permissions(manage_nicknames=True)
	async def name(self,ctx,*,newname: str):
		""" Rename the bot """
		await ctx.me.edit(nick=newname)
		
	async def on_socket_response(self, msg):
		self.bot.socket_stats[msg.get('t')] += 1		
		
	@commands.command()
	@commands.is_owner()
	async def playing(self,ctx,*,game):
		""" Change status to "playing {game}" """
		await self.bot.change_presence(game=discord.Game(name=game,type=0))
		await self.ctx.send(f"Set status to playing {game}")

	@commands.command()
	@commands.is_owner()
	async def streaming(self,ctx,*,game):
		""" Change status to "streaming {game}" """
		await self.bot.change_presence(game=discord.Game(name=game,type=1))
		await self.ctx.send(f"Set status to streaming {game}")
		
	@commands.command()
	@commands.is_owner()
	async def watching(self,ctx,*,game):
		""" Change status to "watching {game}" """
		await self.bot.change_presence(game=discord.Game(name=game,type=3))
		await self.ctx.send(f"Set status to watching {game}")
		
	@commands.command()
	@commands.is_owner()
	async def listening(self,ctx,*,game):
		""" Change status to "listening to {game}" """
		await self.bot.change_presence(game=discord.Game(name=game,type=2))
		await self.ctx.send(f"Set status to listening to {game}")

	def get_bot_uptime(self):
		delta = datetime.datetime.utcnow() - self.bot.uptime
		h, remainder = divmod(int(delta.total_seconds()), 3600)
		m, s = divmod(remainder, 60)
		d, h = divmod(h, 24)

		fmt = f'{h}h {m}m {s}s'
		if d:
			fmt = f'{d}d {fmt}'

		return fmt
		
def setup(bot):
	bot.commands_used = Counter()
	bot.socket_stats = Counter()
	bot.add_cog(Meta(bot))