import discord,os,datetime,re,asyncio,copy,unicodedata,inspect,psutil,sys
from discord.ext.commands.cooldowns import BucketType
from collections import OrderedDict, deque, Counter
from discord.ext import commands
import json

class Meta(commands.Cog):
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
	
	@commands.command()
	@commands.guild_only()
	async def prefix(self,ctx,*,prefix=""):
		""" Lists the bot prefixes for this server.
			Use `@toonbot prefix <prefix>` to toggle <prefix> as a command prefix for this server.."""
		
		try:
			prefixes = self.bot.config[f"{ctx.guild.id}"]["prefix"]
		except KeyError:
			self.bot.config[f"{ctx.guild.id}"].update({"prefix":['$','!','`','.','-','?']})
			await self._save()
			prefixes = ['$','!','`','.','-','?']
		
		if prefix:
			# Server Admin only.
			if  ctx.channel.permissions_for(ctx.author).manage_guild:
				# Get Current prefix list.					
				if prefix not in prefixes:
					prefixes.append(prefix)
					await ctx.send(f'Adding {prefix} to {ctx.guild.name} prefix list.')
				else:
					prefixes.remove(prefix)
					await ctx.send(f'Removing {prefix} from {ctx.guild.name} prefix list.')
				
				self.bot.config[f"{ctx.guild.id}"].update({"prefix":prefixes})
				await self._save()
				
		if not prefixes:
			# How to add prefixes without one.
			return await ctx.send(f"No prefixes found for this server, use {ctx.me.mention} prefix <your prefix> to add one.")
		else:
			await ctx.send(f"Current Command prefixes for this server: ```{' '.join(prefixes)}```")
	
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
	@commands.is_owner()
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
		f"Type {ctx.prefix}help to be DM'd a list of my commands."
		)

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
		
	@commands.command(aliases=['nick'])
	@commands.has_permissions(manage_nicknames=True)
	async def name(self,ctx,*,newname: str):
		""" Rename the bot """
		await ctx.me.edit(nick=newname)
		
	async def on_socket_response(self, msg):
		self.bot.socket_stats[msg.get('t')] += 1		

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