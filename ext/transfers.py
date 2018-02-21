from discord.ext import commands
import discord, aiohttp, asyncio
from lxml import html
from PIL import Image, ImageDraw, ImageFont
import pycountry
import datetime
import operator
import json

# Manual Country Code Flag Dict
ctrydict = {
    "American Virgin Islands": "vi",
    "Antigua and Barbuda": "ag",
    "Bolivia": "bo",
    "Bosnia-Herzegovina": "ba",
    "Botsuana": "bw",
    "British Virgin Islands": "vg",
    "Cape Verde": "cv",
    "Cayman-Inseln": "ky",
    "Chinese Taipei (Taiwan)": "tw",
    "Congo DR": "cd",
	"Curacao" : "cw",
	"DR Congo": "cd",
    "Cote d'Ivoire": "ci",
    "CSSR": "cz",
    "Czech Republic": "cz",
    "England": "gb",
    "Faroe Island": "fo",
    "Federated States of Micronesia": "fm",
    "Hongkong": "hk",
    "Iran": "ir",
    "Korea, North": "kp",
    "Korea, South": "kr",
    "Kosovo": "xk",
    "Laos": "la",
    "Macedonia": "mk",
    "Mariana Islands": "mp",
    "Moldova": "md",
    "N/A": "x",
    "Netherlands Antilles": "nl",
    "Neukaledonien": "nc",
    "Northern Ireland": "gb",
    "Osttimor": "tl",
    "Palästina": "ps",
    "Russia": "ru",
    "Scotland": "gb",
    "Sint Maarten": "sx",
    "St. Kitts &Nevis": "kn",
    "St. Louis": "lc",
    "St. Vincent & Grenadinen": "vc",
    "Tahiti": "fp",
    "Tanzania": "tz",
    "The Gambia": "gm",
    "Trinidad and Tobago": "tt",
    "Turks- and Caicosinseln": "tc",
    "Venezuela": "ve",
    "Vietnam": "vn",
    "Wales": "gb"}
unidict = {
	"a":"🇦","b":"🇧","c":"🇨","d":"🇩","e":"🇪",
	"f":"🇫","g":"🇬","h":"🇭","i":"🇮","j":"🇯",
	"k":"🇰","l":"🇱","m":"🇲","n":"🇳","o":"🇴",
	"p":"🇵","q":"🇶","r":"🇷","s":"🇸","t":"🇹",
	"u":"🇺","v":"🇻","w":"🇼","x":"🇽","y":"🇾","z":"🇿"
	}

