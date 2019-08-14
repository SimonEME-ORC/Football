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
import os

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By	
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

class MatchThread(commands.Cog):
	""" MatchThread Bot rewrite."""
	def __init__(self, bot):
		self.bot = bot
		self.driver = None
		
		
		# URLs
		self.bbclink = ""
		
		# Subreddit info
		# r/NUFC 
		self.subreddit = "nufc"
		self.modchannel = self.bot.get_channel(332167195339522048)
		self.teamurl = "newcastle-united"
		
		# # Test channel/Subreddit.
		# self.subreddit = "themagpiescss"
		# self.modchannel = self.bot.get_channel(332167049273016320)
		# self.teamurl = "liverpool"
		
		# Strings.
		self.archive = "[Match Thread Archive](https://www.reddit.com/r/NUFC/wiki/archive)"
		
		self.radio = "[📻 Radio Commentary](https://www.nufc.co.uk/liveAudio.html)"
		self.tickerheader = ""
		self.botdisclaimer = "\n\n---\n\n^(*Beep boop, I am /u/Toon-bot, a bot coded ^badly by /u/Painezor. If anything appears to be weird or off, please let him know.*)"
		
		# Match Data
		self.attendance = ""
		self.referee = ""
		self.reflink = ""
		self.stadium = ""
		self.kickoff = ""
		self.score = "vs"
		self.matchstats = ""
		self.goals = ""
		self.subs = set()
		self.hometeam = ""
		self.awayteam = ""
		self.homexi = ""
		self.awayxi = ""
		self.competition = ""
		self.ticker = []
		self.penalties = ""
		
		# Bonus
		self.premlink = ""
		self.formations = ""
		self.matchpictures = []
		self.matchsummary = ""
		
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
		self.schedtask = self.bot.loop.create_task(self.scheduler())
		
		# MT Task
		self.stopmatchthread = False
	
	def nufccheck(ctx):
		if ctx.guild:
			return ctx.guild.id in [238704683340922882,332159889587699712]
	
	def __unload(self):
		# Cancel Scheduler loop
		self.schedtask.cancel()
		self.stopmatchthread = True
		
		# Exit Selenium Scraper
		if self.driver:
			self.driver.quit()
	
	# Spawn an instance of headerless chrome.
	def spawn_chrome(self):
		caps = DesiredCapabilities().CHROME
		caps["pageLoadStrategy"] = "normal"  #  complete
		chrome_options = Options()
		chrome_options.add_argument('log-level=3')
		chrome_options.add_argument("--headless")
		chrome_options.add_argument("--window-size=1920x1200")
		chrome_options.add_argument('--no-proxy-server')
		
		driver_path = os.getcwd() +"\\chromedriver.exe"
		prefs = {'profile.default_content_setting_values': {'images': 2, 'javascript': 2}}
		chrome_options.add_experimental_option('prefs', prefs)
		self.driver = webdriver.Chrome(desired_capabilities=caps,chrome_options=chrome_options, executable_path=driver_path)
		self.driver.set_page_load_timeout(20)
		self.driver.implicitly_wait(10)
	
	# Loop to check when to post.-
	async def scheduler(self):
		""" This is the bit that determines when to run a match thread """
		while not self.bot.is_closed():
			# Scrape the next kickoff date & time from the fixtures list on r/NUFC
			async with self.bot.session.get("https://www.nufc.co.uk/matches/first-team") as resp: 
				if resp.status != 200:
					print(f'{resp.status} error in scheduler.')
					await asycio.sleep(10)
					continue
				
				tree = html.fromstring(await resp.text())
				nextfix = tree.xpath('.//div[@class="fixtures__item"]//p[@content]//text()')[0]
				
				nextfix = nextfix.replace("3rd","3").replace("th","").replace("1st","1").replace("2nd","2")
				nextfix = nextfix.strip().split(" ",1)
				
				nextfix[0] = nextfix[0].rjust(2,"0")
				nextfix = " ".join(nextfix)
				print(nextfix)
				
				next = datetime.datetime.strptime(nextfix,"%d %B %Y %I:%M %p")
				
				now = datetime.datetime.now()
				postat = next - now - datetime.timedelta(minutes=15)
				
				
				self.nextmatch = next
				postat = next - now - datetime.timedelta(minutes=15)
				
				self.postat = postat
				# Calculate when to post the next match thread
				sleepuntil = (postat.days * 86400) + postat.seconds
				
				if sleepuntil > 0:
					print(f"The next match thread will be posted in: {sleepuntil} seconds")
					await asyncio.sleep(sleepuntil) # Sleep bot until then.
					await self.do_match_thread()
					await asyncio.sleep(180)
				else:
					await asyncio.sleep(86400)
					
	async def do_match_thread(self):
		""" Core function """
		# Fetch Link from BBC Sport Match Page.
		async with self.bot.session.get(f"http://www.bbc.co.uk/sport/football/teams/{self.teamurl}/scores-fixtures") as resp:
			tree = html.fromstring(await resp.text(encoding="utf-8"))
			self.bbclink = tree.xpath(".//a[contains(@class,'sp-c-fixture')]/@href")[-1]
			self.bbclink = f"http://www.bbc.co.uk{self.bbclink}"

		# Fetch pre-match thread.
		async with self.bot.session.get("https://www.reddit.com/r/NUFC/") as resp:
			tree = html.fromstring(await resp.text())
			for i in tree.xpath(".//p[@class='title']/a"):
				title = "".join(i.xpath('.//text()'))
				if "match" not in title.lower():
					continue
				if not title.lower().startswith("pre"):
					continue
				else:
					self.prematchthread = "".join(i.xpath('.//@href'))
					if self.prematchthread:
						self.prematchthread = f"[Pre-Match Thread]({self.prematchthread})"
					return
		
		# Scrape Initial Data.
		await self.scrape()
		
		# Bonus data if prem.
		if "Premier League" in self.competition:
			await self.bot.loop.run_in_executor(None,self.get_premlink)
			await self.bot.loop.run_in_executor(None,self.get_prem_data)
			print(f"Premier league game. Additional Data should be parseable: {self.premlink}")
		else:
			print(f"Not premier league - {self.competition}")

		# Find TV listings.
		await self.fetch_tv()

		# Get Subreddit info
		try:
			self.homereddit = self.bot.teams[self.hometeam]['subreddit']
		except KeyError:
			pass
		try:
			self.awayreddit = self.bot.teams[self.awayteam]['subreddit']
		except KeyError:
			pass
			
		# Get Icons
		try:
			self.homeicon = self.bot.teams[self.hometeam]['icon']
		except KeyError:
			pass
		try:
			self.awayicon = self.bot.teams[self.awayteam]['icon']
		except KeyError:
			pass			
		# Get Stadium
		try:
			self.stadium = self.bot.teams[self.hometeam]['stadium']
		except KeyError:
			pass
		try:	
			stadiumlink = self.bot.teams[self.hometeam]['stadlink']
		except KeyError:
			pass
		if self.stadium and stadiumlink:
			self.stadium = f"[{self.stadium}]({stadiumlink})"
		
		# Write Markdown
		markdown = await self.write_markdown(False)
		
		# Post initial thread.
		threadname = f"Match Thread: {self.hometeam} vs {self.awayteam}"
		post = await self.bot.loop.run_in_executor(None,self.makepost,threadname,markdown)
		self.matchthread = f"[Match Thread]({post.url})"
		
		e = discord.Embed(color=0xff4500)
		th = ("http://vignette2.wikia.nocookie.net/valkyriecrusade/images"
			  "/b/b5/Reddit-The-Official-App-Icon.png")
		e.set_author(icon_url=th,name="Match Thread Bot")
		e.description = (f"[{post.title}]({post.url}) created.")
		e.timestamp = datetime.datetime.now()
		await self.modchannel.send(embed=e)
		
		# Commence loop.
		while not self.stopmatchthread:
			# Scrape new data
			await self.scrape()
			if self.premlink:
				await self.bot.loop.run_in_executor(None,self.get_prem_data)
			
			# Rebuild markdown
			markdown = await self.write_markdown(False)
			
			# Edit post
			await self.bot.loop.run_in_executor(None,self.editpost,post,markdown)

			# Repeat
			await asyncio.sleep(60)
		
		# Post-loop
		# Scrape final data
		await self.scrape()
		if self.premlink:
			await self.bot.loop.run_in_executor(None,self.get_prem_data)
		
		# Rebuild markdown
		markdown = await self.write_markdown(True)	
		threadname = f"Post-Match Thread: {self.hometeam} {self.score} {self.awayteam}"
		post = await self.bot.loop.run_in_executor(None,self.makepost,threadname,markdown)
		e.description = (f"[{post.title}]({post.url}) created.")
		await self.modchannel.send(embed=e)	
		return post.url
		
	# Formatting.
	async def write_markdown(self,ispostmatch):
		markdown = ""
		
		# Date and Competion bar
		markdown += f"#### {self.kickoff} | {self.competition}\n\n"
		
		# Score bar
		homestring = f"[{self.hometeam}]({self.homereddit})" if self.homereddit else self.hometeam
		homestring = f"{self.homeicon}{homestring}"
		awaystring = f"[{self.awayteam}]({self.awayreddit})" if self.awayreddit else self.awayteam
		awaystring = f"{awaystring}{self.awayicon}"
		markdown += f"# {homestring} {self.score} {awaystring}\n\n"
		
		# Match Threads Bar.
		mts = [self.prematchthread,self.matchthread,self.archive]
		mts = [i for i in mts if i]
		markdown += "---\n\n##" + " | ".join(mts) + "\n\n---\n\n"
		
		# Ref, Venue, Radio, TV.		
		markdown += f"[🥅](#icon-net)**Venue**: {self.stadium}"
		
		if self.attendance:
			markdown += f" (👥 Attendance: {self.attendance})"
		markdown += "\n\n"
			
		if self.referee:
			markdown += f"[](#icon-whistle)**Refree**: [{self.referee}]({self.reflink})\n\n"		
		
		if "Newcastle United" in [self.hometeam,self.awayteam]:
			markdown += f"{self.radio}\n\n"
		
		if not ispostmatch:
			if self.uktv:
				markdown += f"📺 **Television Coverage** (UK): {self.uktv}\n\n"
			if self.tvlink:
				markdown += f"📺🌍 **Television Coverage** (International): {self.tvlink}\n\n"
				
		if any([self.homexi,self.awayxi]):
			markdown += "---\n\n# Lineups\n\n"
			markdown += f"{self.homeicon} {self.hometeam} | {self.awayteam} {self.awayicon}\n"
			markdown += "--:|:--\n"
			
			# >>> Convert Subinfo to same format as goals.
			scorers = [i.split(' ',1) for i in self.goals]
			for i,j in list(zip(self.homexi,self.awayxi)):
				for k,l in scorers:
					l = l.strip(",")
					if k in i.split(' ')[1]:
						i += f" [⚽](#icon-ball) {l}".strip(",")
					if k in j.split(' ')[1]:
						j += f" [⚽](#icon-ball) {l}".strip(",")
				for k,l in self.subs:
					if k in i.split(' ')[1]:
						i += f" [🔄](#icon-sub) {l}"
					if k in j.split(' ')[1]:
						j += f" [🔄](#icon-sub) {l}"
						
				markdown += f"{i} | {j}\n"
		
		if self.formations:
			markdown += f"[Formations]({self.formations})\n\n"
		
		if self.matchstats:
			markdown += f"---\n\n# Match Stats	"
			markdown += f"{self.matchstats}\n\n"	
		
		if self.matchpictures:
			markdown += "## Match Photos\n\n* " + '\n\n* '.join(self.matchpictures) + "\n\n"
		
		if not ispostmatch:
			if self.ticker:
				markdown += self.tickerheader + "\n\n---\n\n" + '\n\n'.join(self.ticker) + "\n\n"
		else:
			if self.matchsummary:
				markdown += "###Match Summary\n\n{self.matchsummary}"
		
		if self.penalties:
			self.penalties = self.penalties.replace(self.hometeam,f"{self.homeicon} {self.hometeam}")
			self.penalties = self.penalties.replace(self.awayteam,f"{self.awayicon} {self.awayteam}") 
			markdown += "# " + self.penalties + "\n\n"
		
		markdown += f"{self.botdisclaimer}\n\n"
		
		return markdown
			
	# Get Premier League Website data.
	def get_premlink(self):
		self.spawn_chrome()
		self.driver.get("https://www.premierleague.com/")	

		src = self.driver.page_source
		tree = html.fromstring(src)
		
		self.premlink = "https://www.premierleague.com/" + tree.xpath('.//nav[@class="mcNav"]//a[.//abbr[@title="Newcastle United"]]')[0].attrib["href"]
		return self.driver.quit()

	# Let's merge these scrapes...
	async def scrape(self):
		async with self.bot.session.get(self.bbclink) as resp:
			if resp.status != 200:
				return
			tree = html.fromstring(await resp.text(encoding="utf-8"))
	
			# Date & Time
			if not self.kickoff:
				kodate = "".join(tree.xpath('.//div[@class="fixture_date-time-wrapper"]/time/text()')).title()
				kotime = "".join(tree.xpath('.//span[@class="fixture__number fixture__number--time"]/text()'))
				self.kickoff = f"{kotime} {kodate}"

			# Teams
			if not self.hometeam:
				self.hometeam = tree.xpath('.//span[@class="fixture__team-name-wrap"]//abbr/@title')[0]
			if not self.awayteam:
				self.awayteam = tree.xpath('.//span[@class="fixture__team-name-wrap"]//abbr/@title')[1]
			
			# Goals
			self.score = " - ".join(tree.xpath("//span[contains(@class,'fixture__number')]//text()")[0:2])
			self.goals = tree.xpath('.//ul[contains(@class,"fixture__scorers")]//li')
			self.goals = ["".join(i.xpath(".//text()")) for i in self.goals]
			self.goals = [i.replace(' minutes','').replace('pen','p.') for i in self.goals]
			
			# Penalty Win Bar
			self.penalties = "".join(tree.xpath(".//span[@class='gel-brevier fixture__win-message']/text()"))
			
			# Referee & Attendance
			if not self.competition:
				self.competition = "".join(tree.xpath(".//span[@class='fixture__title gel-minion']/text()"))
			if not self.attendance:
				self.attendance = "".join(tree.xpath("//dt[contains(., 'Attendance')]/text() | //dt[contains(., 'Attendance')]/following-sibling::dd[1]/text()"))				
			
			if not self.referee:
				self.referee = "".join(tree.xpath("//dt[contains(., 'Referee')]/text() | //dt[contains(., 'Referee')]/following-sibling::dd[1]/text()"))
				url = 'http://www.transfermarkt.co.uk/schnellsuche/ergebnis/schnellsuche'
				p = {"query":self.referee,"Schiedsrichter_page":"0"}
				async with self.bot.session.get(url,params=p) as resp:
					alttree = html.fromstring(await resp.text())
					matches = f".//div[@class='box']/div[@class='table-header'][contains(text(),'referees')]/following::div[1]//tbody/tr"
					trs = alttree.xpath(matches)
					if trs:
						self.reflink = trs[0].xpath('.//td[@class="hauptlink"]/a/@href')[0]
						self.reflink = f"http://www.transfermarkt.co.uk/{self.reflink}"
						self.referee = f"[{self.referee}]({self.reflink})"
				
			# Lineups
			def parse_players(players):
				squad = []
				count = 0
				for i in players:
					name = i.xpath('.//span[2]/abbr/span/text()')[0]
					number = i.xpath('.//span[1]/text()')[0]
										
					# Bookings / Sending offs.
					info = "".join(i.xpath('.//span[2]/i/@class')).replace('sp-c-booking-card sp-c-booking-card--rotate sp-c-booking-card--yellow gs-u-ml','[Yel](#icon-yellow) ').replace('booking-card booking-card--rotate booking-card--red gel-ml','[Red](#icon-red) ')
					if info:
						info += " ".join(i.xpath('.//span[2]/i/span/text()')).replace('Booked at ','').replace('mins','\'')
					try:
						subbed = f"{i.xpath('.//span[3]/span//text()')[1]}{i.xpath('.//span[3]/span//text()')[3]}"
						self.subs.add((name,subbed))
					except IndexError:
						pass
					
					# Italicise Subs
					count += 1
					if count < 12:
						name = f"*{name}*"
					
					squad.append(f"**{number}** {name} {info}".strip())

				return squad

			self.homexi = parse_players(tree.xpath('.//div[preceding-sibling::h2/text()="Line-ups"]/div/div/div[1]//ul/li'))
			self.awayxi = parse_players(tree.xpath('.//div[preceding-sibling::h2/text()="Line-ups"]/div/div/div[2]//ul/li'))
			
			# Stats
			statlookup = tree.xpath("//dl[contains(@class,'percentage-row')]")
			if statlookup:
				self.matchstats = f"\n{self.homeicon} {self.hometeam}|v|{self.awayteam} {self.awayicon}\n--:|:--:|:--\n"
				for i in statlookup:
					stat = "".join(i.xpath('.//dt/text()'))
					dd1 = "".join(i.xpath('.//dd[1]/span[2]/text()'))
					dd2 = "".join(i.xpath('.//dd[2]/span[2]/text()'))
					self.matchstats += f"{dd1} | {stat} | {dd2}\n"
					
			# Ticker
			self.tickerheader = f"### Match updates (via [](#icon-bbc)[BBC]({self.bbclink}))\n\n"
			ticker = tree.xpath("//div[@class='lx-stream__feed']/article")
			await self.parse_ticker(ticker)
			
	async def fetch_tv(self):
		try:
			tvurl = f"http://www.livesoccertv.com/teams/england/{self.bot.teams[self.hometeam]['bbcname']}"
		except KeyError as e:
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
				if "U21" in match:
					continue 
				else:
					live = "".join(i.xpath('.//td[1]//text()')).strip()
					if "FT" in live:
						continue
				
				date = "".join(i.xpath('.//td[4]//text()')).strip()
				if "postp." in date.lower():
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
			
	async def parse_ticker(self,ticker):
		# .reverse() so bottom to top.
		ticker.reverse()
		for i in ticker:
			header = "".join(i.xpath('.//h3//text()')).strip()
			time = "".join(i.xpath('.//time//span[2]//text()')).strip()
			if time:
				time += ":"
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
			time = "".join(i.xpath('.//div[@class="cardMeta"]//time/text()'))
			if time:
				time += ":"
			content = "".join(i.xpath('.//p/text()'))
			
			tick = self.format_tick(header,time,content)
			if tick not in self.ticker:
				self.ticker.append(tick)
			
	def format_tick(self,header,time,content):
		# Swap in icons
		if self.homeicon:
			content = content.replace(self.hometeam,f"{self.homeicon}{self.hometeam}")
		if self.awayicon:
			content = content.replace(self.awayteam,f"{self.awayicon}{self.awayteam}")
		
		# Format by header.
		if "kick off" in header.lower():
			header = "[⚽](#icon-ball) Kick Off:"
			content = content.replace('Kick Off ',"")
			
		elif "get involved" in header.lower():
			return ""
		
		elif "goal" in header.lower():
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
			header = f"[Yellow Card](#icon-yellow)"
		
		elif "dismissal" in header.lower():
			if "second yellow" in content.lower():
				header = f"[**OFF!**](#icon-2yellow) RED CARD"
			else:
				header = f"[**OFF!**](#icon-red) RED CARD"
		
		elif "half time" in header.lower().replace('-',' '):
			header = "# Half Time"
		
		elif "second half" in header.lower().replace('-',' '):
			header = "# Second Half"
			content = content.replace('Second Half',' ')
		
		elif "full time" in header.lower().replace('-',' '):
			header = "# FULL TIME"
			if self.homeicon:
				homestring = f"{self.homeicon}{self.hometeam}"
			else:
				homestring = self.hometeam
				
			if self.awayicon:
				awaystring = f"{self.awayteam}{self.awayicon}"
			else:
				awaystring = self.awayteam
			
			content = f"{homestring} {self.score} {awaystring}"
		elif "penalties in progress" in header.lower().strip():
			header = "# Penalty Shootout\n\n"
			content = "---\n\n"
			
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
				header = "[](#icon-OG) **PENALTY SAVED**"
				content = content.replace("Penalty saved!","")
			
		if "match ends" in content.lower():
				self.stopmatchthread = True
	
		return " ".join([header,time,content]).strip()

	
	def get_prem_data(self):
		if not self.premlink:
			print("Prem link not retrieved")
			return
		self.spawn_chrome()
		self.driver.get(self.premlink)
		tree = html.fromstring(self.driver.page_source)
		# Get ticker
		if not self.tickerheader or "premierleague.com" in self.tickerheader:
			self.tickerheader = "##"
			ticker = tree.xpath('.//ul[@class="commentaryContainer"]/li')
			ticker = self.parse_ticker(ticker)
		self.matchsummary = "\n".join(tree.xpath('.//div[@class="matchReportStreamContainer"]/p/text()'))
		
		# Get Match pictures.
		pics = tree.xpath('.//ul[@class="matchPhotoContainer"]/li')
		for i in pics:
			url = "".join(i.xpath('.//div[@class="thumbnail"]//img/@src'))
			caption = "".join(i.xpath('.//span[@class="captionBody"]/text()'))
			if not url and not caption:
				continue
			thispic = f"[{caption}]({url})"
			if thispic not in self.matchpictures:
				self.matchpictures.append(thispic)
				
		# Get Formations		
		if not self.formations:
			try:
				z = self.driver.find_element_by_xpath(".//ul[@class='tablist']/li[@class='matchCentreSquadLabelContainer']")
				z.click()
				WebDriverWait(self.driver, 2)
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
			except:
				pass
		
		self.driver.quit()
	
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

	# Post to IMGUR
	async def upload_formation(self):
		d = {"image":open("formations.png",'rb')}
		h = {'Authorization': self.bot.credentials["Imgur"]["Authorization"]}
		async with self.bot.session.post("https://api.imgur.com/3/image",data = d,headers=h) as resp:
			res = await resp.json()
		print(f"Debug: --- Formation upload ---\n{res}")
		self.formations = res['data']['link']		
		
	def get_formation(self):
		self.spawn_chrome()
		self.driver.get(self.premlink)
		WebDriverWait(self.driver, 2)
		z = self.driver.find_element_by_xpath(".//ul[@class='tablist']/li[@class='matchCentreSquadLabelContainer']")
		z.click()
		
		WebDriverWait(self.driver, 2)
		
		# Get location & Size
		lineup = self.driver.find_element_by_xpath(".//div[@class='mcTabs']")
		loc = lineup.location
		size = lineup.size
		self.driver.save_screenshot('Debug.png')

		# Crop
		im = Image.open(BytesIO(lineup.screenshot_as_png))
		
		left = loc['x']
		top = loc['y']
		right = loc['x']
		bottom = loc['y']
		im = im.crop((left, top, right, bottom))
		
		im.save("formations.png")
		return self.driver.quit()
		
	# Debug command - Force Test
	@commands.command()
	@commands.is_owner()
	async def forcemt(self,ctx):
		m = await ctx.send('DEBUG: Starting a match thread...')
		post = await self.do_match_thread()
		await ctx.send(post)
	
	@commands.command()
	@commands.is_owner()
	async def checkmtb(self,ctx):
		await ctx.send(f'Debug; self.nextmatch = {self.nextmatch}')
		if self.nextmatch:
			await ctx.send(f'Match thread will be posted in: {self.nextmatch - datetime.datetime.now() - datetime.timedelta(minutes=15)}')
		else:
			await ctx.send('Couldn\'t find next match.')
	
	@commands.command()
	@commands.is_owner()
	async def killmt(self,ctx):
		self.stopmatchthread = True
		await ctx.send('Ending match thread on next loop.')
	
	@commands.is_owner()
	@commands.group()
	async def override(self,ctx,var,*,value):
		setattr(self,var,value)
		await ctx.send(f'Match Thread Bot: Setting "{var}" to "{value}"')		
	
def setup(bot):
	bot.add_cog(MatchThread(bot))