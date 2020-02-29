from selenium.webdriver.common.by import By
from ext.utils import embed_utils
from copy import deepcopy
from io import BytesIO
from lxml import html
import urllib.parse
import datetime
import aiohttp
import discord
import typing
import json

from ext.utils import selenium_driver, transfer_tools
from importlib import reload

reload(selenium_driver)
reload(transfer_tools)


class Fixture:
    def __init__(self, time: typing.Union[str, datetime.datetime], home: str, away: str, **kwargs):
        self.time = time
        self.home = home
        self.away = away
        self.__dict__.update(kwargs)
    
    def stats_markdown(self, driver):
        delete = [(By.XPATH, './/div[@id="lsid-window-mask"]')]
        xp = ".//div[@class='statBox']"
        element = selenium_driver.get_element(driver, self.url + "#match-statistics;0", xp, delete=delete)
        src = element.inner_html
        return
    
    def stats_image(self, driver):
        delete = [(By.XPATH, './/div[@id="lsid-window-mask"]')]
        xp = ".//div[@class='statBox']"
        image = selenium_driver.get_image(driver, self.url + "#match-statistics;0", xp, delete=delete,
                                          failure_message="Unable to find live stats for this match.")
        return image
    
    def formation(self, driver):
        delete = [(By.XPATH, './/div[@id="lsid-window-mask"]')]
        xp = './/div[@id="lineups-content"]'
        image = selenium_driver.get_image(driver, self.url + "#lineups;1", xp, delete=delete,
                                          failure_message="Unable to find formations for this match")
        return image
    
    def summary(self, driver):
        delete = [(By.XPATH, './/div[@id="lsid-window-mask"]')]
        xp = ".//div[@id='summary-content']"
        image = selenium_driver.get_image(driver, self.url + "#match-summary", xp, delete=delete,
                                          failure_message="Unable to find summary for this match")
        return image
    
    @property
    def formatted_score(self):
        if self.score_home is not None:
            return f" {self.score_home} - {self.score_away} "
        else:
            return " vs "
    
    @property
    def emoji_time(self):
        emoji_dict = {"After Pens": "🟢", "FT": "🟢", "AET": "🟢", "HT": "🟡️"}
        try:
            return f"{emoji_dict[self.time]} {self.time} "
        except KeyError:
            if ":" in self.time:
                return f"🔵 {self.time}"
            elif "'" in self.time:
                return f"⚽ {self.time}"
            elif "PP" in self.time:
                return f"🚫 Postp"
            else:
                return self.time
    
    @property
    def colour_time(self):
        if "PP" in self.time:
            return 0xDB4437  # Red
        elif "HT" in self.time:
            return 0xF4B400  # Amber
        elif "FT" in self.time:
            return 0x4285F4  # Blue
        elif "+" in self.time:
            return 0x9932CC  # Purple
        elif "'" in self.time:
            return 0x0F9D58  # Green
        else:
            return 0xB3B3B3  # Gray
    
    @property
    def live_score_text(self):
        return f"`{self.emoji_time}` {self.home} {self.formatted_score} {self.away}"
    
    @property
    def live_score_embed_row(self):
        return f"`{self.emoji_time}` [{self.home} {self.formatted_score} {self.away}]({self.url})"
    
    @property
    def filename(self):
        t = self.time.replace("'", "mins")
        return f"{t}-{self.home}-{self.formatted_score}-{self.away}".replace(' ', '-')
    
    @property
    def base_embed(self):
        e = discord.Embed()
        e.set_author(name=f"≡ {self.home} {self.formatted_score} {self.away} ({self.emoji_time})")
        e.url = self.url
        e.title = f"**{self.country}**: {self.league}"
        e.timestamp = datetime.datetime.now()
        
        if "PP" in self.time:
            e.description = "This match has been postponed."
        
        clr = self.colour_time
        if clr == 0xB3B3B3:
            try:
                h, m = self.time.split(':')
                now = datetime.datetime.now()
                when = datetime.datetime.now().replace(hour=int(h), minute=int(m))
                x = when - now
                e.set_footer(text=f"Kickoff in {x}")
                e.timestamp = when
            except (IndexError, ValueError):
                e.description = "Live data not available for this match."
        return e
    
    @property
    def to_embed_row(self):
        if isinstance(self.time, datetime.datetime):
            if self.time < datetime.datetime.now():  # in the past -> result
                d = self.time.strftime('%a %d %b')
            else:
                d = self.time.strftime('%a %d %b %H:%M')
        else:
            d = self.time
        
        tv = '📺' if hasattr(self, "is_televised") and self.is_televised else ""
        
        if hasattr(self, "url"):
            return f"`{d}:` [{self.home} {self.formatted_score} {self.away} {tv}]({self.url})"
        else:
            return f"`{d}:` {self.home} {self.formatted_score} {self.away} {tv}"


