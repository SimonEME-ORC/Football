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
    "St. Kitts & Nevis": "kn",
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

## TODO: Merge 	Lookup commands via Alias & ctx.invoked_with & typing.optional
## TODO: Split into Transfer Ticker and Transfer lookup cog.	

class Transfers(commands.Cog):
	""" Transfermarket lookups """
	def __init__(self, bot):
		self.bot = bot
		self.parsed = []
		self.transferson = True
		self.bot.loop.create_task(self.update_cache())
		self.bot.transferticker = self.bot.loop.create_task(self.transfer_ticker())
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
			"Squad":{
				"cat":"Clubs",
				"func":self._team,
				"querystr":"Verein_page",			
				"parser":self.parse_clubs,
				"outfunc":self.get_squad			
			},			
			"Rumours":{
				"cat":"Clubs",
				"func":self._team,
				"querystr":"Verein_page",
				"parser":self.parse_clubs,
				"outfunc":self.get_rumours
			}
		}
	
	def cog_unload(self):
		self.transferson = False
		self.bot.transferticker.cancel()
	
	async def update_cache(self):
		self.transfer_channel_cache = {}
		self.transfer_channel_whitelist_cache = {}

		connection = await self.bot.db.acquire()
		async with connection.transaction():
			channels =  await connection.fetch("""SELECT * FROM transfers_channels""")
			whitelists =  await connection.fetch("""SELECT * FROM transfers_whitelists""")
		await self.bot.db.release(connection)
		
		self.transfer_channel_cache = {}
		for r in channels:
			thisitem = {r["channel_id"]: {"shortmode":r["shortmode"]}}
			try:
				self.transfer_channel_cache[r["guild_id"]].update(thisitem)
			except KeyError:
				self.transfer_channel_cache[r["guild_id"]] = thisitem
		
		self.transfer_channel_whitelist_cache = {}
		for r in whitelists:
			this_item = {{"type":r["type"]},{"item":r["item"]},{"alias":r["alias"]}}
			try: 
				self.transfer_channel_whitelist_cache[r["channel_id"]].update(this_item)
			except KeyError:
				self.transfer_channel_whitelist_cache[r["channel_id"]] = this_item
		
	async def imgurify(self,imgurl):
		# upload image to imgur
		d = {"image":imgurl}
		h = {'Authorization': f'Client-ID {self.bot.credentials["Imgur"]["Authorization"]}'}
		async with self.bot.session.post("https://api.imgur.com/3/image",data = d,headers=h) as resp:
			res = await resp.json()
		return res['data']['link']
		
	async def transfer_ticker(self):
		await self.bot.wait_until_ready()
		firstrun = True
		loopiter = 60
		while self.transferson:
			try: 
				async with self.bot.session.get('https://www.transfermarkt.co.uk/statistik/neuestetransfers') as resp:
					if resp.status != 200:
						await asyncio.sleep(loopiter)
						continue
					tree = html.fromstring(await resp.text())
			# Bare excepts are bad but I don't care.
			except Exception as e:
				print("Error fetching transfermarkt data.")
				print(e) # Find out what this error is and narrow the exception down.
				await asyncio.sleep(loopiter)
				continue
				
			players = tree.xpath('.//div[@class="responsive-table"]/div/table/tbody/tr')

			for i in players:
				player_name = "".join(i.xpath('.//td[1]//tr[1]/td[2]/a/text()')).strip()
				if not player_name or player_name in self.parsed:
					continue # skip when duplicate / void.
				else:
					self.parsed.append(player_name)
				
				# We don't need to output when populating after a restart.
				if firstrun:
					print(f"Caching {player_name}")	
					continue
				print(f"Transfer found {player_name}")
				# Player Info
				player_link = "".join(i.xpath('.//td[1]//tr[1]/td[2]/a/@href'))
				age = "".join(i.xpath('./td[2]//text()')).strip()
				pos = "".join(i.xpath('./td[1]//tr[2]/td/text()'))
				nat = i.xpath('.//td[3]/img/@title')
				flags = []
				for j in nat:
					flags.append(self.get_flag(j))
				# nationality = ", ".join([f'{j[0]} {j[1]}' for j in list(zip(flags,nat))])
				nationality = "".join(flags)
				
				# Leagues & Fee 
				new_team = "".join(i.xpath('.//td[5]/table//tr[1]/td/a/text()'))
				new_team_link = "".join(i.xpath('.//td[5]/table//tr[1]/td/a/@href'))
				new_league = "".join(i.xpath('.//td[5]/table//tr[2]/td/a/text()'))
				new_league_link = "".join(i.xpath('.//td[5]/table//tr[2]/td/a/@href'))
				new_league_link = f"https://www.transfermarkt.co.uk{new_league_link}" if new_league_link else ""
				new_league_flag = self.get_flag("".join(i.xpath('.//td[5]/table//tr[2]/td//img/@alt')))
				new_league_markdown = f"{new_league_flag}[{new_league}]({new_league_link})"
				
				old_team = "".join(i.xpath('.//td[4]/table//tr[1]/td/a/text()'))
				old_team_link = "".join(i.xpath('.//td[4]/table//tr[1]/td/a/@href'))
				old_league = "".join(i.xpath('.//td[4]/table//tr[2]/td/a/text()'))
				old_league_link = "".join(i.xpath('.//td[4]/table//tr[2]/td/a/@href'))
				old_league_link = f"https://www.transfermarkt.co.uk{new_league_link}" if old_league_link else ""
				old_league_flag = self.get_flag("".join(i.xpath('.//td[4]/table//tr[2]/td//img/@alt')))
				old_league_markdown = f"{old_league_flag}[{old_league}]({old_league_link})"
				
				if new_league == old_league:
					move_info = f"{old_team} to {new_team} ({new_league_flag}{new_league})"
				else:
					move_info = f"{old_team} ({old_league_flag}{old_league}) to {new_team} ({new_league_flag}{new_league})"			
				
				
				fee = "".join(i.xpath('.//td[6]//a/text()'))
				fee_link = "".join(i.xpath('.//td[6]//a/@href'))
				fee_markdown =  f"[{fee}]({fee_link})"
				
				e = discord.Embed()
				e.description = ""
				e.color = 0x1a3151
				e.title = f"{nationality}{player_name} | {age} | {pos}"
				e.url   = f"https://www.transfermarkt.co.uk{player_link}"
				
				e.description += f"**To: {new_league_markdown}\n"
				e.description += f"**From: {old_league_markdown}"		

				if fee:
					e.add_field(name="Reported Fee",value=fee_markdown,inline=False)
				
				# Get picture and rehost on imgur.
				th = "".join(i.xpath('.//td[1]//tr[1]/td[1]/img/@src'))
				th = await self.imgurify(th)
				e.set_thumbnail(url=th)

				shortstring = f"{nationality} {player_name} | {age} | {pos} | {move_info} | {fee} | <{fee_link}>"

				for g,cl in self.transfer_channel_cache.items():
					for c,k in cl.items():
						print(f"Attempting to get channel {c}")
						ch = self.bot.get_channel(c)
						print(f"Got channel {ch}")
						try:
							whitelisted = self.transfer_channel_whitelist_cache[c]
							print(f"Found whitelist: {whitelisted}")
						except KeyError:
							print("No whitelist found.")
							pass
						else:
							print(f"Comparing values for {new_team_link},{old_team_league},{new_league_link},{old_league_link}")
							this_whitelist = whitelisted[i]
							values = [i['item'] for i in whitelisted]
							print(f"to {values}")
							if not any (new_team_link,old_team_link,new_league_link,old_league_link) in values:
								print("Not found. Aborting sending.")
								continue
							print("Found. Countinuing.")
							
						print("Checking for shortmode.")
						shortmode = self.transfer_channel_cache[c]["shortmode"]
						print(f"Shortmode is {shortmode}")
		
						try:
							if shortmode:
								await ch.send(shortstring)
							else:
								await ch.send(embed=e)
						except discord.Forbidden:
							print(f"Discord.Forbidden while trying to send new transfer to {c}")
						except AttributeError:
							print(f"AttributeError while trying to send new transfer to {c} - Check for channel deletion.")
			if firstrun:
				firstrun = False
				print("Set first run to false.")
			await asyncio.sleep(loopiter)
	
	async def _pick_channels(self,ctx,channels):
		# Assure guild has transfer channel.
		try:
			guild_cache = self.transfer_channel_cache[ctx.guild.id]
		except KeyError:
			await ctx.send(f'{ctx.guild.name} does not have any transfers channels set.')
			channels = []
		else:

			# Channel picker for invoker.
			def check(message):
				return ctx.author.id == message.author.id and message.channel_mentions		
			
			# If no Query provided we check current whitelists.
			if not channels:
				channels = [self.bot.get_channel(i) for i in list(guild_cache)]
			if ctx.channel.id in guild_cache:
				channels = [ctx.channel]			
			elif len(channels) != 1:
				async with ctx.typing():
					mention_list = " ".join([i.mention for i in channels])
					m = await ctx.send(f"{ctx.guild.name} has multiple transfer channels set: ({mention_list}), please specify which one(s) to check or modify.")
								
					try:
						channels = await self.bot.wait_for("message",check=check,timeout=30)
						channels = channels.channel_mentions
						await m.delete()
					except asyncio.TimeoutError:
						await m.edit(content="Timed out waiting for you to reply with a channel list. No channels were modified.")
						channels = []

		return channels
		
	@commands.group(invoke_without_command=True,aliases=["ticker"],usage = "tf (#channel)")
	@commands.has_permissions(manage_channels=True)
	async def tf(self,ctx,channels: commands.Greedy[discord.TextChannel]):
		""" Get info on your server's transfer tickers. """
		channels = await self._pick_channels(ctx,channels)
		guild_cache = self.transfer_channel_cache[ctx.guild.id]
		
		replies = []
		for i in channels:
			if i.id not in guild_cache:
				replies.append(f"{i.mention} is not set as one of {ctx.guild.name}'s transfer tickers.")
			
			mode = guild_cache[i.id]["shortmode"]
			mode = "short" if True else "Embed"
			
			try:
				wl = []
				whitelist = self.transfer_channel_whitelist_cache[i.id]
				for x in whitelist:
					this_whitelist.append(f"{whitelsit[x]['alias']} ({whitelist[x]['type']})")
				wl = ", ".join(wl)
				replies.append(f'Transfers are being output to {i.mention} in **{mode}** mode for your whitelist of `{wl}`')
			except KeyError:
				replies.append(f'**All** Transfers are being output to {i.mention} in **{mode}** mode. You can create a whitelist with {ctx.prefix}tf whitelist add')
			
		await ctx.send("\n".join(replies))
	
	@tf.command(usage="tf mode <Optional: #channel1, #channel2> <'Embed','Short',or leave blank to see current setting.>")
	@commands.has_permissions(manage_channels=True)
	async def mode(self,ctx,channels: commands.Greedy[discord.TextChannel],toggle:commands.clean_content =""):
		""" Toggle Short mode or Embed mode for transfer data """
		channels = await self._pick_channels(ctx,channels)
		
		guildcache = self.transfer_channel_cache[ctx.guild.id]
		
		if not toggle:
			replies = []
			for c in channels:
				try:
					mode = "Short" if guildcache[c.id]["shortmode"] else "Embed" 
				except KeyError:
					replies.append(f"🚫 {c.mention} is not set as a transfers channel")
					continue
				replies.append(f"{c.mention} is set to {mode} mode.")
			return await ctx.send("\n".join(replies))	
		
		if toggle.lower() not in ["embed","short"]:
			return await ctx.send(f'🚫 Invalid mode "{toggle}" specified, mode can either be "embed" or "short"')				
					
		update_toggle = True if toggle == "short" else False
		
		replies = []
		connection = await self.bot.db.acquire()
		async with connection.transaction():
			for c in channels:
				if c.id not in guildcache:
					orepliesut.append(f"🚫 {c.mention} is not a transfers channel.")
					channel_list.pop(c)
					continue
					

					await connection.execute("""UPDATE transfers_channels (mode) VALUES ($1) WHERE (channel_id) = $2""",update_toggle,c.id)
				replies.append(f"✅ {c.mention} was set to {toggle} mode")
			
		await ctx.send("\n".join(replies))
		await self.bot.db.release(connection)			
		await self.update_cache()		
	
	@tf.group(usage="tf whitelist <Optional: #channel>",invoke_without_command=True)
	@commands.has_permissions(manage_channels=True)
	async def whitelist(self,ctx,channels: commands.Greedy[discord.TextChannel]):
		""" Check the whitelist of specified channels """
		channels = await self._pick_channels(ctx,channels)
		replies = []
		for i in channels:
			wl = []
			try:
				whitelist = self.transfer_channel_whitelist_cache[i.id]
			except KeyError:
				await ctx.send(f'The whitelist for {i.mention} is currently empty, all transfers are being output.')				
				continue
			
			for type in whitelist:
				for item in type:
					type = whitelist[i]["item"]
					alias = whitelist[i]["alias"]
					wl.append(f"{alias} ({type})")
			wl = ", ".join(wl)
			replies.append(f'The whitelist for {i.mention} is: `{wl}`')
		await ctx.send("\n".join(replies))
	
	@commands.has_permissions(manage_channels=True)
	@whitelist.command(name="add",usage="tf whitelist add <Optional: #Channel1, #Channel2, #Channel3> <Optional: 'team', defaults to league if not specified)> <Search query>")		
	async def _add(self,ctx,channels:commands.Greedy[discord.TextChannel],*,qry : commands.clean_content = None):
		""" Add a league (or override it to team) to your transfer ticker channel(s)"""
		channels = await self._pick_channels(ctx,channels)
		if not channels:
			return
			
		if qry.startswith("team "):
			qry = qry.split("team ")[0]
			filter_type = "team" 
		else:
			filter_type = "league"
		

		search_type = "domestic competitions" if filter_type == "league:" else "clubs"
		targets,links = await self._search(ctx,qry,search_type,whitelist_fetch = True)

		e = discord.Embed()
		values = {}
		count = 1
		for i,j in targets,links:
			thisvalue = { str(count) : {{"alias":targets} , {"link":j}} }
			values.update(thisvalue)
			e.description += f"{num} {i}\n"
			e.description += f"{num} {i}\n"
			count += 1
		
		m = await ctx.send(embed=e)
		
		def check(message):
			if message.author.id == ctx.author.id and message.content in values:
				return True
		try:
			message = await self.bot.wait_for("message",check=check,timeout=30)
			channels = message.channel_mentions
		except asyncio.TimeoutError:
			await ctx.send("⚠️ Channel selection timed out, your whitelisted items were not updated.")
			return await m.delete()
		
		match = message.content
		result = values[match]
		
		connection = await self.bot.db.acquire()
		replies = []
		for c in channels:
			replies = []
			try:
				whitelist = self.transfer_channel_whitelist_cache[channel.id]
			except KeyError:
				replies.append(f"🚫 {c.mention} is not set as a transfers ticker channel.")
			
			for w in whitelist.items():
				type  = whitelist[w]["type"]
				alias = whitelist[w]["alias"]
				
				wl.append(f"{alias} {type}")
				
				items = ", ".join([i for i in whitelist[type]])
				wl.append(f"{types}: {items}\n")	
			wl = ", ".join(whitelist)			
			
			whitelist.append(query_result)
			await connection.execute("""INSERT INTO transfers_whitelist (channel_id,item,type) VALUES ($1,$2,$3)""",c.id,item,type)
			replies.append(f"✅ Whitelist for {c.mention} updated, current whitelist: ```{wl}```")
		replies = "\n".join(replies)
		await self.bot.db.release(connection)
		await self.update_cache()
		await ctx.send(replioes)
	
	
	@commands.Cog.listener()
	async def on_channel_delete(self,channel):
		if channel.id not in self.transfer_channel_cache[channel.guild.id]:
			return
		connection = await self.bot.db.acquire()
		await connection.execute(""" 
			DELETE FROM transfers_channels WHERE channel_id IS $1
			""",channel_id)
		await self.bot.db.release(connection)					
		await self.update_cache()
			
	
	@commands.has_permissions(manage_channels=True)
	@whitelist.command(name="remove",usage="tf whitelist remove <Whitelsit Item>")	
	async def _remove(self,ctx,channels: commands.Greedy[discord.TextChannel]):
		channels = await self._pick_channels(ctx,channels)
		guild_cache = self.transfer_channel_cache[ctx.guild.id]
		
		combined_whitelist = []
		
		for i in channels:
			combined_whitelist += [y["alias"] for y in self.transfer_channel_whitelist_cache if y["alias"] not in combined_whitelist] 
		
		e = discord.Embed()
		count = 0
		id_whitelist = {}
		for i in combined_whitelist:
			id_whitelist.update({str(count):i})
			e.description += f"{count} {i}"
			
		e.title = "Please type matching ID#"
		
		def check(message):
			return ctx.author.id == message.author.id and m.content in id_whitelist
		
		m = await ctx.send(embed=e)
		try:
			message = await self.bot.wait_for("message",check=check,timeout=30).content
		except asyncio.TimeoutError:
			await m.delete()
			return await ctx.send("Timed out waiting for response. No whitelist items were deleted.")
		
		todelete = td_whitelist[message.content]
		
		replies = []
		connection = await self.bot.db.acquire()
		for i in channels:
			if i.id not in guild_cache:
				replies.append(f"🚫 {i.mention} was not set as a transfer tracker channel.")
				continue
			await connection.execute(""" 
				DELETE FROM transfers_whitelist WHERE (channel_id,alias) == ($1,$2)
				""",id,alias)
		await self.bot.db.release(connection)					
		await self.update_cache()
		
		
	@tf.command(name="set",aliases=["add"],usage = "tf set (Optional: #channel #channel2) (Optional argument: 'short' - use short mode for output.)- will use current channel if not provided.)")
	@commands.has_permissions(manage_channels=True)
	async def _set(self,ctx,channels : commands.Greedy[discord.TextChannel],shortmode=""):
		""" Set channel(s) as a transfer ticker for this server """
		if not channels:
			channels = [ctx.channel]
			
		if shortmode is not False:
			if shortmode.lower() != "short":
				await ctx.send("Invalid mode provided, using Embed mode.")
			else:
				shortmode = True

		connection = await self.bot.db.acquire()
		replies = []
		for c in channels:
			if c.id in self.transfer_channel_cache:
				replies.append(f"🚫 {fail} already set as transfer ticker(s)")
				continue
				
			await connection.execute("""INSERT INTO transfers_channels (guild_id,channel_id,shortmode) VALUES ($1,$2,$3)""",ctx.guild.id,c.id,shortmode)
			mode = "short mode" if shortmode else "embed mode"
			replies.append(f"✅ Set {c.mention} as transfer ticker channel(s) using {mode} mode. ALL transfers will be output there. Please create a whitelist if this gets spammy.")
		await self.bot.db.release(connection)
		await self.update_cache()
		replies = "\n".join(replies)
		await ctx.send(replies)
	
	@tf.command(name="unset",aliases=["remove","delete"])
	@commands.has_permissions(manage_channels=True)
	async def _unset(self,ctx,channels : commands.Greedy[discord.TextChannel]):
		channels = await self._pick_channels(ctx,channels)
		
		connection = await self.bot.db.acquire()
		replies = []
		async with connection.transaction():
			for i in channels:
				if i.id not in guild_cache:
					replies.append(f"🚫 {c.mention} was not set as transfer ticker channels..")
					continue
					
				await connection.execute(""""DELETE FROM transfers_channels WHERE channel_id = $1""",i.id)
				replies.append(f"✅ Deleted transfer ticker from {i.mention}")
		await self.bot.db.release(connection)
		await self.update_cache()
		await ctx.send("\n".join(replies))
	
	# Base lookup - No Subcommand.
	@commands.group(invoke_without_command=True)
	async def lookup(self,ctx,*,target:commands.clean_content):
		""" Perform a database lookup on transfermarkt """
		p = {"query":target} # html encode.
		async with self.bot.session.post(f"http://www.transfermarkt.co.uk/schnellsuche/ergebnis/schnellsuche",params=p) as resp:
			if resp.status != 200:
				return await ctx.send(f"HTTP Error connecting to transfermarkt: {resp.status}")
			tree = html.fromstring(await resp.text())
		
		# Header names, scrape then compare (because they don't follow a pattern.)
		categories = [i.lower() for i in tree.xpath(".//div[@class='table-header']/text()")]

		results = {}
		count = 0
		for i in categories:
			# Just give us the number of matches by replacing non-digit characters.
			try:
				length = [int(n) for n in i if n.isdigit()][0]
			except IndexError:
				continue
			
			for j in self.cats:
				if j in i:
					results[count] = (f"{count}: {self.cats[j]['cat'].title()} ({length} found)",self.cats[j]['func'])	
					count += 1
	
		if not results:
			return await ctx.send(f":no_entry_sign: No results for {target}")
		sortedlist = [i[0] for i in sorted(results.values())]

		# If only one category has results, invoke that search.
		if len(sortedlist) == 1:
			return await ctx.invoke(results[0][1],qry=target)
			
		e = discord.Embed(url = str(resp.url))
		e.title = "Transfermarkt lookup"
		e.description = "Please type matching ID#```"
		e.description += "\n".join(sortedlist) + "```"
		e.color = 0x1a3151
		e.set_footer(text=ctx.author)
		e.set_thumbnail(url="http://www.australian-people-records.com/images/Search-A-Person.jpg")
		
		async with ctx.typing():
			print(f"Debug: {results}")
			m = await ctx.send(embed=e)
		
			def check(message):
				if message.author == ctx.author:
					try:
						return int(message.content) in results
					except ValueError:
						return False
				
			
			# Wait for appropriate reaction
			try:
				msg = await self.bot.wait_for("message",check=check,timeout=120)
			except asyncio.TimeoutError:
				try:
					return await m.clear_reactions()
				except discord.Forbidden:
					return
		
		# invoke appropriate subcommand for category selection.
		await m.delete()
		return await ctx.invoke(results[int(msg.content)][1],qry=target)
	
	@lookup.command(name="player")
	async def _player(self,ctx,*,qry : commands.clean_content):
		""" Lookup a player on transfermarkt """
		await self._search(ctx,qry,"players")
		
	@lookup.command(name="manager",aliases=["staff","trainer","trainers","managers"])
	async def _manager(self,ctx,*,qry : commands.clean_content):
		""" Lookup a manager/trainer/club official on transfermarkt """
		await self._search(ctx,qry,"managers")
		
	@lookup.command(name="team",aliases=["club"])
	async def _team(self,ctx,*,qry : commands.clean_content):
		""" Lookup a team on transfermarkt """
		await self._search(ctx,qry,"clubs")
	
	@lookup.command(name="ref")
	async def _ref(self,ctx,*,qry : commands.clean_content):
		""" Lookup a referee on transfermarkt """
		await self._search(ctx,qry,"referees")
	
	@lookup.command(name="cup",aliases=["domestic"])
	async def _cup(self,ctx,*,qry : commands.clean_content):
		""" Lookup a domestic competition on transfermarkt """
		await self._search(ctx,qry,"domestic competitions")
	
	@lookup.command(name="international",aliases=["int"])
	async def _int(self,ctx,*,qry : commands.clean_content):
		""" Lookup an international competition on transfermarkt """
		await self._search(ctx,qry,"International Competitions")
		
	@lookup.command(name="agent")
	async def _agent(self,ctx,*,qry : commands.clean_content):
		""" Lookup an agent on transfermarkt """
		await self._search(ctx,qry,"Agent")
		
	@commands.command(aliases=["loans"])
	async def transfers(self,ctx,*,qry : commands.clean_content):
		""" Get this season's transfers for a team on transfermarkt """
		await self._search(ctx,qry,"Transfers",special=True)
		
	@commands.command(name="squad",aliases=["roster"])
	async def _squad(self,ctx,*,qry : commands.clean_content):
		""" Lookup the squad for a team on transfermarkt """
		await self._search(ctx,qry,"Squad",special=True)		
	
	@commands.command(name="rumours",aliases=["rumors"])
	async def _rumours(self,ctx,*,qry : commands.clean_content):
		""" Get the latest transfer rumours for a team """
		await self._search(ctx,qry,"Rumours",special=True)
	
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
		e.set_author(name="".join(tree.xpath(f".//div[@class='table-header'][contains(text(),'{categ}')]/text()")))
		e.description = ""
		numpages = int("".join([i for i in e.author.name if i.isdigit()])) // 10 + 1
		e.set_footer(text=f"Page {page} of {numpages}")
		return e,tree.xpath(matches),numpages
	
	async def _search(self,ctx,qry,category,special=False,whitelist_fetch=False):
		page = 1
		e,tree,maxpage = await self.fetch(ctx,category,qry,page)
		if not tree:
			return await ctx.send("No results.")
		
		lines,targets = await self.cats[category]["parser"](tree)
		if whitelist_fetch:
			return lines,targets
		
		
		### TODO: Make this a number select with combined wait_for.
		def make_embed(e,lines,targets):
			e.description = ""
			reactdict = {}	
			
			if special:
				replacelist = ["🇦","🇧",'🇨','🇩','🇪',
							   '🇫','🇬',"🇭","🇮","🇯"]
				
				for i,j in zip(lines,targets):
					emoji = replacelist.pop(0)
					reactdict[emoji] = j
					e.description += f"{emoji} {i}\n"
				return e,reactdict
			else:
				for i in lines:
					e.description += f"{i}\n"
			return e,reactdict
		
		e,reactdict = make_embed(e,lines,targets)

		# Create message and add reactions		
		m = await ctx.send(embed=e)	
		
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
			self.bot.loop.create_task(m.add_reaction("🚫")) # eject
		
		# Only respond to user who invoked command.
		def check(reaction,user):
			if reaction.message.id == m.id and user == ctx.author:
				e = str(reaction.emoji)
				return e.startswith(('⏮','◀','▶','⏭','🚫')) or e in reactdict
		
		# Reaction Logic Loop.
		while True:
			try:
				res = await self.bot.wait_for("reaction_add",check=check,timeout=30)
			except asyncio.TimeoutError:
				try:
					return await m.clear_reactions()
				except discord.Forbidden:
					for i in m.reactions:
						if i.author == ctx.me:
							await message.remove_reaction(i.emoji,ctx.me)
					return
			res = res[0]
			if res.emoji == "⏮": #first
				page = 1
				await m.remove_reaction("⏮",ctx.message.author)
			elif res.emoji == "◀": #prev
				await m.remove_reaction("◀",ctx.message.author)
				if page > 1:
					page = page - 1
			elif res.emoji == "▶": #next	
				await m.remove_reaction("▶",ctx.message.author)
				if page < maxpage:
					page = page + 1
			elif res.emoji == "⏭": #last
				page = maxpage
				await m.remove_reaction("⏭",ctx.message.author)
			elif res.emoji == "🚫": #eject
				return await m.delete()
			elif res.emoji in reactdict:
				await m.delete()
				match = reactdict[res.emoji]
				return await self.cats[category]["outfunc"](ctx,e,match)

			e,tree,maxpage = await self.fetch(ctx,category,qry,page)
			if tree:
				lines,targets = await self.cats[category]["parser"](tree)
				e,reactdict = make_embed(e,lines,targets)
				await m.edit(embed=e)

	def get_flag(self,ctry):
		# Check if pycountry has country
		if not ctry:
			return
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
			player_link = "".join(i.xpath('.//a[@class="spielprofil_tooltip"]/@href'))
			player_link = f"http://transfermarkt.co.uk{player_link}"
			team  = "".join(i.xpath('.//td[3]/a/img/@alt'))
			tlink = "".join(i.xpath('.//td[3]/a/img/@href'))
			tlink = f"http://transfermarkt.co.uk{tlink}"
			age   = "".join(i.xpath('.//td[4]/text()'))
			ppos  = "".join(i.xpath('.//td[2]/text()'))
			flag  = self.get_flag( "".join(i.xpath('.//td/img[1]/@title')))
			
			output.append(f"{flag} [{pname}]({player_link}) {age}, {ppos} [{team}]({tlink})")
			targets.append(player_link)
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
			cup_link = "".join(i.xpath('.//td[2]/a/@href'))
			flag = "".join(i.xpath('.//td[3]/img/@title'))
			if flag:
				flag = self.get_flag(flag)
			else:
				flag = "🌍"
			
			output.append(f"{flag} [{cupname}]({cup_link})")
			targets.append(cuplayer_link)
		return output,targets
	
	async def parse_int(self,trs):
		output,targets = [],[]
		for i in trs:
			cupname = "".join(i.xpath('.//td[2]/a/text()'))
			cuplayer_link = "".join(i.xpath('.//td[2]/a/@href'))
			
			output.append(f"🌍 [{cupname}]({cuplayer_link})")
			targets.append(cuplayer_link)
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
		
		# Winter window, Summer window.
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
			player_link = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/@href'))
			
			player_link = f"http://transfermarkt.co.uk{player_link}"
			age   = "".join(i.xpath('.//td[3]/text()'))
			ppos  = "".join(i.xpath('.//td[2]//tr[2]/td/text()'))
			try:
				flag  = self.get_flag(i.xpath('.//td[4]/img[1]/@title')[0])
			except IndexError:
				flag = ""
			fee = "".join(i.xpath('.//td[6]//text()'))
			if "loan" in fee.lower():
				inloans.append(f"{flag} [{pname}]({player_link}) {ppos}, {age}\n")
				continue
			inlist.append(f"{flag} [{pname}]({player_link}) {ppos}, {age} ({fee})\n")
			
		for i in outtable:
			pname = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/text()'))
			player_link = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/@href'))
			player_link = f"http://transfermarkt.co.uk{player_link}"
			flag  = self.get_flag(i.xpath('.//td/img[1]/@title')[1])
			fee = "".join(i.xpath('.//td[6]//text()'))
			if "loan" in fee.lower():
				outloans.append(f"[{pname}]({player_link}), ")
				continue
			outlist.append(f"[{pname}]({player_link}), ")
		
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
	
	async def get_squad(self,ctx,e,target):
		e.description = ""
		async with self.bot.session.get(target) as resp:
			if resp.status != 200:
				return await ctx.send(f"Error {resp.status} connecting to {resp.url}")
			tree = html.fromstring(await resp.text())
		e.set_author(name = tree.xpath('.//head/title[1]/text()')[0],url=str(resp.url))
		e.set_footer(text=discord.Embed.Empty)
		
		sqdtbl = tree.xpath('.//div[@class="large-8 columns"]/div[@class="box"]')
		await ctx.send(f"WIP Test: {sqdtbl}")
		
		plist = []
		players = tree.xpath('.//div[@class="large-8 columns"]/div[@class="box"]')[0].xpath('.//tbody/tr')
		
		for i in players:
			pname = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/text()'))
			if not pname:
				continue			
			player_link = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/@href'))
			player_link = f"http://transfermarkt.co.uk{player_link}"
			ppos  = "".join(i.xpath('.//td[1]//tr[2]/td/text()'))
			age  = "".join(i.xpath('./td[2]/text()'))
			reason = "".join(i.xpath('.//td[3]//text()'))
			missed = "".join(i.xpath('.//td[6]//text()'))
			dueback = "".join(i.xpath('.//td[5]//text()'))
			
			plist.append(f"**[{pname}]({player_link})** {age}, {ppos}\n")
		
		output = ""
		numparsed = 0
		for i in plist:
			if len(i) + len(output) < 1985:
				output += i
			else:
				output += f"And {len(plist) - numparsed} more..."
				break
			numparsed += 1
		e.description = output		
		await ctx.send(embed=e)
			
	async def get_injuries(self,ctx,e,target):
		e.description = ""
		target = target.replace('startseite','sperrenundverletzungen')
		async with self.bot.session.get(target) as resp:
			if resp.status != 200:
				return await ctx.send(f"Error {resp.status} connecting to {resp.url}")
			tree = html.fromstring(await resp.text())
		e.set_author(name = tree.xpath('.//head/title[1]/text()')[0],url=str(resp.url))
		e.set_footer(text=discord.Embed.Empty)
		hurt = tree.xpath('.//div[@class="large-8 columns"]/div[@class="box"]')[0].xpath('.//tbody/tr')
		hurtlist = []
		for i in hurt:
			pname = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/text()'))
			if not pname:
				continue
			player_link = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/@href'))
			player_link = f"http://transfermarkt.co.uk{player_link}"
			ppos  = "".join(i.xpath('.//td[1]//tr[2]/td/text()'))
			age  = "".join(i.xpath('./td[2]/text()'))
			reason = "".join(i.xpath('.//td[3]//text()'))
			missed = "".join(i.xpath('.//td[6]//text()'))
			dueback = "".join(i.xpath('.//td[5]//text()'))
			
			dueback = f", due back {dueback}" if dueback != "?" else ""
			hurtlist.append(f"**[{pname}]({player_link})** {age}, {ppos}\n{reason} ({missed} games missed{dueback})\n")
		
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
			player_link = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/@href'))
			player_link = f"http://transfermarkt.co.uk{player_link}"
			ppos  = "".join(i.xpath('.//td[2]//tr[2]/td/text()'))
			mv = "".join(i.xpath('.//td[6]//text()')).strip()
			flag  = self.get_flag(i.xpath('.//td[3]/img/@title')[0])
			age  = "".join(i.xpath('./td[4]/text()')).strip()
			team = "".join(i.xpath('.//td[5]//img/@alt'))
			tlink = "".join(i.xpath('.//td[5]//img/@href'))
			odds = "".join(i.xpath('./td[8]//text()')).strip().replace('&nbsp','')
			source = "".join(i.xpath('./td[7]//@href'))
			odds = f"[{odds}likely]({source})" if odds != "-" else f"[rumor info]({source})"
			rumorlist.append(f"{flag} **[{pname}]({player_link})** {age}, {ppos} ({mv})\n*[{team}]({tlink})*, {odds}\n")
		
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