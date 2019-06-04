from discord.ext import commands
import discord
import asyncio
import datetime
import json
import re

class TimeParser:
	def __init__(self, argument):
		compiled = re.compile(r"(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?(?:(?P<seconds>\d+)s)?")
		self.original = argument
		try:
			self.seconds = int(argument)
		except ValueError as e:
			match = compiled.match(argument)
			if match is None or not match.group(0):
				raise commands.BadArgument('Failed to parse time.') from e
			self.seconds = 0
			hours = match.group('hours')
			if hours is not None:
				self.seconds += int(hours) * 3600
			minutes = match.group('minutes')
			if minutes is not None:
				self.seconds += int(minutes) * 60
			seconds = match.group('seconds')
			if seconds is not None:
				self.seconds += int(seconds)
		if self.seconds < 0:
			raise commands.BadArgument("That was in the past mate...")
			
class Timers(commands.Cog):
	def __init__(self,bot):
		self.bot = bot
	
	@commands.command()
	@commands.has_permissions(ban_members=True)
	async def temp_ban(self,ctx,member:discord.Member,*,time: TimeParser):
		""" Temporarily ban a member from the server """
		id = member.id
		try:
			await ctx.ban(member)
		except:
			return await ctx.send('Banning failed.')
		await ctx.send(f'Banned {member.mention} for {time}')
		unbanned = await bot.get_user(id)
		await asyncio.sleep(time.seconds)
		await self.bot.http.unban(who.id, ctx.guild.id)
		
		await ctx.send(f'{member.mention} was unbanned after {time}')
	
	@commands.command(aliases=['reminder','remind','remindme'])
	async def timer(self, ctx, time : TimeParser, *, message : commands.clean_content):
		"""Reminds you of something after a certain amount of time.
		The time can optionally be specified with units such as 'h'
		for hours, 'm' for minutes and 's' for seconds. If no unit
		is given then it is assumed to be seconds. You can also combine
		multiple units together, e.g. 2h4m10s.
		"""
		reminder = None
		completed = None
		remindat = datetime.datetime.now() + datetime.timedelta(seconds=time.seconds)
		
		human_time = datetime.datetime.strftime(remindat,"%H:%M:%S on %a %d %b")
		
		if not message:
			reminder = f"Sound {ctx.author.mention}, I'll give you a shout at {human_time}"
			completed = f"Here, {ctx.author.mention}. You asked me for a reminder."
		else:
			reminder = f"Areet {ctx.author.mention}, I'll give you a shout about '{message}' at {human_time}"
			completed = f"Here {ctx.author.mention}, ya asked me to remind you about '{message}'"
		
		await ctx.send(reminder)
		await asyncio.sleep(time.seconds)
		await ctx.send(completed)

	@timer.error
	async def timer_error(self, error, ctx):
		if type(error) is commands.BadArgument:
			await ctx.send(str(error))

def setup(bot):
    bot.add_cog(Timers(bot))			