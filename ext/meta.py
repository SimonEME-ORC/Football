import discord,os,datetime,re,asyncio,copy,unicodedata,inspect,psutil,sys
from discord.ext.commands.cooldowns import BucketType
from collections import OrderedDict, deque, Counter
from discord.ext import commands
import json

class Meta(commands.Cog):
	"""Commands for utilities related to the Bot itself."""
	def __init__(self, bot):
		self.bot = bot
	
	@commands.command(aliases=["invite"])
	async def inviteme(self,ctx):
		await ctx.send("Use this link to invite me, without moderation accesss. <https://discordapp.com/oauth2/authorize?client_id=250051254783311873&permissions=67488768&scope=bot>")
	
	@commands.command()
	async def hello(self,ctx):
		"""Say hello."""
		await ctx.send(f"Hi {ctx.author.mention}, I'm {ctx.me.display_name}, "
		f"Painezor#8489 coded me to do some football stuff. If you think you've spotted a bug, ping him\n"
		f"Type {ctx.prefix}help to see a list of my commands."
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

	def get_bot_uptime(self):
		delta = datetime.datetime.utcnow() - self.bot.initialised_at
		h, remainder = divmod(int(delta.total_seconds()), 3600)
		m, s = divmod(remainder, 60)
		d, h = divmod(h, 24)

		fmt = f'{h}h {m}m {s}s'
		if d:
			fmt = f'{d}d {fmt}'

		return fmt
		
def setup(bot):
	bot.add_cog(Meta(bot))