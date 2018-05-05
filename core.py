from discord.ext import commands
from collections import Counter
from datetime import datetime
import aiohttp
import discord
import asyncio
import logging
import praw
import json

# Startup Modules
load = [	
	'ext.admin','ext.fixtures','ext.fun','ext.google','ext.images','ext.info',
	'ext.meta','ext.mod','ext.mtb','ext.nufc','ext.quotes',
	'ext.reactions','ext.scores', 'ext.sidebar','ext.timers','ext.twitter',
	'ext.transfers','ext.tv'
	# 'ext.wiki'
]

# Enable Logging
log = logging.getLogger('discord')
log.setLevel(logging.INFO)
handler = logging.FileHandler(filename='rewrite.log',encoding='utf-8', mode='w')
log.addHandler(handler)

async def get_prefix(bot, message):
	if message.guild is None:
		return ['+','-','.','$','!','?','.tb']
	if not f"{message.guild.id}" in bot.config:
		bot.config[f"{message.guild.id}"] = {"prefix":[".tb",'-','+','$','!','?']}
	try:
		pref = bot.config[f"{message.guild.id}"]["prefix"]
	except KeyError:
		pref = []
	return commands.when_mentioned_or(*pref)(bot, message)

description = "Football lookup bot by Painezor#8489"
bot = commands.Bot(command_prefix=get_prefix, description=description,
				   pm_help=None)
				   
# On Client Ready
@bot.event
async def on_ready():
	print(f'{bot.user.name}: {datetime.now()}\n---------------------')
	if not hasattr(bot, 'uptime'):
		bot.uptime = datetime.utcnow()
	bot.reddit = praw.Reddit(**bot.credentials["Reddit"])
	bot.session = aiohttp.ClientSession(loop=bot.loop)
	for c in load:
		try:
			bot.load_extension(c)
		except Exception as e:
			print(f'Failed to load cog {c}\n{type(e).__name__}: {e}')
	await asyncio.sleep(5)
	await bot.change_presence(activity=discord.Game(name="Use -help"))

# Define command handler
@bot.event
async def on_command(ctx):
	bot.commands_used[ctx.command.name] += 1
	destination = None 
	if isinstance(ctx.channel,discord.abc.PrivateChannel):
		destination = 'Private Message'
	else:
		destination = f'#{ctx.channel.name} ({ctx.guild.name})'
	log.info(f'{ctx.message.created_at}: {ctx.author.name} in'
			  f'{destination}: {ctx.message.content}')

# Load bot and logging.
if __name__ == '__main__':
	with open('credentials.json') as f:
		bot.credentials = json.load(f)
	bot.clientid = bot.credentials['bot']['client_id']
	bot.commands_used = Counter()
	with open('ignored.json') as f:
		bot.ignored = json.load(f)
	with open('config.json') as f:
		bot.config = json.load(f)
	with open('tv.json') as f:
		bot.tv = json.load(f)
	bot.configlock = asyncio.Lock()
	bot.run(bot.credentials['bot']['token'])
	
	# Cleanup.
	bot.twitask.cancel()
	bot.scorechecker.cancel()
	self.bot.run_until_complete(bot.session.close()) #Aiohttp ClientSession
	handlers = log.handlers[:]
	for hdlr in handlers:
		hdlr.close()
		log.removeHandler(hdlr)