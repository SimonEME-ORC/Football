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

# >>> Convert upcoming matches to dict
# >>> Convert upcoming matches to get bbc data.

class MatchThreadCommands(commands.Cog):
	""" MatchThread Bot rewrite."""
	def __init__(self, bot):
		self.bot = bot
		self.scheduledthreads = []
		self.activethreads = []
		self.bot.loop.create_task(self.get_schedule())
		self.activemodule = True
		self.stopmatchthread = False
		
	def cog_unload(self):
		self.activemodule = False
	
	async def scrape(self,bbclink,subhasicons=False):
		matchdata = {"uktv":"","tvlink":""}
		async with self.bot.session.get(bbclink) as resp:
			if resp.status != 200:
				return
			tree = html.fromstring(await resp.text(encoding="utf-8"))
	
			# Date & Time
			kodate = "".join(tree.xpath('.//div[@class="fixture_date-time-wrapper"]/time/text()')).title()
			kotime = "".join(tree.xpath('.//span[@class="fixture__number fixture__number--time"]/text()'))
			matchdata["kickoff"] = f"{kotime} {kodate}"
			
			# Teams
			matchdata["hometeam"] = tree.xpath('.//span[@class="fixture__team-name-wrap"]//abbr/@title')[0]
			matchdata["awayteam"] = tree.xpath('.//span[@class="fixture__team-name-wrap"]//abbr/@title')[1]		
			
			# Get Icons
			if subhasicons:
				try:
					homeicon = self.bot.teams[matchdata["hometeam"]]['icon']
				except KeyError:
					homeicon = ""
				try:
					awayicon = self.bot.teams[matchdata["awayteam"]]['icon']
				except KeyError:
					awayicon = ""
			else:
				homeicon = awayicon = ""
			
			# Get Stadium
			try:
				stadium = self.bot.teams[matchdata["hometeam"]]['stadium']
			except KeyError:
				stadium = ""
			else:
				try:
					stadiumlink = self.bot.teams[matchdata["hometeam"]]['stadlink']
					matchdata["stadium"] = f"[{stadium}]({stadiumlink})"
				except KeyError:
					matchdata["stadium"] = stadium
			
			# Goals
			matchdata["score"] = " - ".join(tree.xpath("//span[contains(@class,'fixture__number')]//text()")[0:2])
			goals = ["".join(i.xpath(".//text()")) for i in tree.xpath('.//ul[contains(@class,"fixture__scorers")]//li')]
			matchdata["goals"] = [i.replace(' minutes','').replace('pen','p.') for i in goals]
			
			# Penalty Win Bar
			matchdata["penalties"] = "".join(tree.xpath(".//span[@class='gel-brevier fixture__win-message']/text()"))
			
			# Referee & Attendance
			matchdata["competition"] = "".join(tree.xpath(".//span[@class='fixture__title gel-minion']/text()"))
			matchdata["attendance"] = "".join(tree.xpath("//dt[contains(., 'Attendance')]/text() | //dt[contains(., 'Attendance')]/following-sibling::dd[1]/text()"))				
			
			referee = "".join(tree.xpath("//dt[contains(., 'Referee')]/text() | //dt[contains(., 'Referee')]/following-sibling::dd[1]/text()"))
			url = 'http://www.transfermarkt.co.uk/schnellsuche/ergebnis/schnellsuche'
			p = {"query":referee,"Schiedsrichter_page":"0"}
			async with self.bot.session.get(url,params=p) as resp:
				if resp.status != 200:
					matchdata["referee"] = ""
				else:
					alttree = html.fromstring(await resp.text())
					matches = f".//div[@class='box']/div[@class='table-header'][contains(text(),'referees')]/following::div[1]//tbody/tr"
					trs = alttree.xpath(matches)
					if trs:
						reflink = trs[0].xpath('.//td[@class="hauptlink"]/a/@href')[0]
						reflink = f"http://www.transfermarkt.co.uk/{reflink}"
						matchdata["referee"] = f"[{referee}]({reflink})"
					else:
						matchdata["referee"] = referee
					
			# Lineups
			matchdata["subs"] = []
			def parse_players(players):
				squad = []
				count = 0
				for i in players:
					name = i.xpath('.//span[2]/abbr/span/text()')[0]
					number = i.xpath('.//span[1]/text()')[0]
										
					# Bookings / Sending offs.
					info = "".join(i.xpath('.//span[2]/i/@class'))
					if subhasicons: 
						info = info.replace('sp-c-booking-card sp-c-booking-card--rotate sp-c-booking-card--yellow gs-u-ml','[Yel](#icon-yellow) ')
						info = info.replace('booking-card booking-card--rotate booking-card--red gel-ml','[Red](#icon-red) ')
					else:
						info = info.replace('sp-c-booking-card sp-c-booking-card--rotate sp-c-booking-card--yellow gs-u-ml','⚠ ')
						info = info.replace('booking-card booking-card--rotate booking-card--red gel-ml','🔴 ')
					
					if info:
						info += " ".join(i.xpath('.//span[2]/i/span/text()')).replace('Booked at ','').replace('mins','\'')
					try:
						subbed = f"{i.xpath('.//span[3]/span//text()')[1]}{i.xpath('.//span[3]/span//text()')[3]}"
						matchdata["subs"].append((name,subbed))
					except IndexError:
						pass
					
					# Italicise Subs
					count += 1
					if count > 11:
						name = f"*{name}*"
					
					squad.append(f"**{number}** {name} {info}".strip())

				return squad

			matchdata["homexi"] = parse_players(tree.xpath('(.//div[preceding-sibling::h2/text()="Line-ups"]//div//ul)[1]/li'))
			matchdata["homesubs"] = ", ".join(parse_players(tree.xpath('(.//div[preceding-sibling::h2/text()="Line-ups"]//div//ul)[2]/li')))
			matchdata["awayxi"] = parse_players(tree.xpath('(.//div[preceding-sibling::h2/text()="Line-ups"]//div//ul)[3]/li'))
			matchdata["awaysubs"] = ", ".join(parse_players(tree.xpath('(.//div[preceding-sibling::h2/text()="Line-ups"]//div//ul)[4]/li')))

			# Stats
			statlookup = tree.xpath("//dl[contains(@class,'percentage-row')]")
			matchdata["matchstats"] = ""
			if statlookup:
				for i in statlookup:
					stat = "".join(i.xpath('.//dt/text()'))
					dd1 = "".join(i.xpath('.//dd[1]/span[2]/text()'))
					dd2 = "".join(i.xpath('.//dd[2]/span[2]/text()'))
					matchdata["matchstats"] += f"{dd1} | {stat} | {dd2}\n"
					
			# Ticker
			ticker = tree.xpath("//div[@class='lx-stream__feed']/article")
			
			def format_tick(header,time,content):
				key = False
				# Format by header
				if "kick off" in header.lower():
					if subhasicons:
						header = f"{kotime} [⚽](#icon-ball) Kick Off:"
					else:
						header = f"{kotime} ⚽ Kick Off:"
					content = content.replace('Kick Off ',"")
					
				# Spam header.
				elif "get involved" in header.lower():
					return ""
				
				elif "goal" in header.lower():
					key = True
					if "converts the penalty" in content.lower():
						if penmode:
							header = "[⚽](#icon-ball) **Scored:**" if subhasicons else "⚽ **Scored:**"
						else:
							header = f"{time} ⚽ **Penalty Scored:**" if subhasicons else f"{time} [⚽](#icon-ball) **Penalty Scored:**"
						content = content.replace('converts the penalty with a ',"").title()
					
					elif "own goal" in content.lower():
						header = f"{time} [⚽](#icon-og) **Own Goal:**" if subhasicons else f"{time} ⚽ **Own Goal:**"
							
					else:
						header = f"{time} [⚽](#icon-ball) **Goal:**" if subhasicons else f"{time} ⚽ **Goal:**" 
					content = content.replace('Goal! ','').strip()	
				
				elif "substitution" in header.lower():
					team,subs = content.replace("Substitution, ","").split('.',1)
					on,off = subs.split('replaces')
					
					header = f"{time} [🔄](#icon-sub) Substitution {team}:" if subhasicons else f"{time} 🔄 Substitution {team}:"
					content = f"[⬆](#icon-up){on} for [⬇](#icon-down){off}" if subhasicons else f"⬆{on} for ⬇{off}" 
					
				elif "booking" in header.lower():
					header = f"{time} [⚠](#icon-yellow) Yellow Card:" if subhasicons else f"{time} ⚠ Yellow Card:"
				
				elif "dismissal" in header.lower():
					key = True
					if "second yellow" in content.lower():
						header = f"**{time} [⚠⚠🔴](#icon-2yellow) Red Card** (Second Yellow):" if subhasicons else f"**{time} ⚠⚠🔴 Red Card** (Second Yellow):"
					else:
						header = f"**{time} [🔴](#icon-red) Straight Red Card:**" if subhasicons else f"**{time} 🔴 Straight Red Card:**"
				
				elif "half time" in header.lower().replace('-',' '):
					header = f"**{time} Half Time"
					content += "**"
				
				elif "second half" in header.lower().replace('-',' '):
					header = "Second Half"
					content = content.replace('Second Half',' ')
				
				elif "full time" in header.lower().replace('-',' '):
					header = f"**{time} Full Time"
					content = f"{matchdata['hometeam']} {matchdata['score']} {matchdata['awayteam']}**"
				elif "penalties in progress" in header.lower().strip():
					penmode = True
					header = "# Penalty Shootout\n\n"
					content = "---\n\n"
				elif "penalties over" in header.lower().strip():
					return "---",False
				else:
					if header:
						print(f"MTB: Unhandled header: {header}")
				
					# Format by content.
					elif "injury" in content.lower() or "injured" in content.lower():
						header = f"{time} [🚑](#icon-injury)" if subhasicons else f"{time} 🚑"
					elif "offside" in content.lower():
						header = f"{time} [](#icon-flag)" if subhasicons else time
						content = content.replace("Offside,","Offside:")
					elif content.lower().startswith("corner"):
						header = f"{time} [](#icon-corner)" if subhasicons else time
						content = content.replace("Corner,","Corner:")
					elif "penalty saved" in content.lower():
						key = True
						content = content.replace("Penalty saved!","")
						if penmode:
							header = "[](#icon-OG) **Saved**" if subhasicons else "✖ **Saved**"
							content = content.replace("fails to capitalise on this great opportunity, ","")
						else:
							header = f"**{time} [](#icon-OG) Penalty Saved**" if subhasicons else "{time} ✖ **Saved**"
					else:
						header = time
				if "match ends" in content.lower():
						self.stopmatchthread = True
						header = "#"
						content = content.replace("Match ends, ","")
				
				# Combine
				formatted = " ".join([header,content]).strip()
				return formatted,key
			
			ticks = [f"### Match updates (via [](#icon-bbc)[BBC]({bbclink}))\n\n"] if subhasicons else [f"### Match updates (via [BBC]({bbclink}))\n\n"]
			async def parse_ticker(ticker):
				# .reverse() so bottom to top.
				ticker.reverse()
				for i in ticker:
					header = "".join(i.xpath('.//h3//text()')).strip()
					time = "".join(i.xpath('.//time//span[2]//text()')).strip()
					if time:
						time += ":"
					content = "".join(i.xpath('.//p//text()'))
					
					tick,key = format_tick(header,time,content)

					# Filter tick from reupdating & append to ticker.
					if tick not in ticker:
						ticks.append(tick)
						if key:
							keyevents.append(tick)
			
			
			keyevents = ["###Key Events\n\n"]
			await parse_ticker(ticker)
			
			matchdata["ticker"] = ticks
			matchdata["keyevents"] = keyevents
		return matchdata
	
	async def match_thread(self,bbclink="",subreddit="",discordchannel="",resume=False):
		# Only 1 instance should be running
		if not self.activemodule:
			return
		
		subhasicons = True if subreddit in ["nufc","themagpiescss"] else False
		
		# Try to find bbc sports match page.
		async with self.bot.session.get(f"http://www.bbc.co.uk/sport/football/teams/{bbclink}/scores-fixtures") as resp:
			tree = html.fromstring(await resp.text(encoding="utf-8"))
			bbclink = tree.xpath(".//a[contains(@class,'sp-c-fixture')]/@href")[-1]
			bbclink = f"http://www.bbc.co.uk{bbclink}"
		
		if not bbclink:
			return await discordchannel.send(f"Sorry, I couldn't find a match for {bbclink}. Match Thread cancelled")

		# Fetch Pre-Match Thread if available
		async with self.bot.session.get(f"https://www.reddit.com/r/{subreddit}/") as resp:
			tree = html.fromstring(await resp.text())
			prematch = ""
			for i in tree.xpath(".//p[@class='title']/a"):
				title = "".join(i.xpath('.//text()'))
				if "match" not in title.lower():
					continue
				if not title.lower().startswith("pre"):
					continue
				else:
					prematch = "".join(i.xpath('.//@href'))
					prematch = f"[Pre-Match Thread]({prematch})" if prematch else ""
		
		# Scrape our Initial Data
		matchdata = await self.scrape(bbclink,subhasicons)
		
		# Spawn a driver.
		def spawn_chrome():
			caps = DesiredCapabilities().CHROME
			caps["pageLoadStrategy"] = "normal"  #  complete
			chrome_options = Options()
			chrome_options = Options()
			chrome_options.add_argument("--headless")
			chrome_options.add_argument("--window-size=1920x1200")
			chrome_options.add_argument('--no-proxy-server')
			chrome_options.add_argument("--proxy-server='direct://'")
			chrome_options.add_argument("--proxy-bypass-list=*")
			chrome_options.add_argument("--disable-extensions")
			chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
			
			driver_path = os.getcwd() +"\\chromedriver.exe"
			prefs = {'profile.default_content_setting_values': {'images': 2, 'javascript': 2}}
			chrome_options.add_experimental_option('prefs', prefs)
			driver = webdriver.Chrome(desired_capabilities=caps,chrome_options=chrome_options, executable_path=driver_path)
			driver.set_page_load_timeout(20)
			driver.implicitly_wait(10)
			return driver			
		driver = spawn_chrome()
		
		# Bonus data if prem.
		def get_premlink(driver):
			driver.get("https://www.premierleague.com/")	
			src = driver.page_source
			tree = html.fromstring(src)
			srch = matchdata["hometeam"]
			xp = f".//nav[@class='mcNav']//a[.//abbr[@title='{srch}']]"
			 
			try:
				return "https://www.premierleague.com/" + tree.xpath(xp)[0].attrib["href"]
			except:
				return ""
		
		def get_prem_data(driver,premlink):
			driver.get(premlink)
			# Get Match pictures.
			try:
				pics = driver.find_element_by_xpath('.//ul[@class="matchPhotoContainer"]').get_attribute("innerHTML")

				pics = html.fromstring(pics)
				pics = pics.xpath(".//li")
				
				matchpictures = []
				for i in pics:
					url = "".join(i.xpath('.//div[@class="thumbnail"]//img/@src'))
					caption = "".join(i.xpath('.//span[@class="captionBody"]/text()'))
					if not url and not caption:
						continue
					thispic = f"[{caption}]({url})"
					if thispic not in matchpictures:
						matchpictures.append(thispic)
			except:
				matchpictures = []
			
			try:
				z = driver.find_element_by_xpath(".//ul[@class='tablist']/li[@class='matchCentreSquadLabelContainer']")
				z.click()
				WebDriverWait(driver, 2)
				lineup = driver.find_element_by_xpath(".//div[@class='pitch']")
				driver.save_screenshot('Debug.png')

				# Fuck it we're cropping manually.
				im = Image.open(BytesIO(lineup.screenshot_as_png))
				left = 867
				top = 975
				right = left + 325
				bottom = top + 475
				
				im = im.crop((left, top, right, bottom))
				
				fm = im.save("formations.png")
			except:
				fm = ""
			return matchpictures.reverse(),fm
		
		fm = ""
		matchpictures = ""		
		if "Premier League" in matchdata["competition"]:
			try:
				premlink = await self.bot.loop.run_in_executor(None,get_premlink,driver)
			except Exception as e:
				print(e)
				print("During matchthread loop / get premlink.")
				premlink = ""
			if premlink:
				print(f"Premier league game detected. Additional Data should be parseable: {premlink}")
				matchpictures,fm = await self.bot.loop.run_in_executor(None,get_prem_data,driver,premlink)	
				if fm:
					d = {"image":open("formations.png",'rb')}
					h = {'Authorization': self.bot.credentials["Imgur"]["Authorization"]}
					async with self.bot.session.post("https://api.imgur.com/3/image",data = d,headers=h) as resp:
						res = await resp.json()
						fm = res['data']['link']
		try:
			homereddit = self.bot.teams[matchdata["hometeam"]]['subreddit']
		except KeyError:
			homereddit = ""
		try:
			awayreddit = self.bot.teams[matchdata["awayteam"]]['subreddit']
		except KeyError:
			awayreddit = ""
		
		# Get TV info
		async def fetch_tv(matchdata):
			async with self.bot.session.get(f"https://www.livesoccertv.com/") as resp:
				if resp.status != 200:
					print(f"{resp.status} recieved when trying to fetch TV url {tvurl}")
					return matchdata
				tree = html.fromstring(await resp.text())
				for i in tree.xpath(".//tr//a"):
					if matchdata["hometeam"] in "".join(i.xpath(".//text()")):
						lnk = "".join(i.xpath(".//@href"))
						matchdata["tvlink"] = f"http://www.livesoccertv.com{lnk}"
						break
			
			if not matchdata["tvlink"]:
				return matchdata
			
			async with self.bot.session.get(matchdata["tvlink"]) as resp:
				if resp.status != 200:
					print("Failed to fetch TV Link.")
					return matchdata
				tree = html.fromstring(await resp.text())
				tvtable = tree.xpath('.//table[@id="wc_channels"]//tr')
				
				if not tvtable:
					return matchdata
					
				for i in tvtable:
					ctry = i.xpath('.//td[1]/span/text()')
					if "United Kingdom" not in ctry:
						continue
					uktvchannels = i.xpath('.//td[2]/a/text()')
					uktvlinks = i.xpath('.//td[2]/a/@href')
					uktvlinks = [f'http://www.livesoccertv.com/{i}' for i in uktvlinks]
					uktv = list(zip(uktvchannels,uktvlinks))
					matchdata["uktv"] = ", ".join([f"[{i}]({j})" for i,j in uktv])
					return matchdata
				return matchdata
		
		matchdata = await fetch_tv(matchdata)
		
		async def write_markdown(matchdata,subhasicons,fm,prematch="",mt="",pm="",ispostmatch=False):
			markdown = ""
			# Date and Competion bar
			markdown += f"#### {matchdata['kickoff']} | {matchdata['competition']}\n\n"
			
			# Grab Match Icons
			if subhasicons:
				try:
					homeicon = self.bot.teams[matchdata["hometeam"]]['icon']
				except KeyError:
					homeicon = ""
				try:
					awayicon = self.bot.teams[matchdata["awayteam"]]['icon']
				except KeyError:
					awayicon = ""
			else:
				homeicon = awayicon = ""
			
			# Score bar
			homestring = f"{homeicon}[{matchdata['hometeam']}]({homereddit})" if homereddit else matchdata['hometeam']
			awaystring = f"[{matchdata['awayteam']}]({awayreddit}){awayicon}" if awayreddit else matchdata['awayteam']
			
			if ":" in matchdata['score']:
				markdown += f"# {homestring} vs {awaystring}\n\n"
			else:
				markdown += f"# {homestring} {matchdata['score']} {awaystring}\n\n"
			if matchdata['penalties']:
				markdown += "#### " + matchdata['penalties'] + "\n\n"
			
			# Referee and Venue
			if any([hasattr(matchdata,'referee'),hasattr(matchdata,'stadium')]):
				venue = ref = ""
				if hasattr(matchdata,'referee'):
					ref = f"[](#icon-whistle)**Referee**: {matchdata['referee']}" if subhasicons else f"**Referee**: {matchdata['referee']}"
				if hasattr(matchdata,'stadium'):
					venue += f"[🥅](#icon-net)**Venue**: {matchdata['stadium']}" if subhasicons else f"🥅 **Venue**: {matchdata['stadium']}"
				if matchdata['attendance']:
					venue += f" (👥 Attendance: {matchdata['attendance']})"
				markdown += "####" + " |".join([i for i in [ref,venue] if i]) + "\n\n"
				
			# Match Threads Bar.	
			archive = "[Match Thread Archive](https://www.reddit.com/r/NUFC/wiki/archive)" if subreddit.lower() in ["nufc","themagpiescss"] else ""
			
			mts = [prematch,mt,archive]
			mts = [i for i in mts if i]
			markdown += "---\n\n##" + " | ".join(mts) + "\n\n---\n\n"
			
			# Radio, TV.
			if not pm:
				if subreddit.lower() in ["nufc","themagpiescss"]:
					markdown += "[📻 Radio Commentary](https://www.nufc.co.uk/liveAudio.html)\n\n"
					markdown += "[](#icon-discord) [Join the chat with us on Discord](http://discord.gg/tbyUQTV)\n\n"
				if matchdata["uktv"]:
					markdown += f"📺🇬🇧 **TV** (UK): {matchdata['uktv']}\n\n"
				if matchdata["tvlink"]:
					markdown += f"📺🌍 **TV** (Intl): [Click here for International Coverage]({matchdata['tvlink']})\n\n"					
			
			if any([matchdata['homexi'],matchdata['awayxi']]):
				markdown += "---\n\n# Lineups\n"
				if fm:
					markdown += f"([Formations]({fm}))"
					markdown += ""
				markdown += f"{homeicon} **{matchdata['hometeam']}** | **{matchdata['awayteam']}** {awayicon}\n"
				markdown += "--:|:--\n"
								
				def insert_goals(input):
					output = []
					for i in input:
						for k,l in [i.split(' ',1) for i in matchdata["goals"]]:
							l = l.strip(",")
							if k in i.split(' ')[1]:
								i += f" [⚽](#icon-ball) {l}".strip(",") if subhasicons else f" ⚽ {l}".strip(",")
						for k,l in matchdata["subs"]:
							if k in i.split(' ')[1]:
								i += f" [🔄](#icon-sub) {l}" if subhasicons else f"🔄 {l}"
						output.append(i)
					return output
			
			formattedhome = ", ".join(insert_goals(matchdata['homexi']))
			formattedaway = ", ".join(insert_goals(matchdata['awayxi']))
			markdown += f"{formattedhome} | {formattedaway}\n"			
			markdown += f"{matchdata['homesubs']} | {matchdata['awaysubs']}\n"
			
			if matchdata["matchstats"]:
				markdown += f"---\n\n# Match Stats	"
				markdown += f"\n{homeicon} {matchdata['hometeam']}|v|{matchdata['awayteam']} {awayicon}\n--:|:--:|:--\n"
				markdown += f"{matchdata['matchstats']}\n\n"
			
			if matchpictures:
				markdown += "###Match Photos\n\n* " + '\n\n* '.join(matchpictures) + "\n\n"
			
			if ispostmatch:
				formatted = '\n\n'.join(matchdata["keyevents"])
			elif matchdata["ticker"]:
				formatted = '\n\n'.join(matchdata["ticker"])				
			formatted = formatted.replace(matchdata['hometeam'],f"{homeicon}{matchdata['hometeam']}")
			formatted = formatted.replace(matchdata['awayteam'],f"{awayicon}{matchdata['awayteam']}")			
			markdown += "\n\n---\n\n" + formatted + "\n\n"
			markdown += "\n\n---\n\n^(*Beep boop, I am /u/Toon-bot, a bot coded ^badly by /u/Painezor. If anything appears to be weird or off, please let him know.*)"
			return markdown		
		
		# Write Markdown
		markdown = await write_markdown(matchdata,subhasicons,fm,prematch=prematch)
		
		# Reddit posting shit.
		# Make a reddit post.
		def makepost(threadname,markdown):
			try:
				return self.bot.reddit.subreddit(subreddit).submit(threadname,selftext=markdown)
			except RequestException:
				return None
		
		# Fetch an existing reddit post.
		def fetchpost(resume):
			if not "://" in resume:
				try:
					post = self.bot.reddit.submission(id=resume)
				except:
					post = None
			else:
				try:
					post = self.bot.reddit.submission(url=resume)
				except:
					post = None
			return post
		
		# Edit an existing reddit post.
		def editpost(post,markdown):
			try:
				post.edit(markdown)
			except:
				editpost(post,markdown)
			return
		
		# Post initial thread.
		e = discord.Embed(color=0xff4500)
		post = None
		if not resume:
			threadname = f"Match Thread: {matchdata['hometeam']} vs {matchdata['awayteam']}"
			while post is None:
				post = await self.bot.loop.run_in_executor(None,makepost,threadname,markdown)
				await asyncio.sleep(5)
			e.description = (f"[{post.title}]({post.url}) created.")
		else:
			while post is None:
				post = await self.bot.loop.run_in_executor(None,fetchpost,resume)
				await asyncio.sleep(5)
			e.description = (f"[{post.title}]({post.url}) resumed.")
		
		th = ("http://vignette2.wikia.nocookie.net/valkyriecrusade/images"
				  "/b/b5/Reddit-The-Official-App-Icon.png")
		e.set_author(icon_url=th,name="Toonbot: Match Thread Bot")
		e.timestamp = datetime.datetime.now()
		await discordchannel.send(embed=e)
		
		# Update variables for loop.
		mt = f"[Match Thread]({post.url})"
		
		# Match Thread Loop.
		while self.activemodule:
			# Scrape new data
			try:
				matchdata = await self.scrape(bbclink,subhasicons)
			except ServerDisconnectedError:
				continue
			
			# Rebuild markdown
			markdown = await write_markdown(matchdata,subhasicons,fm,prematch=prematch,mt=mt)
			
			# Edit post
			await self.bot.loop.run_in_executor(None,editpost,post,markdown)

			# Repeat
			if self.stopmatchthread:
				break
				
			await asyncio.sleep(60)
		
		if not self.activemodule:
			return
		
		matchdata = await self.scrape(bbclink,subhasicons)
		
		# Rebuild markdown
		markdown = await write_markdown(matchdata,subhasicons,fm,prematch=prematch,mt=mt)
		threadname = f"Post-Match Thread: {matchdata['hometeam']} {matchdata['score']} {matchdata['awayteam']}"
		
		
		pmpost = None
		
		while pmpost is not None:
			pmpost = await self.bot.loop.run_in_executor(None,makepost,threadname,markdown)
			await asyncio.sleep(5)
		
		pm = f"[Post-Match Thread]({pmpost.url})"
		
		# One final edit to update postmatch into both threads.
		markdown = await write_markdown(matchdata,subhasicons,fm,prematch=prematch,mt=mt,pm=pm,ispostmatch=True)
		await self.bot.loop.run_in_executor(None,editpost,pmpost,markdown)
		
		markdown = await write_markdown(matchdata,subhasicons,fm,prematch=prematch,mt=mt,pm=pm)
		await self.bot.loop.run_in_executor(None,editpost,post,markdown)

		e.description = (f"[{pmpost.title}]({pmpost.url}) created.")
		await discordchannel.send(embed=e)	

		driver.quit()
			
	async def schedule_thread(self,delta,scheduletext,subreddit="",discordchannel="",teamurl=""):
		await asyncio.sleep(delta.total_seconds())
		if not self.activemodule:
			return
		self.scheduledthreads.remove(scheduletext)
		await self.match_thread(bbclink=teamurl,subreddit=subreddit,discordchannel=discordchannel)
		
	# Schedule a block of match threads.
	async def get_schedule(self):
		# Number of minutes before the match to post
		mtoffset = 30
		subreddit = "nufc"
		discordchannel = self.bot.get_channel(332167049273016320)
		teamurl = "newcastle-united"
		async with self.bot.session.get("https://www.nufc.co.uk/matches/first-team") as resp: 
			while resp.status != 200:
				print(f"{resp.status} error in scheduler. Retrying in 10 seconds.")
				await asycio.sleep(10)
			
			tree = html.fromstring(await resp.text())
			blocks = tree.xpath('.//div[@class="fixtures__item__content"]')
			
			fixtures = {}
			
			for i in blocks:
				date = "".join(i.xpath('.//p[@content]//text()')).strip()
				if not date:
					continue
				date = date.replace("3rd","3").replace("th","").replace("1st","1").replace("2nd","2")
				venue = "".join(i.xpath('.//h4//text()')).strip()
				opp = "".join(i.xpath('.//h3/span/text()')).strip()
				
				if "St. James'" in venue:
					fixtures[date] = f"Newcastle United vs {opp}"
				else:
					fixtures[date] = f"{opp} vs Newcastle United"
			
			now = datetime.datetime.now()		
			
			for k,v in fixtures.items():
				k = datetime.datetime.strptime(k,"%d %B %Y %I:%M %p")
				
				# Offset by x mins
				k = k - datetime.timedelta(minutes=mtoffset)
				postin = k - now								

				scheduletext = f"**{k}**: {v}"
				self.scheduledthreads.append(scheduletext)
				
				self.bot.loop.create_task(self.schedule_thread(postin,scheduletext,subreddit=subreddit,discordchannel=discordchannel,teamurl=teamurl))
				
	# NUFC-Specific Commands.
	def nufccheck(ctx):
		if ctx.guild:
			return ctx.guild.id in [238704683340922882,332159889587699712]
		
	# Debug command - Force Test
	@commands.command()
	@commands.has_permissions(manage_channels=True)
	async def forcemt(self,ctx,*,subreddit=""):
		if not subreddit:
			return await ctx.send("Which subreddit dickhead?")
			
		if "r/" in subreddit:	
			subreddit = subreddit.split("r/")[1]
			
		m = await ctx.send(f'Starting a match thread on r/{subreddit}...')
		post = await self.match_thread(bbclink="newcastle-united",subreddit=subreddit,discordchannel=ctx.channel)
	
	@commands.command()
	@commands.has_permissions(manage_channels=True)
	async def resume(self,ctx,*,linkorbase64):
		await ctx.send(f'Resuming match thread {linkorbase64}')
		post = await self.match_thread(bbclink="newcastle-united",subreddit="nufc",discordchannel=ctx.channel,resume=linkorbase64)

	@commands.command(aliases=["mtbcheck"])
	@commands.has_permissions(manage_channels=True)
	async def checkmtb(self,ctx):
		e = discord.Embed()
		e.color = 0x000000
		self.scheduledthreads.sort()
		e.description = "\n".join(self.scheduledthreads)
		e.title = "r/NUFC Scheduled Match Threads"
		await ctx.send(embed=e)
	
	@commands.is_owner()
	@commands.has_permissions(manage_channels=True)
	async def override(self,ctx,var,*,value):
		setattr(self,var,value)
		await ctx.send(f'Match Thread Bot: Setting "{var}" to "{value}"')		
	
def setup(bot):
	bot.add_cog(MatchThreadCommands(bot))