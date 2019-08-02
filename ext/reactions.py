import discord
from discord.ext import commands
import random
import datetime
import json

reactdict = {
			"digi":[":digi:332195917157629953"],
			"gamez":["✝"],
			"mackem":["💩"],
			"mbemba":[":mbemba:332196308825931777"],
			"ki ":["🔑","👃","👀"],
			"nobby":["🎺"],
			"shola":["🚴🏿","🍏"],
			"solano":["🎺"],
			"sunderland":["💩"],
			"yedlin":["🇺🇸"],
			}

# Enable/disable			  
class GlobalChecks(commands.Cog):
	def __init__(self, bot):	
		self.bot = bot
		self.bot.add_check(self.disabledcmds)
		self.bot.add_check(self.muted)

	def muted(self,ctx):
		return not str(ctx.author.id) in self.bot.ignored

	def disabledcmds(self,ctx):
		if ctx.guild is None:
			return True
		try:
			return not str(ctx.command) in self.bot.config[f"{ctx.guild.id}"]["disabled"]
		except:
			self.bot.config[f"{ctx.guild.id}"] = {"disabled":[]}
			return not str(ctx.command) in self.bot.config[f"{ctx.guild.id}"]["disabled"]
								
	
class Reactions(commands.Cog):
	def __init__(self, bot):
		self.bot = bot
		with open('girlsnames.txt',"r") as f:
			self.bot.girls = f.read().splitlines()

	async def _save(self):
		with await self.bot.configlock:
			with open('config.json',"w",encoding='utf-8') as f:
				json.dump(self.bot.config,f,ensure_ascii=True,
				sort_keys=True,indent=4, separators=(',',':'))
	
	@commands.Cog.listener()
	async def on_guild_remove(self,guild):
		self.bot.config.pop(f"{guild.id}")
		await self._save()

	@commands.Cog.listener()
	async def on_member_update(self,before,after):
		# Goala 178631560650686465
		# Keegs 272722118192529409
		if not before.id == 272722118192529409:
			return
		if before.nick != after.nick:	
			async for i in before.guild.audit_logs(limit=1):
				if i.user.id == 272722118192529409:
					await after.edit(nick=random.choice(self.bot.girls).title())	
	
	@commands.Cog.listener()			
	async def on_member_join(self,member):
		if not member.id == 272722118192529409:
			return
		await member.edit(nick=random.choice(self.bot.girls).title())
	
	@commands.Cog.listener()
	async def on_message_delete(self,message):
		if message.guild is None:
			return
		if not message.guild.id == 332159889587699712:
			return
		if message.author.bot:
			return
		for i in self.bot.config[f"{message.guild.id}"]["prefix"]:
			if message.content.startswith(i):
				return
				
		# Filter out deleted numbers - Toonbot.
		try:
			int(message.content)
		except ValueError:
			pass
		else:
			return
		delchan = self.bot.get_channel(id=335816981423063050)
		e = discord.Embed(title="Deleted Message")
		e.description = f"'{message.content}'"
		e.set_author(name=message.author.name)
		e.add_field(name="User ID",value=message.author.id)
		e.add_field(name="Channel",value=message.channel.mention)
		e.set_thumbnail(url=message.author.avatar_url)
		e.timestamp = datetime.datetime.now()
		e.set_footer(text=f"Created: {message.created_at}")
		e.color = message.author.color
		if message.attachments:
			att = message.attachments[0]
			if hasattr(att,"height"):
				e.add_field(name=f"Attachment info {att.filename} ({att.size} bytes)",value=f"{att.height}x{att.width}")
				e.set_image(url=att.proxy_url)
		await delchan.send(embed=e)
	
	@commands.Cog.listener()
	async def on_message(self,m):
		c = m.content.lower()
		# ignore bot messages
		if m.author.bot:
			if c.startswith("NUFC: "):
				lf = f"New item in modqueue: <http://www.reddit.com/{m.content}>"
				await m.channel.send(lf)
				await m.delete()
			return
		if m.guild and m.guild.id == 332159889587699712:
			if len(m.mentions) >= 5:
				await m.author.kick(reason="Mention spam")
				await m.channel.send(f"👢 {m.author.mention} was autokicked.")
			for string,reactions in reactdict.items():
				if string in c:
					for emoji in reactions:
						await m.add_reaction(emoji)
			autokicks = ["make me a mod","make me mod","give me mod"]
			for i in autokicks:
				if i in c:
					try:
						await m.author.kick(reason="Asked to be made a mod.")
					except:
						return await m.channel.send(f"Done. {m.author.mention} is now a moderator.")
					await m.channel.send(f"{m.author} was auto-kicked.")
			if "https://www.reddit.com/r/" in c and "/comments/" in c:
				if not "nufc" in c:
					rm = ("*Reminder: Please do not vote on submissions or "
						  "comments in other subreddits.*")
					await m.channel.send(rm)			
		# if user ignored.
		if str(m.author.id) in self.bot.ignored:
			return
		# Emoji reactions
		if "toon toon" in c:
			await m.channel.send("**Black and white army.**")
			
		
def setup(bot):
	bot.add_cog(Reactions(bot))
	bot.add_cog(GlobalChecks(bot))
	# bot.add_cog(RoleReactor(bot))