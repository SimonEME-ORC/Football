import datetime

# Discord.py
import discord
from discord.ext import commands

# Web Scraping
import os
from lxml import html
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.common.exceptions import TimeoutException
import requests

# Imaging
from PIL import Image
from io import BytesIO
import base64

# Data manipulation
import datetime
import asyncio

# Config
import json

#### Config structure
#### =================
#### {
####	guildid:{
####		"scores":{
####			channel: int,
####			leagues: ["league 1","league 2", ... ]
####		}
####	},guildid2:{
####		"scores":{
####			channel: int,
####			leagues: ["league 3","league 5", ... ]	
####		}
####	}
#### }

#### Games Dict Structure
#### ====================
#### {
####	"leaguename":{
####		"raw" : "...",
####		"id1":{"time": "...","hometeam": "...","awayteam": "...","score": "...","aggregate": "..."},
####		"id2":{"time": "...","hometeam": "...","awayteam": "..."}
####	},"leaguename2":{
####		"raw" : "...",
####		"id3":{"time": "...","hometeam": "...","awayteam": "..."}
#### 	}
#### }

#### Message Dict
#### ============
#### {
####    guildid:{
####		"rawdata":["...","..."],
####		"channel": int,
####		"messages":{guildid:[msg1id, msg2id],guildid2: [msg1id,msg2id]}
####    },guildid2:{
####		"rawdata":["...","..."],
####		"channel": int,
####		"messages":{guildid2:[msgid],guildid3: [msgid]}
#### 	}
#### }

 # TODO: Lookup Scores per league.
 # TODO: Allow setting of default team & league for server.
 # TODO: Build reactor menu.
 # TODO: Code Goals
 # TODO: Code Stats
 # TODO: Fix Bare Except.
 
