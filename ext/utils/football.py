import json
from collections import defaultdict
import datetime

import typing
from copy import deepcopy

from lxml import html
import aiohttp
import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec, wait

from ext.utils import embed_utils
from ext.utils.selenium_driver import spawn_driver

from typing import List
import urllib.parse


def get_html(url, expected_element_xpath, driver):
    if driver.current_url != url:
        driver.get(url)
        wait.WebDriverWait(driver, 5).until(ec.visibility_of_element_located((By.XPATH, expected_element_xpath)))
    src = driver.page_source
    return src


class Fixture:
    def __init__(self, time: typing.Union[str, datetime.datetime], home: str, away: str, **kwargs):
        self.time = time
        self.home = home
        self.away = away
        self.__dict__.update(kwargs)
    
    @property
    async def to_embed_row(self):
        if isinstance(self.time, datetime.datetime):
            if self.time < datetime.datetime.now():  # in the past -> result
                d = self.time.strftime('%a %d %b')
            else:
                d = self.time.strftime('%a %d %b %H:%M')
        else:
            d = self.time
        
        sc, tv = "vs", ""
        if hasattr(self, "score") and self.score:
            sc = self.score
        if hasattr(self, "is_televised") and self.is_televised:
            tv = '📺'
        
        if hasattr(self, "url"):
            output = f"`{d}:` [{self.home} {sc} {self.away} {tv}]({self.url})"
        else:
            output = f"`{d}:` {self.home} {sc} {self.away} {tv}"
        return output
        

class FlashScoreFixtureList:
    def __init__(self, url, driver):
        self.driver = driver
        self.url = url
        self.fs_page_title = None
        self.fs_page_image = None
        self.items = self.get_fixtures()
    
    def get_fixtures(self) -> List[Fixture]:
        src = get_html(self.url, './/div[@class="sportName soccer"]', driver=self.driver)
        logo = self.driver.find_element_by_xpath('.//div[contains(@class,"logo")]')
        if logo != "none":
            logo = logo.value_of_css_property('background-image')
            self.fs_page_image = logo.strip("url(").strip(")").strip('"')
        
        tree = html.fromstring(src)
        self.fs_page_title = "".join(tree.xpath('.//div[@class="teamHeader__name"]/text()')).strip()
        fixture_rows = tree.xpath('.//div[contains(@class,"sportName soccer")]/div')
        fixtures = []
        
        league, country = None, None
        for i in fixture_rows:
            try:
                fixture_id = i.xpath("./@id")[0].split("_")[-1]
                url = "http://www.flashscore.com/match/" + fixture_id
            except IndexError:
                cls = i.xpath('./@class')
                # This (might be) a header row.
                if "event__header" in cls:
                    country, league = i.xpath('.//div[@class="event__titleBox"]/span/text()')
                continue
            
            time = "".join(i.xpath('.//div[@class="event__time"]//text()')).strip("Pen").strip('AET')
            if "Postp" not in time:  # Should be dd.mm hh:mm or dd.mm.yyyy
                try:
                    time = datetime.datetime.strptime(time, '%d.%m.%Y')
                except ValueError:
                    time = datetime.datetime.strptime(f"{datetime.datetime.now().year}.{time}", '%Y.%d.%m. %H:%M')
            
            is_televised = True if i.xpath(".//div[contains(@class,'tv')]") else False
            
            # score
            sc = " - ".join(i.xpath('.//div[contains(@class,"event__scores")]/span/text()'))
            home, away = i.xpath('.//div[contains(@class,"event__participant")]/text()')
            fixture = Fixture(time, home.strip(), away.strip(), score=sc, is_televised=is_televised,
                              country=country, league=league, url=url)
            fixtures.append(fixture)
        return fixtures
    
    @property
    async def to_embeds(self) -> List[discord.Embed]:
        e = discord.Embed()
        if self.fs_page_title is not None:
            e.title = self.fs_page_title
        
        if self.fs_page_image is not None:
            e.set_thumbnail(url=self.fs_page_image)
        e.colour = await embed_utils.get_colour(e.thumbnail.url)
        pages = [self.items[i:i + 10] for i in range(0, len(self.items), 10)]
        
        embeds = []
        count = 0
        if not pages:
            e.description = "No games found!"
            embeds.append(e)
            
        for page in pages:
            count += 1
            e.description = "\n".join([await i.to_embed_row for i in page])
            embeds.append(deepcopy(e))
        return embeds


