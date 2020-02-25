from selenium.webdriver.support import expected_conditions as ec, wait
from selenium.webdriver.common.by import By
from ext.utils import embed_utils
from copy import deepcopy
import PIL.Image as Image
from io import BytesIO
from lxml import html
import urllib.parse
import datetime
import aiohttp
import discord
import typing
import json

from ext.utils import selenium_driver
from importlib import reload

reload(selenium_driver)


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


class Player:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FlashScorePlayerList:
    def __init__(self, url, driver):
        self.driver = driver
        self.url = url
        self.fs_page_title = None
        self.fs_page_image = None
        self.items = self.get_players()
    
    def get_players(self) -> typing.List[Player]:
        delete = [(By.XPATH, './/div[@id="lsid-window-mask"]')]
        clicks = [(By.ID, 'overall-all')]
        src = selenium_driver.get_html(self.url, './/div[contains(@class,"playerTable")]', driver=self.driver,
                                       delete=delete, clicks=clicks)
        players = []
        x = html.fromstring(src)
        
        return x


class FlashScoreFixtureList:
    def __init__(self, url, driver):
        self.driver = driver
        self.url = url
        self.fs_page_title = None
        self.fs_page_image = None
        self.items = self.get_fixtures()
    
    def get_fixtures(self) -> typing.List[Fixture]:
        src = selenium_driver.get_html(self.driver, self.url, './/div[@class="sportName soccer"]')
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
            else:
                time = "Postpooned"
            
            is_televised = True if i.xpath(".//div[contains(@class,'tv')]") else False
            
            # score
            sc = " - ".join(i.xpath('.//div[contains(@class,"event__scores")]/span/text()'))
            home, away = i.xpath('.//div[contains(@class,"event__participant")]/text()')
            fixture = Fixture(time, home.strip(), away.strip(), score=sc, is_televised=is_televised,
                              country=country, league=league, url=url)
            fixtures.append(fixture)
        return fixtures
    
    @property
    async def to_embeds(self) -> typing.List[discord.Embed]:
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
    
    def link(self):
        if hasattr(self, 'override'):
            return self.override
        if self.participant_type_id == 1:
            # Example Team URL: https://www.flashscore.com/team/thailand-stars/jLsL0hAF/
            return f"https://www.flashscore.com/team/{self.url}/{self.id}"
        elif self.participant_type_id == 0:
            # Example League URL: https://www.flashscore.com/soccer/england/premier-league/
            ctry = self.country_name.lower().replace(' ', '-')
            return f"https://www.flashscore.com/soccer/{ctry}/{self.url}"
    
    def fixtures(self, driver) -> FlashScoreFixtureList:
        return FlashScoreFixtureList(str(self.link()) + "/fixtures", driver)
    
    def results(self, driver) -> FlashScoreFixtureList:
        return FlashScoreFixtureList(str(self.link()) + "/results", driver)
    
    def table(self, driver) -> BytesIO:
        xp = './/div[@class="table__wrapper"]'
        clicks = [(By.XPATH, ".//span[@class='button cookie-law-accept']")]
        delete = [(By.XPATH, './/div[@class="seoAdWrapper"]'), (By.XPATH, './/div[@class="banner--sticky"]')]
        err = f"No table found on {self.url}"
        image = selenium_driver.get_image(driver, self.link() + "/standings/", xp, err,
                                          clicks=clicks, delete=delete)
        return image