class Player:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    
    @property
    def player_embed_row(self):
        return f"`{str(self.number).rjust(2)}`: {self.flag} [{self.name}]({self.link}) {self.position}{self.injury}"
    
    @property
    def injury_embed_row(self):
        return f"{self.flag} [{self.name}]({self.link}) ({self.position}): {self.injury}"
    
    @property
    def scorer_embed_row(self):
        return f"{self.flag} [{self.name}]({self.link}) {self.goals} in {self.apps} appearances"


class FlashScorePlayerList:
    def __init__(self, url, driver):
        self.driver = driver
        self.url = url
        self.fs_page_title = None
        self.fs_page_image = None
        self.players = self.get_players()
    
    def get_players(self) -> typing.List[Player]:
        delete = [(By.XPATH, './/div[@id="lsid-window-mask"]')]
        clicks = [(By.ID, 'overall-all')]
        xp = './/div[contains(@class,"playerTable")]'
        
        src = selenium_driver.get_html(self.driver, self.url, xp, delete=delete, clicks=clicks)
        tree = html.fromstring(src)
        rows = tree.xpath('.//div[contains(@id,"overall-all-table")]//div[contains(@class,"profileTable__row")]')[1:]
        
        logo = self.driver.find_element_by_xpath('.//div[contains(@class,"logo")]')
        if logo != "none":
            logo = logo.value_of_css_property('background-image')
            self.fs_page_image = logo.strip("url(").strip(")").strip('"')
        self.fs_page_title = "".join(tree.xpath('.//div[@class="teamHeader__name"]/text()')).strip()
        
        players = []
        position = ""
        for i in rows:
            pos = "".join(i.xpath('./text()')).strip()
            if pos:  # The way the data is structured contains a header row with the player's position.
                try:
                    position = pos.rsplit('s')[0]
                except IndexError:
                    position = pos
                continue  # There will not be additional data.
            
            name = "".join(i.xpath('.//div[contains(@class,"")]/a/text()'))
            try:  # Name comes in reverse order.
                player_split = name.split(' ', 1)
                name = f"{player_split[1]} {player_split[0]}"
            except IndexError:
                pass
            
            country = "".join(i.xpath('.//span[contains(@class,"flag")]/@title'))
            flag = transfer_tools.get_flag(country)
            number = "".join(i.xpath('.//div[@class="tableTeam__squadNumber"]/text()'))
            try:
                age, apps, g, y, r = i.xpath(
                    './/div[@class="playerTable__icons playerTable__icons--squad"]//div/text()')
            except ValueError:
                age = "".join(i.xpath('.//div[@class="playerTable__icons playerTable__icons--squad"]//div/text()'))
                apps = g = y = r = 0
            injury = "".join(i.xpath('.//span[contains(@class,"absence injury")]/@title'))
            if injury:
                injury = f"<:injury:682714608972464187> " + injury  # I really shouldn't hard code emojis.
            
            link = "".join(i.xpath('.//div[contains(@class,"")]/a/@href'))
            link = f"http://www.flashscore.com{link}" if link else ""
            
            try:
                number = int(number)
            except ValueError:
                number = 00
            
            pl = Player(name=name, number=number, country=country, link=link, position=position,
                        age=age, apps=apps, goals=g, yellows=y, reds=r, injury=injury, flag=flag)
            players.append(pl)
        return players
    
    @property
    async def base_embed(self):
        e = discord.Embed()
        if self.fs_page_image:
            e.set_thumbnail(url=self.fs_page_image)
            e.colour = await embed_utils.get_colour(self.fs_page_image)
        return e
    
    @property
    async def squad_as_embed(self):
        e = await self.base_embed
        srt = sorted(self.players, key=lambda x: x.number)
        players = [i.player_embed_row for i in srt]
        if self.fs_page_title:
            e.title = f"All players for {self.fs_page_title}"
            e.url = self.url
        embeds = embed_utils.rows_to_embeds(e, players)
        return embeds
    
    @property
    async def injuries_to_embeds(self):
        pl = [i for i in self.players if i.injury]
        description_rows = [i.injury_embed_row for i in pl] if pl else ['No injuries found']
        e = await self.base_embed
        if self.fs_page_title:
            e.title = f"Injuries for {self.fs_page_title}"
            e.url = self.url
        embeds = embed_utils.rows_to_embeds(e, description_rows)
        return embeds
    
    @property
    async def scorers_to_embeds(self):
        pl = [i for i in self.players if i.goals > 0]
        description_rows = [i.goal_embed_row for i in pl] if pl else ['No goals found.']
        e = await self.base_embed
        if self.fs_page_title:
            e.title = f"Top Scorers for {self.fs_page_title}"
            e.url = self.url
        embeds = embed_utils.rows_to_embeds(e, description_rows)
        return embeds


