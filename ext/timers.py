from discord.ext import commands
import discord
import asyncio
import datetime
import typing
import json

### TODO
### >>> Port tempban to new system
### >>> Port tempmute to new system

class Timers(commands.Cog):
	def __init__(self,bot):
		self.bot = bot
		self.activemodule = True

		with open('reminders.json') as f:
			bot.reminders = json.load(f)	
		
		for k,v in bot.reminders.items():
			self.bot.loop.create_task(self.spool_reminders(k,v))
	
	async def _save(self):
		with await self.bot.timerlock:
			with open('reminders.json',"w",encoding='utf-8') as f:
				json.dump(self.bot.reminders,f,ensure_ascii=True,
				indent=4, separators=(',',':'))
	
	def cog_unload(self):
		self.activemodule = False	
	
	async def spool_reminders(self,msgid,values):
		dtc = datetime.datetime.strptime(values["time"], '%Y-%m-%d %H:%M:%S.%f')
		time = dtc - datetime.datetime.now()
		
		await asyncio.sleep(time.total_seconds())
		
		if not self.activemodule:
			return 

		destin = values["destination"]
		destin = self.bot.get_channel(destin)
		
		member = destin.guild.get_member(values["user"]).mention
		ts = datetime.datetime.strptime(values['ts'], '%Y-%m-%d %H:%M:%S.%f')
		
		e = discord.Embed()
		e.timestamp = ts
		e.color = 0x00ff00
		
		if "message" in values:
			message = values['message']
			e.title = f"⏰ Reminder"
			e.description = message
			try: # Jump to message if found.
				e.description += f"\n\n[⬆️ Jump to message.]({values['jumpurl']})"
			except AttributeError as f:
				print(f"Attribute Error {f}")
		if "mode" in values:
			if values["mode"] == "unban":
				try:
					await self.bot.http.unban(values["target"], self.bot.get_channel(values["destination"]).guild)
					e.description = f'Userid {values["target"]} was unbanned'
				except discord.NotFound:
					e.description = f"Failed to unban userid {values['target']} - are they already unbanned?"
				
		await destin.send(member,embed=e)
		del self.bot.reminders[msgid]
		await self._save()
		
		
		
	async def parse_time(self,time):
		delta = datetime.timedelta()	
		if "d" in time:
			d,time = time.split("d")
			delta += datetime.timedelta(days=int(d))
		if "h" in time:
			h,time = time.split("h")
			delta += datetime.timedelta(hours=int(h))
		if "m" in time:
			m,time = time.split("m")
			delta += datetime.timedelta(minutes=int(m))
		if "s" in time:
			s = time.split("s")[0]
			delta += datetime.timedelta(seconds=int(s))
		return delta

	@commands.command(aliases=['reminder','remind','remindme'])
	async def timer(self, ctx, time, *, message : commands.clean_content):
		""" Remind you of something at a specified time. 
		    Format is remind 1d2h3m4s <note>, e.g. remind 1d3h Kickoff."""
			
		delta = await self.parse_time(time.lower())
			
		remindat = datetime.datetime.now() + delta
		human_time = datetime.datetime.strftime(remindat,"%H:%M:%S on %a %d %b")
		
		e = discord.Embed()
		e.title = "⏰ Reminder Set"
		e.description = message
		e.color = 0x00ffff
		e.timestamp = remindat
		
		await ctx.send(embed=e)
		
		reminder = {
			ctx.message.id:{
				"user":ctx.author.id,
				"destination":ctx.channel.id,
				"message":message,
				"time":str(remindat),
				"ts":str(ctx.message.created_at),
				"jumpurl":ctx.message.jump_url
			}
		}
		
		self.bot.reminders.update(reminder)
		await self._save()
		for k,v in reminder.items():
			self.bot.loop.create_task(self.spool_reminders(k,v))

	@commands.command(aliases=["timers"])
	async def reminders(self,ctx):
		""" Check your active reminders """
		
		e = discord.Embed()
		e.description = ""
		e.color = 0x7289DA
		e.title = f"⏰ {ctx.author.name}'s reminders"
		
		for i in self.bot.reminders.keys():
			if self.bot.reminders[i]["user"] != ctx.author.id:
				continue
				
			delta = datetime.datetime.strptime(self.bot.reminders[i]['time'],'%Y-%m-%d %H:%M:%S.%f') - datetime.datetime.now()
			#### TODO: Paginate this.
			e.description +=  "**`" + str(delta).split(".")[0] + "`** " + self.bot.reminders[i]['message'] + "\n"
		await ctx.send(embed=e)
	
	@commands.command()
	@commands.has_permissions(ban_members=True)
	async def tempban(self,ctx,arg1: typing.Union[discord.Member,str],arg2: typing.Union[discord.Member,str],*, reason: commands.clean_content = None):
		""" Temporarily ban a member from the server """
		if isinstance(arg1,discord.Member):
			member = arg1
			time = arg2
		elif isinstance(arg2,discord.Member):
			member = arg2
			time = arg1
		else:
			return await ctx.send("That doesn't look right. try again.")
			
		delta = await self.parse_time(time.lower())
		remindat = datetime.datetime.now() + delta
		human_time = datetime.datetime.strftime(remindat,"%H:%M:%S on %a %d %b")		
		id = member.id
		try:
			await ctx.guild.ban(member,reason=reason)
		except:
			return await ctx.send('🚫 Banning failed.')
		
		reminder = {
			ctx.message.id:{
				"user":ctx.author.id,
				"destination":ctx.channel.id,
				"message":f"Temporary ban ending for {member}",
				"target":id,
				"mode":"unban",
				"time":str(remindat),
				"ts":str(ctx.message.created_at),
				"jumpurl":ctx.message.jump_url
			}
		}			
			
		self.bot.reminders.update(reminder)
		await self._save()
		await ctx.send(f'☠️ Banned {member.mention} until {human_time}')
		for k,v in reminder.items():
			self.bot.loop.create_task(self.spool_reminders(k,v))


def setup(bot):
    bot.add_cog(Timers(bot))			