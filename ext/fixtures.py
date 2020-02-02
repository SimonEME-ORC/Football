# TODO: Lookup Scores per league.
# TODO: Build reactor menu.
# TODO: Code Goals

import asyncio
import datetime
import typing
import discord
from discord.ext import commands

from ext.utils.embed_paginator import paginate
from ext.utils.selenium_driver import spawn_driver
from lxml import html
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, WebDriverException, ElementNotInteractableException, \
    TimeoutException, ElementClickInterceptedException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

import json

# Imaging.
from colorthief import ColorThief
from copy import deepcopy
from PIL import Image
from io import BytesIO

# Max concurrency sharing.
from ext.utils import transfer_tools

# 'cause
from importlib import reload

# max_concurrency equivalent
sl_lock = asyncio.Semaphore()


async def get_colour(ctx, url):
    async with ctx.bot.session.get(url) as resp:
        r = await resp.read()
        # Convert to base 16 int.
        f = BytesIO(r)
        c = ColorThief(f).get_color(quality=1)
        return int('%02x%02x%02x' % c, 16)


async def build_embeds(ctx, base_embed, description_rows=None, embed_fields=None):
    # Un-Null.
    embed_fields = [] if embed_fields is None else embed_fields
    description_rows = [] if description_rows is None else description_rows
    
    try:
        base_embed.colour = await get_colour(ctx, base_embed.thumbnail.url)
    except AttributeError:
        pass
    
    embeds = []
    if description_rows:
        pages = [description_rows[i:i + 10] for i in range(0, len(description_rows), 10)]
        count = 1
        base_embed.description = ""
        
        for i in pages:
            base_embed.description += "\n".join(i)
            iu = "http://pix.iemoji.com/twit33/0056.png"
            base_embed.set_footer(text=f"Page {count} of {len(pages)} ({ctx.author.name})", icon_url=iu)
            te = deepcopy(base_embed)
            embeds.append(te)
            base_embed.description = ""
            count += 1
    
    if embed_fields:
        embeds = [base_embed.add_field(name=x, value=y, inline=False) for x, y in embed_fields]
    
    await paginate(ctx, embeds)


