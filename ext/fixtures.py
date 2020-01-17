import asyncio
import discord
from discord.ext import commands

import aiohttp
import requests
import html
from lxml import html as htmlc
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.common.exceptions import TimeoutException

from colorthief import ColorThief
import datetime
from copy import deepcopy
from PIL import Image
from io import BytesIO
import os
import json

class Fixtures(commands.Cog):
	""" Rewrite of fixture & result lookups. """
	def __init__(self, bot):
		self.bot = bot

	# Spawn an instance of headerless chrome.
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
		
	async def _search(self,ctx,m,qry,mode=None):
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
			if i["participant_type_id"] == 0: # League
				if mode is not "team":
					# Sample League URL: https://www.flashscore.com/soccer/england/premier-league/
					resdict[str(key)] = {"Match":i['title'],"url":f"soccer/{i['country_name'].lower()}/{i['url']}"}	
			elif i["participant_type_id"] == 1: # Team
				if mode is not "league":
					# Sample Team URL: https://www.flashscore.com/team/thailand-stars/jLsL0hAF/
					resdict[str(key)] = {"Match":i["title"],"url":f"team/{i['url']}/{i['id']}"}
			key += 1
		
		if not resdict:
			return await m.edit(content=f"No results for query: {qry}")
		
		if len(resdict) == 1:
			return f'https://www.flashscore.com/{resdict["0"]["url"]}'
			
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
		await m.edit(content=f"Grabbing data...")
		
		try:
			await match.delete()
		except:
			pass
		return f'https://www.flashscore.com/{resdict[mcontent]["url"]}'

	async def get_default(self,ctx,mode):
		# Get
		connection = await self.bot.db.acquire()
		record = await connection.fetchrow(
		"""
			SELECT default_team FROM scores_settings
			WHERE default_team is NOT NULL AND (guild_id) = $1
		""",ctx.guild.id)
		try:
			team = record["default_team"]
		except TypeError:
			team = ""
			
		record = await connection.fetchrow(
		"""
			SELECT default_league FROM scores_settings
			WHERE default_league is NOT NULL AND (guild_id) = $1
		""",ctx.guild.id)
		
		try:
			league = record["default_league"]
		except TypeError:
			league = ""
		
		# Release
		await self.bot.db.release(connection)
		
		# Decide
		if mode == "team":
			return team if team else league
		else:
			return league if league else team

	@commands.command()
	async def table(self,ctx,*,qry:commands.clean_content =None):
		""" Get table for a league """
		async with ctx.typing():
			url = await self.get_default(ctx,"league") if qry is None else ""
				
			if url == "" and qry is not None:
				m = await ctx.send(f"Searching for {qry}...")
				url = await self._search(ctx,m,qry)
			elif qry is None:
				return await ctx.send(f'Specify a search query. A default team or league can be set by server moderators using {ctx.prefix}default <"team" or "league"> <search string>')
			
			if url is None:
				return #rip
			else:
				m = await ctx.send(f"Grabbing table from <{url}>...")

			p = await self.bot.loop.run_in_executor(None,self.parse_table,url)
			
			try:
				await ctx.send(file=p)
			except discord.HTTPException:
				await m.edit(content=f"Failed to grab table from <{url}>")
			
			await m.delete()	
	
	def parse_table(self,url):
		url += "/standings/"
		driver = self.spawn_chrome()
		driver.get(url)
		driver.save_screenshot('screenie.png')
		xp = './/div[@id="glib-stats-data"]'
		
		try:
			tbl = driver.find_element_by_xpath(xp)
		except NoSuchElementException:
			WebDriverWait(driver, 2)
			try:
				tbl = driver.find_element_by_xpath(xp)
			except NoSuchElementException:
				driver.quit()
				return # Rip
		
		# Perform cropoperations.
		location = tbl.location
		size = tbl.size
		im = Image.open("screenie.png")
		left = location['x']
		top = location['y']
		right = location['x'] + size['width']
		bottom = location['y'] + size['height']
		im = im.crop((left, top, right, bottom))
		output = BytesIO()
		im.save(output,"PNG")
		output.seek(0)
		df = discord.File(output,filename="table.png")
		driver.quit()
		return df

	@commands.command()
	async def bracket(self,ctx,*,qry:commands.clean_content=None):
		""" Get btacket for a tournament """
		async with ctx.typing():
			url =  await self.get_default(ctx,"league") if qry is None else ""
			
			if url == "" and qry is not None:
				m = await ctx.send(f"Searching for {qry}...")
				url = await self._search(ctx,m,qry)
			elif qry is None:
				return await ctx.send(f'Specify a search query. A default team or league can be set by server moderators using {ctx.prefix}default <"team" or "league"> <search string>')
			elif url is None:
				return #rip
			else:	
				await ctx.send(f'Grabbing competition bracket for {qry}...',delete_after=5)	
				
			p = await self.bot.loop.run_in_executor(None,self.parse_bracket,url)
			
			try:
				await ctx.send(file=p)
			except discord.HTTPException:
				return await m.edit(content=f"Failed to grab table from <{url}>")		
		
	@commands.command(aliases=["fx"])
	async def fixtures(self,ctx,*,qry:commands.clean_content=None ):
		""" Displays upcoming fixtures for a team or league.
			Navigate with reactions.
		"""
		async with ctx.typing():
			url = await self.get_default(ctx,"team") if qry is None else ""
				
			if url == "" and qry is not None:
				m = await ctx.send(f"Searching for {qry}...")
				url = await self._search(ctx,m,qry)
			elif qry is None:
				return await ctx.send(f'Specify a search query. A default team or league can be set by server moderators using {ctx.prefix}default <"team" or "league"> <search string>')
			elif url is None:
					return #rip
			else:
				await ctx.send(f'Grabbing fixtures data for {qry}...',delete_after=5)			
			
			pages = await self.bot.loop.run_in_executor(None,self.parse_fixtures,url,ctx.author.name)
		await self.paginate(ctx,pages)

	@commands.command(aliases=['sc'])
	async def scorers(self,ctx,*,qry:commands.clean_content=None ):
		""" Displays top scorers for a team or league.
			Navigate with reactions.
		"""
		async with ctx.typing():
			url =  await self.get_default(ctx,preferred="team") if qry is None else ""
				
			if url == "" and qry is not None:
				m = await ctx.send(f"Searching for {qry}...")
				url = await self._search(ctx,m,qry)
			elif qry is None:
				return await ctx.send(f'Specify a search query. A default team or league can be set by server moderators using {ctx.prefix}default <"team" or "league"> <search string>')				
			elif url is None:
				return #rip
			else:
				await ctx.send(f'Grabbing scorers data for {qry}...',delete_after=5)					
				
			pages = await self.bot.loop.run_in_executor(None,self.parse_scorers,url,ctx.author.name)
		await self.paginate(ctx,pages)	
		
	@commands.command(aliases=["rx"])
	async def results(self,ctx,*,qry:commands.clean_content=None ):
		""" Displays previous results for a team or league.
			Navigate with reactions.
		"""
		async with ctx.typing():
			url =  await self.get_default(ctx,"team") if qry is None else ""

			if url == "" and qry is not None:
				m = await ctx.send(f"Searching for {qry}...")
				url = await self._search(ctx,m,qry)
			elif qry is None:
				return await ctx.send(f'Specify a search query. A default team or league can be set by server moderators using {ctx.prefix}default <"team" or "league"> <search string>')				
			
			if url is None:
				return #rip
			else:
				await ctx.send(f'Grabbing results data for {qry}...',delete_after=5)	
			pages = await self.bot.loop.run_in_executor(None,self.parse_results,url,ctx.author.name)
			await self.paginate(ctx,pages)
	
	@commands.command(aliases=["suspensions"])
	async def injuries(self,ctx,*,qry:commands.clean_content = None):
		""" Get a team's current injuries """
		async with ctx.typing():
			url = await self.get_default(ctx,"team") if qry is None else ""

			if url == "" and qry is not None:
				m = await ctx.send(f"Searching for {qry}...")
				url = await self._search(ctx,m,qry)
			elif qry is None:
				return await ctx.send(f'Specify a search query. A default team or league can be set by server moderators using {ctx.prefix}default <"team" or "league"> <search string>')				
			elif url is None:
				return #rip
			else:
				await ctx.send(f'Grabbing injury data for {qry}...',delete_after=5)
			
			e = await self.bot.loop.run_in_executor(None,self.parse_injuries,url,ctx.author.name)
			await m.edit(content="",embed = e)
	
	def parse_injuries(self,url,au):
		t,e,driver = self.get_html(url)
		url += "/squad"
		driver.get(url)
		WebDriverWait(driver,2)
		driver.save_screenshot("injuries.png")
		tree = htmlc.fromstring(driver.page_source)
		driver.quit()
		rows = tree.xpath('.//div[contains(@id,"overall-all-table")]/div[contains(@class,"profileTable__row")]')
		matches = []
		position = ""
		
		for i in rows:
			pos = "".join(i.xpath('./text()')).strip()
			if pos:
				try:
					position = pos.rsplit('s')[0]
				except IndexError:
					position = pos
			
			injury = "".join(i.xpath('.//span[contains(@class,"absence injury")]/@title'))
			if not injury: 
				continue
						
			player = "".join(i.xpath('.//div[contains(@class,"")]/a/text()'))
			link = "".join(i.xpath('.//div[contains(@class,"")]/a/@href'))
			if link:
				link = "http://www.flashscore.com" + link
			
			# Put name in the right order.
			playersplit = player.split(' ',1)
			try:
				player = f"{playersplit[1]} {playersplit[0]}"
			except IndexError:
				pass
			matches.append(f"[{player}]({link}) ({position}): {injury}")
		
		title = "".join(t.xpath('.//div[@class="teamHeader__name"]/text()')).strip()
		e.title = f"Injuries for {title}"
		e.url = url
		if matches:
			e.description = "\n".join(matches)
		else:
			e.description = "No injuries found!"
		return e
			
	def get_color(self,url):
		url = url.strip('"')
		r = requests.get(url).content
		r = BytesIO(r)
		r.seek(0)
		ct = ColorThief(r)
		rgb = ct.get_color(quality=1)
		# Convert to base 16 int.
		return int('%02x%02x%02x' % rgb,16)	
		
	def get_html(self,url):
		driver = self.spawn_chrome()		
		try:
			driver.get(url)
		except TimeoutException:
			driver.execute_script("window.stop();")
			 
		e = discord.Embed()
		try:
			th = driver.find_element_by_xpath(".//div[contains(@class,'logo')]")
			th = th.value_of_css_property('background-image')
			th = th.strip("url(").strip(")")
			e.set_thumbnail(url=th.strip('"'))
			e.color = self.get_color(th)
		except:
			pass
		
		e.url = url
		t = htmlc.fromstring(driver.page_source)
		return t,e,driver

	def parse_results(self,url,au):
		url += "/results"
		t,e,driver = self.get_html(url)
		driver.quit()
		matches = []
		results = t.xpath(".//div[contains(@class,'sportName soccer')]/div")
		
		title = "".join(t.xpath('.//div[@class="teamHeader__name"]/text()')).strip()
		e.title = f"≡ Results for {title}"		
		for i in results:
			d = "".join(i.xpath('.//div[@class="event__time"]//text()')).strip("Pen")
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
			
			# Score
			h,a = i.xpath('.//div[contains(@class,"event__scores")]/span/text()')
			sc = f"{h} - {a}"
			
			# Teams
			ht,at = i.xpath('.//div[contains(@class,"event__participant")]/text()')
			ht,at = ht.strip(),at.strip()
			
			if "(" in ht:
				ht = ht.split('(')[0].strip()
			if "(" in at:
				at = at.split('(')[0].strip()
			
			if "/team/" in url:
				# if we're actually the away team.
				if title in ht:
					wh,op = "A",at
					w = "L" if h < a else "D" if h == a else "W"
				else:
					wh,op = "H",ht
					w = "W" if h < a else "D" if h == a else "L"
				
				matches.append((f"`{wh}: {d}`",f"`{w}: {sc} v {op}`"))
			else:
				matches.append((f"`{d}`",f"`{ht} {sc} {at}`"))
		
		embeds = self.build_embeds(au,e,matches,"Result")
		return embeds
		
	def parse_fixtures(self,url,au):
		url = f"{url}/fixtures"
		t,e,driver = self.get_html(url)
		driver.quit()
		
		title = "".join(t.xpath('.//div[@class="teamHeader__name"]/text()')).strip()
		e.title = f"≡ Fixtures for {title}"
		
		fixtures = t.xpath(".//div[contains(@class,'sportName soccer')]/div")
		matches = []		
		for i in fixtures:
			d = "".join(i.xpath('.//div[@class="event__time"]//text()'))

			if not d:
				continue
				
			try:
				d = datetime.datetime.strptime(d,"%d.%m. %H:%M")
				d = d.replace(year=datetime.datetime.now().year)
				
				if d.month < datetime.datetime.now().month:
					d = d.replace(year=datetime.datetime.now().year + 1)
				elif d.month == datetime.datetime.now().month:
					if d.day < datetime.datetime.now().day:
						d = d.replace(year=datetime.datetime.now().year + 1)

				d = datetime.datetime.strftime(d,"%a %d %b: %H:%M")
			except ValueError: # Fuck this cant be bothered to fix it.
				d = "Tue 31 Feb: 15:00"
				
			tv = i.xpath(".//div[contains(@class,'tv')]")
			if tv:
				tv = i.xpath("./@id")[0].split("_")[-1]
				tv = f" [`📺`](http://www.flashscore.com/match/{tv}/)"
			else:
				tv = ""
			
			h,a = i.xpath('.//div[contains(@class,"event__participant")]/text()')
			
			if "team" in url:
				op,wh = h,"A"
				if title in op:
					op,wh = a,"H"
				matches.append((f"`{d}`",f"`{wh}: {op}`{tv}"))
			else:
				matches.append((f"`{d}`",f"`{h} v {a}` {tv}"))
		embeds = self.build_embeds(au,e,matches,"Fixture")
		return embeds
	
	def parse_bracket(self,bracket):
		driver = self.spawn_chrome()
		driver.get(bracket)

		totwid = 0
		xp = './/div[@class="viewport"]'
		# Generate our base image.
		canvas = Image.new('RGB',(0,0))
		initheight = 0
		runnum = 0

		lastrun = False
		while True:
			bkt = driver.find_element_by_xpath(xp)
			location = bkt.location
			size = bkt.size
			# Try to delete dem ugly arrows.
			try:
				driver.execute_script("document.getElementsByClassName('scroll-left playoff-scroll-button playoff-scroll-button-left')[0].style.display = 'none';")
			except WebDriverException as e:
				print(f"Error'd.\n {e}")
			im = Image.open(BytesIO(bkt.screenshot_as_png))
			left = location['x']
			top = location['y']
			right = location['x'] + size['width']
			bottom = location['y'] + size['height']
			im = im.crop((left, top, right, bottom))
			try:
				z = driver.find_element_by_link_text("scroll right »")
				z.click()
				time.sleep(1)
			except NoSuchElementException:
				lastrun = True
			
			if initheight == 0:
				initheight = size['height']
			# Create new base image and paste old, new.
			if canvas.size[0] == 0:
				newcanvas = Image.new('RGB',(size['width'],initheight))
			else:
				newcanvas = Image.new('RGB',(canvas.size[0] + 220,initheight))
			newcanvas.paste(canvas,(0,0))
			newcanvas.paste(im,(newcanvas.size[0] - size['width'],0,newcanvas.size[0] - size['width'] + im.size[0],0 + im.size[1]))
			canvas = newcanvas
			if lastrun:
				break
		output = BytesIO()
		canvas.save(output,"PNG")
		output.seek(0)
		df = discord.File(output,filename="bracket.png")
		driver.quit()
		return df
	
	def parse_scorers(self,url,au):
		t,e,driver = self.get_html(url)
		
		print(url)
		
		if "team" in url:
			# For individual Team
			scorerdict = {}
			team = "".join(t.xpath('.//div[@class="team-name"]/text()'))
			e.title = f"≡ Top Scorers for {team}"
			players = t.xpath('.//table[contains(@class,"squad-table")]/tbody/tr')
			for i in players:
				p = "".join(i.xpath('.//td[contains(@class,"player-name")]/a/text()'))
				
				if not p:
					continue	
				g = "".join(i.xpath('.//td[5]/text()'))
				if g == "0" or not g:
					continue
				l = "".join(i.xpath('.//td[contains(@class,"player-name")]/a/@href'))
				if g in scorerdict.keys():
					scorerdict[g].append(f"[{' '.join(p.split(' ')[::-1])}](http://www.flashscore.com{l})")
				else:
					scorerdict.update({g:[f"[{' '.join(p.split(' ')[::-1])}](http://www.flashscore.com{l})"]})
			sclist = [[f"{k} : {i}" for i in v] for k,v in scorerdict.items()]
			sclist = [i for sublist in sclist for i in sublist]
			tmlist = [f"[{team}]({url})" for i in sclist]
		else:
			# For cross-league.
			sclist = []
			tmlist = []
			comp = "".join(t.xpath('.//div[@class="tournament-name"]/text()'))
			e.title = f"≡ Top Scorers for {comp}"
			# Re-scrape!
			
			url += "/standings/"
			driver.get(url)
			WebDriverWait(driver, 2)
			try:
				x = driver.find_element_by_link_text("Top Scorers")
				x.click()			
				players = driver.find_element_by_id("table-type-10")
				t = players.get_attribute('innerHTML')
				tree = htmlc.fromstring(t)
				players = tree.xpath('.//tbody/tr')
				for i in players:
					p = "".join(i.xpath('.//td[contains(@class,"player_name")]//a/text()'))
					p = ' '.join(p.split(' ')[::-1])
					if not p:
						continue
					pl = "".join(i.xpath('.//td[contains(@class,"player_name")]/span[contains(@class,"team_name_span")]/a/@onclick'))
					pl = pl.split("'")[1]
					pl = f"http://www.flashscore.com{pl}"
					g = "".join(i.xpath('.//td[contains(@class,"goals_for")]/text()'))
					if g == "0":
						continue
					tm = "".join(i.xpath('.//td[contains(@class,"team_name")]/span/a/text()'))
					tml = "".join(i.xpath('.//td[contains(@class,"team_name")]/span/a/@onclick'))
					tml = tml.split("\'")[1]
					tml = f"http://www.flashscore.com{tml}"
					sclist.append(f"{g} [{p}]({pl})")
					tmlist.append(f"[{tm}]({tml})")
			except WebDriverException:
				driver.save_screenshot('scorers_fail.png')
		driver.quit()
				
		z = list(zip(sclist,tmlist))
		# Make Embeds.
		embeds = []
		p = [z[i:i+10] for i in range(0, len(z), 10)]
		pages = len(p)
		count = 1
		for i in p:
			j = "\n".join([j for j,k in i])
			k = "\n".join([k for j,k in i])
			e.add_field(name="Goals / Player",value=j,inline=True)
			e.add_field(name="Team",value=k,inline=True)
			iu = "http://pix.iemoji.com/twit33/0056.png"
			e.set_footer(text=f"Page {count} of {pages} ({au})",icon_url=iu)
			te = deepcopy(e)
			embeds.append(te)
			e.clear_fields()
			count += 1

		return embeds	

	async def paginate(self,ctx,pages):
		page = 0
		if not pages:
			return
		numpages = len(pages)
		m = await ctx.send(embed=pages[0])
		if numpages == 1:
			return
		await m.add_reaction("⏮")
		if numpages > 2:
			await m.add_reaction("⬅")
			await m.add_reaction("➡")
		await m.add_reaction("⏭")
		await m.add_reaction("⏏")
		def check(r,u):
			if r.message.id == m.id and u == ctx.author:
				e = str(r.emoji)
				return e.startswith(('⏮','⬅','➡','⏭','⏏'))
		while True:
			try:
				wf = "reaction_add"
				r = await self.bot.wait_for(wf,check=check,timeout=120)
			except asyncio.TimeoutError:
				try:
					await m.clear_reactions()
				except discord.Forbidden:
					pass
				break
			r = r[0]
			if r.emoji == "⏮": #first	
				page = 0
				try:
					await m.remove_reaction("⏮",ctx.author)
				except discord.Forbidden:
					pass
			if r.emoji == "⬅": #prev
				try:
					await m.remove_reaction("⬅",ctx.author)
				except discord.Forbidden:
					pass
				if page > 0:
					page = page - 1
			if r.emoji == "➡": #next
				try:
					await m.remove_reaction("➡",ctx.author)
				except discord.Forbidden:
					pass
				if page < numpages - 1:
					page = page + 1
			if r.emoji == "⏭": #last
				page = numpages - 1
				try:
					await m.remove_reaction("⏭",ctx.author)
				except discord.Forbidden:
					pass
			if r.emoji == "⏏": #eject
				return await m.delete()
			await m.edit(embed=pages[page])
		
	def build_embeds(self,au,e,z,type):
		embeds = []
		p = [z[i:i+10] for i in range(0, len(z), 10)]
		pages = len(p)
		count = 1
		for i in p:
			j = "\n".join([j for j,k in i])
			k = "\n".join([k for j,k in i])
			e.add_field(name="Date",value=j,inline=True)
			e.add_field(name=type,value=k,inline=True)
			iu = "http://pix.iemoji.com/twit33/0056.png"
			e.set_footer(text=f"Page {count} of {pages} ({au})",icon_url=iu)
			te = deepcopy(e)
			embeds.append(te)
			e.clear_fields()
			count += 1
		return embeds
	
	@commands.has_permissions(manage_guild=True)
	@commands.command(usage = "default <'team' or 'league'> <(Your Search Query) or ('None' to unset default.)")
	async def default(self,ctx,type,*,qry:commands.clean_content = None):
		""" Set a default team or league for your server's lookup commands """
		# Validate
		type = type.lower()
		if type not in ["league","team"]:
			return await ctx.send(':no_entry_sign: Invalid default type specified, valid types are "league" or "team"')
		xtype = "default_team" if type == "team" else "default_league"
		
		if qry is None:
			try:
				return await ctx.send(self.defaults[ctx.guild.id][type])
			except:
				return await ctx.send(f"Your current {type} is not set! Set it with {ctx.prefix}{ctx.	command.usage}")

		# Find
		if qry == "none":
			url = None
		elif qry.lower() is not "none":
			m = await ctx.send(f'Searching for {qry}...')
			url = await self._search(ctx,m,qry,mode=type)
			if not url:
				return await ctx.send("Couldn't find anything for {qry}, try searching for something else.")
		
		connection = await self.bot.db.acquire()
		
		async with connection.transaction():
			await connection.execute(
			f"""INSERT INTO scores_settings (guild_id,{xtype})
				VALUES ($1,$2)
				
				ON CONFLICT (guild_id) DO UPDATE SET 
					{xtype} = $2
				WHERE excluded.guild_id = $1
			""",ctx.guild.id,url)
		
		await self.bot.db.release(connection)
		
		if qry is not None:
			return await ctx.send(f'Your commands will now use <{url}> as a default {type}')
		else:
			return await ctx.send(f'Your commands will no longer use a default {type}')
			


			
def setup(bot):
	bot.add_cog(Fixtures(bot))