class Transfers:
	""" Transfermarket lookups """
	def __init__(self, bot):
		self.bot = bot
		self.parsed = []
		self.transferson = True
		self.bot.transferticker = bot.loop.create_task(self.transfer_ticker())
		self.cats = {
			"players":{
				"cat":"players",
				"func":self._player,
				"querystr":"Spieler_page",
				"parser":self.parse_players
			},
			"managers":{
				"cat":"Managers",
				"func":self._manager,
				"querystr":"Trainer_page",
				"parser":self.parse_managers
			},
			"clubs":{
				"cat":"Clubs",
				"func":self._team,
				"querystr":"Verein_page",
				"parser":self.parse_clubs
			},
			"referees":{
				"cat":"referees",
				"func":self._ref,
				"querystr":"Schiedsrichter_page",
				"parser":self.parse_refs
			},
			"domestic competitions":{
				"cat":"to competitions",
				"func":self._cup,
				"querystr":"Wettbewerb_page",
				"parser":self.parse_cups
			},
			"international Competitions":{
				"cat":"International Competitions",
				"func":self._int,
				"querystr":"Wettbewerb_page",
				"parser":self.parse_int
			},
			"agent":{
				"cat":"Agents",
				"func":self._agent,
				"querystr":"page",
				"parser":self.parse_agent
			},
			"Transfers":{
				"cat":"Clubs",
				"func":self._team,
				"querystr":"Verein_page",
				"parser":self.parse_clubs,
				"outfunc":self.get_transfers
			},
			"Injuries":{
				"cat":"Clubs",
				"func":self._team,
				"querystr":"Verein_page",
				"parser":self.parse_clubs,
				"outfunc":self.get_injuries
			},
			"Rumours":{
				"cat":"Clubs",
				"func":self._team,
				"querystr":"Verein_page",
				"parser":self.parse_clubs,
				"outfunc":self.get_rumours
			}
		}
	
	def __unload(self):
		self.bot.transferticker.cancel()
		self.transferson = False
	
	async def imgurify(self,imgurl):
		d = {"image":imgurl}
		h = {'Authorization': self.bot.credentials["Imgur"]["Authorization"]}
		async with self.bot.session.post("https://api.imgur.com/3/image",data = d,headers=h) as resp:
			res = await resp.json()
		return res['data']['link']
		
	async def transfer_ticker(self):
		await self.bot.wait_until_ready()
		firstrun = True
		while self.transferson:
			try:
				async with self.bot.session.get('https://www.transfermarkt.co.uk/statistik/neuestetransfers') as resp:
					if resp.status != 200:
						return await ctx.send(f'{resp.status} error accessing to {resp.url}')
					tree = html.fromstring(await resp.text())
			except:
				continue
			players = tree.xpath('.//div[@class="responsive-table"]/div/table/tbody/tr')

			for i in players:
				pname = "".join(i.xpath('.//td[1]//tr[1]/td[2]/a/text()'))
				if not pname:
					continue
				if pname in self.parsed:
					continue # continue when loop.
				if firstrun:
					self.parsed.append(pname)
					continue
				e = discord.Embed(color = 0x1a3151)
				e.set_author(name=pname)
				
				# Player Profile Link
				plink = "".join(i.xpath('.//td[1]//tr[1]/td[2]/a/@href'))
				e.url = f"https://www.transfermarkt.co.uk{plink}"
				
				# Age and position
				age = "".join(i.xpath('./td[2]//text()')).strip()
				pos = "".join(i.xpath('./td[1]//tr[2]/td/text()'))
				e.description = f"{age}, {pos}"
				
				# Nationality
				nat = i.xpath('.//td[3]/img/@title')
				flags = []
				for j in nat:
					flags.append(self.get_flag(j))
				natout = ", ".join([f'{j[0]} {j[1]}' for j in list(zip(flags,nat))])
				e.description += f" ({natout})"
				
				# To, From, Fee
				movedtoteam = "".join(i.xpath('.//td[5]/table//tr[1]/td/a/text()'))
				movedtolink = "".join(i.xpath('.//td[5]/table//tr[1]/td/a/@href'))
				mtleague = "".join(i.xpath('.//td[5]/table//tr[2]/td/a/text()'))
				mtllink = "".join(i.xpath('.//td[5]/table//tr[2]/td/a/@href'))
				if mtllink:
					mtllink = f"https://www.transfermarkt.co.uk{mttlink}"
				mttflag = self.get_flag("".join(i.xpath('.//td[5]/table//tr[2]/td//img/@alt')))
				mttflag = f"{mttflag} "
				movedto = f"[{movedtoteam}](https://www.transfermarkt.co.uk{movedtolink}) " \
							f"([{mttflag}{mtleague}]({mtllink}))"
				
				e.description += f"\n**To:** {movedto}"				
				
				movedfromteam = "".join(i.xpath('.//td[4]/table//tr[1]/td/a/text()'))
				movedfromlink = "".join(i.xpath('.//td[4]/table//tr[1]/td/a/@href'))
				mfleague = "".join(i.xpath('.//td[4]/table//tr[2]/td/a/text()'))
				mfleague = "".join(i.xpath('.//td[4]/table//tr[2]/td/a/@href'))
				if mfleague:
					mfleague = f"https://www.transfermarkt.co.uk{mfleague}"
				mftflag = self.get_flag("".join(i.xpath('.//td[4]/table//tr[2]/td//img/@alt')))
				mftflag = f"{mftflag} "
				movedfrom = f"[{movedfromteam}](https://www.transfermarkt.co.uk{movedfromlink}) " \
							f"([{mflflag}{mfleague}](https://www.transfermarkt.co.uk{mfleague}))"
				
				e.description += f"\n**From:** {movedfrom}"
							
				fee = "".join(i.xpath('.//td[6]//a/text()'))
				feelink = "".join(i.xpath('.//td[6]//a/@href'))
				
				e.description += f"\n**Fee:** [{fee}]({feelink})"
				# Get picture and rehost on imgur.
				th = "".join(i.xpath('.//td[1]//tr[1]/td[1]/img/@src'))
				th = await self.imgurify(th)
				e.set_thumbnail(url=th)
				self.parsed.append(pname)
				for i in self.bot.config:
					try:
						ch = self.bot.config[i]["transfers"]["channel"]
						ch = self.bot.get_channel(ch)
						if ch is None:
							continue
					except KeyError:
						continue
					try:
						mode = self.bot.config[i]["transfers"]["mode"]
					except:
						await ch.send(embed=e)
					if mode == "default":
						await ch.send(embed=e)
					elif mode == "blacklist":
						blacklist = self.bot.config[i]["transfers"]["blacklist"]
						if mfleague in blacklist and mtleague in blacklist:
							continue
						else:
							await ch.send(embed=e)
					elif mode == "whitelist":
						whitelist = self.bot.config[i]["transfers"]["whitelist"]
						if mfleague in blacklist or mtleague in whitelist:
							await ch.send(embed=e)
						
			firstrun = False
			# Run every 5 mins
			await asyncio.sleep(60)
	
	# Enable the ticker
	@commands.group(invoke_without_command=True,aliases=["tf"])
	@commands.is_owner()
	async def transferticker(self,ctx):
		""" Check the status of the transfers channel """
		e = discord.Embed(title="Transfer Channel Status")
		e.set_thumbnail(url=ctx.guild.icon_url)
		if self.transferson:
			e.description = "```diff\n+ Enabled```"
			e.color=0x00ff00
		else:
			e.description = "```diff\n- Disabled```"
			e.color = 0xff0000
		
		try:
			ch = self.bot.config[str(ctx.guild.id)]['transfers']['channel']
			chan = self.bot.get_channel(ch)
			chanval = chan.mention
		except KeyError:
			chanval = "None Set"
			e.color = 0xff0000
		e.add_field(name=f"output Channel",value=chanval,inline=False)
		
		if self.bot.is_owner(ctx.author):
			x =  self.bot.transferticker._state
			if x == "PENDING":
				v = "? Task running."
			elif x == "CANCELLED":
				e.color = 0xff0000
				v = "? Task Cancelled."
			elif x == "FINISHED":
				e.color = 0xff0000
				self.bot.transferticker.print_stack()
				v = "? Task Finished"
				z = self.bot.transferticker.exception()
			else:
				v = f"? `{self.bot.transferticker._state}`"
			e.add_field(name="Debug Info",value=v,inline=False)
			try:
				e.add_field(name="Exception",value=z,inline=False)
			except NameError:
				pass
		await ctx.send(embed=e)
	
	@transferticker.command(name="on")
	@commands.has_permissions(manage_messages=True)
	async def transfers_on(self,ctx):
		""" Turn the transfer ticker channel back on """
		if not self.transferson:
			self.transferson = True
			await ctx.send("? Transfer ticker channel has been enabled.")
			self.bot.transferticker = self.bot.loop.create_task(self.ls())
		elif self.bot.scorechecker._state == ["FINISHED","CANCELLED"]:
			await ctx.send(f"? Restarting {self.bot.transferticker._state} task after exception {self.bot.transferticker.exception()}.")
			self.bot.transferticker = bot.loop.create_task(self.ls())
		else:
			await ctx.send("? Transfer ticker channel has been enabled.")
	
	@transferticker.command(name="off")
	@commands.has_permissions(manage_messages=True)
	async def transfers_off(self,ctx):	
		""" Turn off the transfer ticker channel """
		if self.transferson:
			self.transferson = False
			await ctx.send("? Transfer ticker channel has been disabled.")
		else:
			await ctx.send("? Transfer ticker channel already disabled.")
	
	@transferticker.command(name="mode")
	@commands.has_permissions(manage_channels=True)
	async def mode(self,ctx,*,mode=None):
		""" Set the transfer channel to blacklist or whitelist mode"""
		try:
			ch = self.bot.config[str(ctx.guild.id)]['transfers']['channel']
			chan = self.bot.get_channel(ch).mention
		except AttributeError:
			return await ctx.send(f"Please set your transfers channel first using {ctx.prefix}tf set in your desired transfers channel")
		
		if not mode:
			try:
				mode = self.bot.config[str(ctx.guild.id)]["transfers"]["mode"]
			except KeyError:
				self.bot.config[str(ctx.guild.id)]["transfers"]["mode"] = "default"
				mode = "default"
				with await self.bot.configlock:
					with open('config.json',"w",encoding='utf-8') as f:
						json.dump(self.bot.config,f,ensure_ascii=True,
						sort_keys=True,indent=4, separators=(',',':'))
			if mode == "default":
				return await ctx.send(f'{chan} mode is currently set to default, all detected transfers will be output.')
			elif mode == "blacklist":
				await ctx.send(f'{chan} mode is currently set to blacklist mode, transfers from your blacklisted leagues will not be output:')
				return await ctx.invoke(self.blacklist)
			elif mode == "whitelist":
				await ctx.send(f'{chan} mode is currently set to whitelist mode, only transfers from your whitelisted leagues will be output:')
				return await ctx.invoke(self.whitelist)				
		else:
			mode = mode.lower()
			
		if mode not in ["blacklist","whitelist","default"]:
			return await ctx.send('Invalid mode selected, valid modes are "default", "blacklist", or "whitelist"')

		self.bot.config[str(ctx.guild.id)]["transfers"]["mode"] = mode
		with await self.bot.configlock:
			with open('config.json',"w",encoding='utf-8') as f:
				json.dump(self.bot.config,f,ensure_ascii=True,
				sort_keys=True,indent=4, separators=(',',':'))
		return await ctx.send(f"{chan} mode set to {mode}")
	
	@transferticker.group(invoke_without_command=True)
	@commands.has_permissions(manage_channels=True)
	async def whitelist(self,ctx):
		# Check we have an active transfers channel.
		ch = self.bot.config[str(ctx.guild.id)]['transfers']['channel']
		try:
			chan = self.bot.get_channel(ch).mention
		except AttributeError:
			return await ctx.send('Please set your transfers channel first using {ctx.prefix}tf set in your desired transfers channel')
		
		try:
			whitelist = self.bot.config[str(ctx.guild.id)]['transfers']['whitelist']
		except KeyError:
			self.bot.config[str(ctx.guild.id)]['transfers']['whitelist'] = []
			whitelist = []
		if not whitelist:
			await ctx.send(f'Your current whitelist is empty, use {ctx.prefix}tf whitelist add leaguename')
		else:
			try:
				await ctx.send(f'Your current whitelist is: ```{", ".join(whitelist)}```, use {ctx.prefix}tf whitelist `add` or `del` and a name to add or delete to edit this list')
			except:
				await ctx.send(f'Your current whitelist has {len(whitelist)} items, use {ctx.prefix}tf whitelist `add` or `del` and a name to add or delete to edit this list')
	
	@whitelist.command(name="add")
	@commands.has_permissions(manage_channels=True)
	async def wl_add(self,ctx,*,item):
		# Check we have an active transfers channel.
		ch = self.bot.config[str(ctx.guild.id)]['transfers']['channel']
		try:
			chan = self.bot.get_channel(ch).mention
		except AttributeError:
			return await ctx.send('Please set your transfers channel first using {ctx.prefix}tf set in your desired transfers channel')
	
		if item in self.bot.config[str(ctx.guild.id)]['transfers']['whitelist']:
			return await ctx.send(f'{item} is already in your transfers whitelist')
		else:
			self.bot.config[str(ctx.guild.id)]['transfers']['whitelist'].append(item)
		
		with await self.bot.configlock:
			with open('config.json',"w",encoding='utf-8') as f:
				json.dump(self.bot.config,f,ensure_ascii=True,
				sort_keys=True,indent=4, separators=(',',':'))
		
		bl = ", ".join(self.bot.config[str(ctx.guild.id)]['transfers']['whitelist'])
		await ctx.send(f"{chan} whitelist updated: ```{bl}```")
		
	@whitelist.command(name="del")
	@commands.has_permissions(manage_channels=True)
	async def wl_del(self,ctx,*,item):
		# Check we have an active transfers channel.
		ch = self.bot.config[str(ctx.guild.id)]['transfers']['channel']
		try:
			chan = self.bot.get_channel(ch).mention
		except AttributeError:
			return await ctx.send('Please set your transfers channel first using {ctx.prefix}tf set in your desired transfers channel')
	
		if not item in self.bot.config[str(ctx.guild.id)]['transfers']['whitelist']:
			return await ctx.send(f'{item} is not your transfers whitelist')
		else:
			self.bot.config[str(ctx.guild.id)]['transfers']['whitelist'].remove(item)
		
		with await self.bot.configlock:
			with open('config.json',"w",encoding='utf-8') as f:
				json.dump(self.bot.config,f,ensure_ascii=True,
				sort_keys=True,indent=4, separators=(',',':'))
		
		bl = ", ".join(self.bot.config[str(ctx.guild.id)]['transfers']['whitelist'])
		if not bl:
			await ctx.send(f'{item} removed from {chan}, your transfers whitelist is now empty')
		else:
			try:
				await ctx.send(f"{item} removed from {chan}, your current whitelist: ```{bl}```")
			except:
				await ctx.send(f"{item} removed from {chan}.")
	
	
	@transferticker.group(invoke_without_command=True)
	@commands.has_permissions(manage_channels=True)
	async def blacklist(self,ctx):
		# Check we have an active transfers channel.
		ch = self.bot.config[str(ctx.guild.id)]['transfers']['channel']
		try:
			chan = self.bot.get_channel(ch).mention
		except AttributeError:
			return await ctx.send('Please set your transfers channel first using {ctx.prefix}tf set in your desired transfers channel')
		
		try:
			blacklist = self.bot.config[str(ctx.guild.id)]['transfers']['blacklist']
		except KeyError:
			self.bot.config[str(ctx.guild.id)]['transfers']['blacklist'] = []
			blacklist = []
		if not blacklist:
			await ctx.send(f'Your current blacklist is empty, use {ctx.prefix}tf blacklist add leaguename')
		else:
			try:
				await ctx.send(f'Your current blacklist is: ```{", ".join(blacklist)}```, use {ctx.prefix}tf blacklist `add` or `del` and a name to add or delete to edit this list')
			except:
				await ctx.send(f'Your current blacklist has {len(blacklist)} items, use {ctx.prefix}tf blacklist `add` or `del` and a name to add or delete to edit this list')

	@blacklist.command(name="add")
	@commands.has_permissions(manage_channels=True)
	async def bl_add(self,ctx,*,item):
		# Check we have an active transfers channel.
		ch = self.bot.config[str(ctx.guild.id)]['transfers']['channel']
		try:
			chan = self.bot.get_channel(ch).mention
		except AttributeError:
			return await ctx.send('Please set your transfers channel first using {ctx.prefix}tf set in your desired transfers channel')
	
		if item in self.bot.config[str(ctx.guild.id)]['transfers']['blacklist']:
			return await ctx.send(f'{item} is already in your transfers blacklist')
		else:
			self.bot.config[str(ctx.guild.id)]['transfers']['blacklist'].append(item)
		
		with await self.bot.configlock:
			with open('config.json',"w",encoding='utf-8') as f:
				json.dump(self.bot.config,f,ensure_ascii=True,
				sort_keys=True,indent=4, separators=(',',':'))
		
		bl = ", ".join(self.bot.config[str(ctx.guild.id)]['transfers']['blacklist'])
		await ctx.send(f"{chan} blacklist updated: ```{bl}```")
		
	@blacklist.command(name="del")
	@commands.has_permissions(manage_channels=True)
	async def bl_del(self,ctx,*,item):
		# Check we have an active transfers channel.
		ch = self.bot.config[str(ctx.guild.id)]['transfers']['channel']
		try:
			chan = self.bot.get_channel(ch).mention
		except AttributeError:
			return await ctx.send('Please set your transfers channel first using {ctx.prefix}tf set in your desired transfers channel')
	
		if not item in self.bot.config[str(ctx.guild.id)]['transfers']['blacklist']:
			return await ctx.send(f'{item} is not your transfers blacklist')
		else:
			self.bot.config[str(ctx.guild.id)]['transfers']['blacklist'].remove(item)
		
		with await self.bot.configlock:
			with open('config.json',"w",encoding='utf-8') as f:
				json.dump(self.bot.config,f,ensure_ascii=True,
				sort_keys=True,indent=4, separators=(',',':'))
		
		bl = ", ".join(self.bot.config[str(ctx.guild.id)]['transfers']['blacklist'])
		if not bl:
			await ctx.send(f'{item} removed from {chan}, your transfers blacklist is now empty')
		else:
			try:
				await ctx.send(f"{item} removed from {chan}, your current blacklist: ```{bl}```")
			except:
				await ctx.send(f"{item} removed from {chan}.")
	
	@transferticker.command(name="set")
	@commands.has_permissions(manage_channels=True)
	async def _set(self,ctx):
		""" Sets the transfer ticker channel for this server """
		self.bot.config[f"{ctx.guild.id}"].update({"transfers":{"channel":ctx.channel.id}})
		with await self.bot.configlock:
			with open('config.json',"w",encoding='utf-8') as f:
				json.dump(self.bot.config,f,ensure_ascii=True,
				sort_keys=True,indent=4, separators=(',',':'))
		await ctx.send(f"Transfer ticker channel for {ctx.guild.name} set to {ctx.channel.mention}")
	
	@transferticker.command(name="unset")
	@commands.has_permissions(manage_channels=True)
	async def _unset(self,ctx):
		""" Unsets the live score channel for this server """
		self.bot.config[str(ctx.guild.id)]["transfers"]["channel"] = None
		with await self.bot.configlock:
			with open('config.json',"w",encoding='utf-8') as f:
				json.dump(self.bot.config,f,ensure_ascii=True,
				sort_keys=True,indent=4, separators=(',',':'))
		await ctx.send(f"Transfer ticker channel for {ctx.guild.name} set to None")
	
	# Base lookup - No Subcommand.
	@commands.group(invoke_without_command=True)
	async def lookup(self,ctx,*,target:str):
		""" Perform a database lookup on transfermarkt """
		p = {"query":target} # html encode.
		async with self.bot.session.post(f"http://www.transfermarkt.co.uk/schnellsuche/ergebnis/schnellsuche",params=p) as resp:
			if resp.status != 200:
				return await ctx.send(f"HTTP Error connecting to transfernarkt: {resp.status}")
			tree = html.fromstring(await resp.text())
		
		replacelist = ["🇦","🇧",'🇨','🇩','🇪','🇫','🇬']
		
		# Header names, scrape then compare (because they don't follow a pattern.)
		cats = [i.lower() for i in tree.xpath(".//div[@class='table-header']/text()")]

		res = {}
		for i in cats:
			# Just give us the number of matches by replacing non-digit characters.
			length = [int(n) for n in i if n.isdigit()][0]
			if length:
				letter = replacelist.pop(0)
				for j in self.cats:
					if j in i:
						res[letter] = (f"{letter} {length} {self.cats[j]['cat']}",self.cats[j]['func'])
		if not res:
			return await ctx.send(f":mag: No results for {target}")
		sortedlist = [i[0] for i in sorted(res.values())]

		# If only one category has results, invoke that search.
		if len(sortedlist) == 1:
			return await ctx.invoke(res["🇦"][1],qry=target)
			
		res["⏏"] = ("","")
		e = discord.Embed(url = str(resp.url))
		e.title = "Transfermarkt lookup"
		e.description = "\n".join(sortedlist)
		e.color = 0x1a3151
		e.set_footer(text="Select a category using reactions")
		e.set_thumbnail(url="http://www.australian-people-records.com/images/Search-A-Person.jpg")
		m = await ctx.send(embed=e)
		for key in sorted(res.keys()):
			await m.add_reaction(key)

		def check(reaction,user):
			if reaction.message.id == m.id and user == ctx.author:
				e = str(reaction.emoji)
				return e in res.keys()
		
		# Wait for appropriate reaction
		try:
			rea = await self.bot.wait_for("reaction_add",check=check,timeout=120)
		except asyncio.TimeoutError:
			return await m.clear_reactions()
		rea = rea[0]
		if rea.emoji == "⏏": #eject cancels.
			return await m.clear_reactions()
		elif rea.emoji in res.keys():
			# invoke appropriate subcommand for category selection.
			await m.delete()
			return await ctx.invoke(res[rea.emoji][1],qry=target)
	
	@lookup.command(name="player")
	async def _player(self,ctx,*,qry):
		""" Lookup a player on transfermarkt """
		await self.search(ctx,qry,"players")
		
	@lookup.command(name="manager",aliases=["staff","trainer","trainers","managers"])
	async def _manager(self,ctx,*,qry):
		""" Lookup a manager/trainer/club official on transfermarkt """
		await self.search(ctx,qry,"managers")
		
	@lookup.command(name="team",aliases=["club","squad","teams","clubs"])
	async def _team(self,ctx,*,qry):
		""" Lookup a team on transfermarkt """
		await self.search(ctx,qry,"clubs")
	
	@lookup.command(name="ref")
	async def _ref(self,ctx,*,qry):
		""" Lookup a referee on transfermarkt """
		await self.search(ctx,qry,"referees")
	
	@lookup.command(name="cup",aliases=["domestic"])
	async def _cup(self,ctx,*,qry):
		""" Lookup a domestic competition on transfermarkt """
		await self.search(ctx,qry,"domestic competitions")
	
	@lookup.command(name="international",aliases=["int"])
	async def _int(self,ctx,*,qry):
		""" Lookup an international competition on transfermarkt """
		await self.search(ctx,qry,"International Competitions")
		
	@lookup.command(name="agent")
	async def _agent(self,ctx,*,qry):
		""" Lookup an agent on transfermarkt """
		await self.search(ctx,qry,"Agent")
		
	@commands.command(aliases=["loans"])
	async def transfers(self,ctx,*,qry):
		""" Get this season's transfers for a team on transfermarkt """
		if ctx.channel.id == 332163136239173632:
			return await ctx.send(self.bot.get_channel(332167049273016320).mention)
		await self.search(ctx,qry,"Transfers",special=True)
	
	@commands.command()
	async def rumours(self,ctx,*,qry):
		await self.search(ctx,qry,"Rumours",special=True)
	
	@commands.command(alises=["bans","suspensions","injured","hurt","banned"])
	async def injuries(self,ctx,*,qry):
		""" Get current injuries and suspensions for a team on transfermarkt """
		await self.search(ctx,qry,"Injuries",special=True)	
	
	async def fetch(self,ctx,category,query,page):
		p = {"query":query,self.cats[category]["querystr"]:page}
		url = 'http://www.transfermarkt.co.uk/schnellsuche/ergebnis/schnellsuche'
		async with self.bot.session.post(url,params=p) as resp:
			if resp.status != 200:
				await ctx.send(f"HTTP Error connecting to transfernarkt: {resp.status}")
				return None
			tree = html.fromstring(await resp.text())	
		categ = self.cats[category]["cat"]
		
		# Get trs of table after matching header / {categ} name.
		matches = f".//div[@class='box']/div[@class='table-header'][contains(text(),'{categ}')]/following::div[1]//tbody/tr"
		e = discord.Embed()
		e.color = 0x1a3151
		e.title = "View full results on transfermarkt"
		e.url = str(resp.url)
		e.set_author(name=tree.xpath(f".//div[@class='table-header'][contains(text(),'{categ}')]/text()")[0])
		e.description = ""
		numpages = int("".join([i for i in e.author.name if i.isdigit()])) // 10 + 1
		e.set_footer(text=f"Page {page} of {numpages}")
		return e,tree.xpath(matches),numpages
	
	async def search(self,ctx,qry,category,special=False):
		page = 1
		e,tree,maxpage = await self.fetch(ctx,category,qry,page)
		if not tree:
			return await ctx.send("No results.")
		
		lines,targets = await self.cats[category]["parser"](tree)
		
		def make_embed(e,lines,targets):
			e.description = ""
			if special:
				replacelist = ["🇦","🇧",'🇨','🇩','🇪',
							   '🇫','🇬',"🇭","🇮","🇯"]
				reactdict = {}
				for i,j in zip(lines,targets):
					emoji = replacelist.pop(0)
					reactdict[emoji] = j
					e.description += f"{emoji} {i}\n"
				return e,reactdict
			else:
				for i in lines:
					e.description += f"{i}\n"
			return e
		
		if special:
			e,reactdict = make_embed(e,lines,targets)
		else:
			e = make_embed(e,lines,targets)
		# Create message and add reactions		
		m = await ctx.send(embed=e)	
		await m.add_reaction("⏏") # eject
		if maxpage > 2:
			await m.add_reaction("⏮") # first
		if maxpage > 1:
			await m.add_reaction("◀") # prev
		if special:
			for i in reactdict:
				await m.add_reaction(i)
		if maxpage > 1:
			await m.add_reaction("▶") # next
		if maxpage > 2:
			await m.add_reaction("⏭") # last
		
		# Only respond to user who invoked command.
		def check(reaction,user):
			if reaction.message.id == m.id and user == ctx.author:
				e = str(reaction.emoji)
				if special:
					return e.startswith(('⏮','◀','▶','⏭','⏏')) or e in reactdict
				else:
					return e.startswith(('⏮','◀','▶','⏭','⏏'))
		
		# Reaction Logic Loop.
		while True:
			try:
				res = await self.bot.wait_for("reaction_add",check=check,timeout=30)
			except asyncio.TimeoutError:
				await m.clear_reactions()
				break
			res = res[0]
			if res.emoji == "⏮": #first
				page = 1
				await m.remove_reaction("⏮",ctx.message.author)
			if res.emoji == "◀": #prev
				await m.remove_reaction("◀",ctx.message.author)
				if page > 1:
					page = page - 1
			if res.emoji == "▶": #next	
				await m.remove_reaction("▶",ctx.message.author)
				if page < maxpage:
					page = page + 1
			if res.emoji == "⏭": #last
				page = maxpage
				await m.remove_reaction("⏭",ctx.message.author)
			if res.emoji == "⏏": #eject
				await m.clear_reactions()
				break
			if res.emoji in reactdict:
				await m.delete()
				match = reactdict[res.emoji]
				return await self.cats[category]["outfunc"](ctx,e,match)

			e,tree,maxpage = await self.fetch(ctx,category,qry,page)
			if tree:
				lines,targets = await self.cats[category]["parser"](tree)
				e,reactdict = make_embed(lines,targets)
				await m.edit(embed=e)

	def get_flag(self,ctry):
		# Check if pycountry has country
		try:					
			ctry = pycountry.countries.get(name=ctry.title()).alpha_2
		except KeyError:
			try:
				# else revert to manual dict.
				ctry = ctrydict[ctry]
			except KeyError:
				print(f"Fail for: {ctry}")
		ctry = ctry.lower()
		for key,value in unidict.items():
			ctry = ctry.replace(key,value)
		return ctry

	async def parse_players(self,trs):	
		output,targets = [],[]
		for i in trs:
			pname = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/text()'))
			plink = "".join(i.xpath('.//a[@class="spielprofil_tooltip"]/@href'))
			plink = f"http://transfermarkt.co.uk{plink}"
			team  = "".join(i.xpath('.//td[3]/a/img/@alt'))
			tlink = "".join(i.xpath('.//td[3]/a/img/@href'))
			tlink = f"http://transfermarkt.co.uk{tlink}"
			age   = "".join(i.xpath('.//td[4]/text()'))
			ppos  = "".join(i.xpath('.//td[2]/text()'))
			flag  = self.get_flag( "".join(i.xpath('.//td/img[1]/@title')))
			
			output.append(f"{flag} [{pname}]({plink}) {age}, {ppos} [{team}]({tlink})")
			targets.append(plink)
		return output,targets

	async def parse_managers(self,trs):
		output,targets = [],[]
		for i in trs:
			mname = "".join(i.xpath('.//td[@class="hauptlink"]/a/text()'))
			mlink = "".join(i.xpath('.//td[@class="hauptlink"]/a/@href'))
			mlink = f"http://transfermarkt.co.uk{mlink}"
			team  = "".join(i.xpath('.//td[2]/a/img/@alt'))
			tlink = "".join(i.xpath('.//td[2]/a/img/@href'))
			tlink = f"http://transfermarkt.co.uk{tlink}"
			age   = "".join(i.xpath('.//td[3]/text()'))
			job   = "".join(i.xpath('.//td[5]/text()'))
			flag  = self.get_flag("".join(i.xpath('.//td/img[1]/@title')))
			
			output.append(f"{flag} [{mname}]({mlink}) {age}, {job} [{team}]({tlink})")
			targets.append(mlink)
		return output,targets
	
	async def parse_clubs(self,trs):
		output,targets = [],[]
		for i in trs:
			cname = "".join(i.xpath('.//td[@class="hauptlink"]/a/text()'))
			clink = "".join(i.xpath('.//td[@class="hauptlink"]/a/@href'))
			clink = f"http://transfermarkt.co.uk{clink}"
			leagu = "".join(i.xpath('.//tr[2]/td/a/text()'))
			lglin = "".join(i.xpath('.//tr[2]/td/a/@href'))
			flag  = self.get_flag("".join(i.xpath('.//td/img[1]/@title')).strip())
			if leagu:
				club = f"[{cname}]({clink}) ([{leagu}]({lglin}))"
			else:
				club = f"[{cname}]({clink})"
				
			output.append(f"{flag} {club}")
			targets.append(clink)
		return output,targets
	
	async def parse_refs(self,trs):
		output = [],[]
		for i in trs:
			rname = "".join(i.xpath('.//td[@class="hauptlink"]/a/text()'))
			rlink = "".join(i.xpath('.//td[@class="hauptlink"]/a/@href'))
			rage  = "".join(i.xpath('.//td[@class="zentriert"]/text()'))
			flag  = self.get_flag("".join(i.xpath('.//td/img[1]/@title')).strip())
			
			output.append(f"{flag} [{rname}]({rlink}) {rage}")
			targets.append(rlink)
		return output,targets
		
	async def parse_cups(self,trs):
		output,targets = [],[]
		for i in trs:
			cupname = "".join(i.xpath('.//td[2]/a/text()'))
			cuplink = "".join(i.xpath('.//td[2]/a/@href'))
			flag = "".join(i.xpath('.//td[3]/img/@title'))
			if flag:
				flag = self.get_flag(flag)
			else:
				flag = "🌍"
			
			output.append(f"{flag} [{cupname}]({cuplink})")
			targets.append(cuplink)
		return output,targets
	
	async def parse_int(self,trs):
		output,targets = [],[]
		for i in trs:
			cupname = "".join(i.xpath('.//td[2]/a/text()'))
			cuplink = "".join(i.xpath('.//td[2]/a/@href'))
			
			output.append(f"🌍 [{cupname}]({cuplink})")
			targets.append(cuplink)
		return output,targets
	
	async def parse_agent(self,trs):
		output,targets = [],[]
		for i in trs:
			company = "".join(i.xpath('.//td[2]/a/text()'))
			comlink = "".join(i.xpath('.//td[2]/a/@href'))
			
			output.append(f"[{company}]({comlink})")
			targets.append(comlink)
		return output,targets
	
	async def get_transfers(self,ctx,e,target):
		e.description = ""
		target = target.replace('startseite','transfers')
		if datetime.datetime.now().month < 7:
			period = "w"
			seasonid = datetime.datetime.now().year - 1
		else:
			period = "s"
			seasonid = datetime.datetime.now().year
		target = f"{target}/saison_id/{seasonid}/pos//detailpos/0/w_s={period}"
			
		p = {"w_s":period}
		async with self.bot.session.get(target,params=p) as resp:
			if resp.status != 200:
				return await ctx.send(f"Error {resp.status} connecting to {resp.url}")
			tree = html.fromstring(await resp.text())
		
		e.set_author(name = "".join(tree.xpath('.//head/title/text()')),url=target)
		e.set_footer(text=discord.Embed.Empty)
		ignore,intable,outtable = tree.xpath('.//div[@class="large-8 columns"]/div[@class="box"]')
		
		intable = intable.xpath('.//tbody/tr')
		outtable = outtable.xpath('.//tbody/tr')
		
		inlist,inloans,outlist,outloans = [],[],[],[]

		for i in intable:
			pname = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/text()'))
			plink = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/@href'))
			
			plink = f"http://transfermarkt.co.uk{plink}"
			age   = "".join(i.xpath('.//td[3]/text()'))
			ppos  = "".join(i.xpath('.//td[2]//tr[2]/td/text()'))
			try:
				flag  = self.get_flag(i.xpath('.//td[4]/img[1]/@title')[0])
			except IndexError:
				flag = ""
			fee = "".join(i.xpath('.//td[6]//text()'))
			if "loan" in fee.lower():
				inloans.append(f"{flag} [{pname}]({plink}) {ppos}, {age}\n")
				continue
			inlist.append(f"{flag} [{pname}]({plink}) {ppos}, {age} ({fee})\n")
			
		for i in outtable:
			pname = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/text()'))
			plink = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/@href'))
			plink = f"http://transfermarkt.co.uk{plink}"
			flag  = self.get_flag(i.xpath('.//td/img[1]/@title')[1])
			fee = "".join(i.xpath('.//td[6]//text()'))
			if "loan" in fee.lower():
				outloans.append(f"[{pname}]({plink}), ")
				continue
			outlist.append(f"[{pname}]({plink}), ")
		
		def write_field(input_list,title):
			output = ""
			for i in input_list:
				if len(i) + len(output) < 1009:
					input_list.remove(i)
					output += i
				else:
					output += f"And {len(input_list)} more..."
					break
			e.add_field(name=title,value=output.strip(","))
		
		if inlist:
			write_field(inlist,"Inbound Transfers")
		if inloans:
			write_field(inloans,"Inbound Loans")
		if outlist:
			write_field(outlist,"Outbound Transfers")
		if outloans:
			write_field(outloans,"Outbound Loans")
		
		await ctx.send(embed=e)
	
	async def get_injuries(self,ctx,e,target):
		e.description = ""
		target = target.replace('startseite','sperrenundverletzungen')
		async with self.bot.session.get(f"{target}") as resp:
			if resp.status != 200:
				return await ctx.send(f"Error {resp.status} connecting to {resp.url}")
			tree = html.fromstring(await resp.text())
		e.set_author(name = tree.xpath('.//head/title[1]/text()')[0],url=str(resp.url))
		e.set_footer(text=discord.Embed.Empty)
		hurt,ignore = tree.xpath('.//div[@class="large-8 columns"]/div[@class="box"]')
		hurt = hurt.xpath('.//tbody/tr')
		hurtlist = []
		for i in hurt:
			pname = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/text()'))
			if not pname:
				continue
			plink = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/@href'))
			plink = f"http://transfermarkt.co.uk{plink}"
			ppos  = "".join(i.xpath('.//td[1]//tr[2]/td/text()'))
			age  = "".join(i.xpath('./td[2]/text()'))
			reason = "".join(i.xpath('.//td[3]//text()'))
			missed = "".join(i.xpath('.//td[6]//text()'))
			dueback = "".join(i.xpath('.//td[5]//text()'))
			
			dueback = f", due back {dueback}" if dueback != "?" else ""
			hurtlist.append(f"**[{pname}]({plink})** {age}, {ppos}\n{reason} ({missed} games missed{dueback})\n")
		
		output = ""
		numparsed = 0
		for i in hurtlist:
			if len(i) + len(output) < 1985:
				output += i
			else:
				output += f"And {len(hurtlist) - numparsed} more..."
				break
			numparsed += 1
		e.description = output
			
		await ctx.send(embed=e)
	
	async def get_rumours(self,ctx,e,target):
		e.description = ""
		target = target.replace('startseite','geruechte')
		async with self.bot.session.get(f"{target}") as resp:
			if resp.status != 200:
				return await ctx.send(f"Error {resp.status} connecting to {resp.url}")
			tree = html.fromstring(await resp.text())
		e.set_author(name = tree.xpath('.//head/title[1]/text()')[0],url=str(resp.url))
		e.set_footer(text=discord.Embed.Empty)
		
		rumours = tree.xpath('.//div[@class="large-8 columns"]/div[@class="box"]')[0]
		rumours = rumours.xpath('.//tbody/tr')
		rumorlist = []
		for i in rumours:
			pname = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/text()'))
			if not pname:
				continue
			plink = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/@href'))
			plink = f"http://transfermarkt.co.uk{plink}"
			ppos  = "".join(i.xpath('.//td[2]//tr[2]/td/text()'))
			mv = "".join(i.xpath('.//td[6]//text()')).strip()
			flag  = self.get_flag(i.xpath('.//td[3]/img/@title')[0])
			age  = "".join(i.xpath('./td[4]/text()')).strip()
			team = "".join(i.xpath('.//td[5]//img/@alt'))
			tlink = "".join(i.xpath('.//td[5]//img/@href'))
			odds = "".join(i.xpath('./td[8]//text()')).strip().replace('&nbsp','')
			source = "".join(i.xpath('./td[7]//@href'))
			odds = f"[{odds}likely]({source})" if odds != "-" else f"[rumor info]({source})"
			rumorlist.append(f"{flag} **[{pname}]({plink})** {age}, {ppos} ({mv})\n*[{team}]({tlink})*, {odds}\n")
		
		output = ""
		numparsed = 0
		for i in rumorlist:
			if len(i) + len(output) < 1985:
				output += i
			else:
				output += f"And {len(hurtlist) - numparsed} more..."
				break
			numparsed += 1
		e.description = output
			
		await ctx.send(embed=e)
		
def setup(bot):
	bot.add_cog(Transfers(bot))