class Fixtures(commands.Cog):
    """ Rewrite of fixture & result lookups. """
    
    def __init__(self, bot):
        self.bot = bot
        self.driver = None
        reload(transfer_tools)
    
    def cog_unload(self):
        if self.driver is not None:
            self.driver.quit()
    
    def get_html(self, url, xpath, image_fetch=False, clicks=None, delete_elements=None, debug=False,
                 multi_capture=None):
        
        # Build the base embed for this
        e = discord.Embed()
        e.timestamp = datetime.datetime.now()
        e.url = url
        # Spawn driver if none exists.
        self.driver = spawn_driver() if not self.driver else self.driver
        
        # Un-null some shit.
        clicks = [] if clicks is None else clicks
        delete_elements = [] if delete_elements is None else delete_elements
        
        # Fetch the page
        self.driver.get(url)
        
        # Get logo for embed if it exists.
        xp = ".//div[contains(@class,'logo')]"
        try:
            element = WebDriverWait(self.driver, 5).until(ec.visibility_of_element_located((By.XPATH, xpath)))
        except TimeoutException:
            element = None  # Rip
        th = self.driver.find_element_by_xpath(xp)
        th = th.value_of_css_property('background-image')
        if th !=  "none":
            logo_url = th.strip("url(").strip(")").strip('"')
            print(logo_url)
            e.set_thumbnail(url=logo_url)
        
        # Delete floating ad banners or other shit that gets in the way
        for z in delete_elements:
            try:
                x = WebDriverWait(self.driver, 3).until(ec.presence_of_element_located(z))
            except TimeoutException:
                continue  # Element does not exist, do not need to delete it.
            scr = """var element = arguments[0];element.parentNode.removeChild(element);"""
            self.driver.execute_script(scr, x)
        
        # Hide cookie popups, switch tabs, etc.
        for z in clicks:
            try:
                x = WebDriverWait(self.driver, 3).until(ec.presence_of_element_located(z))
                x.click()
            except (TimeoutException, ElementNotInteractableException):
                WebDriverWait(self.driver, 1)  # Wait for a second.
                continue  # Can't click on what we can't find.
        
        if debug:
            self.driver.save_screenshot('debug.png')
        
        if multi_capture:
            max_iter = 10
            captures = []
            trg = self.driver.find_element_by_xpath(xpath)
            captures.append(Image.open(BytesIO(trg.screenshot_as_png)))
            while max_iter > 0:
                try:
                    z = WebDriverWait(self.driver, 3).until(ec.visibility_of_element_located(multi_capture))
                    z.click()
                except TimeoutException:
                    print("Unable to locate an element.")
                    break
                except ElementNotInteractableException as err:
                    print(err)
                    print(err.__traceback__)
                else:
                    self.driver.execute_script(
                        "document.getElementsByClassName('playoff-scroll-button')[0].style.display = 'none';"
                        "document.getElementsByClassName('playoff-scroll-button')[1].style.display = 'none';")
                    trg = self.driver.find_element_by_xpath(xpath)
                    captures.append(Image.open(BytesIO(trg.screenshot_as_png)))
                # THIS SHOULD NOT BE HARD-CODED.

                max_iter -= 1
            return captures, e,  self.driver.page_source
        
        if image_fetch:
            if element is None:
                return None, e, self.driver.page_source
            self.driver.execute_script("arguments[0].scrollIntoView();", element)
            im = Image.open(BytesIO(element.screenshot_as_png))
            
            output = BytesIO()
            im.save(output, "PNG")
            output.seek(0)
            df = discord.File(output, filename="img.png")
            return df, e, self.driver.page_source
        return e, self.driver.page_source
    
    def parse_live(self, league, game, mode):
        game_uri = game.split('_')[-1]
        url = f"https://www.flashscore.com/match/{game_uri}/"
        if mode == "stats":
            url += "#match-statistics;0"
            xp = ".//div[@class='statBox']"
        elif mode == "formation":
            url += "#lineups;1"
            xp = './/div[@id="lineups-content"]'
        elif mode == "summary":
            xp = ".//div[@id='summary-content']"
        else:
            print(f"Can't parse stats for invalid mode: {mode}")
            return
        
        image, e, inner_html = self.get_html(url, xpath=xp, image_fetch=True)
        
        home = self.bot.live_games[league][game]["home_team"]
        away = self.bot.live_games[league][game]["away_team"]
        score = self.bot.live_games[league][game]["score"]
        time = self.bot.live_games[league][game]["time"]
        
        e.set_author(name=f"≡ {home} {score} {away} ({time})")
        e.title = league
        e.timestamp = datetime.datetime.now()
        if image is None:
            e.description = f"⛔ Sorry, no {mode} found for this match."
        if "PP" in time:
            e.colour = 0xDB4437  # Red
            e.description = "This match has been postponed."
        elif "HT" in time:
            e.colour = 0xF4B400  # Amber
        elif "FT" in time:
            e.colour = 0x4285F4  # Blue
        elif "+" in time:
            e.colour = 0x9932CC  # Purple
        elif "'" in time:
            e.colour = 0x0F9D58  # Green
        else:
            try:
                h, m = time.split(':')
                now = datetime.datetime.now()
                when = datetime.datetime.now().replace(hour=int(h), minute=int(m))
                x = when - now
                e.set_footer(text=f"Kickoff in {x}")
                e.timestamp = when
            except (IndexError, ValueError):
                e.description = "Live data not available for this match."
            
            e.colour = 0xB3B3B3  # Gray
            
        return e, image
    
    def parse_match_list(self, url, return_mode):
        url += f"/{return_mode}"
        xp = './/div[@class="sportName soccer"]'
        e, inner_html = self.get_html(url, xpath=xp)
        
        tree = html.fromstring(inner_html)
        title = "".join(tree.xpath('.//div[@class="teamHeader__name"]/text()')).strip()
        title = f"≡ {return_mode.title()} for {title}"
        
        xp = ".//div[contains(@class,'sportName soccer')]/div"
        items = tree.xpath(xp)
        matches = []
        for i in items:
            try:
                url = i.xpath("./@id")[0].split("_")[-1]
                url = "http://www.flashscore.com/match/" + url
            except IndexError:
                continue  # Not all rows have links.
            
            d = "".join(i.xpath('.//div[@class="event__time"]//text()')).strip("Pen").strip(
                'Postp.')  # dd.mm hh:mm or dd.mm.yyyy
            if not "Postp" in d:
                yn = datetime.datetime.today().year  # Year now
                try:
                    d = datetime.datetime.strptime(d, '%d.%m.%Y')
                except ValueError:
                    # This is ugly but February 29th can suck my dick.
                    d = datetime.datetime.strptime(f"{datetime.datetime.now().year}.{d}", '%Y.%d.%m. %H:%M')
                    
                    # CHeck if game is next year.
                    if return_mode == "fixtures":
                        if d < datetime.datetime.today():
                            d = d.replace(year=yn + 1)
                
                if d.year != yn:
                    d = d.strftime('%d %b %Y')
                else:
                    if return_mode == "fixtures":
                        d = d.strftime('%a %d %b %H:%M')
                    else:
                        d = d.strftime('%a %d %b')
            
            # TV
            tv = i.xpath(".//div[contains(@class,'tv')]")
            tv = "📺" if tv else ""
            
            # score
            sc = " - ".join(i.xpath('.//div[contains(@class,"event__scores")]/span/text()'))
            sc = "vs" if not sc else sc
            h, a = i.xpath('.//div[contains(@class,"event__participant")]/text()')
            h, a = h.strip(), a.strip()
            matches.append(f"`{d}:` [{h} {sc} {a} {tv}]({url})")
        e.title = title
        return e, matches
    
    def parse_table(self, url):
        url += "/standings/"
        clicks = [(By.XPATH, ".//span[@class='button cookie-law-accept']")]
        xp = './/div[@class="table__wrapper"]'
        delete = [(By.XPATH, './/div[@class="seoAdWrapper"]'), (By.XPATH, './/div[@class="banner--sticky"]')]
        image, e, src = self.get_html(url, xpath=xp, clicks=clicks, image_fetch=True, delete_elements=delete)
        return image
    
    def parse_scorers(self, url, team=None):
        url += "/standings"
        xp = ".//div[@class='tabs__group']"
        clicks = [(By.ID, "tabitem-top_scorers")]
        
        e, inner_html = self.get_html(url, xpath=xp, clicks=clicks)
        
        tree = html.fromstring(inner_html)
        
        title = "".join(tree.xpath('.//div[@class="teamHeader__name"]/text()')).strip()
        rows = tree.xpath('.//div[@id="table-type-10"]//div[contains(@class,"table__row")]')
        description_rows = []
        for i in rows:
            items = i.xpath('.//text()')
            items = [i.strip() for i in items if i.strip()]
            uri = "".join(i.xpath(".//span[@class='team_name_span']//a/@onclick")).split("'")
            
            try:
                tm_url = "http://www.flashscore.com/" + uri[3]
            except IndexError:
                tm_url = ""
            try:
                p_url = "http://www.flashscore.com/" + uri[1]
            except IndexError:
                p_url = ""
            
            rank, name, tm, goals, assists = items
            tm = f" ([{tm}]({tm_url})) " if tm else ""
            
            if team is not None:
                if team.lower() not in tm.lower():
                    continue
            
            country = "".join(i.xpath('.//span[contains(@class,"flag")]/@title')).strip()
            flag = transfer_tools.get_flag(country)
            description_rows.append(f'`{rank}` {flag} [{name}]({p_url}){tm}: {goals} Goals, {assists} Assists')
        
        if team:
            title = f"≡ Top Scorers (from {team.title()}) for {title}"
        else:
            title = f"≡ Top Scorers for {title}"
        e.title = title
        return e, description_rows

    def parse_team(self, url, mode):
        url += "/squad"
        xp = './/div[contains(@class,"playerTable")]'
    
        delete = [(By.XPATH, './/div[@id="lsid-window-mask"]')]
        clicks = [(By.ID, 'overall-all')]
        e, inner_html = self.get_html(url, xpath=xp, clicks=clicks, delete_elements=delete)
        tree = html.fromstring(inner_html)
    
        title = "".join(tree.xpath('.//div[@class="teamHeader__name"]/text()')).strip()
        title = f"≡ {mode.title()} for {title}"
        rows = tree.xpath('.//div[contains(@id,"overall-all-table")]//div[contains(@class,"profileTable__row")]')[1:]
        tuples = []
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
            country = "".join(i.xpath('.//span[contains(@class,"flag")]/@title'))
            flag = transfer_tools.get_flag(country)
        
            sq = "".join(i.xpath('.//div[@class="tableTeam__squadNumber"]/text()'))
            try:
                age, apps, g, y, r = i.xpath(
                    './/div[@class="playerTable__icons playerTable__icons--squad"]//div/text()')
            except ValueError:
                age = "".join(i.xpath('.//div[@class="playerTable__icons playerTable__icons--squad"]//div/text()'))
                apps = g = y = r = 0
            injury = "".join(i.xpath('.//span[contains(@class,"absence injury")]/@title'))
        
            link = "".join(i.xpath('.//div[contains(@class,"")]/a/@href'))
            link = f"http://www.flashscore.com{link}" if link else ""
        
            # Put name in the right order.
            try:
                player_split = name.split(' ', 1)
                name = f"{player_split[1]} {player_split[0]}"
            except IndexError:
                pass
        
            tuples.append((sq, flag, name, link, position, injury, age, apps, int(g), y, r))
        e.title = title
    
        if mode == "squad":
            embed_fields = []
            for x in list(set([i[4] for i in tuples])):  # All unique Positions.
                embed_fields.append((x, ", ".join(
                    [f"`{z[0]}` {z[2]}".replace("``", "") for z in tuples if z[4] == x])))
            return e, embed_fields
    
        description_rows = []
        if mode == "injuries":
            description_rows = [f"{i[1]} [{i[2]}]({i[3]}) ({i[4]}): {i[5]}" for i in tuples if i[5]]
            description_rows = ["No injuries found!"] if not description_rows else description_rows
        elif mode == "Top scorers":
            filtered = [i for i in tuples if i[8]]
            output = sorted(filtered, key=lambda v: v[8], reverse=True)
            description_rows = [f"{i[1]} [{i[2]}]({i[3]}): {i[8]} Goals" for i in output]  # 0 is falsey.
            description_rows = ["No goal data found."] if not description_rows else description_rows
        return e, description_rows

    def parse_bracket(self, url):
        url += "/draw/"
        xp = './/div[@id="box-table-type--1"]'
        multi = (By.LINK_TEXT, 'scroll right »')
        clicks = [(By.XPATH, ".//span[@class='button cookie-law-accept']")]
        delete = [(By.XPATH, './/div[@class="seoAdWrapper"]'), (By.XPATH, './/div[@class="banner--sticky"]')]
        captures, e, src = self.get_html(url, xpath=xp, clicks=clicks, multi_capture=multi, delete_elements=delete)
        
        e.title = "Bracket"
        e.description = "Please click on picture -> open original to enlarge"
        e.timestamp = datetime.datetime.now()
        # Captures is a list of opened PIL images.
        print(f"Found {len(captures)} images to stitch")
        w = int(captures[0].width / 3 * 2 + sum(i.width / 3 for i in captures))
        h = captures[0].height
        
        canvas = Image.new('RGB', (w, h))
        x = 0
        for i in captures:
            canvas.paste(i, (x, 0))
            x += int(i.width / 3)
        output = BytesIO()
        canvas.save(output, "PNG")
        output.seek(0)
        canvas.save('canvas.png',"png")
        file = discord.File(fp=output, filename="img.png")
        return file, e
    
    @commands.command(aliases=['draw'])
    async def bracket(self, ctx, *, qry: commands.clean_content = None):
        """ Get btacket for a tournament """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            url = await self._fetch_default(ctx, m, qry, preferred="league")
            if url is None:
                return  # rip.
            
            await m.edit(content=f'Grabbing competition bracket for {qry}...', delete_after=5)
            async with sl_lock:
                file, e = await self.bot.loop.run_in_executor(None, self.parse_bracket, url)
            
            e.set_image(url="attachment://img.png")
            e.title = f"Bracket for {qry}"
            await ctx.send(file=file, embed=e)
    
    @commands.command()
    async def table(self, ctx, *, qry: commands.clean_content = None):
        """ Get table for a league """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            url = await self._fetch_default(ctx, m, qry, preferred="league")
            if url is None:
                return  # rip.
            
            await m.edit(content=f"Grabbing table from <{url}>...", delete_after=5)
            async with sl_lock:
                p = await self.bot.loop.run_in_executor(None, self.parse_table, url)
            try:
                await ctx.send(file=p)
            except discord.HTTPException:
                await ctx.send(f"Failed to grab table from <{url}>")
    
    @commands.command(aliases=["fx"])
    async def fixtures(self, ctx, *, qry: commands.clean_content = None):
        """ Displays upcoming fixtures for a team or league.
            Navigate with reactions.
        """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            url = await self._fetch_default(ctx, m, qry, preferred="team")
            if url is None:
                return  # rip.
            
            await m.edit(content=f'Grabbing fixtures data from <{url}>...', delete_after=5)
            async with sl_lock:
                e, matches = await self.bot.loop.run_in_executor(None, self.parse_match_list, url,"fixtures")
            await build_embeds(ctx, e, description_rows=matches)
    
    @commands.command(aliases=["rx"])
    async def results(self, ctx, *, qry: commands.clean_content = None):
        """ Displays previous results for a team or league.
            Navigate with reactions.
        """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            url = await self._fetch_default(ctx, m, qry, preferred="team")
            if url is None:
                return  # rip.
            
            await m.edit(content=f'Grabbing results data from <{url}>...', delete_after=5)
            async with sl_lock:
                e, matches = await self.bot.loop.run_in_executor(None, self.parse_match_list, url, "results")
            await build_embeds(ctx, e, description_rows=matches)
    
    @commands.command(aliases=["suspensions"])
    async def injuries(self, ctx, *, qry: commands.clean_content = None):
        """ Get a team's current injuries """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            url = await self._fetch_default(ctx, m, qry, preferred="team")
            if url is None:
                return  # rip.
            
            await m.edit(content=f'Grabbing injury data from <{url}>...', delete_after=5)
            async with sl_lock:
                e, rows = await self.bot.loop.run_in_executor(None, self.parse_team, url, "injuries")
            await build_embeds(ctx, e, description_rows=rows)
    
    @commands.command()
    async def stats(self, ctx, *, qry: commands.clean_content):
        """ Look up the stats for one of today's games """
        async with ctx.typing():
            m = await ctx.send('Searching...')
            league, game = await self.pick_game(m, ctx, qry.lower())
            if game is None:
                return await ctx.send(f"Unable to find a match for {qry}")
            async with sl_lock:
                e, file = await self.bot.loop.run_in_executor(None, self.parse_live, league, game, "stats")
            e.set_image(url="attachment://img.png")
            await ctx.send(file=file, embed=e)
    
    @commands.command(aliases=["formations", "lineup", "lineups"])
    async def formation(self, ctx, *, qry: commands.clean_content):
        """ Get the formations for the teams in one of today's games """
        async with ctx.typing():
            m = await ctx.send('Searching...')
            league, game = await self.pick_game(m, ctx, qry.lower())
            if game is None:
                return await ctx.send(f"Unable to find a match for {qry}")
            
            async with sl_lock:
                e, file = await self.bot.loop.run_in_executor(None, self.parse_live, league, game,"formation")
            e.set_image(url="attachment://img.png")
            await ctx.send(file=file, embed=e)
            
    @commands.command()
    async def summary(self, ctx, *, qry: commands.clean_content):
        """ Get a summary for one of today's games. """
        async with ctx.typing():
            m = await ctx.send('Searching...')
            league, game = await self.pick_game(m, ctx, qry.lower())
            if game is None:
                return await ctx.send(f"Unable to find a match for {qry}")

            async with sl_lock:
                e, file = await  self.bot.loop.run_in_executor(None, self.parse_live, league, game, "summary")
            e.set_image(url="attachment://img.png")
            await ctx.send(file=file, embed=e)

    async def pick_game(self, m, ctx, qry):
        matches = []
        key = 0
        url = ""
        if qry is None:
            url = await self._fetch_default(ctx, m, qry, preferred="team")
            url = "" if url is None else url
        
        for league in self.bot.live_games:
            for game_id in self.bot.live_games[league]:
                # Ignore our output strings.
                if game_id == "raw":
                    continue
                
                home = self.bot.live_games[league][game_id]["home_team"]
                away = self.bot.live_games[league][game_id]["away_team"]
                
                if game_id in url or qry in home.lower() or qry in away.lower():
                    game = f"{home} vs {away} ({league})"
                    matches.append((str(key), game, league, game_id))
                    key += 1
        
        if not matches:
            return None, None
        
        if len(matches) == 1:
            # return league and game of only result.
            return matches[0][2], matches[0][3]
        
        selector = "Please Type Matching ID```"
        for i in matches:
            selector += f"{i[0]}: {i[1]}\n"
        selector += "```"
        
        try:
            m = await ctx.send(selector, delete_after=30)
        except discord.HTTPException:
            # TODO: Paginate.
            return await ctx.send(content=f"Too many matches to display, please be more specific.")
        
        def check(message):
            if message.author.id == ctx.author.id and message.content.isdigit():
                if int(message.content) < len(matches):
                    return True
        
        try:
            match = await self.bot.wait_for("message", check=check, timeout=30)
            match = match.content
        except asyncio.TimeoutError:
            return None, None
        else:
            try:
                await m.delete()
            except discord.NotFound:
                pass
            return matches[int(match)][2], matches[int(match)][3]
    
    @commands.command(aliases=["team", "roster"])
    async def squad(self, ctx, *, qry: commands.clean_content = None):
        async with ctx.typing():
            m = await ctx.send("Searching...")
            url = await self._fetch_default(ctx, m, qry, preferred="team")
            if url is None:
                return  # rip.
            
            await m.edit(content=f'Grabbing team squad data from <{url}>...', delete_after=5)
            async with sl_lock:
                e, embed_fields = await self.bot.loop.run_in_executor(None, self.parse_team, url, "squad")
            await build_embeds(ctx, e, embed_fields=embed_fields)
    
    @commands.group(invoke_without_command=True, aliases=['sc'])
    async def scorers(self, ctx, league: typing.Optional[commands.clean_content], *,
                      team: commands.clean_content = None):
        """ Get top scorers from a league, optionally by team. """
        if league is not None:
            await ctx.send(f'Trying to get the top scorers from League: "{league}", team: {team}\n'
                           f'*Tip: Doesn\'t look right? Try {ctx.prefix}{ctx.command} "League Name" "Team Name"',
                           delete_after=10)
        else:
            await ctx.send("Trying to find top scorers for your default league...", delete_after=10)
        m = await ctx.send("...")
        
        url = await self._fetch_default(ctx, m, league, preferred='league')
        if url is None:
            return  # rip
        
        await m.edit(content=f'Grabbing Top Scorers data from <{url}>...', delete_after=5)
        async with sl_lock:
            e, rows = await self.bot.loop.run_in_executor(None, self.parse_scorers, url, team)
        await build_embeds(ctx, e, description_rows=rows)
    
    @scorers.command()
    async def team(self, ctx, *, qry: commands.clean_content = None):
        """ Get a team's top scorers across all competitions """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            url = await self._fetch_default(ctx, m, qry, preferred="team")
            if url is None:
                return  # rip.
            
            if "team" not in url:
                return await ctx.send("That looks like a league, not a team, "
                                      "please check which sub-command you're using.")
            
            await m.edit(content=f'Grabbing Top Scorers data from <{url}>...', delete_after=5)
            async with sl_lock:
                e, description_rows = await self.bot.loop.run_in_executor(None, self.parse_team, url, "Top scorers")
            await build_embeds(ctx, e, description_rows=description_rows)

    # TODO: Cache these.
    async def _fetch_default(self, ctx, m, qry, preferred=None, mode=None):
        # Check if default is set and return that.
        if qry is None:
            connection = await self.bot.db.acquire()
            r = await connection.fetchrow("""
                 SELecT * FROM scores_settings
                 WHERE (guild_id) = $1
                 AND (default_league is NOT NULL OR default_team IS NOT NULL)
             """, ctx.guild.id)
            await self.bot.db.release(connection)
            if r:
                try:
                    team = r["default_team"]
                except KeyError:
                    team = ""
                try:
                    league = r["default_league"]
                except KeyError:
                    league = ""
            
                # Decide if found, yell if not.
                if any([league, team]):
                    if preferred == "team":
                        return team if team else league
                    else:
                        return league if league else team
        
            await m.edit(
                content=f'Please specify a search query. A default team or league can be set by moderators '
                        f'using {ctx.prefix}default <"team" or "league"> <search string>')
            return None
    
        qry = qry.replace("'", "")
        url = f"https://s.flashscore.com/search/?q={qry}&l=1&s=1&f=1%3B1&pid=2&sid=1"
        async with self.bot.session.get(url) as resp:
            res = await resp.text()
            res = res.lstrip('cjs.search.jsonpCallback(').rstrip(");")
            res = json.loads(res)
    
        resdict = {}
        key = 0
        # Remove irrel.
        for i in res["results"]:
            if i["participant_type_id"] == 0:  # League
                if mode is not "team":
                    # Sample League URL: https://www.flashscore.com/soccer/england/premier-league/
                    resdict[str(key)] = {"Match": i['title'], "url": f"soccer/{i['country_name'].lower()}/{i['url']}"}
            elif i["participant_type_id"] == 1:  # Team
                if mode is not "league":
                    # Sample Team URL: https://www.flashscore.com/team/thailand-stars/jLsL0hAF/
                    resdict[str(key)] = {"Match": i["title"], "url": f"team/{i['url']}/{i['id']}"}
            key += 1
    
        if not resdict:
            await m.edit(content=f"No results for query: {qry}")
            return None
    
        if len(resdict) == 1:
            return f'https://www.flashscore.com/{resdict["0"]["url"]}'
    
        outtext = ""
        for i in resdict:
            outtext += f"{i}: {resdict[i]['Match']}\n"
    
        try:
            await m.edit(content=f"Please type matching id: ```{outtext}```")
        except discord.HTTPException:
            #  TODO: Paginate.
            await m.edit(content=f"Too many matches to display, please be more specific.")
            return None
        try:
            def check(message):
                if message.author.id == ctx.author.id and message.content in resdict:
                    return True
        
            match = await self.bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            await m.edit(content="Timed out waiting for you to select matching ID.")
            return None
    
        mcontent = match.content
        await m.edit(content=f"Grabbing data...", delete_after=5)
    
        try:
            await match.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        return f'https://www.flashscore.com/{resdict[mcontent]["url"]}'
    
    # TODO: Cache.
    @commands.has_permissions(manage_guild=True)
    @commands.command(usage="default <'team' or 'league'> <(Your Search Query) or ('None' to unset default.)")
    async def default(self, ctx, mode, *, qry: commands.clean_content = None):
        """ Set a default team or league for your server's lookup commands """
        # Validate
        mode = mode.lower()
        if mode not in ["league", "team"]:
            return await ctx.send(':no_entry_sign: Invalid default type specified, valid types are "league" or "team"')
        mode = "default_team" if mode == "team" else "default_league"
        
        if qry is None:
            connection = await self.bot.db.acquire()
            record = await connection.fetchrow("""
                SELecT * FROM scores_settings
                WHERE (guild_id) = $1
                AND (default_league is NOT NULL OR default_team IS NOT NULL)
            """, ctx.guild.id)
            await self.bot.db.release(connection)
            if not record:
                return await ctx.send(f"{ctx.guild.name} does not currently have a default team or league set.")
            league = record["default_league"] if record["default_league"] is not None else "not set."
            output = f"Your default league is: {league}"
            team = record["default_team"] if record["default_team"] is not None else "not set."
            output += "\n" + team
            
            return await ctx.send(output)
        
        if qry.lower() == "none":  # Intentionally set Null for DB entry
            url = None
        else:  # Find
            m = await ctx.send(f'Searching for {qry}...')
            url = await self._fetch_default(ctx, m, qry, mode=mode)
            if not url:
                return await ctx.send(f"Couldn't find anything for {qry}, try searching for something else.")
        
        connection = await self.bot.db.acquire()
        
        async with connection.transaction():
            await connection.execute(
                f"""INSERT INTO scores_settings (guild_id,{mode})
                VALUES ($1,$2)
                
                ON CONFLICT (guild_id) DO UPDATE SET 
                    {mode} = $2
                WHERE excluded.guild_id = $1
            """, ctx.guild.id, url)
        
        await self.bot.db.release(connection)
        
        if qry is not None:
            return await ctx.send(f'Your commands will now use <{url}> as a default {mode}')
        else:
            return await ctx.send(f'Your commands will no longer use a default {mode}')


def setup(bot):
    bot.add_cog(Fixtures(bot))
