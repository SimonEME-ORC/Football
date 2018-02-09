from prawcore.exceptions import RequestException
import praw

import json
import asyncio

import aiohttp
from aiohttp import ServerDisconnectedError
from lxml import html

from discord.ext import commands
import discord
import datetime

class MatchThreads:
	""" MatchThread functions """
	def __init__(self, bot):
		self.bot = bot
		
		# Scheduler
		self.scheduler = True
		self.schedtask = self.bot.loop.create_task(self.mt_scheduler())
		
		# MT Link
		self.mturl = None
		
		# r/NUFC 
		self.subreddit = "NUFC"
		self.modchannel = self.bot.get_channel(332167195339522048)
		
		# Test Channel
		# self.subreddit = "themagpiescss"
		# self.modchannel = self.bot.get_channel(250252535699341312) 

	def __unload(self):
		self.schedtask.cancel()
	
	async def automt(self):
		""" This is the bit that does the match thread. """
		# Get BBC Sport Match page
		link = await self.get_bbc_link()
		
		# Fetch pre-match thread.
		prematch = await self.get_prematch()
		
		async with self.bot.session.get(link) as resp:
			if resp.status != 200:
				await self.modchannel.send(f"HTTP Error attempting to retrieve {link}: {resp.status}. Match thread cancelled.")
				return
			tree = html.fromstring(await resp.text())
			if "/live/" in link:
				ko = "".join(tree.xpath('//div[@class="fixture_date-time-wrapper"]/time/text()')).title()
				ko = f'{ko}\n\n'
				try:
					kotime = tree.xpath('//span[@class="fixture__number fixture__number--time"]/text()')[0]
					ko = f"[🕒](#icon-clock) **Kickoff**: {kotime} on {ko}"
				except IndexError:
					ko = f"[🕒](#icon-clock) **Kickoff**: {ko}"

				home = tree.xpath('//span[@class="fixture__team-name fixture__team-name--home"]//abbr/@title')[0]
				away = tree.xpath('//span[@class="fixture__team-name fixture__team-name--away"]//abbr/@title')[0]

			else:
				ko 	= "".join(tree.xpath('//div[@class="fixture_date-time-wrapper"]/time/text()')).title()
				ko = f'{ko}\n\n'
				try:
					kotime = tree.xpath('//span[@class="fixture__number fixture__number--time"]/text()')[0]
					ko = f"[🕒](#icon-clock) **Kickoff**: {kotime} on {ko}"
				except IndexError:
					ko = f"[🕒](#icon-clock) **Kickoff**: {ko}"
				teams = tree.xpath('//div[@class="fixture__wrapper"]//abbr/@title')
				home = teams[0]
				away = teams[1]
		try:
			tvlink = tv = f"http://www.livesoccertv.com/teams/england/{self.bot.teams[home]['bbcname']}/"
		except KeyError:
			tv = ""
		if tv != "":
			tv = ""
			async with self.bot.session.get(tvlink) as resp:
				if resp.status != 200:
					pass
				else:
					btree = html.fromstring(await resp.text())
					for i in btree.xpath(".//table[@class='schedules'][1]//tr"):
						if away in "".join(i.xpath('.//td[5]//text()')).strip():
							fnd = "".join(i.xpath('.//td[6]//a/@href'))
							fnd = f"http://www.livesoccertv.com/{fnd}"
							tv = f"[📺](#icon-tv)[Television Coverage]({fnd})\n\n"

		hreddit = self.bot.teams[home]['subreddit']
		hicon = self.bot.teams[home]['icon']
		venue = f"[{self.bot.teams[home]['stadium']}]({self.bot.teams[home]['stadlink']})"
		ground = f"[🥅](#icon-net) **Venue**: {venue}\n\n"


		areddit = self.bot.teams[away]['subreddit']
		aicon = self.bot.teams[away]['icon']

		
		archive = "[Match Thread Archive](https://www.reddit.com/r/NUFC/wiki/archive)\n\n"
		try:
			blocks = tree.xpath('.//dt[//span[contains(text(),"Referee")]]/following-sibling::dd//text()')
			print(f"MTB :: BLOCKS - {blocks}")
			ref = f"[ℹ](#icon-whistle) **Referee**: {blocks[1]}\n\n"
		except IndexError:
			ref = ""
	
		# Update loop.
		async def update(prematch,ispostmatch):
			try:
				async with self.bot.session.get(link) as resp:
					if resp.status != 200:
						return "skip","skip","skip"
					tree = html.fromstring(await resp.text())
			except:
				return "skip","skiP","skip"
			
			# Fetch players
			async def parse_players(inputlist):
				out = []
				for i in inputlist:
					player = i.xpath('.//span[2]/abbr/span/text()')[0]
					infos  = "".join(i.xpath('.//span[2]/i/@class'))
					infotime = "".join(i.xpath('.//span[2]/i/span/text()'))
					infotime = infotime.replace('Booked at ','')
					infotime = infotime.replace('mins','\'')
					infos = infos.replace('sp-c-booking-card sp-c-booking-card--rotate sp-c-booking-card--yellow gs-u-ml','[💛](#icon-yellow)')
					infos = infos.replace('booking-card booking-card--rotate booking-card--red gel-ml','[🔴](#icon-red)')
					subinfo = i.xpath('.//span[3]/span//text()')
					subbed = subinfo[1] if subinfo else ""
					subtime = subinfo[3].strip() if subinfo else ""
					if subbed:
						subbed = f"[♻](#icon-sub) {subbed} {subtime}"
					if infos:
						if subbed:
							thisplayer = f"**{player}** ({infos}{infotime}, {subbed})"
						else:
							thisplayer = f"**{player}** ({infos}{infotime})"
					else:
						if subbed:
							thisplayer = f"**{player}** ({subbed})"
						else:
							thisplayer = f"**{player}**"
					out.append(thisplayer)
				return out
			
			# Get First Teams
			homex = tree.xpath('.//ul[@class="gs-o-list-ui gs-o-list-ui--top-no-border gel-pica"][1]/li')[:11]
			homex = await parse_players(homex)
			homexi = ", ".join(homex)
			awayx = tree.xpath('.//ul[@class="gs-o-list-ui gs-o-list-ui--top-no-border gel-pica"][1]/li')[11:]
			awayx = await parse_players(awayx)
			awayxi = ", ".join(awayx)
			
			# Get Subs
			subs = tree.xpath('//ul[@class="gs-o-list-ui gs-o-list-ui--top-no-border gel-pica"][2]/li/span[2]/abbr/span/text()')
			sublen = int(len(subs)/2)
			homesubs = [f"*{i}*" for i in subs[:sublen]]
			homesubs = ", ".join(homesubs)
			awaysubs = [f"*{i}*" for i in subs[sublen:]]
			awaysubs = ", ".join(awaysubs)
			
			# Fetch Goals
			hgoals = "".join(tree.xpath('.//ul[contains(@class,"fixture__scorers")][1]//text()'))
			if hgoals != "":
				hgoals = f"{hicon}[⚽](#icon-ball) {hgoals}\n\n"
			agoals = "".join(tree.xpath('.//ul[contains(@class,"fixture__scorers")][2]//text()'))
			if agoals != "":
				agoals = f"{aicon}[⚽](#icon-ball) {agoals}\n\n"
			goals = f"{hgoals}{agoals}".replace(" minutes","")
			
			score = " - ".join(tree.xpath("//section[@class='fixture fixture--live-session-header']//span[@class='fixture__block']//text()")[0:2])
			if score == "":
				score = "v"

			# Match Stats Block
			statlookup = tree.xpath("//dl[contains(@class,'percentage-row')]")
			stats = f"\n{home}|v|{away}\n:--|:--:|--:\n"
			for i in statlookup:
				stat = "".join(i.xpath('.//dt/text()'))
				dd1 = "".join(i.xpath('.//dd[1]/span[2]/text()'))
				dd2 = "".join(i.xpath('.//dd[2]/span[2]/text()'))
				stats += f"{dd1} | {stat} | {dd2}\n"
			stats += "\n"
			
			# Discord Link
			dsc = f"[](#icon-discord)[Come join us on Discord](https://discord.gg/tbyUQTV)\n\n"
			
			hreddit = self.bot.teams[home]['subreddit']
			hicon = self.bot.teams[home]['icon']
			venue = f"[{self.bot.teams[home]['stadium']}]({self.bot.teams[home]['stadlink']})"
			ground = f"[🥅](#icon-net) **Venue**: {venue}\n\n"


			areddit = self.bot.teams[away]['subreddit']
			aicon = self.bot.teams[away]['icon']
			venue = ""
			ground = ""
			
			if hreddit is None:
				hheader = home
			else:
				hheader = f"{hicon} [{home}]({hreddit})"
				
			if areddit is None:
				aheader = away
			else:
				aheader = f"[{away}]({areddit}) {aicon}"
			headerline = f"# {hheader} {score} {aheader}\n\n"
			
			blocks = tree.xpath('.//dt[//span[contains(text(),"Referee")]]/following-sibling::dd//text()')
			try:
				attenda = f'**Attendance**: {blocks[2]}\n\n'
			except IndexError:
				attenda = f'**Attendance**: Not announced yet.\n\n'
			if prematch == "Not found":
				prematch = "Couldn't find the pre-match thread."
			else:
				prematch = f"[Pre-Match Thread]({prematch})\n\n"
			
			quickstats = f"{ko}{ground}{ref}{attenda}{prematch}"
			
			if ispostmatch:
				quickstats += f"[Match Thread]({self.mturl})\n\n"
				threadname = f"Post-Match Thread: {home} {score} {away}"
			else:
				quickstats += f"{tv}\n\n[📻 Radio Commentary](https://www.nufc.co.uk/liveAudio.html)\n\n{dsc}\n\n"
				threadname = f"Match Thread: {home} v {away}"
				
			quickstats += f"{archive}\n\n---\n\n"
			
			# Fuck sake, this is Luton's Fault.
			hicon = home if hicon is None else hicon
			aicon = away if aicon is None else aicon
			lineups = f"{hicon} XI: {homexi}\n\nSubs: {homesubs}\n\n{aicon} XI: {awayxi}\n\nSubs: {awaysubs}\n\n---\n\n"
			
			bbcheader = f"##MATCH UPDATES (COURTESY OF [](#icon-bbc)[BBC]({link}))\n\n---\n\n"
			
			toptext = headerline+quickstats+lineups+goals+stats
			if not ispostmatch:
				toptext += f"{bbcheader}"
				
			ticker = tree.xpath(".//div[@class='lx-stream__feed']/article")
			return toptext,threadname,ticker,score
		
		# Generate Reddit post
		toptext,threadname,ticker,score = await update(prematch,False)

		post = await self.bot.loop.run_in_executor(None,self.makepost,threadname,toptext)
		self.mturl = post.url
		
		e = discord.Embed()
		ball = "https://emojipedia-us.s3.amazonaws.com/thumbs/120/lg/57/soccer-ball_26bd.png"
		e.set_author(name=f"r/{self.subreddit} Match Thread posted",icon_url=ball)
		e.color = 0xff4500
		e.description = f"[{post.title}]({post.url})"
		e.timestamp = datetime.datetime.now()
		
		await self.modchannel.send(embed=e)
		
		# Ticker Variables.
		tickids = []
		ticker = ""
		stop = False

		while True:
			toptext,threadname,newticks,score = await update(prematch,False)
			if toptext == "skip":
				pass
			else:
				newticks.reverse()
				for i in newticks:
					tickid = "".join(i.xpath("./@id"))
					if tickid in tickids:
						continue
					tickids.append(tickid)
					header = "".join(i.xpath('.//h3//text()')).strip()
					time = "".join(i.xpath('.//time//span[2]//text()')).strip()
					content = "".join(i.xpath('.//p//text()'))
					content = content.replace(home,f"{hicon} {home}")
					content = content.replace(away,f"{aicon} {away}").strip()
					if "Goal!" in header:
						if "Own Goal" in content:
							header = f"[⚽](#icon-OG) **OWN GOAL** "
						else:
							header = f"[⚽](#icon-ball) **GOAL** "
						time = f"**{time}**"
						content = f"**{content.replace('Goal! ','').strip()}**"
					if "Substitution" in header:
						header = f"[🔄](#icon-sub) **SUB**"
						team,subs = content.replace("Substitution, ","").split('.',1)
						on,off = subs.split('replaces')
						content = f"**{team} [🔺](#icon-up){on} [🔻](#icon-down){off}**"
						time = f"**{time}**"
					if content.lower().startswith("offside"):
						content = f"[](#icon-flag) {content}"
					elif content.lower().startswith("penalty saved"):
						content = f"[](#icon-OG) {content}"
					elif content.lower().startswith("corner"):
						content = f"[](#icon-corner) {content}"
					if "Booking" in header:
						header = f"[YC](#icon-yellow)"
					if "Dismissal" in header:
						if "second yellow" in content.lower():
							header = f"[OFF!](#icon-2yellow) **RED**"
						else:
							header = f"[OFF!](#icon-red) **RED**"
						content = f"**{content}**"
					if "injury" in content.lower() or "injured" in content.lower():
						content = f"[🚑](#icon-injury) {content}"
					if "Full Time" in header:
						stop = True
						ticker += f"# FULL TIME: {time} {hicon} [{home}]({hreddit}) {score} [{away}]({areddit}) {aicon}\n\n"
					else:
						ticker += f"{header} {time}: {content}\n\n"
				
				# Update match thread with new data.
				newcontent = toptext+ticker
				await self.bot.loop.run_in_executor(None,self.editpost,post,newcontent)
				
				if stop:
					# Final update when the match thread ends.
					msg = await self.modchannel.send("Match thread ended, submitting post-match thread.")
					
					# Post post-match thread.
					toptext,threadname,ticker,score = await update(prematch,True)
					post = await self.bot.loop.run_in_executor(None,self.makepost,threadname,toptext)
					
					e.set_author(name=f"r/{self.subreddit} Post-Match Thread posted.",icon_url=ball)
					e.description = f"[{post.title}]({post.url})"
					e.timestamp = datetime.datetime.now()
					return await msg.edit(content="",embed=e)

					
			await asyncio.sleep(120)
	
	# Scrape Fixtures to get current match
	async def get_bbc_link(self):
		async with self.bot.session.get("http://www.bbc.co.uk/sport/football/teams/newcastle-united/scores-fixtures") as resp:
			if resp.status != 200:
				await self.modchannel.send(":no_entry_sign: Match Thread Bot Aborted: HTTP Error: attempting to access game listings. {resp.url} returned status {resp.status}")
				return
			tree = html.fromstring(await resp.text())
			link = tree.xpath(".//a[contains(@class,'sp-c-fixture')]/@href")[-1]
			return f"http://bbc.co.uk{link}"
	
	# Get Pre-Match Thread From Reddit.
	async def get_prematch(self):
		async with self.bot.session.get("https://www.reddit.com/r/NUFC/") as resp:
			if resp.status != 200:
				await self.modchannel.send(content=f"HTTP Error accessing https://www.reddit.com/r/NUFC/ : {resp.status}",delete_after=5)
			else:
				tree = html.fromstring(await resp.text())
				for i in tree.xpath(".//p[@class='title']/a"):
					title = "".join(i.xpath('.//text()'))
					if "match" not in title.lower():
						continue
					if not title.lower().startswith("pre"):
						continue
					else:
						return "".join(i.xpath('.//@href'))
				else:
					return "Not found"
	
	# Make a reddit post.
	def makepost(self,threadname,toptext):
		print(f"Entered MakePost: {threadname}")
		try:
			post = self.bot.reddit.subreddit(f"{self.subreddit}").submit(threadname,selftext=toptext)
		except RequestException:
			post = self.makepost(threadname,toptext)
		return post
	
	# Edit an existing reddit post.
	def editpost(self,post,newcontent):
		try:
			post.edit(newcontent)
		except:
			self.editpost(post,newcontent)
		return
	
	# Scheduler.
	@commands.command(hidden=True,aliases=['mtbcheck'])
	@commands.has_permissions(manage_messages=True)
	async def checkmtb(self,ctx):
		""" Checks when the next match thread will be posted """
		mt = await self.get_bbc_link()
		await ctx.send(f"Next match thread scheduled at {self.nextmatch} (in " +
					f"{self.nextmatch - datetime.datetime.now()}) for {mt}")
		
	@commands.command()
	@commands.is_owner()
	async def forcemt(self,ctx):
		""" PANIC MODE """
		with ctx.typing():
			await ctx.send("Shit. Ok. Posting.")
			await self.bot.loop.create_task(self.automt())	
	
	@commands.command()
	@commands.has_permissions(manage_messages=True)
	async def schedon(self,ctx):
		self.scheduler = True
		await ctx.send(f"Match thread scheduler enabled.")
	
	@commands.command()
	@commands.has_permissions(manage_messages=True)
	async def schedoff(self,ctx):
		self.scheduler = False
		await ctx.send(f"Match thread scheduler disabled.")

	async def mt_scheduler(self):
		""" This is the bit that determines when to run a match thread """
		while self.scheduler:
			# Scrape the next kickoff date & time from the fixtures list on r/NUFC
			async with self.bot.session.get("https://www.reddit.com/r/NUFC/") as resp: 
				if resp.status != 200:
					return "Error: {resp.status}","Error {resp.status}"
				tree = html.fromstring(await resp.text())
				fixture = tree.xpath('.//div[@class="titlebox"]//div[@class="md"]//li[5]//table/tbody/tr[1]/td[1]//text()')[-1]
				next = datetime.datetime.strptime(fixture,'%a %d %b %H:%M').replace(year=datetime.datetime.now().year)
				if not next:
					return "No matches found","No matches found"
					await asyncio.sleep(86400) # sleep for a day.
				now = datetime.datetime.now()
				self.nextmatch = next
				postat = next - now - datetime.timedelta(minutes=15)
				
				# Calculate when to post the next match thread
				sleepuntil = (postat.days * 86400) + postat.seconds
				if sleepuntil > 0:
					await asyncio.sleep(sleepuntil) # Sleep bot until then.
					await self.bot.loop.create_task(self.automt())
					await asyncio.sleep(180)
				else:
					await asyncio.sleep(86400)
					
def setup(bot):
	bot.add_cog(MatchThreads(bot))