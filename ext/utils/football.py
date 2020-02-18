from collections import defaultdict

from lxml import html
import aiohttp
import discord

from ext.utils.embed_utils import get_colour


async def get_stadiums(query):
	venue = query.replace(" ", "+")
	output = []
	async with aiohttp.ClientSession() as cs:
		async with cs.get(f'https://www.footballgroundmap.com/search/{venue}') as resp:
			await resp.text()
			tree = html.fromstring(await resp.text())
		
		results = tree.xpath(".//div[@class='using-grid'][1]/div[@class='grid']/div")
		
		# Fetching colours is VERY resource intensive.
		with_colour = False if len(results) > 20 else True
		for i in results:
			all_text = i.xpath(".//text()")
			country = all_text[3]
			league = all_text[5]
			names = all_text[7:]
			links_all = i.xpath('.//a[contains(@href, "/ground/")]/@href')
			groups = zip(names[::2], names[1::2], links_all)
			
			grounds = defaultdict(dict)
			
			for former_or_current, name, link in groups:
				grounds[former_or_current].update({name.title(): link})

			old_venues = grounds['Former Ground:']
			venues = grounds['Ground:']
			
			output.append(await Stadium(
				with_colour=with_colour,
				venues=venues,
				old_venues=old_venues,
				image=i.xpath('.//img/@src')[0],
				team=i.xpath('.//a[contains(@href, "team")]//text()')[0].title(),
				team_url=i.xpath('.//a[contains(@href, "team")]/@href')[0],
				league=f"**{country}**: {league}"
			).to_embed)
		return output



class FixtureList:
	def __init__(self, driver, query):
		self.driver = driver
		self.query = query


class Fixture:
	def __init__(self, time, home, away, **kwargs):
		self.time = time
		self.home = home
		self.away = away
		self.__dict__.update(kwargs)
		
	@property
	async def to_embed_row(self):
		return
		
class Stadium:
	def __init__(self, team, **kwargs):
		self.team = team
		self.__dict__.update(kwargs)
	
	@property
	async def to_embed(self):
		e = discord.Embed()
		e.title = self.team
		if hasattr(self, "image") and self.image:  # Check not ""
			e.set_thumbnail(url=self.image)
			if hasattr(self, "with_colour") and self.with_colour:
				e.colour = await get_colour(self.image)
			else:
				e.colour = discord.Colour.blurple()
		
		if hasattr(self, "link") and self.link:
			e.url = self.link
		
		if hasattr(self, "venues") and self.venues:
			venues = "\n".join([f"[{k}]({v})" for k, v in self.venues.items()])
			e.add_field(name="Grounds", value = venues, inline=False)
		
		if hasattr(self, "old_venues") and self.old_venues:
			venues = "\n".join([f"[{k}]({v})" for k, v in self.old_venues.items()])
			e.add_field(name="Former Grounds", value=venues, inline=False)
		
		if hasattr(self, "league"):
			e.description = self.league
		return e