class LiveScores(commands.Cog):
	""" Rewrite of the livescores channel module """	
	def __init__(self,bot):
		print(f"{datetime.datetime.now()}: Loaded ls module")
		self.bot = bot
		self.scoreson = True
		self.games = {}
		self.msgdict = {}

		self.bot.flashscore = self.bot.loop.create_task(self.fsloop())
		self.messagedict = {}
		
		# Loop frequency // Debug 15, normal 60.
		self.intervaltimer = 15
		
		# Default leagues.
		self.default = ["WORLD: Friendly international","EUROPE: Champions League","EUROPE: Euro",
			"ENGLAND: Premier League","ENGLAND: Championship","ENGLAND: FA Cup","ENGLAND: EFL Cup","FRANCE: Ligue 1","GERMANY: Bundesliga",
			"ITALY: Serie A","NETHERLANDS: Eredivisie","SCOTLAND: Premiership",	"USA: MLS","SPAIN: LaLiga"]
	
	def cog_unload(self):
		self.scoreson = False
		self.bot.flashscore.cancel()
	
	async def _save(self):
		with await self.bot.configlock:
			with open('config.json',"w",encoding='utf-8') as f:
				json.dump(self.bot.config,f,ensure_ascii=True,
				sort_keys=True,indent=4, separators=(',',':'))
	
	# Core Loop
	async def fsloop(self):
		""" Score Checker Loop """
		await self.bot.wait_until_ready()
		while self.scoreson:
			try:
				games = await self.bot.loop.run_in_executor(None,self.fetch_data)
			except:
				await asyncio.sleep(5)
				continue
			await self.write_raw(games)
			# Iterate: Check vs each server's individual config settings
			await self.localise_data()
			
			# Send message to server.
			if self.scoreson:
				await self.spool_messages()
			else:
				return
			
			# Loop.
			await asyncio.sleep(self.intervaltimer)
	
	# Spawn Chrome
	def spawn_chrome(self):
		caps = DesiredCapabilities().CHROME
		caps["pageLoadStrategy"] = "normal"  #  complete
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
		return driver		
	
	def fetch_data(self):
		driver = self.spawn_chrome()
		
		driver.get("http://www.flashscore.com/")
		WebDriverWait(driver, 2)

		fixturelist = driver.find_element_by_class_name('leagues--live')
		fixturelist = fixturelist.get_attribute('innerHTML')
		fixturelist = html.fromstring(fixturelist)
		
		fixturelist = fixturelist.xpath('./div')
		driver.quit()
		
		games = {}
		for i in fixturelist:
			# Header rows do not have IDs
			if not i.xpath('.//@id'):
				league = ": ".join(i.xpath('.//span//text()'))
				games[league] = {}
			else:
				gameid = ''.join(i.xpath('.//@id'))
				games[league][gameid] = {}
				
				# Time
				time = i.xpath('.//div[contains(@class,"event__stage--block")]//text()')
				if not time:
					time = i.xpath('.//div[contains(@class,"event__time")]//text()')
				
				time = "".join(time).replace('FRO',"").strip("\xa0").strip()
				if "Finished" in time:
					time = "FT"
				elif "After ET" in time:
					time = "AET"
				elif "Half Time" in time:
					time = "HT"
				elif "Postponed" in time:
					time = "PP"
				elif not ":" in time:
					time = f"{time}'"
				games[league][gameid]["time"] = time
				games[league][gameid]["hometeam"] = "".join(i.xpath('.//div[contains(@class,"home")]//text()')).strip()
				games[league][gameid]["awayteam"] = "".join(i.xpath('.//div[contains(@class,"away")]//text()')).strip()
				# games[league][gameid]["aggregate"] = "".join(i.xpath('.//div[@class="event__part"]//text()')).strip()
				score = "".join(i.xpath('.//div[contains(@class,"event__scores")]//text()')).strip()
				score = "vs" if not score else score
				games[league][gameid]["score"] = score
		
		return games
		
	async def write_raw(self,games):
		for league,data in games.items():
			# i is a gameid
			raw = f"**{league}**\n"
			for k,v in data.items():
				time = f"{data[k]['time']}"
				
				time = "✅ FT" if time == "FT" else time
				time = "✅ AET" if time == "AET" else time
				time = "⏸️ HT" if time == "HT" else time
				time = "🚫 PP" if time == "PP" else time
				time = f"🔜 {time}" if ":" in time else time
				time = f"⚽ {time}" if "'" in time else time				
				
				home = data[k]["hometeam"]
				away = data[k]["awayteam"]
				score = data[k]["score"]
				
				raw += f"`{time}` {home} {score} {away}\n"

			games[league]["raw"] = raw
		self.games = games

	async def localise_data(self):
		for k,v in self.bot.config.items():
			if "scores" not in self.bot.config[k]:
				continue
			if not self.bot.config[k]["scores"]["channel"]:
				continue
			leagues = self.bot.config[k]["scores"]["leagues"]
			
						
			try:
				prefix = self.bot.config[k]["prefix"][0]
			except:
				prefix = self.bot.user.mention
			
			if not leagues:
				tf = f"**You can now customise the leagues for your server!** Use `{prefix}ls add League Name` to add new leagues!\n\n"
			else:
				tf = ""
				
			leagues = self.default if leagues == [] else leagues
			
			if k not in self.msgdict:
				self.msgdict[k] = {}
				self.msgdict[k]["channel"] = self.bot.config[k]["scores"]["channel"]
				self.msgdict[k]["msglist"] = []
			
			self.msgdict[k]["rawdata"] = []

			
			tf += f"Live Scores for **%a %d %b %Y** (last updated at **%H:%M:%S**)\n\n"
			today = datetime.datetime.now().strftime(tf)
			rawtext = today
			for j in leagues:
				if j not in self.games:
					continue
				if len(rawtext) + len (self.games[j]["raw"]) < 2045:
					rawtext += self.games[j]["raw"] + "\n"
				else:
					self.msgdict[k]["rawdata"] += [rawtext]
					rawtext = self.games[j]["raw"] + "\n"
			
			self.msgdict[k]["rawdata"] += [rawtext]
	
	async def spool_messages(self):
		if not self.scoreson:
			print("Scores disabled, aborting update.")
			return
		for k,v in self.msgdict.items():
			# Create messages if none exist.
			# Or if a different number of messages is required.
			if self.msgdict[k]["msglist"] == [] or len(self.msgdict[k]["msglist"]) != len(self.msgdict[k]["rawdata"]):
				ch = self.bot.get_channel(self.msgdict[k]["channel"])
				try:
					await ch.purge()
				except discord.Forbidden:
					await ch.send("Unable to clean previous messages, please make sure I have manage_messages permissions.")
				except AttributeError:
					print(f'Invalid channel: {self.msgdict[k]["channel"]}')
					continue
				for c in self.msgdict[k]["rawdata"]:
					# Append message ID to our list
					m = await ch.send(c)
					self.msgdict[k]["msglist"].append(m)
			else:
				# Edit message pairs if pre-existing.
				tuples = list(zip(self.msgdict[k]["msglist"],self.msgdict[k]["rawdata"]))
				for x,y in tuples:
					try:
						await x.edit(content=y)
					### Fix this bare accept.
					except:
						pass 

	@commands.group(invoke_without_command=True)
	@commands.has_permissions(manage_channel=True)
	async def ls(self,ctx):
		""" View the status of your live scores channel. """
		e = discord.Embed()
		e.set_thumbnail(url=ctx.me.avatar_url)
		e.title = "Livescore channel config"
		e.color = 0x0000ff
		try:
			e.add_field(name="Channel",value=self.bot.get_channel(self.bot.config[str(ctx.guild.id)]["scores"]["channel"]).mention)
			leagues = self.bot.config[str(ctx.guild.id)]["scores"]["leagues"]
			if leagues == []:
				leagues = self.default
			try:
				footer = f"Add/remove leagues with {ctx.prefix}{ctx.invoked_With} add leaguename or {ctx.prefix}{ctx.invoked_with} remove leaguename"
			except AttributeError:
				footer = f"Add/remove leagues with {ctx.prefix}{ctx.command} add leaguename or {ctx.prefix}{ctx.command} remove leaguename"
			e.set_footer(text=footer)
			e.description = f"**Your Server's Tracked Leagues**\n" + '\n'.join(leagues)
		except KeyError:
			e.description = f"Your live scores channel has not been set! Use `{ctx.prefix}{ctx.command} create` to create one."
			e.color = 0xff0000
		except AttributeError:
			e.description = f"Unable to find the live-scores channel for your server. Please use `{ctx.prefix}{ctx.command} set` in your scores channel."
		
		m = await ctx.send(embed=e)
	
	@ls.command(hidden=True)
	@commands.has_permissions(manage_channels=True)
	async def set(self,ctx):
		""" Use this command to reset the livescores channel for your server to the current channel.\n\n
		This should only be used if there is an error with your current channel's configuration.
		If you do not have a scores channel. please use "create" instead of "set"
		"""
		await ctx.send('All messages in this channel will be deleted. Please type "confirm" if you sure you wish to continue?')
		
		def check(message):
			if message.author.id == ctx.author.id and message.content == "confirm":
				return True
		try:
			res = await self.bot.wait_for("message",check=check,timeout=30)
		except asyncio.TimeoutError:
			return await ctx.send("Timed out.")
			
		self.bot.config[f"{ctx.guild.id}"]["scores"]["channel"] = ctx.id
		
		await self._save()
		await ctx.send(f"✅ {ctx.guild.name} scores channel set to {ctx.channel.mention}")
	
	@ls.command()
	@commands.has_permissions(manage_channels=True)
	async def create(self,ctx):
		""" Create a live-scores channel for your server. """
		try:
			ow = {ctx.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True,	embed_links=True, read_message_history=True),
				ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False,read_message_history=True)
			}
			reason = f'{ctx.author} (ID: {ctx.author.id}) created live-scores channel.'
			ch = await ctx.guild.create_text_channel(name="live-scores",overwrites = ow,reason=reason)
		except discord.Forbidden:
			return await ctx.send("Unable to create live-scores channel. Please make sure I have the manage_channels permission.")
		except discord.HTTPException:
			return await ctx.send("An unknown error occured trying to create the live-scores channel, please try again later.")
		self.bot.config[f"{ctx.guild.id}"]["scores"] = {"channel":ch.id,"leagues":[]}
		with await self.bot.configlock:
			with open('config.json',"w",encoding='utf-8') as f:
				json.dump(self.bot.config,f,ensure_ascii=True,
				sort_keys=True,indent=4, separators=(',',':'))
		await self._save()
		await ctx.send(f"The {ch.mention} channel was created!")
		
		#restart loop for new additions.
		self.scoreson = False
		self.bot.flashscore.cancel()
		self.scoreson = True
		self.bot.flashscore = self.bot.loop.create_task(self.fsloop())
		
	@ls.command()
	@commands.has_permissions(manage_channels=True)
	async def delete(self,ctx):
		""" Delete the live-scores channel from your server. """
		channel = self.bot.get_channel(self.bot.config[f"{ctx.guild.id}"]["scores"]["channel"])
		m = await ctx.send("** ⚠️ Are you sure that you want to delete the {channel.mention} channel? **")
		for i in ["✅","🚫"]:
			await m.add_reaction(i)
			
		def check(reaction,user):
			if reaction.message.id == m.id and user == ctx.author:
				return reaction.emoji in ["✅","🚫"]
		
		# Wait for appropriate reaction
		try:
			rea = await self.bot.wait_for("reaction_add",check=check,timeout=30)
		except:
			await ctx.send("Channel not deleted.")
			return await m.clear_reactions()
			
		if rea == "🚫":
			return await ctx.send("Channel not deleted.")
		
		if "scores" in self.bot.config[f"{ctx.guild.id}"]:
			await channel.delete()
			del self.bot.config[f"{ctx.guild.id}"]
		await self._save()
		await ctx.send(f"Your livescores channel was deleted. You can create a new one with {ctx.prefix}ls create")
	
	@ls.command()
	@commands.has_permissions(manage_channels=True)
	async def add(self,ctx,*,qry=None):
		""" Add a league to your live-scores channel """
		if qry is None:
			return await ctx.send("Specify a league name.")
		qry = discord.utils.escape_mentions(qry)
		m = await ctx.send(f"Searching for {qry}...")
		res = await self._search(ctx,m,qry)
		
		if not res:
			return #rip
		
		try:
			leagues = self.bot.config[str(ctx.guild.id)]["scores"]["leagues"]
		except KeyError:
			await ctx.send(f'Please create your livescores channel first with {ctx.prefix}{ctx.command}{create}')
		if not leagues:
			leagues = self.default
		else:
			if res in leagues:
				return await ctx.send(f"🚫 **{res}** is already in your server's tracked leagues.")
		
		leagues.append(res)
		self.bot.config[str(ctx.guild.id)]["scores"]["leagues"] = leagues
		await self._save()
		await ctx.send(f"✅ **{res}** was added to your server's tracked leagues.")
		
	@ls.command(aliases=["del"])
	@commands.has_permissions(manage_channels=True)
	async def remove(self,ctx,*,league):
		""" Remove a league from your live-scores channel """
		league = discord.utils.escape_mentions(league)
		leagues = self.bot.config[str(ctx.guild.id)]["scores"]["leagues"]
		leagues = self.default if leagues == [] else leagues
		if league not in leagues:
			return await ctx.send(f"🚫 Could not find **'{league}'** in your server's tracked leagues. Make sure you included the country, e.g. `{ctx.prefix}ls remove ENGLAND: Premier League`")
		
		leagues.remove(league)
		self.bot.config[str(ctx.guild.id)]["scores"]["leagues"] = leagues
		await self._save()
		await ctx.send(f"✅ **{league}** was removed from your server's tracked leagues.")
	
	async def _search(self,ctx,m,qry):
		# aiohttp lookup for json.
		qry = qry.replace("'","")

		qryurl = f"https://s.flashscore.com/search/?q={qry}&l=1&s=1&f=1%3B1&pid=2&sid=1"
		async with self.bot.session.get(qryurl) as resp:
			res = await resp.text()
			res = res.lstrip('cjs.search.jsonpCallback(').rstrip(");")
			res = json.loads(res)
		
		resdict = {}
		key = 0
		# Remove irrel.
		for i in res["results"]:
			# Format for LEAGUE
			if i["participant_type_id"] == 0:
				# Sample League URL: https://www.flashscore.com/soccer/england/premier-league/
				resdict[str(key)] = {"Match":i['title']} 			
			key += 1
		
		if not resdict:
			return await m.edit(content=f"No results for query: {qry}")
		
		if len(resdict) == 1:
			try:
				await m.delete()
			except:
				pass
			return resdict["0"]["Match"]
			
		outtext = ""
		for i in resdict:
			outtext += f"{i}: {resdict[i]['Match']}\n"
		
		try:
			await m.edit(content=f"Please type matching id: ```{outtext}```")
		except discord.HTTPException:
			### TODO: Paginate.
			return await m.edit(content=f"Too many matches to display, please be more specific.")
		
		def check(message):
			if message.author.id == ctx.author.id and message.content in resdict:
				return True
		try:
			match = await self.bot.wait_for("message",check=check,timeout=30)
		except asyncio.TimeoutError:
			return await m.delete()
		
		mcontent = match.content
		try:
			await m.delete()
			await match.delete()
		except:
			pass
		return resdict[mcontent]["Match"]
		
	async def pick_game(self,ctx,qry):
		matches = []
		id = 0
		for league in self.games:
			for gameid in self.games[league]:
				# Ignore our output strings.
				if gameid == "raw":
					continue
				
				home = self.games[league][gameid]["hometeam"]
				away = self.games[league][gameid]["awayteam"]
					
				if qry in home.lower() or qry in away.lower():
					str = f"{home} vs {away} ({league})"
					matches.append((id,str,league,gameid))
					id += 1
		
		print(matches)
		
		if not matches:
			return None,None
		
		if len(matches) == 1:
			# return league and game of only result.
			return matches[0][2],matches[0][3]
		
		selector = "Please Type Matching ID```"
		for i in matches:
			selector += f"{i[0]}: {i[1]}\n" 
		selector += "```"	
		
		try:
			m = await ctx.send(selector,delete_after=30)
		except discord.HTTPException:
			### TODO: Paginate.
			return await ctx.send(content=f"Too many matches to display, please be more specific.")
		
		def check(message):
			if message.author.id == ctx.author.id and message.content.isdigit():
				if int(message.content) < len(matches):
					return True
		try:
			match = await self.bot.wait_for("message",check=check,timeout=30)
			match = int(match.content)
		except asyncio.TimeoutError:
			return None,None
		else:
			try:
				await m.delete()
			except discord.NotFound:
				pass
			return matches[match][2],matches[match][3]	

	def fetch_match_data(self,league,game):
		url =  f"https://www.flashscore.com/match/{game.split('_')[-1]}/#match-statistics;0"
		driver = self.spawn_chrome()
		wait = 0
		driver.get(url)
		WebDriverWait(driver, wait)
		while driver.current_url != url:
			print(f"fs: test / {url} vs {driver.current_url}")
			driver.get(url)
			WebDriverWait(driver, wait)
			wait += 1
			if wait > 5:
				return None
		
		# Statistics
		s,h,a = [],[],[]
		
		# Attempt to grab Stats.
		tree = html.fromstring(driver.page_source)
		statlist = tree.xpath(".//div[@class='statContent']")
		
		try:
			for i in statlist[0]:
				new_s = "\n".join(i.xpath(".//div[contains(@class,'titleValue')]/text()")).strip()
				if new_s in s:
					continue
				s.append(new_s)
				h.append("\n".join(i.xpath(".//div[contains(@class,'homeValue')]/text()")).strip())
				a.append("\n".join(i.xpath(".//div[contains(@class,'awayValue')]/text()")).strip())
		except IndexError:
			pass
	
		# Attempt to grab Formation.
		formation = ""
		try:
			z = driver.find_element_by_link_text('Lineups')
			z.click()
			WebDriverWait(driver, 3)
			
			img = driver.save_screenshot('formations.png')
			
			x = driver.find_element_by_class_name('soccer-formation')
			loc = x.location 
			size = x.size
			
			voffset = -27
			hoffset = 0
			
			left = loc['x'] + hoffset
			top = loc['y'] + voffset
			right = loc['x'] + size['width'] + hoffset
			bottom = loc['y'] + size['height']
			
			im = Image.open('formations.png')
			
			im = im.crop((left, top, right, bottom))
			
			im.save("formations.png","PNG")

			# Send to Imgur
			res = self.bot.imgur.upload_from_path("formations.png",anon=True)
			formation = res["link"]
		
		except NoSuchElementException:
			pass
		except AttributeError as e:
			print(e)
			
		driver.quit()
		
		e = discord.Embed()
		home = self.games[league][game]["hometeam"]
		away = self.games[league][game]["awayteam"]
		score = self.games[league][game]["score"]
		time = self.games[league][game]["time"]
		e.title = f"{home} {score} {away}"
		
		if formation:
			e.set_image(url=formation)
		
		if not ":" in time and not "PP" in time:
			e.title += f" ({time})"
			e.color = 0x448fea
		else:
			e.color = 0xA4DD74
		e.url = url
		
		if a and h and s:
			e.add_field(name="Home",value="\n".join(h),inline=True)
			e.add_field(name="Stat",value="\n".join(s),inline=True)
			e.add_field(name="Away",value="\n".join(a),inline=True)
		elif "PP" in time:
			e.color = 0xe85342
			e.description = "This match has been postponed."			
		elif ":" not in time:
			e.color = 0xe85342
			e.description = "Live data not available for this match."
		
		if ":" in time:
			h,m = time.split(':')
			now = datetime.datetime.now()
			when = datetime.datetime.now().replace(hour=int(h),minute=int(m))
			
			x = when - now
			
			e.set_footer(text=f"Kickoff in {x}")
			e.timestamp = when
			
		return e

	@commands.command()
	@commands.is_owner()
	async def stats(self,ctx,*,qry : commands.clean_content()):
		""" Look up the stats for one of today's games """
		with ctx.typing():
			if not qry:
				return await ctx.send("Please specify a search query.")
			
			league,game = await self.pick_game(ctx,qry.lower())
			if game is None:
				return await ctx.send(f"Unable to find a match for {qry}")
				
			e = await self.bot.loop.run_in_executor(None,self.fetch_match_data,league,game)
			
			if e is None:
				return await ctx.send("Timed out getting url.")
			await ctx.send(embed=e)


	def test_data(self,game):
		url =  f"https://www.flashscore.com/match/{game}/#match-statistics;0"
		driver = self.spawn_chrome()
		wait = 0
		driver.get(url)
		WebDriverWait(driver, wait)
		while driver.current_url != url:
			driver.get(url)
			WebDriverWait(driver, wait)
			wait += 1
			if wait > 5:
				return None
		
		# Statistics
		s,h,a = [],[],[]
		
		tree = html.fromstring(driver.page_source)
		statlist = tree.xpath(".//div[@class='statContent']")
		
		for i in statlist[0]:
			new_s = "\n".join(i.xpath(".//div[contains(@class,'titleValue')]/text()")).strip()
			if new_s in s:
				continue
			s.append(new_s)
			h.append("\n".join(i.xpath(".//div[contains(@class,'homeValue')]/text()")).strip())
			a.append("\n".join(i.xpath(".//div[contains(@class,'awayValue')]/text()")).strip())
	
		driver.save_screenshot('lst.png')
		driver.quit()
		
		e = discord.Embed()
		if a and h and s:
			e.add_field(name="Newcatle",value="\n".join(h),inline=True)
			e.add_field(name="1 - 0",value="\n".join(s),inline=True)
			e.add_field(name="Crystal Palace",value="\n".join(a),inline=True)
		return e
		
	@commands.command()
	@commands.is_owner()
	async def ts(self,ctx):
		with ctx.typing():
			e = await self.bot.loop.run_in_executor(None,self.test_data,"G6ZwPXlr")
			
			if e is None:
				return await ctx.send("Timed out getting url.")
			await ctx.send(file=discord.File('lst.png'))
			await ctx.send(embed=e)
	
			
def setup(bot):
	bot.add_cog(LiveScores(bot))			
			