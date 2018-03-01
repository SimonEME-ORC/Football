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
		
		# Discord and Subreddit
		# r/NUFC 
		# self.subreddit = "NUFC"
		# self.modchannel = self.bot.get_channel(332167195339522048)
		
		# Painezor's Test Server/Subreddit.
		self.subreddit = "themagpiescss"
		self.modchannel = self.bot.get_channel(250252535699341312)
		
		# URLs
		self.bbclink = ""
		self.prematchthread = ""
		self.matchthread = ""
		
		# Strings.
		self.discord = "https://discord.gg/tbyUQTV"
		self.archive = "https://www.reddit.com/r/NUFC/wiki/archive"
		
		# self.teamurl = "newcastle-united"	
		self.teamurl = "huddersfield-town" # DEBUG
		self.radio = "[📻 Radio Commentary](https://www.nufc.co.uk/liveAudio.html)"
		self.bbcheader = f"##Match updates (from [](#icon-bbc)[bbc]({self.bbclink}))"
		self.botdisclaimer = "*beep boop, I am /u/Toon-bot, a bot coded by /u/Painezor. If anything appears to be weird or off, please let him know.*"
		
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
		self.formations = ""
		self.hometeam = ""
		self.awayteam = ""
		self.substituted = set()
		self.ticker = set()
		
		# Reddit info
		self.homereddit = ""
		self.homeicon = ""
		self.awayreddit = ""
		self.awayicon = ""
		self.prematch = ""
		self.matchthread = ""
		
		# TV info
		self.tvlink = ""
		self.uktvchannels = ""
		self.uktvlinks = ""
		
		# Scheduler
		self.scheduling = True
		self.schedtask = self.bot.loop.create_task(self.scheduler())
		
		# MT Task
		self.match_thread_task = ""
		self.stopmatchthread = False
		
	def __unload(self):
		# Scheduler loop
		self.schedtask.cancel()
		
		# Selenium Scraper
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
		return
		
	# Match Thread Loop
	async def start_match_thread(self):
		""" Core function """
		# Fetch Link from BBC Sport Match Page.
		await self.get_bbc_link()
		if self.bbclink.isdigit():
			await self.modchannel.send(f"🚫 Match Thread Failed, error, bbclink is {self.bbclink}")
			return
		
		# Fetch pre-match thread.
		await self.fetch_prematch()
		
		# Scrape Initial Data.
		if "/live/" in self.bbcurl:
			await self.scrape_live()
		else:
			await self.scrape_normal()
		
		# Bonus data if prem.
		if "Premier League" in self.competition:
			await self.bot.loop.run_in_executor(None,self.get_prem_link)
			await self.bot.loop.run_in_executor(None,self.get_prem_data)

		# Find TV listings.
		await self.fetch_tv()
		
		# Get Subreddit info & badges.
		await self.get_team_reddit_info()
		
		# Write Markdown
		markdown = await self.write_markdown()
		
		# Post initial thread.
		post = await self.bot.loop.run_in_executor(None,self.makepost,threadname,toptext)
		self.matchthread = post.url
		
		# Commence loop.
		while not self.stopmatchthread:
			# Scrape new data
			
			# Edit post
			
			# Repeat
			await asyncio.sleep(60)
				
	
	# Formatting.
	async def write_markdown(self):
		markdown = ""
		
		if self.homeicon:
			homestring = f"{self.homeicon}{self.hometeam}"
		else:
			homestring = self.hometeam
		if self.homereddit:
			homestring = f"[{homestring}](self.homereddit)"
			
		if self.awayicon:
			awaystring = f"{self.awayteam}{self.awayicon}"
		else:
			awaystring = self.awayteam
		if self.awayreddit:
			homestring = f"[{awaystring}](self.awayreddit)"
			
		titleline = f"# {homestring} {self.score} {awaystring}\n\n"
		markdown += titleline
		
		kickoff = "[🕒](#icon-clock)**Kick-Off**: {self.kickoff}\n\n"
		markdown += kickoff
		
		competition = "[](#icon-trophy)**Competition**: {self.competition}\n\n"
		markdown += competition
		
		if self.stadium:
			if self.stadiumlink:
				venue = "[🥅](#icon-net)**Venue**: [{self.stadium}]({self.stadiumlink})\n\n"
			else:
				venue = "[🥅](#icon-net)**Venue**: {self.stadium}\n\n"
			markdown += venue
		
		if self.referee:
			if self.reflink:
				referee = "[](#icon-whistle)**Refree**: [{self.referee}]({self.reflink})\n\n"
			else:
				referee = "[](#icon-whistle)**Refree**: {self.referee}\n\n"
			markdown += referee
			
		if self.attendance:
			markdown += f"**Attendance: {self.attendance}\n\n"
			
		return markdown
			
	# Get Premier League Website data.
	def get_prem_link(self):
		if not self.driver:
			self.bot.loop.run_in_executor(None,self.spawn_phantom)
		
		self.driver.get("http://www.premierleague.com/fixtures")
		WebDriverWait(self.driver, 5)
		self.driver.implicitly_wait(10)
		
		self.driver.find_elements_by_xpath("//span[@class='teamName' and contains(text(), 'Newcastle')]")[0].click()

		WebDriverWait(self.driver, 5)
		
		self.premlink = self.driver.current_url
		
	# Scrape Fixtures to get current match
	async def get_bbc_link(self):
		async with self.bot.session.get(f"http://www.bbc.co.uk/sport/football/teams/{self.teamurl}/scores-fixtures") as resp:
			if resp.status != 200:
				self.bbclink = f"{resp.status}"
				return
			tree = html.fromstring(await resp.text(encoding="utf-8"))
			self.bbclink = tree.xpath(".//a[contains(@class,'sp-c-fixture')]/@href")[-1]
			self.bbcheader = f"##MATCH UPDATES (COURTESY OF [](#icon-bbc)[BBC]({self.bbclink}))"
			return
	
	# Scrape data NORMAL version
	async def scrape_normal(self):
		async with self.bot.session.get(self.bbcurl) as resp:
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
		

			# Ticker
			ticker = tree.xpath(".//div[@class='lx-stream__feed']/article")

			await self.parse_ticker_normal(ticker)		
			
	# Scrape data (LIVE version)
	async def scrape_live(self):
		async with self.bot.session.get(self.bbcurl) as resp:
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
			
			# Ticker
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
					return
	
	async def fetch_tv(self):
		try:
			tvurl = f"http://www.livesoccertv.com/teams/england/{self.bot.teams[self.hometeam]['bbcname']}"
		except KeyError:
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
				self.uktvchannels = i.xpath('.//td[2]/a/text()')
				self.uktvlinks = i.xpath('.//td[2]/a/@href')
				self.uktvlinks = [f'http://www.livesoccertv.com/{i}' for i in self.uktvlinks]
	
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
				name = f"*{name}"
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
			self.ticker.add(tick)
	
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
			self.ticker.add(tick)

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
			self.ticker.append(tick)
			
	def format_tick(self,header,time,content):
		# Swap in icons
		key = False
		if self.homeicon:
			content = content.replace(self.hometeam,f"[{self.homeicon}]({self.hometeam})")
		if self.awayicon:
			content = content.replace(self.awayteam,f"[{self.awayicon}]({self.awateam})")
		
		# Format by header.
		if "goal" in header.lower():
			key = True
			if "own goal" in content.lower():
				header = "[⚽](#icon-og) **OWN GOAL**"
			else:
				header = "[⚽](#icon-ball) **GOAL**"
			
			content = content.replace('Goal! ','').strip()		
		
		elif "substitution" in header.lower():
			header = f"[🔄][#icon-sub] **Substitution for"
			team,subs = content.replace("Substitution, ","").split('.',1)
			on,off = subs.split('replaces')
			content = f" {team}** [⬆](#icon-up){on} [⬇](#icon-down){off}"
			
		elif "booking" in header.lower():
			header = f"[YC](#icon-yellow)"
		
		elif "dismissal" in header.lower():
			key = True
			if "second yellow" in content.lower():
				header = f"[OFF!](#icon-2yellow) RED CARD"
			else:
				header = f"[OFF!](#icon-red) RED CARD"
		
		elif "full time" in header.lower():
			self.match_ended = True
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
		if not self.premlink:
			return
		self.spawn_phantom() # Delete after testing.
		self.driver.get(self.premlink)
		WebDriverWait(self.driver, 5)
		
		# Get ticker
		if "live" in self.bbclink or not self.bbclink:
			tree = html.fromstring(self.driver.page_source)
			ticker = tree.xpath('.//ul[@class="commentaryContainer"]/li')
			ticker = self.parse_ticker_prem(ticker)
		
		
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
		top = 980
		right = left + 274
		bottom = top + 561
		
		print(left,top,right,bottom)
		im = im.crop((left, top, right, bottom))
		
		im.save("formations.png")
		self.driver.save_screenshot('Debug.png')
		
		# self.formations = self.bot.loop.create_task(self.upload_formation,"formations.png")
		
		# Get Match pictures.
	
	

	async def upload_formation(self,im):
		d = {"image":imgurl}
		h = {'Authorization': self.bot.credentials["Imgur"]["Authorization"]}
		async with self.bot.session.post("https://api.imgur.com/3/image",data = d,headers=h) as resp:
			res = await resp.json()
		return res['data']['link']	
	
	# Reddit posting shit.
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
	
	# Debug command - Force Test
	@commands.command()
	@commands.is_owner()
	async def forcemt(self,ctx):
		m = await ctx.send('DEBUG: Starting a match thread...')
		post = await self.start_match_thread()
		await m.edit(content=f'DEBUG: {post.url}')
		
	@commands.command()
	@commands.is_owner()
	async def killmt(self,ctx):
		pass
	
	# Debug command - fixtures
	@commands.command()
	@commands.is_owner()
	async def formation(self,ctx):
		await self.upload_formation('formations.png')
	
	# Debug command - PL site.
	@commands.command()
	@commands.is_owner()
	async def prem(self,ctx):
		# self.premlink = "https://www.premierleague.com/match/22606"# Man Utd vs NCL
		self.premlink = "https://www.premierleague.com/match/22600" # Watford vs Chelsea
		
		await self.bot.loop.run_in_executor(None,self.get_prem_data)
		await ctx.send(file=discord.File('formations.png'))
		
	# Debug Command
	@commands.command()
	@commands.is_owner()
	async def dry_run(self,ctx):
		await ctx.send('Running. Check Console.')
		# self.bbcurl = "http://www.bbc.co.uk/sport/football/42756095" # FA Cup / Peterboro - Leicester
		self.bbcurl = "http://www.bbc.co.uk/sport/football/42849448"
		await self.start_match_thread()
		
	# Debug Command Live
	@commands.command()
	@commands.is_owner()
	async def dry_live(self,ctx):
		await ctx.send('Running. Check Console.')
		self.bbcurl = "http://www.bbc.co.uk/sport/live/football/42709993"
		await self.scrape_live()
		print("\n".join(self.ticker))
		
def setup(bot):
	bot.add_cog(MatchThread(bot))