from discord.ext import commands
from collections import Counter
import discord
import asyncio
import copy

## TODO: Merge Info/hackyinfo.
class Info(commands.Cog):
	""" Get information about users or servers. """
	def __init__(self, bot):
		self.bot = bot
		self.bot.commands_used = Counter()
	
	@commands.command(aliases=['botstats',"uptime"])
	async def about(self,ctx):
		"""Tells you information about the bot itself."""
		e = discord.Embed(colour = 0x111111,timestamp = self.bot.user.created_at)
		e.set_footer(text = "Toonbot was created on")
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
		e.add_field(name='Commands this run', value=sum(self.bot.commands_used.values()))
		e.add_field(name='Memory Usage', value='{:.2f} MiB'.format(memory_usage))
		e.add_field(name='Python Version',value=sys.version)

		m = await ctx.send(embed=e)
		await m.edit(content=" ",embed=e) # to grab ping.
		time = f"{str((m.edited_at - m.created_at).microseconds)[:3]}ms"
		e.add_field(name="Ping",value=time)
		await m.edit(content=None,embed=e)

	@commands.command(aliases=["lastmsg","lastonline","lastseen"])
	async def seen(self,ctx,t : discord.Member = None):
		""" Find the last message from a user in this channel """
		if t == None:
			return await ctx.send("No user provided")
		
		m = await ctx.send("Searching...")
		with ctx.typing():
			if ctx.author == t:
				return await ctx.send("Last seen right now, being an idiot.")
				
			async for msg in ctx.channel.history(limit=50000):
				if msg.author.id == t.id:
					if t.id == 178631560650686465:
						c = (f"{t.mention} last seen being a spacker in "
							f" {ctx.channel.mention} at {msg.created_at} "
							f"saying '{msg.content}'")
						await m.edit(content=c)
					else:
						c = (f"{t.mention} last seen in {ctx.channel.mention} "
							 f"at {msg.created_at} saying '{msg.content}'")
						await m.edit(content=c)
					return
			await m.edit(content="Couldn't find a recent message from that user.")		
		
	@commands.command()
	async def hackyinfo(self,ctx,*,id):
		""" Get info about a user by their ID #"""
		user = await self.bot.fetch_user(id)
		e = discord.Embed()
		e.color = 0x7289DA
		e.set_author(name=str(user))
		e.add_field(name='ID', value=user.id,inline=True)
		e.add_field(name='Created at', value=user.created_at,inline=True)
		e.add_field(name="Is bot?",value=user.bot)
		e.set_thumbnail(url=user.avatar_url)
		await ctx.send(embed=e)
	
	@commands.group(invoke_without_command=True)
	@commands.guild_only()
	async def info(self,ctx,*,member: discord.Member = None):
		"""Shows info about a member.
		This cannot be used in private messages. If you don't specify
		a member then the info returned will be yours.
		"""
		if member is None:
			member = ctx.author

		e = discord.Embed()
		roles = [role.name.replace('@', '@\u200b') for role in member.roles]
		shared = sum(1 for m in self.bot.get_all_members() if m.id == member.id)
		voice = member.voice
		if voice is not None:
			voice = voice.channel
			other_people = len(voice.members) - 1
			voice_fmt = f'{voice.name} with {other_people} others' if other_people else f'{voice.name} alone'
			voice = voice_fmt
		else:
			voice = 'Not connected.'

		e.set_author(name=str(member), icon_url=member.avatar_url or member.default_avatar_url)
		e.set_footer(text='Member since').timestamp = member.joined_at
		e.add_field(name="Status",value=str(member.status).title(),inline=True)
		e.add_field(name='ID', value=member.id,inline=True)
		e.add_field(name='Servers', value='%s shared' % shared,inline=True)
		e.add_field(name='Voice', value=voice,inline=True)
		e.add_field(name="Is bot?",value=member.bot,inline=True)
		if member.activity is not None:
			e.add_field(name='Game',value=member.activity,inline=True)
		e.add_field(name='Created at', value=member.created_at,inline=True)
		e.add_field(name='Roles', value=', '.join(roles),inline=True)
		e.colour = member.colour
		if member.avatar:
			e.set_thumbnail(url=member.avatar_url)
		try:
			await ctx.send(embed=e)
		except discord.Forbidden:
			outstr = "```"
			outstr = f"Member: {str(member)}\n"
			outstr += f"Avatar URL: {member.avatar_url}\n"
			outstr += f"Joined: {member.joined_at}\n"
			outstr += f"Created: {member.created_at}"
			outstr += f"User ID: {member.id}\n"
			outstr += f"Mutual Servers with bot: {shared}\n"
			if member.bot:
				outstr += "User is a bot.\n"
			if member.activity is not None:
				outstr += f"Activity: {member.activity}\n"
			if voice:
				outstr == f"Voice Status: {voice}\n"
			outstr += f"User Roles: {', '.join(roles)}"
			outstr += "```"
			await ctx.send(outstr)
	
	@info.command(name='guild', aliases=["server"])
	@commands.guild_only()
	async def server_info(self, ctx):
		""" Shows information about the server """
		guild = ctx.guild
		roles = [role.name.replace('@', '@\u200b') for role in guild.roles]

		secret_member = copy.copy(guild.me)
		secret_member.roles = [guild.default_role]

		# figure out what channels are 'secret'
		secret_channels = 0
		secret_voice = 0
		text_channels = 0
		for channel in guild.channels:
			perms = channel.permissions_for(secret_member)
			is_text = isinstance(channel, discord.TextChannel)
			text_channels += is_text
			if is_text and not perms.read_messages:
				secret_channels += 1
			elif not is_text and (not perms.connect or not perms.speak):
				secret_voice += 1

		regular_channels = len(guild.channels) - secret_channels
		voice_channels = len(guild.channels) - text_channels
		mstatus = Counter(str(m.status) for m in guild.members)

		e = discord.Embed()
		e.add_field(name="Server Name",value=guild.name)
		e.add_field(name='ID', value=guild.id)
		e.add_field(name='Owner', value=guild.owner)
		e.add_field(name="Owner ID",value=guild.owner.id)
		emojis = ""
		for emoji in guild.emojis:
			if len(emojis) + len(str(emoji)) < 1024:
				emojis += str(emoji)
		if emojis:
			e.add_field(name="Custom Emojis",value=emojis)
		e.add_field(name="Region",value=str(guild.region).title())
		e.add_field(name="Verification Level",value=str(guild.verification_level).title())
		if guild.icon:
			e.set_thumbnail(url=guild.icon_url)

		fmt = 'Text %s (%s secret)\nVoice %s (%s locked)'
		e.add_field(name='Channels', value=fmt % (text_channels, secret_channels, voice_channels, secret_voice))

		members = f'Total {guild.member_count} ({mstatus["online"]})\nDND:{mstatus["dnd"]}\nIdle {mstatus["idle"]}'
		e.add_field(name='Members', value=members)
		e.add_field(name='Roles', value=', '.join(roles) if len(roles) < 10 else '%s roles' % len(roles))
		e.set_footer(text='Created').timestamp = guild.created_at
		await ctx.send(embed=e)
		
	@commands.command()
	async def avatar(self,ctx,user:discord.User = None):
		""" Shows a member's avatar """
		if user == None:
			user = ctx.author
		await ctx.send(user.avatar_url_as(static_format="png"))
		
def setup(bot):
	bot.add_cog(Info(bot))