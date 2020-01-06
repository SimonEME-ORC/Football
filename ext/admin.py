from discord.ext import commands
import discord, asyncio
import aiohttp
import inspect
import json
import traceback
import sys

# to expose to the eval command
import datetime
from collections import Counter

class Admin(commands.Cog):
	"""Code debug & 1oading of modules"""
	def __init__(self, bot):
		self.bot = bot

	# Error Handler
	@commands.Cog.listener()
	async def on_command_error(self,ctx,error):
		# Let local error handling override.
		if hasattr(ctx.command,'on_error'):
			return
		
		# NoPM
		elif isinstance(error, commands.NoPrivateMessage):
			await ctx.send('Sorry, this command cannot be used in DMs.')
				
		elif isinstance(error,discord.Forbidden):
			try:
				print(f"Forbidden: {ctx.message.content} ({ctx.author})in {ctx.channel.name} on {ctx.guild.name}")
				await ctx.message.add_reaction('⛔')
			except discord.Forbidden:
				print(f"Forbidden: {ctx.message.content} ({ctx.author})in {ctx.channel.name} on {ctx.guild.name}")
		
		elif isinstance(error,commands.DisabledCommand):
			await ctx.message.add_reaction('🚫')
		
		elif isinstance(error,commands.BotMissingPermissions):
			# Fail Silently.
			pass
			
		elif isinstance(error, commands.CommandNotFound):
			pass				
		
		elif isinstance(error, commands.CommandInvokeError):
			print('In {0.command.qualified_name}:'.format(ctx), file=sys.stderr)
			traceback.print_tb(error.original.__traceback__)
			print('{0.__class__.__name__}: {0}'.format(error.original),
				  file=sys.stderr)	

		else:
			print(f"Error: ({ctx.author.id} on {ctx.guild.id})\n caused the following error\n{error}\nContext: {ctx.message.content}")
		
	@commands.command()
	@commands.is_owner()
	async def load(self,ctx, *, module : str):
		"""Loads a module."""
		try:
			self.bot.load_extension(module)
		except Exception as e:
			await ctx.send(f':no_entry_sign: {type(e).__name__}: {e}')
		else:
			await ctx.send(f':gear: Loaded {module}')

	@commands.command()
	@commands.is_owner()
	async def unload(self,ctx, *, module : str):
		"""Unloads a module."""
		try:
			self.bot.unload_extension(module)
		except Exception as e:
			await ctx.send(f':no_entry_sign: {type(e).__name__}: {e}')
		else:
			await ctx.send(f':gear: Unloaded {module}')

	@commands.command(name='reload',aliases=["releoad"])
	@commands.is_owner()
	async def _reload(self,ctx, *, module : str):
		"""Reloads a module."""
		try:
			self.bot.reload_extension(module)
		except Exception as e:
			await ctx.send(f':no_entry_sign: {type(e).__name__}: {e}')
		else:
			await ctx.send(f':gear: Reloaded {module}')
	
	@commands.command()
	@commands.is_owner()
	async def ignore(self,ctx,user : discord.Member,*,reason="Unspecified"):
		""" Ignore commands from a user (reason opptional)"""
		if f"{user.id}"  in self.bot.ignored:
			del self.bot.ignored[f"{user.id}"]
			await ctx.send(f"Stopped ignoring commands from {user.mention}.")
		else:
			self.bot.ignored.update({f"{user.id}":reason})
			await ctx.send(f"Ignoring commands from {user.mention}.")
		with open('ignored.json',"w",encoding='utf-8') as f:
			json.dump(self.bot.ignored,f,ensure_ascii=True,
			sort_keys=True,indent=4, separators=(',',':'))
	
	@commands.command()
	@commands.is_owner()
	async def debug(self, ctx, *, code : str):
		"""Evaluates code."""
		code = code.strip('` ')
		result = None

		env = {
			'bot': self.bot,
			'ctx': ctx,
			'message': ctx.message,
			'guild': ctx.message.guild,
			'channel': ctx.message.channel,
			'author': ctx.message.author
		}
		env.update(globals())
		try:
			result = eval(code, env)
			if inspect.isawaitable(result):
				result = await result
		except Exception as e:
			await ctx.send(f"```py\n{type(e).__name__}: {str(e)}```")
			return
		
		# Send to gist if too long.
		if len(str(result)) > 2000:
			p = {'scope':'gist'}
			tk = self.bot.credentials["Github"]["gisttoken"]
			h={'Authorization':f'token {tk}'}
			payload={"description":"Debug output.",
					 "public":True,
					 "files":{"Output":{"content":result}}}
			cs = self.bot.session
			async with cs.post("https://api.github.com/gists",params=p,
								headers=h,data=json.dumps(payload)) as resp:
					if resp.status != 201:
						await ctx.send(f"{resp.status} Failed uploading to gist.")
					else:
						await ctx.send("Output too long, uploaded to gist"
									   f"{resp.url}")
		else:
			await ctx.send(f"```py\n{result}```")
	
	@commands.command()
	@commands.is_owner()
	async def ownersay(self,ctx,channel:discord.TextChannel,*,msg):
		await channel.send(msg)
		await ctx.message.delete()
	
	@commands.command()
	@commands.is_owner()
	async def guilds(self,ctx):
		guilds = []
		for i in self.bot.guilds:
			guilds.append(f"{i.id}: {i.name}")
		guilds = "\n".join(guilds)
		await ctx.send(guilds)
		
	@commands.command()
	@commands.is_owner()
	async def commandstats(self,ctx):
		p = commands.Paginator()
		counter = self.bot.commands_used
		width = len(max(counter, key=len))
		total = sum(counter.values())

		fmt = '{0:<{width}}: {1}'
		p.add_line(fmt.format('Total', total, width=width))
		for key, count in counter.most_common():
			p.add_line(fmt.format(key, count, width=width))

		for page in p.pages:
			await ctx.send(page)

	@commands.command()
	@commands.is_owner()
	async def socketstats(self,ctx):
		delta = datetime.datetime.utcnow() - self.bot.uptime
		minutes = delta.total_seconds() / 60
		total = sum(self.bot.socket_stats.values())
		cpm = total / minutes

		fmt = '%s socket events observed (%.2f/minute):\n%s'
		await ctx.send(fmt % (total, cpm, self.bot.socket_stats))
		
	@commands.command(aliases=['logout','restart'])
	@commands.is_owner()
	async def kill(self,ctx):
		"""Restarts the bot"""
		await ctx.send(":gear: Restarting.")
		await self.bot.logout()
		
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
		
	@commands.command()
	@commands.is_owner()
	async def shared(self,ctx,*,id):
		""" Check ID for shared servers """
		matches = []
		id = int(id)
		for i in self.bot.guilds:
			if i.get_member(id) is not None:
				matches.append(f"{i.name} ({i.id})")
		
		e = discord.Embed()
		if not matches:
			e.color = 0x00ff00
			e.description = f"User id {id} not found on shared servers."
			return await ctx.send(embed=e)
		
		user = self.bot.get_user(id)
		e.title = f"Shared servers for {user} (ID: {id})"
		e.description = "\n".join(matches)
		await ctx.send(embed=e)
	
def setup(bot):
    bot.add_cog(Admin(bot))