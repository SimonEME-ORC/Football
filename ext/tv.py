import asyncio
import discord
from discord.ext import commands
import datetime

import json
import aiohttp
from lxml import html

class Tv(commands.Cog):
	""" Search for live TV matches """
	def __init__(self, bot):
		self.bot = bot
		with open('tv.json') as f:
			bot.tv = json.load(f)
			
	async def save_tv(self):
		with await self.bot.configlock:
			with open('tv.json',"w",encoding='utf-8') as f:
				json.dump(self.bot.tv,f,ensure_ascii=True,
				sort_keys=True,indent=4, separators=(',',':'))

	@commands.command()
	@commands.is_owner()
	async def poptv(self,ctx):
		""" Repopulate the livescoreTV team Database """
		with ctx.typing():
			await ctx.send("Rebuilding the TV Database...")
			async with self.bot.session.get("http://www.livesoccertv.com/competitions/") as comps:
				compstree = html.fromstring(await comps.text())
				complist = compstree.xpath('.//div[@class="tab_container"]//ul/li/a/@href')
				compname = compstree.xpath('.//div[@class="tab_container"]//ul/li/a//text()')
				comps = zip(complist,compname)
				# Phase 1 :  GET ALL COMPETITION TV LISTINGS
				for i in comps:
					tvdict.update({i[1]:f"http://www.livesoccertv.com{i[0]}"})
			# Phase 2 : Get all teams from competitions.
			for i in {key: value[:] for key, value in tvdict.items()}:
				async with self.bot.session.get(tvdict[i]) as resp:
					tree = html.fromstring(await resp.text())
					# If a table exists, we can grab the teams from it.
					teams = tree.xpath('.//table//table//tr//td/a')
					for i in teams:
						y = "".join(i.xpath('.//text()'))
						z = "".join(i.xpath('.//@href'))
						if y and z:
							self.bot.tv.update({y:f"http://www.livesoccertv.com{z}"})
			await ctx.send("Done. Saving")
			await self.save_tv()
			await ctx.send("Saved.")

	async def _pick_team(self,ctx,team):
		em = discord.Embed()
		em.color = 0x034f76
		em.set_author(name = "LiveSoccerTV.com")

		if team is not None:
			matches = {i for i in self.bot.tv if team.lower() in i.lower()}
			if not matches:
				return await ctx.send(f"Could not find a matching team/league for {team}.")
			if len(matches) == 1:
				team = list(matches)[0]
			else:
				for i in matches:
					if team == i:
						result = i
				else:
					count = 0
					matchdict = {}
					for i in matches:
						matchdict[str(count)] = i
						count += 1
					matchlist = [f'{i}: {matchdict[i]}' for i in matchdict]
					strify = '\n'.join(matchlist)
					msg = f"Please type matching id ```{strify}```"
					def check(message):
						if message.author.id == ctx.author.id and message.content in matchdict:
							return True
					delme = await ctx.send(msg)
					result = await self.bot.wait_for("message",check=check,timeout=30)
					team = matchdict[result.content]
					await delme.delete()
					await result.delete()
			
			em.url = self.bot.tv[team]
			em.title = f"Televised Fixtures for {team}\n"
		else:
			em.url = "http://www.livesoccertv.com/schedules/"
			em.title = f"Today's Televised Matches\n"
		em.description = ""
		return em

	@commands.command()
	@commands.is_owner()
	async def tv(self,ctx,*,team:commands.clean_content = None):
		""" Lookup next televised games for a team """
		async with ctx.typing():
			em = await self._pick_team(ctx,team)
			tvlist = []
			async with self.bot.session.get(em.url) as resp:
				if resp.status != 200:
					return await ctx.send(f"🚫 <{em.url}> returned {resp.status}")
				tree = html.fromstring(await resp.text())
				
				matchcol = 3 if not team else 5
				
				for i in tree.xpath(".//table[@class='schedules'][1]//tr"):
					# Discard finished games.
					isdone = "".join(i.xpath('.//td[@class="livecell"]//span/@class')).strip()
					if isdone in ["narrow ft","narrow repeat"]:
						continue
						
					match = "".join(i.xpath(f'.//td[{matchcol}]//text()')).strip()
					if not match:
						continue
					ml = i.xpath(f'.//td[{matchcol + 1}]//text()')
					
					try:
						link = i.xpath(f'.//td[{matchcol + 1}]//a/@href')[-1]
						link = f"http://www.livesoccertv.com/{link}"
					except IndexError:
						link = ""
					
					ml = ", ".join([x.strip() for x in ml if x != "nufcTV" and x.strip() != ""])
					
					if ml == []:
						continue
					
					if isdone != "narrow live":
						date = "".join(i.xpath('.//td[@class="datecell"]//span/text()')).strip()
						time = "".join(i.xpath('.//td[@class="timecell"]//span/text()')).strip()
						# Correct TimeZone offset.
						try:
							time = datetime.datetime.strptime(time,'%H:%M')+ datetime.timedelta(hours=5)
							time = datetime.datetime.strftime(time,'%H:%M')
							dt = f"{date} {time}"
						except ValueError as e:
							dt = ""
					elif not team:
						dt = i.xpath('.//td[@class="timecell"]//span/text()')[-1].strip()
						if dt == "FT":
							continue
						if dt != "HT" and not ":" in dt:
							dt = f"LIVE {dt}'"
					else:
						date = "".join(i.xpath('.//td[@class="datecell"]//span/text()')).strip()
						time = "".join(i.xpath('.//td[@class="timecell"]//span/text()')).strip()
						if date == datetime.datetime.now().strftime("%b %d"):
							dt = time
						else:
							dt = date
					
					tvlist.append((f'`{dt}` [{match}]({link})'))
			
			if not tvlist:
				return await ctx.send(f"Couldn't find any televised matches happening soon, check online at {em.url}")
			dtn = datetime.datetime.now().strftime("%H:%M")

			em.set_footer(text=f"Time now: {dtn} Your Time:")
			em.timestamp = datetime.datetime.now()
			chars = 0
			remain = len(tvlist)
			for x in tvlist:
				if len(x) + + chars < 2000:
					em.description += x + "\n"
					remain -= 1
				chars += len(x) + 5
				
			if remain:
				em.description += f"\n *and {remain} more...*"
			await ctx.send(embed=em)


def setup(bot):
	bot.add_cog(Tv(bot))