class Stadium:
    def __init__(self, url, name, team, league, country, **kwargs):
        self.url = url
        self.name = name.title()
        self.team = team
        self.league = league
        self.country = country
        self.__dict__.update(kwargs)
    
    def to_picker_row(self) -> str:
        return f"**{self.name}** ({self.country}: {self.team})"
    
    async def to_embed(self) -> discord.Embed:
        tree = html.fromstring(await get_html_async(self.url))
        e = discord.Embed()
        e.set_author(name="FootballGroundMap.com", url="http://www.footballgroundmap.com")
        e.title = self.name
        e.url = self.url
        
        image = "".join(tree.xpath('.//div[@class="page-img"]/img/@src'))
        
        try:  # Check not ""
            e.colour = await embed_utils.get_colour(self.team_badge)
        except AttributeError:
            pass
        
        if image:
            e.set_image(url=image.replace(' ', '%20'))
        
        # Teams
        old = tree.xpath('.//tr/th[contains(text(), "Former home")]/following-sibling::td')
        home = tree.xpath('.//tr/th[contains(text(), "home to")]/following-sibling::td')
        
        for s in home:
            team_list = []
            links = s.xpath('.//a/@href')
            teams = s.xpath('.//a/text()')
            for x, y in list(zip(teams, links)):
                if "/team/" in y:
                    team_list.append(f"[{x}]({y})")
            if team_list:
                e.add_field(name="Home to", value=", ".join(team_list), inline=False)
        
        for s in old:
            team_list = []
            links = s.xpath('.//a/@href')
            teams = s.xpath('.//a/text()')
            for x, y in list(zip(teams, links)):
                if "/team/" in y:
                    team_list.append(f"[{x}]({y})")
            if team_list:
                e.add_field(name="Former home to", value=", ".join(team_list), inline=False)
        
        # Location
        map_link = "".join(tree.xpath('.//figure/img/@src'))
        address = "".join(tree.xpath('.//tr/th[contains(text(), "Address")]/following-sibling::td//text()'))
        address = "Link to map" if not address else address
        
        if map_link:
            e.add_field(name="Location", value=f"[{address}]({map_link})")
        elif address:
            e.add_field(name="Location", value=address, inline=False)
        
        # Misc Data.
        e.description = ""
        capacity = "".join(tree.xpath('.//tr/th[contains(text(), "Capacity")]/following-sibling::td//text()'))
        cost = "".join(tree.xpath('.//tr/th[contains(text(), "Cost")]/following-sibling::td//text()'))
        website = "".join(tree.xpath('.//tr/th[contains(text(), "Website")]/following-sibling::td//text()'))
        att = "".join(tree.xpath('.//tr/th[contains(text(), "Record attendance")]/following-sibling::td//text()'))
        if capacity:
            e.description += f"Capacity: {capacity}\n"
        if att:
            e.description += f"Record Attendance: {att}\n"
        if cost:
            e.description += f"Cost: {cost}\n"
        if website:
            e.description += f"Website: {cost}\n"
        
        return e


async def get_html_async(url):
    async with aiohttp.ClientSession() as cs:
        async with cs.get(url) as resp:
            return await resp.text()


async def get_fs_results(query) -> typing.List[FlashScoreSearchResult]:
    query = query.replace("'", "")  # For some reason, ' completely breaks FS search, and people keep doing it?
    query = urllib.parse.quote(query)
    res = await get_html_async(f"https://s.flashscore.com/search/?q={query}&l=1&s=1&f=1%3B1&pid=2&sid=1")
    
    # Un-fuck FS JSON reply.
    res = res.lstrip('cjs.search.jsonpCallback(').rstrip(");")
    res = json.loads(res)
    
    results = []
    
    for i in res['results']:
        fsr = FlashScoreSearchResult(**i)
        results.append(fsr)
    
    return results


async def get_stadiums(query) -> typing.List[Stadium]:
    qry = urllib.parse.quote_plus(query)
    stadiums = []
    tree = html.fromstring(await get_html_async(f'https://www.footballgroundmap.com/search/{qry}'))
    results = tree.xpath(".//div[@class='using-grid'][1]/div[@class='grid']/div")
    for i in results:
        team = "".join(i.xpath('.//small/preceding-sibling::a//text()')).title()
        team_badge = i.xpath('.//img/@src')[0]
        ctry_league = i.xpath('.//small/a//text()')
        
        if not ctry_league:
            continue
        country = ctry_league[0]
        try:
            league = ctry_league[1]
        except IndexError:
            league = ""
        
        subnodes = i.xpath('.//small/following-sibling::a')
        for s in subnodes:
            name = "".join(s.xpath('.//text()')).title()
            link = "".join(s.xpath('./@href'))
            
            if query.lower() not in name.lower() and query.lower() not in team.lower():
                continue  # Filtering.
            
            if not any(c.name == name for c in stadiums) and not any(c.url == link for c in stadiums):
                stadiums.append(Stadium(url=link, name=name, team=team, team_badge=team_badge,
                                        country=country, league=league))
    return stadiums
