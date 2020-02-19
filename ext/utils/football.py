from collections import defaultdict
import datetime

import typing
from lxml import html
import aiohttp
import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec, wait

from ext.utils.embed_utils import get_colour
from ext.utils.selenium_driver import spawn_driver


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


def get_html(url, xpath, driver=None):
    driver = spawn_driver() if driver is None else driver
    driver.get(url)
    wait.WebDriverWait(driver, 5).until(ec.visibility_of_element_located((By.XPATH, xpath)))
    return driver.page_source


class Fixture:
    def __init__(self, time: typing.Union[str, datetime.datetime], home: str, away: str, **kwargs):
        self.time = time
        self.home = home
        self.away = away
        self.__dict__.update(kwargs)
    
    @property
    async def to_embed_row(self):
        # TODO: write.
        if isinstance(self.time, datetime.datetime):
            if self.time < datetime.datetime.now():  # in the past -> result
                d = self.time.strftime('%a %d %b')
            else:
                d = self.time.strftime('%a %d %b %H:%M')
        else:
            d = self.time
        
        sc, tv = "", ""
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
    def __init__(self, driver, url):
        self.driver = driver
        self.url = url
        self.fs_page_title = None
        self.fs_page_image = None
        self.items = self.get_fixtures()
    
    def get_fixtures(self):
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
            e.add_field(name="Grounds", value=venues, inline=False)
        
        if hasattr(self, "old_venues") and self.old_venues:
            venues = "\n".join([f"[{k}]({v})" for k, v in self.old_venues.items()])
            e.add_field(name="Former Grounds", value=venues, inline=False)
        
        if hasattr(self, "league"):
            e.description = self.league
        return e
