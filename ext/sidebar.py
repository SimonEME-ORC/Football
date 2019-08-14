from discord.ext import commands
import datetime
from PIL import Image
from lxml import html
from io import BytesIO
from prawcore.exceptions import RequestException
import aiohttp
import asyncio
import discord
import math	
import praw
import json
import re
import os

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.common.exceptions import TimeoutException

class Sidebar(commands.Cog):
	def __init__(self, bot):
		self.bot = bot
		self.sidebaron = True
		self.nextrun = "Not defined"
		self.subreddit = "NUFC"
		self.sidetask = bot.loop.create_task(self.looptask())
		self.driver = None
		with open('teams.json') as f:
			self.bot.teams = json.load(f)
		
	def __unload(self):
		self.sidetask.cancel()
		self.sidebaron = False
		self.driver.quit()
	
	def nufccheck(message):
		return message.guild.id == 332159889587699712
	
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
	
	@commands.group(invoke_without_command=True)
	@commands.is_owner()
	async def sidebar(self,ctx):
		""" Show the status of the sidebar updater, or use sidebar manual """
		e = discord.Embed(title="Sidebar Updater Status",color=0xff4500)
		th = ("http://vignette2.wikia.nocookie.net/valkyriecrusade/images/b/"
			  "b5/Reddit-The-Official-App-Icon.png")
		e.set_thumbnail(url=th)
		if self.sidebaron:
			e.description = "```diff\n+ Enabled```"
			ttn = self.nextrun - datetime.datetime.now()
			ttn = str(ttn).split(".")[0]
			e.set_footer(text=f"Next update in: {ttn}")
		else:
			e.description = "```diff\n- Disabled```"
		
		e.add_field(name="Target Subreddit",value=self.subreddit)
		
		if await self.bot.is_owner(ctx.author):
			x =  self.sidetask._state
			if x == "PENDING":
				v = "✅ No problems reported."
			elif x == "CANCELLED":
				v = "```diff\n- Loop aborted.```"
				e.color = 0xff0000
			elif x == "FINISHED":
				v = "```diff\n- Loop finished with error.```"
				z = self.sidetask.exception()
				e.color = 0xff0000
			else:
				v = f"❔ `{self.sidetask._state}`"
			e.add_field(name="Debug Info",value=v,inline=False)
			try:
				e.add_field(name="Reported Error",value=z,inline=False)
			except NameError:
				pass
		await ctx.send(embed=e)

	async def looptask(self):
		while self.sidebaron and not self.bot.is_closed():
			nowt = datetime.datetime.now()
			if nowt.hour < 18:
				self.nextrun = nowt.replace(hour=18,minute=0,second=0)
			elif 17 < nowt.hour < 22:
				self.nextrun = nowt.replace(hour=22,minute=0,second=0)
			else:
				self.nextrun = nowt.replace(hour=18,minute=0,second=0)
				self.nextrun += datetime.timedelta(days=1)
			runin = self.nextrun - nowt
			await asyncio.sleep(runin.seconds)
			
			table = await self.table()
			sb,fixtures,res,lastres,threads = await self.bot.loop.run_in_executor(None,self.get_data)
			sb = await self.bot.loop.run_in_executor(None,self.build_sidebar,sb,table,fixtures,res,lastres,threads)
			await self.bot.loop.run_in_executor(None,self.post_sidebar,sb)
	
	@sidebar.command(aliases=["captext","text","manual"])
	@commands.has_permissions(manage_messages=True)
	async def caption(self,ctx,*,captext=None):
		""" Set the sidebar caption on r/NUFC """
		
		await ctx.trigger_typing()
		sb = await self.bot.loop.run_in_executor(None,self.get_wiki)
		if captext is not None:
			captext = f"---\n\n> {captext}\n\n---"
			sb = re.sub(r'\-\-\-.*?\-\-\-',captext,sb,flags=re.DOTALL)
			await self.bot.loop.run_in_executor(None,self.post_wiki,sb)
			
		table = await self.table()
		sb,fixtures,res,lastres,threads = await self.bot.loop.run_in_executor(None,self.get_data)
		sb = await self.bot.loop.run_in_executor(None,self.build_sidebar,sb,table,fixtures,res,lastres,threads)
		await self.bot.loop.run_in_executor(None,self.post_sidebar,sb)
		
		e = discord.Embed(color=0xff4500)
		th = ("http://vignette2.wikia.nocookie.net/valkyriecrusade/images"
			  "/b/b5/Reddit-The-Official-App-Icon.png")
		e.set_author(icon_url=th,name="Sidebar updater")
		e.description = (f"Sidebar for http://www.reddit.com/r/"
						 f"{self.subreddit} manually updated.")
		e.timestamp = datetime.datetime.now()
		e.set_footer(text=f"{len(sb)} / 10240 Characters")
		await ctx.send(embed=e)
		
	@sidebar.command()
	@commands.has_permissions(manage_messages=True)
	async def image(self,ctx,*,link=""):
		""" Set the sidebar image on r/NUFC (400 x 300) """
		if not ctx.message.attachments:
			if not link:
				return await ctx.send("Upload the image with the command, or provide a link to the image.")
			async with self.bot.session.get(link) as resp:
				if resp.status != 200:
					return await ctx.send(f"{link} returned error status {resp.status}")
				image = await resp.content.read()
		else:	
			async with self.bot.session.get(ctx.message.attachments[0].url) as resp:
				if resp.status != 200:
					return await ctx.send("Something went wrong retrieving the image from discord.")
				image = await resp.content.read()
		im = Image.open(BytesIO(image))
		im.save('sidebar.png')
		s = self.bot.reddit.subreddit(f'{self.subreddit}')
		try:
			s.stylesheet.upload('sidebar', 'sidebar.png')
		except:
			return await ctx.send("Failed. File too large?")
		style = s.stylesheet().stylesheet
		s.stylesheet.update(style,reason=f"{ctx.author.name} Updated sidebar image via discord.")
		await ctx.send(f"Sidebar image changed on http://www.reddit.com/r/{self.subreddit}")	

	
	def build_sidebar(self,sb,table,fixtures,res,lastres,threads):
		sb = (f"{sb}{table}{fixtures}")
		
		lastres = lastres + threads
		thetime = datetime.datetime.now().strftime('%a %d %b at %H:%M')
		ts = f"\n#####Sidebar auto-updated {thetime}\n"
		
		# Get length, iterate results to max length.
		dc = "\n\n[](https://discord.gg/TuuJgrA)"
		sb += "* Previous Results\n"
		pr = "\n W|Home|-|Away\n--:|--:|:--:|:--\n"
			
		outlen = 0
		bufferlen = len(pr)
		outblocks = []
		count = 0
		for i in res:
			if count % 20 == 0:
				bufferlen += len(pr)
			totallen = (len(sb + i + ts + lastres + dc) +
					   bufferlen + outlen + 14)
			if totallen < 10220:
				outblocks.append(i)
				outlen += len(i)
				count += 1

		numblocks = (len(outblocks) // 20) + 1
		blocklen = math.ceil(len(outblocks)/numblocks)
		
		reswhead = []
		if blocklen:
			for i in range(0, len(outblocks), blocklen):
				reswhead.append(outblocks[i:i+blocklen])
		
		reswhead.reverse()

		outlist = ""
		for i in reswhead:
			outlist += pr
			outlist += "".join(i)
			if len(i) < blocklen:
				outlist += ("||||.\n")
		sb += outlist
		
		# Build end of sidebar.
		sb += ts
		sb += lastres
		sb += dc
		return sb
			
	
	def upload_image(self,image):
		im = Image.open(BytesIO(image))
		im.save('sidebar.png')
		s = self.bot.reddit.subreddit(f'{self.subreddit}')
		try:
			s.stylesheet.upload('sidebar', 'sidebar.png')
		except:
			return False
		style = s.stylesheet().stylesheet
		s.stylesheet.update(style,reason=f"{ctx.author.name} Updated sidebar image via discord.")
		e = discord.Embed(color=0xff4500)
		th = ("http://vignette2.wikia.nocookie.net/valkyriecrusade/images"
			  "/b/b5/Reddit-The-Official-App-Icon.png")
		e.set_author(icon_url=th,name="Sidebar updater")
		e.description = (f"Sidebar image for http://www.reddit.com/r/"
						 f"{self.subreddit} updated.")
		e.timestamp = datetime.datetime.now()
		
		return e

	def post_wiki(self,wikisidebar):
		try:
			s = self.bot.reddit.subreddit(f'{self.subreddit}')
			s.wiki['sidebar'].edit(wikisidebar,reason="SideCaption")
		except RequestException as e:
			sleep(60) # Infinite recursion bad.
			print("Failed to post wiki page, retrying.")
			if not self.bot.is_closed():
				self.post_wiki(wikisidebar)
			
	def get_wiki(self):
		# Grabs the dynamic chunk of sidebar.
		try:
			s = self.bot.reddit.subreddit(f'{self.subreddit}')
			s = s.wiki['sidebar'].content_md
			return s
		except RequestException:
			sleep(60) # Infinite recursion bad.
			print("Failed at get_wiki, retrying.")
			if not self.bot.is_closed():
				s = self.get_wiki()
				return s
		else:
			return s
			
	def post_sidebar(self,sidebar):
		keyColor = self.bot.reddit.subreddit(f"{self.subreddit}").key_color
		try:
			s = self.bot.reddit.subreddit(f"{self.subreddit}")
			s.mod.update(description=sidebar,key_color=keyColor)
		except RequestException:
			print("Failed at post_sidebar")
			if not self.bot.is_closed():
				self.post_sidebar(sidebar)
				
	def get_data(self):
		self.spawn_chrome()
		fixtures=results=threads="Retry"
		sb = self.get_wiki()
		fixtures = self.fixtures()
		results,lastres,lastop = self.results()
		threads = self.threads(lastop)
		self.driver.quit()
		return sb,fixtures,results,lastres,threads
	
	def threads(self,lastop):
		trds = []
		lastop = lastop.split(" ")[0]
		toappend = "#"
		for submission in self.bot.reddit.subreddit('NUFC').search('flair:"Pre-match thread"', sort="new", limit=10,syntax="lucene"):
			if lastop in submission.title:
				toappend = submission.url
				break
		trds.append(toappend)
		toappend = "#"
		for submission in self.bot.reddit.subreddit('NUFC').search('flair:"Match thread"', sort="new", limit=10,syntax="lucene"):
			if not submission.title.startswith("Match"):
				continue
			if lastop in submission.title:
				toappend = submission.url
				break
		trds.append(toappend)
		toappend = "#"
		for submission in self.bot.reddit.subreddit('NUFC').search('flair:"Post-match thread"', sort="new", limit=10,syntax="lucene"):
			if lastop in submission.title:
				toappend = submission.url
				break
		trds.append(toappend)
		pre = "Pre" if trds[0] == "#" else f"[Pre]({trds[0].split('?ref=')[0]})"
		match = "Match" if trds[1] == "#" else f"[Match]({trds[1].split('?ref=')[0]})"
		post = "Post" if trds[2] == "#" else f"[Post]({trds[2].split('?ref=')[0]})"
		threads = f"\n\n### {pre} - {match} - {post}"
		return threads
	
	async def table(self):
		cs = self.bot.session
		url = 'http://www.bbc.co.uk/sport/football/premier-league/table'
		async with cs.get(url) as resp:
			if resp.status != 200:
				return "Retry"
			tree = html.fromstring(await resp.text())
		xp = './/table[contains(@class,"gs-o-table")]//tbody/tr'
		tablerows = tree.xpath(xp)[:20]
		tbldata = ("\n\n* Premier League Table"
		         "\n\n Pos.|Team *click to visit subreddit*|P|W|D|L|GD|Pts"
				 "\n--:|:--|:--:|:--:|:--:|:--:|:--:|:--:\n")
		for i in tablerows:
			p = i.xpath('.//td//text()')
			r = p[0].strip() # Ranking
			m = p[1].strip() # Movement
			m = m.replace("team hasn't moved",'[](#icon-nomove)')
			m = m.replace('team has moved up','[](#icon-up)')
			m = m.replace('team has moved down','[](#icon-down)')
			t = p[2]		 # Team
			t = f"[{t}]({self.bot.teams[t]['subreddit']})"
			pd = p[3]		 # Played
			w = p[4]         # Wins
			d = p[5]	     # Drawn
			l = p[6]		 # Lost
			gf = p[7]        # Goals For
			ga = p[8]        # Goals Against
			gd = p[9]        # GoalDiff
			pts = p[10]      # Points
			
			try:
				form = p[11]
			except IndexError:
				pass
			tbldata += f"{r} {m}|{t}|{pd}|{w}|{d}|{l}|{gd}|{pts}\n"
		return tbldata

	def fixtures(self):	
		self.driver.get("http://www.flashscore.com/team/newcastle-utd/p6ahwuwJ/fixtures/")
		t = html.fromstring(self.driver.page_source)

		fixtures = t.xpath(".//div[contains(@class,'sportName soccer')]/div")
		fixblock = []
		for i in fixtures:
			# Date
			d = "".join(i.xpath('.//div[@class="event__time"]//text()'))
			
			if not d:
				continue
			try:
				d = datetime.datetime.strptime(d,"%d.%m. %H:%M")
				d = datetime.datetime.strftime(d,"%a %d %b: %H:%M")
			except ValueError: # Fuck this cant be bothered to fix it.
				d = "Tue 31 Feb: 15:00"			

			matchid = "".join(i.xpath(".//@id")).split('_')[2]
			lnk = f"http://www.flashscore.com/match/{matchid}/#h2h;overall"
			
			h,a = i.xpath('.//div[contains(@class,"event__participant")]/text()')
			if '(' in h:
				h = h.split('(')[0].strip()
			if '(' in a:
				a = a.split('(')[0].strip()
				
			ic = "[](#icon-home)" if "Newcastle" in h else "[](#icon-away)"
			op = h if "Newcastle" in a else a

			try:
				op = f"{self.bot.teams[op]['icon']}{self.bot.teams[op]['shortname']}"
			except KeyError:
				print(f"Sidebar - fixtures - No db entry for: {op}")
			fixblock.append(f"[{d}]({lnk})|{ic}|{op}\n")
		
		fixmainhead = "\n* Upcoming fixtures"
		fixhead = "\n\n Date & Time|at|Opponent\n:--:|:--:|:--:|:--|--:\n"
		
		numblocks = (len(fixblock) // 20) + 1
		blocklen = math.ceil(len(fixblock)/numblocks)
		try:
			chunks = [fixblock[i:i+blocklen] for i in range(0, len(fixblock), blocklen)]
		except ValueError:
			return ""
		chunks.reverse()
		for i in chunks:
			if len(i) < blocklen:
				i.append("|||||")
		chunks = ["".join(i) for i in chunks]
		chunks = fixmainhead + fixhead + fixhead.join(chunks)
		return chunks
			
	def results(self):
		self.driver.get("http://www.flashscore.com/team/newcastle-utd/p6ahwuwJ/results/")
		t = html.fromstring(self.driver.page_source)
		
		resultlist = []
		lastres,lastop = "",""

		
		results = t.xpath(".//div[contains(@class,'sportName soccer')]/div")
		for i in results:
			d = "".join(i.xpath('.//div[@class="event__time"]//text()'))
			
			if not d:
				continue
			try:
				d = datetime.datetime.strptime(d,"%d.%m. %H:%M")
				d = d.replace(year=datetime.datetime.now().year)
				d = datetime.datetime.strftime(d,"%a %d %b")
			except ValueError:
				# Fix older than a year games.
				d = datetime.datetime.strptime(d,"%d.%m.%Y")
				d = datetime.datetime.strftime(d,"%d/%m/%Y")	
		
			matchid = "".join(i.xpath(".//@id")).split('_')[2]
			# Hack together link.
			lnk = f"http://www.flashscore.com/match/{matchid}/#match-summary"

			# Score
			h,a = i.xpath('.//div[contains(@class,"event__scores")]/span/text()')
			sc = f"[{h} - {a}]({lnk})"

			ht,at = i.xpath('.//div[contains(@class,"event__participant")]/text()')
			if '(' in ht:
				ht = ht.split('(')[0]
			if '(' in at:
				at = at.split('(')[0]
			
			ht,at = ht.strip(),at.strip()		

			# Top of Sidebar Chunk
			if not lastop:
				# Fetch badge if required
				def get_badge(link,team):
					self.driver.get(link)
					frame = self.driver.find_element_by_class_name(f"tlogo-{team}")
					img = frame.find_element_by_xpath(".//img").get_attribute('src')
					self.bot.loop.create_task(self.fetch_badge(img))					

				lastop = at if "Newcastle" in ht else ht
				if at in self.bot.teams.keys():
					lasta = (f"[{self.bot.teams[at]['shortname']}]"
							f"({self.bot.teams[at]['subreddit']})")
				else:
					get_badge(lnk,"away")
					lasta = f"[{at}](#temp/)"
				if ht in self.bot.teams.keys():
					lasth = (f"[{self.bot.teams[ht]['shortname']}]"
							f"({self.bot.teams[ht]['subreddit']}/)")
				else:
					get_badge(lnk,"home")
					lasth = F"[{ht}](#temp)"
				lastres = f"> {lasth.replace(' (Eng)','')} {sc} {lasta.replace(' (Eng)','')}"

			if ht in self.bot.teams.keys():
				ht = (f"{self.bot.teams[ht]['icon']}"
					f"{self.bot.teams[ht]['shortname']}")
			if at in self.bot.teams.keys():
				at = (f"{self.bot.teams[at]['shortname']}"
					f"{self.bot.teams[at]['icon']}")
			ic = "[](#icon-home)" if "Newcastle" in ht else "[](#icon-away)"
			
			if "Newcastle" in ht:
				if h > a:
					resultlist.append(f"[W](#icon-win)|{ht}|{sc}|{at}\n")
				elif h == a:
					resultlist.append(f"[D](#icon-draw)|{ht}|{sc}|{at}\n")
				else:
					resultlist.append(f"[L](#icon-loss)|{ht}|{sc}|{at}\n")
			else:
				if h > a:
					resultlist.append(f"[L](#icon-loss)|{ht}|{sc}|{at}\n")
				elif h == a:
					resultlist.append(f"[D](#icon-draw)|{ht}|{sc}|{at}\n")
				else:
					resultlist.append(f"[W](#icon-win)|{ht}|{sc}|{at}\n")
		return resultlist,lastres,lastop
	
	async def fetch_badge(self,src):
		async with self.bot.session.get(src) as resp:
			if resp.status != 200:
				print("Error {resp.status} downloading image.")
			image = await resp.content.read()
		await self.bot.loop.run_in_executor(None,self.upload_badge,image)
		
	def upload_badge(self,image):
		im = Image.open(BytesIO(image))
		im.save('badge.png')
		s = self.bot.reddit.subreddit(f'{self.subreddit}')
		s.stylesheet.upload('temp', 'badge.png')
		style = s.stylesheet().stylesheet
		s.stylesheet.update(style,reason="Update temporary badge image")
		
def setup(bot):
	bot.add_cog(Sidebar(bot))