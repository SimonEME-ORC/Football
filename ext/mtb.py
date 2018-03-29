import praw
from prawcore.exceptions import RequestException

import json
import asyncio

import aiohttp
from aiohttp import ServerDisconnectedError
from lxml import html

from discord.ext import commands
import discord
import datetime

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, WebDriverException

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

class MatchThread:
	""" MatchThread Bot rewrite."""
	def __init__(self, bot):
		self.bot = bot
		# Debug data
		# self.prem_link = "https://www.premierleague.com/match/22606"# Man Utd vs NCL
		# self.prem_link = "https://www.premierleague.com/match/22600"# Watford vs Chelsea
		
		# Spawn PhantomJS
		self.spawn_phantom()
		
		# Discord and Subreddit
		# r/NUFC 
		self.subreddit = "NUFC"
		self.modchannel = self.bot.get_channel(332167195339522048)
		
		# Painezor's Test Server/Subreddit.
		# self.subreddit = "themagpiescss"
		# self.modchannel = self.bot.get_channel(250252535699341312)
		
		# URLs
		self.bbclink = ""
		
		# Strings.
		self.discord = "[](#icon-discord)[Come chat with us on Discord!](https://discord.gg/tbyUQTV)"
		self.archive = "https://www.reddit.com/r/NUFC/wiki/archive"
			
		self.teamurl = "newcastle-united"	
		# self.teamurl = "huddersfield-town" # DEBUG
		self.radio = "[📻 Radio Commentary](https://www.nufc.co.uk/liveAudio.html)"
		self.tickerheader = ""
		self.botdisclaimer = "---\n\n(*Beep boop, I am /u/Toon-bot, a bot coded ^badly by /u/Painezor. If anything appears to be weird or off, please let him know.*)"
		
		# Match Data
		self.attendance = ""
		self.referee = ""
		self.reflink = ""
		self.stadium = ""
		self.stadiumlink = ""
		self.kickoff = ""
		self.score = "vs"
		self.matchstats = ""
		self.homegoals = ""
		self.awaygoals = ""
		self.hometeam = ""
		self.awayteam = ""
		self.homexi = ""
		self.awayxi = ""
		self.homesubs = ""
		self.awaysubs = ""
		self.substituted = set()
		self.ticker = []
		
		# Bonus
		self.prem_link = ""
		self.formations = ""
		self.matchpictures = set()
		
		# Reddit info
		self.homereddit = ""
		self.homeicon = ""
		self.awayreddit = ""
		self.awayicon = ""
		self.prematchthread = ""
		self.matchthread = ""
		
		# TV info
		self.tvlink = ""
		self.uktv = ""
		
		# Scheduler
		self.nextmatch = ""
		self.postat = ""
		self.scheduling = True
		self.schedtask = self.bot.loop.create_task(self.scheduler())
		
		# MT Task
		self.stopmatchthread = False
	
	def nufccheck(ctx):
		if ctx.guild:
			return ctx.guild.id in [238704683340922882,332159889587699712]
	
	def __unload(self):
		# Cancel Scheduler loop
		self.schedtask.cancel()
		
		# Exit Selenium Scraper
		try:
			self.driver.quit()
		except AttributeError:
			pass
	
	# PhantomJS for premier league website scraping.
	def spawn_phantom(self):
		webdriver.DesiredCapabilities.PHANTOMJS['phantomjs.page.settings.userAgent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.2564.116 Safari/537.36'
		headers = { 'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
			'Accept-Language':'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
			'User-Agent': 'Mozilla/5.0 (Windows NT 6.2; WOW64; rv:47.0) Gecko/20100101 Firefox/47.0',
			'Connection': 'keep-alive'
		}

		for key, value in headers.items():
			webdriver.DesiredCapabilities.PHANTOMJS['phantomjs.page.customHeaders.{}'.format(key)] = value
		self.driver = webdriver.PhantomJS()
	
	# Loop to check when to post.-
	async def scheduler(self):
		""" This is the bit that determines when to run a match thread """
		print("Scheduler Started.")
		while self.scheduling:
			# Scrape the next kickoff date & time from the fixtures list on r/NUFC
			async with self.bot.session.get("https://www.reddit.com/r/NUFC/") as resp: 
				if resp.status != 200:
					print(f'{resp.status} error in scheduler.')
					await asycio.sleep(10)
					continue
				tree = html.fromstring(await resp.text())
				print("Scheduler parsing.")
				fixture = tree.xpath('.//div[@class="titlebox"]//div[@class="md"]//li[5]//table/tbody/tr[1]/td[1]//text()')[-1]
				next = datetime.datetime.strptime(fixture,'%a %d %b %H:%M').replace(year=datetime.datetime.now().year)
				if not next:
					print("No matches found. Sleeping 24h.")
					await asyncio.sleep(86400) # sleep for a day.
				else:
					print(f"Match found: {next}")
				now = datetime.datetime.now()
				self.nextmatch = next
				postat = next - now - datetime.timedelta(minutes=15)
				
				self.postat = postat
				# Calculate when to post the next match thread
				sleepuntil = (postat.days * 86400) + postat.seconds
				if sleepuntil > 0:
					await asyncio.sleep(sleepuntil) # Sleep bot until then.
					await self.bot.loop.create_task(self.start_match_thread())
					await asyncio.sleep(180)
				else:
					await asyncio.sleep(86400)

					# Match Thread Loop
	async def start_match_thread(self):
		""" Core function """
		# Fetch Link from BBC Sport Match Page.
		await self.get_bbc_link()
		
		if self.bbclink.isdigit():
			return await self.modchannel.send(f"🚫 Match Thread Failed, error, bbclink is {self.bbclink}")
		
		# Fetch pre-match thread.
		await self.fetch_prematch()
		
		# Scrape Initial Data.
		if "/live/" in self.bbclink:
			await self.scrape_live()
		else:
			await self.scrape_normal()
		
		# Bonus data if prem.
		if "Premier League" in self.competition:
			await self.bot.loop.run_in_executor(None,self.get_prem_link)
			await self.bot.loop.run_in_executor(None,self.get_prem_data)
		else:
			print(f"Not premier league - {self.competition}")

		# Find TV listings.
		await self.fetch_tv()

		# Get Subreddit info & badges.
		await self.get_team_reddit_info()
		
		# Write Markdown
		markdown = await self.write_markdown(False)
		
		# Post initial thread.
		threadname = f"Match Thread: {self.hometeam} vs {self.awayteam}"
		post = await self.bot.loop.run_in_executor(None,self.makepost,threadname,markdown)
		self.matchthread = post.url
		
		await self.modchannel.send(f"Match Thread Created: {post.url}")
		
		# Commence loop.
		while True:
			# Scrape new data
			if "/live/" in self.bbclink:
				await self.scrape_live()
			else:
				await self.scrape_normal()

			if self.prem_link:
				await self.bot.loop.run_in_executor(None,self.get_prem_data)
			# Rebuild markdown
			markdown = await self.write_markdown(False)
			
			# Edit post
			await self.bot.loop.run_in_executor(None,self.editpost,post,markdown)
			
			if self.stopmatchthread:
				break

			# Repeat
			await asyncio.sleep(60)
		
		# Post-loop
		# Scrape final data
		if "/live/" in self.bbclink:
			await self.scrape_live()
		else:
			await self.scrape_normal()
		if self.prem_link:
			await self.bot.loop.run_in_executor(None,self.get_prem_data)
		
		# Rebuild markdown
		markdown = await self.write_markdown(True)	
		threadname = f"Post-Match Thread: {self.hometeam} {self.score} {self.awayteam}"
		post = await self.bot.loop.run_in_executor(None,self.makepost,threadname,markdown)
		await self.modchannel.send(f"Post-Match Thread Created: {post.url}")
		
	# Formatting.
	async def write_markdown(self,ispostmatch):
		markdown = ""
		
		homestring = f"{self.homeicon}{self.hometeam}"
		if self.homereddit:
			homestring = f"[{homestring}]({self.homereddit})"
			
		awaystring = f"{self.awayteam}{self.awayicon}"
		if self.awayreddit:
			awaystring = f"[{awaystring}]({self.awayreddit})"
			
		markdown += f"# {homestring} {self.score} {awaystring}\n\n"
		markdown += f"[🕒](#icon-clock)**Kick-Off**: {self.kickoff}\n\n"
		markdown += f"[](#icon-trophy)**Competition**: {self.competition}\n\n"

		if self.prematchthread:
			if ispostmatch:
				markdown += f"[Pre-Match Thread]({self.prematchthread}) - [Match Thread]({self.matchthread}) - [Archive]({self.archive})\n\n"
			else:
				markdown += f"[Pre-Match Thread]({self.prematchthread}) - [Match Thread Archive]({self.archive})\n\n"
		else:
			if ispostmatch:
				markdown += f"[Match Thread]({self.matchthread}) - [Archive]({self.archive})\n\n"
			else:
				markdown += f"[Match Thread Archive]({self.archive})\n\n"
		
		markdown += f"{self.discord}\n\n"
		
		if self.stadium:
			if self.stadiumlink:
				markdown += f"[🥅](#icon-net)**Venue**: [{self.stadium}]({self.stadiumlink})\n\n"
			else:
				markdown +=  f"[🥅](#icon-net)**Venue**: {self.stadium}\n\n"

		if self.referee:
			if self.reflink:
				referee = f"[](#icon-whistle)**Refree**: [{self.referee}]({self.reflink})\n\n"
			else:
				referee = f"[](#icon-whistle)**Refree**: {self.referee}\n\n"
			markdown += referee
			
		if self.attendance:
			markdown += f"**👥 Attendance**: {self.attendance}\n\n"
		
		if "Newcastle United" in [self.hometeam,self.awayteam]:
			markdown += f"{self.radio}\n\n"
		
		if self.uktv:
			markdown += f"📺 **Television Coverage** (UK): {self.uktv}\n\n"
		if self.tvlink:
			markdown += f"📺🌍 **Television Coverage** (International): {self.tvlink}\n\n"
			
		if any([self.homexi,self.awayxi]):
			markdown += "### Lineups\n\n---\n\n"
			markdown += f"**{self.homeicon}{self.hometeam} XI**: {self.homexi}\n\n"
			markdown += f"*Subs*: {self.homesubs}\n\n"
			markdown += f"**{self.awayicon}{self.awayteam} XI**: {self.awayxi}\n\n"
			markdown += f"*Subs*: {self.awaysubs}\n\n"
		
		if self.formations:
			markdown += f"[Formations](self.formations)\n\n"
		
		if self.matchstats:
			markdown += f"{self.matchstats}\n\n"
		
		if self.homegoals:
			markdown += f"**{self.homeicon}{self.hometeam} Goals**: {self.homegoals}\n\n"
		if self.awaygoals:
			markdown += f"**{self.awayicon}{self.awayteam} Goals**: {self.awaygoals}\n\n"
		
		if self.matchpictures:
			markdown += f"## Match Photos\n\n{self.matchpictures}\n\n"
		
		ticker = '\n\n'.join(self.ticker)
		if self.ticker:
			markdown += f"{self.tickerheader}\n\n---\n\n{ticker}\n\n"
			
		markdown += f"^^{self.botdisclaimer}\n\n"
		
		return markdown
			
	# Get Premier League Website data.
	def get_prem_link(self):
		self.driver.get("http://www.premierleague.com/fixtures")
		WebDriverWait(self.driver, 5)
		self.driver.implicitly_wait(10)
		
		try:
			self.driver.find_elements_by_xpath("//span[@class='teamName' and contains(text(), 'Newcastle')]")[0].click()
		except IndexError:
			return
		WebDriverWait(self.driver, 5)
		
		self.prem_link = self.driver.current_url
		
	# Scrape Fixtures to get current match
	async def get_bbc_link(self):
		async with self.bot.session.get(f"http://www.bbc.co.uk/sport/football/teams/{self.teamurl}/scores-fixtures") as resp:
			if resp.status != 200:
				self.bbclink = f"{resp.status}"
				return
			tree = html.fromstring(await resp.text(encoding="utf-8"))
			self.bbclink = tree.xpath(".//a[contains(@class,'sp-c-fixture')]/@href")[-1]
			self.bbclink = f"http://www.bbc.co.uk{self.bbclink}"
			return
	
	# Scrape data NORMAL version
	async def scrape_normal(self):
		async with self.bot.session.get(self.bbclink) as resp:
			if resp.status != 200:
				return
			tree = html.fromstring(await resp.text(encoding="utf-8"))
			
			# Date & Time
			kodate = "".join(tree.xpath('//div[@class="fixture_date-time-wrapper"]/time/text()')).title()
			try:
				kotime = tree.xpath('//span[@class="fixture__number fixture__number--time"]/text()')[0]
				self.kickoff = f"{kotime} on {kodate}"
			except IndexError:
				self.kickoff = kodate
			

			# Teams
			teams = tree.xpath('//div[@class="fixture__wrapper"]//abbr/@title')
			self.hometeam = teams[0]
			self.awayteam = teams[1]
			
			# Referee, competition & Attendance
			self.referee = "".join(tree.xpath("//dt[contains(., 'Referee')]/text() | //dt[contains(., 'Referee')]/following-sibling::dd[1]/text()"))
			await self.get_ref_link()
			
			self.competition = "".join(tree.xpath('//span[contains(@class,"fixture__title gel-minion")]/text()'))

			self.attendance = "".join(tree.xpath("//dt[contains(., 'Attendance')]/text() | //dt[contains(., 'Attendance')]/following-sibling::dd[1]/text()"))		

			# Lineups
			players = tree.xpath('.//ul[@class="gs-o-list-ui gs-o-list-ui--top-no-border gel-pica"][1]/li')
			home = players[:11]
			away = players[11:]			
			
			self.homexi = ", ".join(await self.parse_players(home))
			self.awayxi = ", ".join(await self.parse_players(away))
			
			# Substitutes
			subs = tree.xpath('//ul[@class="gs-o-list-ui gs-o-list-ui--top-no-border gel-pica"][2]/li/span[2]/abbr/span/text()')
			sublen = int(len(subs)/2)
			self.homesubs = ", ".join([f"*{i}*" for i in subs[:sublen]])
			self.awaysubs = ", ".join([f"*{i}*" for i in subs[sublen:]])
			
			# Goals
			self.score = " - ".join(tree.xpath("//section[@class='fixture fixture--live-session-header']//span[@class='fixture__block']//text()")[0:2])
			self.homegoals = "".join(tree.xpath('.//ul[contains(@class,"fixture__scorers")][1]//text()')).replace(' minutes','').replace('pen','p.')
			self.awaygoals = "".join(tree.xpath('.//ul[contains(@class,"fixture__scorers")][2]//text()')).replace(' minutes','').replace('pen','p.')
			
			# Match Stats
			statlookup = tree.xpath("//dl[contains(@class,'percentage-row')]")
			
			if statlookup:
				self.matchstats = f"\n{self.hometeam}|v|{self.awayteam}\n:--|:--:|--:\n"
				for i in statlookup:
					stat = "".join(i.xpath('.//dt/text()'))
					dd1 = "".join(i.xpath('.//dd[1]/span[2]/text()'))
					dd2 = "".join(i.xpath('.//dd[2]/span[2]/text()'))
					self.matchstats += f"{dd1} | {stat} | {dd2}\n"
		

			# Ticker
			self.tickerheader = f"## Match updates (via [](#icon-bbc)[BBC]({self.bbclink}))\n\n"
			ticker = tree.xpath(".//div[@class='lx-stream__feed']/article")
			await self.parse_ticker_normal(ticker)		
			
	# Scrape data (LIVE version)
	async def scrape_live(self):
		async with self.bot.session.get(self.bbclink) as resp:
			if resp.status != 200:
				return
			tree = html.fromstring(await resp.text(encoding="utf-8"))
						
			# Date & Time
			kodate = "".join(tree.xpath('//div[@class="fixture_date-time-wrapper"]/time/text()')).title()
			try:
				kotime = tree.xpath('//span[@class="fixture__number fixture__number--time"]/text()')[0]
				self.kickoff = f"{kotime} on {kodate}"
			except IndexError:
				self.kickoff = datetime.datetime.now() + datetime.timedelta(minutes=15)
			
			# Teams
			self.hometeam = tree.xpath('//span[@class="fixture__team-name fixture__team-name--home"]//abbr/@title')[0]
			self.awayteam = tree.xpath('//span[@class="fixture__team-name fixture__team-name--away"]//abbr/@title')[0]
			self.score = " - ".join(tree.xpath('//span[@class="fixture__block"]//text()'))
			
			# Referee & Attendance
			self.referee = "".join(tree.xpath("//dt[contains(., 'Referee')]/text() | //dt[contains(., 'Referee')]/following-sibling::dd[1]/text()"))
			await self.get_ref_link()
			self.attendance = "".join(tree.xpath("//dt[contains(., 'Attendance')]/text() | //dt[contains(., 'Attendance')]/following-sibling::dd[1]/text()"))		

	
			# Lineups
			players = tree.xpath('.//ul[@class="gs-o-list-ui gs-o-list-ui--top-no-border gel-pica"][1]/li')
			home = players[:11]
			away = players[11:]			
			
			self.homexi = await self.parse_players(home)
			self.awayxi = await self.parse_players(away)
			
			# Substitutes
			subs = tree.xpath('//ul[@class="gs-o-list-ui gs-o-list-ui--top-no-border gel-pica"][2]/li/span[2]/abbr/span/text()')
			sublen = int(len(subs)/2)
			homesubs = [f"*{i}*" for i in subs[:sublen]]
			awaysubs = [f"*{i}*" for i in subs[sublen:]]
			
			# Goals
			self.score = " - ".join(tree.xpath("//section[@class='fixture fixture--live-session-header']//span[@class='fixture__block']//text()")[0:2])
			self.homegoals = "".join(tree.xpath('.//ul[contains(@class,"fixture__scorers")][1]//text()'))
			self.awaygoals = "".join(tree.xpath('.//ul[contains(@class,"fixture__scorers")][2]//text()'))
			
			# Match Stats
			statlookup = tree.xpath("//dl[contains(@class,'percentage-row')]")
			self.matchstats = ""
			for i in statlookup:
				stat = "".join(i.xpath('.//dt/text()'))
				dd1 = "".join(i.xpath('.//dd[1]/span[2]/text()'))
				dd2 = "".join(i.xpath('.//dd[2]/span[2]/text()'))
				self.matchstats += f"{dd1} | {stat} | {dd2}\n"
			
			# Ticker (Live is last resort, after premier league.)
			if not "Premier League" in self.competition:
				ticker = tree.xpath("//div[@class='lx-stream__feed']/article")
				await self.parse_ticker_live(ticker)
			
	# Get Pre-Match Thread From Reddit.
	async def fetch_prematch(self):
		async with self.bot.session.get("https://www.reddit.com/r/NUFC/") as resp:
			if resp.status != 200:
				return
			tree = html.fromstring(await resp.text())
			for i in tree.xpath(".//p[@class='title']/a"):
				title = "".join(i.xpath('.//text()'))
				if "match" not in title.lower():
					continue
				if not title.lower().startswith("pre"):
					continue
				else:
					self.prematchthread = "".join(i.xpath('.//@href'))
					print(self.prematchthread)
					return
	
	async def fetch_tv(self):
		print(f"Fetching TV for {self.hometeam}")
		try:
			tvurl = f"http://www.livesoccertv.com/teams/england/{self.bot.teams[self.hometeam]['bbcname']}"
		except KeyError as e:
			print(f"Key error. {self.hometeam}")
			return
		async with self.bot.session.get(tvurl) as resp:
			if resp.status != 200:
				return
			tree = html.fromstring(await resp.text())
			for i in tree.xpath(".//table[@class='schedules'][1]//tr"):
				match = "".join(i.xpath('.//td[5]//text()')).strip()
				
				# Completed matches are irrelevant.
				if not "vs" in match:
					continue
				tvpage = "".join(i.xpath('.//td[5]//a/@href'))
				self.tvlink = f"http://www.livesoccertv.com/{tvpage}"
				break
			if not self.tvlink:
				return
		async with self.bot.session.get(self.tvlink) as resp:
			if resp.status != 200:
				return
			tree = html.fromstring(await resp.text())
			tvtable = tree.xpath('.//table[@id="wc_channels"]//tr')
			if not tvtable:
				return
			for i in tvtable:
				ctry = i.xpath('.//td[1]/span/text()')
				if "United Kingdom" not in ctry:
					continue
				uktvchannels = i.xpath('.//td[2]/a/text()')
				uktvlinks = i.xpath('.//td[2]/a/@href')
				uktvlinks = [f'http://www.livesoccertv.com/{i}' for i in uktvlinks]
				self.uktv = list(zip(uktvchannels,uktvlinks))
				self.uktv = ", ".join([f"[{i}]({j})" for i,j in self.uktv])
	
	async def get_team_reddit_info(self):
		try:
			self.homereddit = self.bot.teams[self.hometeam]['subreddit']
			self.homeicon = self.bot.teams[self.hometeam]['icon']
			self.stadium = self.bot.teams[self.hometeam]['stadium']
			self.stadiumlink = self.bot.teams[self.hometeam]['stadlink']
		except KeyError:
			pass
		try:
			self.awayreddit = self.bot.teams[self.awayteam]['subreddit']
			self.awayicon = self.bot.teams[self.awayteam]['icon']
		except KeyError:
			pass
	
	async def parse_players(self,players):
		squad = []
		self.sendthis = []
		for i in players:
			name = i.xpath('.//span[2]/abbr/span/text()')[0]
			number = i.xpath('.//span[1]/text()')[0]
			
			# Bookings / Sending offs.
			info = "".join(i.xpath('.//span[2]/i/@class')).replace('sp-c-booking-card sp-c-booking-card--rotate sp-c-booking-card--yellow gs-u-ml','[Yel](#icon-yellow) ').replace('booking-card booking-card--rotate booking-card--red gel-ml','[Red](#icon-red) ')
			if info:
				info += " ".join(i.xpath('.//span[2]/i/span/text()')).replace('Booked at ','').replace('mins','\'')
			try:
				subinfo = f" [🔄](#icon-sub){i.xpath('.//span[3]/span//text()')[3]}"
				self.substituted.add(i.xpath('.//span[3]/span//text()')[1])
				self.substituted.add(name)
			except IndexError:
				subinfo = ""
			
			# Italicise players who have been substituted.
			if subinfo:
				name = f"*{name}*"
			squad.append(f"**{number}** {name} {info}{subinfo}".strip())
		return squad
	
	async def parse_ticker_normal(self,ticker):
		# .reverse() so bottom to top.
		ticker.reverse()
		for i in ticker:
			key = False
			header = "".join(i.xpath('.//h3//text()')).strip()
			time = "".join(i.xpath('.//time//span[2]//text()')).strip()
			if time:
				time = f"{time}:"
			content = "".join(i.xpath('.//p//text()'))
			
			tick = self.format_tick(header,time,content)

			# Filter tick from reupdating & append to ticker.
			if tick not in self.ticker:
				self.ticker.append(tick)
	
	def parse_ticker_prem(self,ticker):
		# .reverse() so bottom to top.
		ticker.reverse()
		for i in ticker:
			header = "".join(i.xpath('.//h6/text()'))
			time = "".join(i.xpath('//time/text()'))
			if time:
				time += ":"
			content = "".join(i.xpath('.//p/text()'))
			
			tick = self.format_tick(header,time,content)
			if tick not in self.ticker:
				self.ticker.append(tick)

	async def parse_ticker_live(self,ticker):
		# .reverse() so bottom to top.
		ticker.reverse()
		for i in ticker:
			header = "".join(i.xpath('.//h3//text()')).strip()
			time = "".join(i.xpath('.//time//span[2]//text()')).strip()
			if time:
				time += ":"
			content = "".join(i.xpath('.//p//text()'))
			
			tick = self.format_tick(header,time,content)
			
			# Append to ticker.
			if tick not in self.ticker:
				self.ticker.append(tick)
			
	def format_tick(self,header,time,content):
		# Swap in icons
		key = False
		if self.homeicon:
			content = content.replace(self.hometeam,f"{self.homeicon}{self.hometeam}")
		if self.awayicon:
			content = content.replace(self.awayteam,f"{self.awayicon}{self.awayteam}")
		
		# Format by header.
		if "kick off" in header.lower():
			key = True
			header = "[⚽](#icon-ball) Kick Off:"
			content = content.replace('Kick Off ',"")
		
		elif "goal" in header.lower():
			key = True
			if "own goal" in content.lower():
				header = "[⚽](#icon-og) **OWN GOAL**"
			else:
				header = "[⚽](#icon-ball) **GOAL**"
			
			content = content.replace('Goal! ','').strip()		
		
		elif "substitution" in header.lower():
			header = f"[🔄](#icon-sub)"
			team,subs = content.replace("Substitution, ","").split('.',1)
			on,off = subs.split('replaces')
			content = f"**Substitution for {team}** [⬆](#icon-up){on} [⬇](#icon-down){off}"
			
		elif "booking" in header.lower():
			header = f"[YC](#icon-yellow)"
		
		elif "dismissal" in header.lower():
			key = True
			if "second yellow" in content.lower():
				header = f"[OFF!](#icon-2yellow) RED CARD"
			else:
				header = f"[OFF!](#icon-red) RED CARD"
		
		elif "full time" in header.lower() or "full-time" in header.lower():
			self.stopmatchthread = True
			header = "# FULL TIME"
			if self.homeicon:
				homestring = f"{self.homeicon}{self.hometeam}"
			else:
				homestring = self.hometeam
				
			if self.awayicon:
				awaystring = f"{self.awayteam}{self.awayicon}"
			else:
				awaystring = self.awayteam
			
			return f"{homestring} {self.score} {awaystring}"
		else:
			if header:
				print(f"MTB: Unhandled header: {header}")
		
			# Format by content.
			elif "injury" in content.lower() or "injured" in content.lower():
				content = f"[🚑](#icon-injury) {content}"
			elif "offside" in content.lower():
				content = f"[](#icon-flag) {content}"
			elif content.lower().startswith("corner"):
				content = f"[](#icon-corner) {content}"
			elif "penalty saved" in content.lower():
				key = True
				header = "PENALTY SAVED"
				content = f"[](#icon-OG) {content}"	
	
		return " ".join([header,time,content]).strip()
	
	async def get_ref_link(self):
		url = 'http://www.transfermarkt.co.uk/schnellsuche/ergebnis/schnellsuche'
		p = {"query":self.referee,"Schiedsrichter_page":"0"}
		async with self.bot.session.get(url,params=p) as resp:
			tree = html.fromstring(await resp.text())
			matches = f".//div[@class='box']/div[@class='table-header'][contains(text(),'referees')]/following::div[1]//tbody/tr"
			trs = tree.xpath(matches)
			if trs:
				self.reflink = trs[0].xpath('.//td[@class="hauptlink"]/a/@href')[0]
				self.reflink = f"http://www.transfermarkt.co.uk/{self.reflink}"
	
	def get_prem_data(self):
		if not self.prem_link:
			return
		self.spawn_phantom # Delete after testing.
		self.driver.get(self.prem_link)
		WebDriverWait(self.driver, 5)
		
		tree = html.fromstring(self.driver.page_source)
		# Get ticker
		if not self.tickerheader or "premierleague.com" in self.tickerheader:
			self.tickerheader = "##"
			ticker = tree.xpath('.//ul[@class="commentaryContainer"]/li')
			ticker = self.parse_ticker_prem(ticker)
		
		# Get Match pictures.
		pics = tree.xpath('.//ul[@class="matchPhotoContainer"]')
		for i in pics:
			url = i.xpath('.//div[@class="thumbnail"]//img/@src')
			caption = i.xpath('.//span[@class="captionBody"]/text()')
			thispic = "[{caption}]({url})"
			if thispic not in self.matchpictures:
				self.matchpictures.append(thispic)
		
		# Get Formations
		z = self.driver.find_element_by_xpath(".//ul[@class='tablist']/li[@class='matchCentreSquadLabelContainer']")
		z.click()
		WebDriverWait(self.driver, 2)
		self.driver.implicitly_wait(2)
		lineup = self.driver.find_element_by_xpath(".//div[@class='pitch']")
		self.driver.save_screenshot('Debug.png')

		# Fuck it we're cropping manually.
		im = Image.open(BytesIO(lineup.screenshot_as_png))
		left = 867
		top = 975
		right = left + 325
		bottom = top + 475
		
		im = im.crop((left, top, right, bottom))
		
		im.save("formations.png")
		# self.driver.save_screenshot('Debug.png')
		
		self.bot.loop.create_task(self.upload_formation())

	# Post to IMGUR
	async def upload_formation(self):
		d = {"image":open("formations.png",'rb')}
		h = {'Authorization': self.bot.credentials["Imgur"]["Authorization"]}
		async with self.bot.session.post("https://api.imgur.com/3/image",data = d,headers=h) as resp:
			res = await resp.json()
		self.formations = res['data']['link']
	
	# Reddit posting shit.
	# Make a reddit post.
	def makepost(self,threadname,markdown):
		print(f"Entered MakePost: {threadname}")
		try:
			post = self.bot.reddit.subreddit(f"{self.subreddit}").submit(threadname,selftext=markdown)
		except RequestException:
			post = self.makepost(threadname,markdown)
		return post
	
	# Edit an existing reddit post.
	def editpost(self,post,markdown):
		try:
			post.edit(markdown)
		except:
			self.editpost(post,markdown)
		return
	
	# Debug command - Get Prem info
	@commands.command()
	@commands.is_owner()
	async def prem(self,ctx):
		await self.bot.loop.run_in_executor(None,self.get_prem_link)
		await self.bot.loop.run_in_executor(None,self.get_prem_data)
		await ctx.send(self.prem_link)
	
	# Debug command - Force Test
	@commands.command()
	@commands.is_owner()
	async def forcemt(self,ctx):
		m = await ctx.send('DEBUG: Starting a match thread...')
		post = await self.start_match_thread()
		await m.edit(content=f'DEBUG: {post.url}')
	
	@commands.command()
	@commands.is_owner()
	async def checkmtb(self,ctx):
		await ctx.send(f'Debug; self.nextmatch = {self.nextmatch}')
		await ctx.send()
	
	@commands.command()
	@commands.is_owner()
	async def killmt(self,ctx):
		m = await ctx.send("Cancelling...")
		self.stopmatchthread = True
		await m.edit(content="Match thread ended early.")
		
	# Debug Command Live
	@commands.command()
	@commands.is_owner()
	async def dry_live(self,ctx):
		await ctx.send('Running. Check Console.')
		self.bbclink = "http://www.bbc.co.uk/sport/live/football/42709993"
		await self.scrape_live()
		print("\n".join(self.ticker))
		
def setup(bot):
	bot.add_cog(MatchThread(bot))