class FlashScoreSearchResult:
    def __init__(self, **kwargs):
        self.__dict__.update(**kwargs)
    
    @property
    def link(self):
        if self.participant_type_id == 1:
            # Example Team URL: https://www.flashscore.com/team/thailand-stars/jLsL0hAF/
            return f"https://www.flashscore.com/team/{self.url}/{self.id}"
        elif self.participant_type_id == 0:
            # Example League URL: https://www.flashscore.com/soccer/england/premier-league/
            # resdict[str(key)] = {"Match": i['title'], "url": f"soccer/{i['country_name'].lower()}/{i['url']}"
            ctry = self.country_name.lower().replace(' ', '-')
            return f"https://www.flashscore.com/soccer/{ctry}/{self.url}"
        
    @classmethod
    def fixtures(cls, driver) -> FlashScoreFixtureList:
        return FlashScoreFixtureList(str(cls.link) + "/fixtures", driver)
    
    @classmethod
    def results(cls, driver) -> FlashScoreFixtureList:
        return FlashScoreFixtureList(str(cls.link) + "/results", driver)


async def get_fs_results(query) -> List[FlashScoreSearchResult]:
        query = urllib.parse.quote(query)
        url = f"https://s.flashscore.com/search/?q={query}&l=1&s=1&f=1%3B1&pid=2&sid=1"
        async with aiohttp.ClientSession() as cs:
            async with cs.get(url) as resp:
                res = await resp.text()
                res = res.lstrip('cjs.search.jsonpCallback(').rstrip(");")
                res = json.loads(res)

        results = []

        for i in res['results']:
            fsr = FlashScoreSearchResult(**i)
            results.append(fsr)
            
        return results


class Stadium:
    def __init__(self, url, name, team, league, country, **kwargs):
        self.url= url
        self.name = name
        self.team = team
        self.league = league
        self.country = country
        self.__dict__.update(kwargs)
    
    @property
    def to_picker_row(self) -> str:
        return f"**{self.name}** ({self.country}: {self.team})"
    
    @property
    async def to_embed(self) -> discord.Embed:
        e = discord.Embed()
        e.set_author(name = self.team)
        e.title = f"{self.country}: {self.league}"
        if hasattr(self, "team_url"):
            e.url = self.team_url
            
        if hasattr(self, "image") and self.image:  # Check not ""
            e.set_thumbnail(url=self.image)
            e.colour = await embed_utils.get_colour(self.image)
        
        if hasattr(self, "link") and self.link:
            e.url = self.link
        
        if hasattr(self, "venues") and self.venues:
            for i in self.venues:
                venues = "\n".join([f"[{k}]({v})" for k, v in self.venues[i].items()])
                e.add_field(name=i, value=venues, inline=False)
        
        if hasattr(self, "league"):
            e.description = self.league
            
        return e


async def get_stadiums(query) -> List[Stadium]:
    query = urllib.parse.quote(query)
    output = []
    async with aiohttp.ClientSession() as cs:
        async with cs.get(f'https://www.footballgroundmap.com/search/{query}') as resp:
            await resp.text()
            tree = html.fromstring(await resp.text())
        
        results = tree.xpath(".//div[@class='using-grid'][1]/div[@class='grid']/div")
        
        for i in results:
            links = i.xpath('.//a[contains(@href, "/ground/")]/@href')
            # Some nasty <div><element></element> text() <element></element></div> shit.
            strings = i.xpath('.//small/following-sibling::*//text() | //small/following-sibling::text()')
            # Pair "Ground:" or "Former Ground:"  Line with the name of the ground, then pair those with their links..
            if not strings:
                continue
                
            groups = zip(strings[::2], strings[1::2], links)
            grounds = defaultdict(dict)
            
            # Grab the constructor data.
            team = "".join(i.xpath('.//small/preceding-sibling::*//text()')).title()
            ctry_league = i.xpath('.//small/a//text()')

            if not stl:
                continue
            country = ctry_league[0]
            try:
                league = ctry_league[1]
            except IndexError:
                league = "N/A"
            
            # Include any other info we can find.
            team_badge = i.xpath('.//img/@src')[0]
            team_url = i.xpath('.//a[contains(@href, "team")]/@href')[0]
            
            # Convert string lists into a dict for easier parsing.
            for former_or_current, name, link in groups:
                std = Stadium(url=link, name=name, type=former_or_current,
                              team=team, team_url=team_url, team_badge=team_badge, country=country, league=league)
            
            std.venues = grounds
            output.append(std)
        return output