class FlashScoreFixtureList:
    def __init__(self, url, driver):
        self.driver = driver
        self.url = url
        self.fs_page_title = None
        self.fs_page_image = None
        self.items = self.get_fixtures()
        
    def __getitem__(self, value):
        return self.items[value]
    
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
                time = "🚫 Postponed "
            
            is_televised = True if i.xpath(".//div[contains(@class,'tv')]") else False
            
            # score
            try:
                score_home, score_away = i.xpath('.//div[contains(@class,"event__scores")]/span/text()')
            except ValueError:
                score_home, score_away = None, None
            
            home, away = i.xpath('.//div[contains(@class,"event__participant")]/text()')
            fixture = Fixture(time, home.strip(), away.strip(), score_home=score_home, score_away=score_away,
                              is_televised=is_televised,
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
        if not pages:
            e.description = "No games found!"
            embeds.append(e)
        
        for page in pages:
            e.description = "\n".join([i.to_embed_row for i in page])
            embeds.append(deepcopy(e))
        return embeds


class FlashScoreSearchResult:
    def __init__(self, **kwargs):
        self.__dict__.update(**kwargs)
    
    def fixtures(self, driver) -> FlashScoreFixtureList:
        return FlashScoreFixtureList(str(self.link) + "/fixtures", driver)
    
    def results(self, driver) -> FlashScoreFixtureList:
        return FlashScoreFixtureList(str(self.link) + "/results", driver)


async def get_fs_results(query) -> typing.List[FlashScoreSearchResult]:
    query = query.replace("'", "")  # For some reason, ' completely breaks FS search, and people keep doing it?
    query = urllib.parse.quote(query)
    res = await get_html_async(f"https://s.flashscore.com/search/?q={query}&l=1&s=1&f=1%3B1&pid=2&sid=1")
    
    # Un-fuck FS JSON reply.
    res = res.lstrip('cjs.search.jsonpCallback(').rstrip(");")
    res = json.loads(res)
    filtered = filter(lambda i: i['participant_type_id'] in (0, 1), res['results'])  # discard players.
    return [Team(**i) if i['participant_type_id'] == 1 else Competition(**i) for i in filtered]


class Competition(FlashScoreSearchResult):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
    @property
    def link(self):
        if hasattr(self, 'override'):
            return self.override
        # Example league URL: https://www.flashscore.com/football/england/premier-league/
        ctry = self.country_name.lower().replace(' ', '-')
        return f"https://www.flashscore.com/soccer/{ctry}/{self.url}"
    
    def table(self, driver) -> BytesIO:
        xp = './/div[@class="table__wrapper"]'
        clicks = [(By.XPATH, ".//span[@class='button cookie-law-accept']")]
        delete = [(By.XPATH, './/div[@class="seoAdWrapper"]'), (By.XPATH, './/div[@class="banner--sticky"]'),
                  (By.XPATH, './/div[@class="box_over_content"]')]
        if hasattr(self, "override"):
            err = f"No table found on {self.override}"
        else:
            err = f"No table found for {self.title}"
        image = selenium_driver.get_image(driver, self.link + "/standings/", xp, err, clicks=clicks, delete=delete)
        return image


class Team(FlashScoreSearchResult):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @property
    def link(self):
        if hasattr(self, 'override'):
            return self.override
        # Example Team URL: https://www.flashscore.com/team/thailand-stars/jLsL0hAF/
        return f"https://www.flashscore.com/team/{self.url}/{self.id}"
    
    def players(self, driver) -> FlashScorePlayerList:
        return FlashScorePlayerList(str(self.link) + "/squad", driver)
    
    def competitions(self):
        raise AssertionError('Getting all competitions of a team has not yet been implemented.')
    
    def most_recent_game(self, driver) -> Fixture:
        results = FlashScoreFixtureList(self.link, driver)
        return results[0]
    
    def table(self, driver):
        # TODO: Table. Get all leagues team is in, give selector menu, edit css property to highlight row
        raise AssertionError('Fetching a table via a team has not yet been implemented.')
    

class Stadium:
    def __init__(self, url, name, team, league, country, **kwargs):
        self.url = url
        self.name = name.title()
        self.team = team
        self.league = league
        self.country = country
        self.__dict__.update(kwargs)
    
    async def fetch_more(self):
        this = dict()
        tree = html.fromstring(await get_html_async(self.url))
        this['image'] = "".join(tree.xpath('.//div[@class="page-img"]/img/@src'))
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
            this['home'] = team_list
        
        for s in old:
            team_list = []
            links = s.xpath('.//a/@href')
            teams = s.xpath('.//a/text()')
            for x, y in list(zip(teams, links)):
                if "/team/" in y:
                    team_list.append(f"[{x}]({y})")
            this['old'] = team_list
        
        this['map_link'] = "".join(tree.xpath('.//figure/img/@src'))
        this['address'] = "".join(tree.xpath('.//tr/th[contains(text(), "Address")]/following-sibling::td//text()'))
        this['capacity'] = "".join(tree.xpath('.//tr/th[contains(text(), "Capacity")]/following-sibling::td//text()'))
        this['cost'] = "".join(tree.xpath('.//tr/th[contains(text(), "Cost")]/following-sibling::td//text()'))
        this['website'] = "".join(tree.xpath('.//tr/th[contains(text(), "Website")]/following-sibling::td//text()'))
        this['att'] = "".join(
            tree.xpath('.//tr/th[contains(text(), "Record attendance")]/following-sibling::td//text()'))
        return this
    
    @property
    def to_picker_row(self) -> str:
        return f"**{self.name}** ({self.country}: {self.team})"
    
    @property
    async def to_embed(self) -> discord.Embed:
        e = discord.Embed()
        e.set_author(name="FootballGroundMap.com", url="http://www.footballgroundmap.com")
        e.title = self.name
        e.url = self.url
        
        data = await self.fetch_more()
        try:  # Check not ""
            e.colour = await embed_utils.get_colour(self.team_badge)
        except AttributeError:
            pass
        
        if data['image']:
            e.set_image(url=data['image'].replace(' ', '%20'))
        
        if data['home']:
            e.add_field(name="Home to", value=", ".join(data['home']), inline=False)
        
        if data['old']:
            e.add_field(name="Former home to", value=", ".join(data['old']), inline=False)
        
        # Location
        address = "Link to map" if not data['address'] else data['address']
        
        if data['map_link']:
            e.add_field(name="Location", value=f"[{address}]({data['map_link']})")
        elif data['address']:
            e.add_field(name="Location", value=address, inline=False)
        
        # Misc Data.
        e.description = ""
        if data['capacity']:
            e.description += f"Capacity: {data['capacity']}\n"
        if data['att']:
            e.description += f"Record Attendance: {data['att']}\n"
        if data['cost']:
            e.description += f"Cost: {data['cost']}\n"
        if data['website']:
            e.description += f"Website: {data['website']}\n"
        
        return e


async def get_html_async(url):
    async with aiohttp.ClientSession() as cs:
        async with cs.get(url) as resp:
            return await resp.text()


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
