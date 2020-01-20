from discord.ext import commands
import discord, asyncio
from os import system
import datetime
import aiohttp
import inspect
import json
import asyncpg
import sys
import traceback

# to expose to the eval command
import datetime
from collections import Counter

class Admin(commands.Cog):
	"""Code debug & 1oading of modules"""
	def __init__(self, bot):
		self.bot = bot
		self.bot.socket_stats = Counter()
		self.bot.loop.create_task(self.update_cache())
	
	async def update_cache(self):
		pass
	
	@commands.command()
	@commands.is_owner()
	async def setavatar(self,ctx,newpic : str):
		""" Change the bot's avatar """
		async with self.bot.session.get(newpic) as resp:
			if resp.status != 200:
				await ctx.send(f"HTTP Error: Status Code {resp.status}")
				return None
			profileimg = await resp.read()
			await self.bot.user.edit(avatar=profileimg)
	
	@commands.command()
	@commands.is_owner()
	async def clearconsole(self,ctx):
		""" Clear the command window. """
		system('cls')
		print(f'{self.bot.user}: {self.bot.initialised_at}\n-----------------------------------------')		
		await ctx.send("Console cleared.")
		print(f"Console cleared at: {datetime.datetime.utcnow()}")
	
	@commands.command(aliases=["releoad"])
	@commands.is_owner()
	async def reload(self,ctx, *, module : str):
		"""Reloads a module."""
		try:
			self.bot.reload_extension(module)
		except Exception as e:
			await ctx.send(f':no_entry_sign: {type(e).__name__}: {e}')
		else:
			await ctx.send(f':gear: Reloaded {module}')
	
	@commands.command()
	@commands.is_owner()
	async def load(self,ctx, *, module : str):
		"""Loads a module."""
		try:
			self.bot.load_extension(module)
		except Exception as e:
			await ctx.send(f':no_entry_sign: {type(e).__name__}: {e} \n{e.__traceback__	}')
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
		await self.bot.db.close()
		await self.bot.logout()
		await ctx.send(":gear: Restarting.")
		
	@commands.command(aliases=['streaming','watching','listening'])
	@commands.is_owner()
	async def playing(self,ctx,*,status):
		""" Change status to <cmd> {status} """
		values = {"playing":0,"streaming":1,"watching":2,"listening":3}
		
		act = discord.Activity(type=values[ctx.invoked_with],name=status)
		
		await self.bot.change_presence(activity=act)
		await ctx.send(f"Set status to {ctx.invoked_with} {status}")
		
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
		
def setup(bot):
    bot.add_cog(Admin(bot))