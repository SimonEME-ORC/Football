# TODO: Find somewhere to get goal clips from.

import asyncio
import datetime
import typing
import discord
from discord.ext import commands

from ext.utils.selenium_driver import spawn_driver
from lxml import html
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import ElementNotInteractableException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

# Imaging.
from copy import deepcopy
from PIL import Image
from io import BytesIO

from ext.utils import transfer_tools, football, embed_utils

# 'cause
from importlib import reload

# max_concurrency equivalent
sl_lock = asyncio.Semaphore()

# TODO: Finish Refactor into ext.utils.football Classes


# TODO: Kill this.
async def build_embeds(ctx, base_embed, description_rows=None, embed_fields=None):
    # Un-Null.
    embed_fields = [] if embed_fields is None else embed_fields
    description_rows = [] if description_rows is None else description_rows
    
    base_embed.colour = await embed_utils.get_colour(base_embed.thumbnail.url)
    
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
    
    await embed_utils.paginate(ctx, embeds)


class Fixtures(commands.Cog):
    """ Lookups for Past, Present and Future football matches. """
    
    def __init__(self, bot):
        self.bot = bot
        self.driver = spawn_driver()
        for package in [transfer_tools, football, embed_utils]:
            reload(package)

    def cog_unload(self):
        if self.driver is not None:
            self.driver.quit()
    
    # Master picker.
    async def _search(self, ctx, qry, mode=None) -> str or None:
        if qry is None:
            err = "Please specify a search query."
            if ctx.guild is not None:
                result = await self._fetch_default(ctx, mode)
                if result is not None:
                    if mode == "team":
                        sr = football.Tean(override=result, title=f"{ctx.guild.name} default")
                    else:
                        sr = football.Competition(override=result, title=f"{ctx.guild.name} default")
                    return sr
            else:
                err += f"\nA default team or league can be set by moderators using {ctx.prefix}default)"
            await ctx.send(err)
            return None

        search_results = await football.get_fs_results(qry)
        pt = 0 if mode == "league" else 1 if mode == "team" else None  # Mode is a hard override.
        if pt is not None:
            item_list = [i.title for i in search_results if i.participant_type_id == pt]  # Check for specifics.
        else:  # All if no mode
            item_list = [i.title for i in search_results]
        index = await embed_utils.page_selector(ctx, item_list)

        if index is None:
            return  # Timeout or abort.

        return search_results[index]

    # TODO: Cache these.
    async def _fetch_default(self, ctx, mode=None):
        connection = await self.bot.db.acquire()
        r = await connection.fetchrow("""
             SELecT * FROM scores_settings WHERE (guild_id) = $1
             AND (default_league is NOT NULL OR default_team IS NOT NULL) """, ctx.guild.id)
        await self.bot.db.release(connection)
        if r:
            team = r["default_team"]
            league = r["default_league"]
            # Decide if found, yell if not.
            if any([league, team]):
                if mode == "team":
                    return team if team else league
                return league if league else team
        return None

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
            await ctx.send(f'Searching for {qry}...', delete_after=5)
            fsr = await self._search(ctx, qry, mode=mode)
        
            if fsr is None:
                return await ctx.send(f"Couldn't find matching {mode} for {qry}, try searching for something else.")
        
            url = fsr.link
    
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
    
    @commands.command(usage="table <league to search for>>")
    async def table(self, ctx, *, qry: commands.clean_content = None):
        """ Get table for a league """
        async with ctx.typing():
            await ctx.send("Searching...", delete_after=5)
            fsr = await self._search(ctx, qry, mode="league")
            if fsr is None:
                return  # rip.
            
            async with sl_lock:
                p = await self.bot.loop.run_in_executor(None, fsr.table, self.driver)
            
            p = discord.File(fp=p, filename=f"Table {fsr.title} {datetime.datetime.now().date}.png")
            await ctx.send(file=p)
    
    @commands.command(aliases=['fx'], usage="fixtures <team or league to search for>")
    async def fixtures(self, ctx, *, qry: commands.clean_content = None):
        """ Fetch upcoming fixtures for a team or league.
        Navigate pages using reactions. """
        await ctx.send('Searching...', delete_after=5)
        fsr = await self._search(ctx, qry)
        if fsr is None:
            return  # Handled in _search.
        
        async with sl_lock:
            fslist = await self.bot.loop.run_in_executor(None, fsr.fixtures, self.driver)
        embeds = await fslist.to_embeds

        for e in embeds:
            e.title = f"≡ Fixtures for {e.title}"
        return await embed_utils.paginate(ctx, embeds)
    
    @commands.command(aliases=['rx'], usage="results <team or league to search for>")
    async def results(self, ctx, *, qry: commands.clean_content = None):
        """ Get past results for a team or league.
        Navigate pages using reactions. """
        await ctx.send('Searching...', delete_after=5)
        fsr = await self._search(ctx, qry)
        if fsr is None:
            return
        
        async with sl_lock:
            fslist = await self.bot.loop.run_in_executor(None, fsr.results, self.driver)
        embeds = await fslist.to_embeds
        
        for e in embeds:
            e.title = f"≡ Results for {e.title}"
        return await embed_utils.paginate(ctx, embeds)
    
    # TODO: Migrate.
    @commands.command()
    async def stats(self, ctx, *, qry: commands.clean_content):
        """ Look up the stats for one of today's games """
        async with ctx.typing():
            await ctx.send('Searching...', delete_after=5)
            league, game = await self.pick_game(ctx, qry.lower())
            if game is None:
                return await ctx.send(f"Unable to find a match for {qry}")
            async with sl_lock:
                e, file = await self.bot.loop.run_in_executor(None, self.parse_live, league, game, "stats")
            e.set_image(url="attachment://img.png")
            await ctx.send(file=file, embed=e)

    # TODO: Migrate.
    @commands.command(usage="formation <team to search for>", aliases=["formations", "lineup", "lineups"])
    async def formation(self, ctx, *, qry: commands.clean_content):
        """ Get the formations for the teams in one of today's games """
        async with ctx.typing():
            await ctx.send('Searching...', delete_after=5)
            league, game = await self.pick_game(ctx, qry.lower())
            if game is None:
                return await ctx.send(f"Unable to find a match for {qry}")
            
            async with sl_lock:
                e, file = await self.bot.loop.run_in_executor(None, self.parse_live, league, game, "formation")
            e.set_image(url="attachment://img.png")
            await ctx.send(file=file, embed=e)
    
    # TODO: Migrate
    @commands.command()
    async def summary(self, ctx, *, qry: commands.clean_content):
        """ Get a summary for one of today's games. """
        async with ctx.typing():
            await ctx.send('Searching...', delete_after=5)
            league, game = await self.pick_game(ctx, qry.lower())
            if game is None:
                return await ctx.send(f"Unable to find a match for {qry}")
            
            async with sl_lock:
                e, file = await  self.bot.loop.run_in_executor(None, self.parse_live, league, game, "summary")
            e.set_image(url="attachment://img.png")
            await ctx.send(file=file, embed=e)

    @commands.command(aliases=["suspensions"])
    async def injuries(self, ctx, *, qry: commands.clean_content = None):
        """ Get a team's current injuries """
        async with ctx.typing():
            await ctx.send("Searching...", delete_after=5)
            fsr = await self._search(ctx, qry, mode="team")
        
            if fsr is None:
                return
        
            async with sl_lock:
                players = await self.bot.loop.run_in_executor(None, fsr.players, self.driver)
                embeds = await players.injuries_to_embeds
            await embed_utils.paginate(ctx, embeds)
    
    @commands.command(aliases=["team", "roster"])
    async def squad(self, ctx, *, qry: commands.clean_content = None):
        async with ctx.typing():
            m = await ctx.send("Searching...")
            fsr = await self._search(ctx, qry, mode="team")
            
            async with sl_lock:
                players = await self.bot.loop.run_in_executor(None, fsr.players, self.driver)
                embeds = await players.squad_as_embed
            await embed_utils.paginate(ctx, embeds)
    
    # TODO -> FSSearchResult
    @commands.group(invoke_without_command=True, aliases=['sc'])
    async def scorers(self, ctx, league: typing.Optional[commands.clean_content], *,
                      team: commands.clean_content = None):
        """ Get top scorers from a league, optionally by team. """
        if league is not None:
            await ctx.send(f'Trying to get the top scorers from League: "{league}", team: {team}\n'
                           f'*Tip: Doesn\'t look right? Try {ctx.prefix}{ctx.command} "League Name" "Team Name"',
                           delete_after=10)
        else:
            await ctx.send("Trying to find top scorers for your default league...", delete_after=5)
        
        fsr = await self._search(ctx, league, mode='league')
        if fsr is None:
            return  # rip
        
        url = fsr.link

        async with sl_lock:
            e, rows = await self.bot.loop.run_in_executor(None, self.parse_scorers, url, team)
        await build_embeds(ctx, e, description_rows=rows)
    
    @scorers.command()
    async def team(self, ctx, *, qry: commands.clean_content = None):
        """ Get a team's top scorers across all competitions """
        async with ctx.typing():
            await ctx.send("Searching...", delete_after=5)
            fsr = await self._search(ctx, qry, mode="team")
            if fsr is None:
                return  # rip.
            
            async with sl_lock:
                players = await self.bot.loop.run_in_executor(None, fsr.squad_as_embed, self.driver)
                embeds = await players.scorers_to_embeds
            await embed_utils.paginate(ctx, embeds)
    
    # TODO: -> FSSearchResult
    @commands.command(usage="scores <league- to search for>")
    async def scores(self, ctx, *, search_query: commands.clean_content = ""):
        """ Fetch current scores for a specified league """
        embeds = []
        e = discord.Embed()
        e.colour = discord.Colour.blurple()
        if search_query:
            e.set_author(name=f'Live Scores matching "{search_query}"')
        else:
            e.set_author(name="Live Scores for all known competitions")
        e.timestamp = datetime.datetime.now()
        dtn = datetime.datetime.now().strftime("%H:%M")
        matches = {k: v for k, v in self.bot.live_games.items() if search_query.lower() in k.lower()}
        page = 1
        if not matches:
            e.description = "No results found!"
            return await embed_utils.paginate(ctx, [e])
        for league in matches:
            if len(matches[league]['raw_with_link']) < 1966:
                e.description = matches[league]['raw_with_link']
            elif len(matches[league]['raw']) < 1966:
                e.description = matches[league]['raw']
            else:
                e.description = ""
                discarded = 0
                for row in matches[league]['raw'].split('\n'):
                    if len(e.description + row) > 1946:
                        e.description += row
                    else:
                        discarded += 1
                if discarded:
                    e.description += f"*and {discarded} more...*"
            e.description += f"\n*Local time: {dtn}\nPlease note this menu will NOT auto-update. It is a snapshot.*"
            e.set_footer(text=f"{ctx.author}: Page {page} of {len(matches)}")
            embeds.append(deepcopy(e))
            page += 1
        await embed_utils.paginate(ctx, embeds)

    @commands.command(usage="Stadium <team or stadium to search for.>")
    async def stadium(self, ctx, *, query):
        """ Lookup information about a team's stadiums """
        stadiums = await football.get_stadiums(query)
        item_list = [i.to_picker_row for i in stadiums]
    
        index = await embed_utils.page_selector(ctx, item_list)
    
        if index is None:
            return  # Timeout or abort.
    
        await ctx.send(embed=await stadiums[index].to_embed)

    # TODO: Re-write this once LiveScores is converted to football.Fixture
    async def pick_game(self, ctx, qry):
        matches = []
        key = 0
        url = ""
        if qry is None:
            fsr = await self._search(ctx, qry, mode="team")
            url = fsr.link
            url = "" if url is None else url
    
        for league in self.bot.live_games:
            for game_id in self.bot.live_games[league]:
                # Ignore our output strings.
                if game_id in ("raw", 'raw_with_link'):
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

    # TODO: Kill this.
    def get_html(self, url, xpath, **kwargs):
        sub_funcs = kwargs
        # Build the base embed for this
        e = discord.Embed()
        e.timestamp = datetime.datetime.now()
        e.url = url
    
        # Fetch the page
        self.driver.get(url)
    
        try:
            element = WebDriverWait(self.driver, 5).until(ec.visibility_of_element_located((By.XPATH, xpath)))
        except TimeoutException:
            element = None  # Rip
    
        # Get logo for embed if it exists.
        xp = ".//div[contains(@class,'logo')]"
        th = self.driver.find_element_by_xpath(xp)
        th = th.value_of_css_property('background-image')
        if th != "none":
            logo_url = th.strip("url(").strip(")").strip('"')
            e.set_thumbnail(url=logo_url)
    
        # Delete floating ad banners or other shit that gets in the way
        if "delete_elements" in sub_funcs:
            for z in sub_funcs['delete_elements']:
                try:
                    x = WebDriverWait(self.driver, 3).until(ec.presence_of_element_located(z))
                except TimeoutException:
                    continue  # Element does not exist, do not need to delete it.
                scr = """var element = arguments[0];element.parentNode.removeChild(element);"""
                self.driver.execute_script(scr, x)
    
        # Hide cookie popups, switch tabs, etc.
        if "clicks" in sub_funcs:
            for z in sub_funcs['clicks']:
                try:
                    x = WebDriverWait(self.driver, 3).until(ec.presence_of_element_located(z))
                    x.click()
                except (TimeoutException, ElementNotInteractableException, StaleElementReferenceException):
                    WebDriverWait(self.driver, 1)  # Wait for a second.
                    continue  # Can't click on what we can't find.
    
        if "multi_capture" in sub_funcs:
            max_iter = 10
            captures = []
            trg = self.driver.find_element_by_xpath(xpath)
            captures.append(Image.open(BytesIO(trg.screenshot_as_png)))
            while max_iter > 0:
                locator = sub_funcs['multi_capture']
                try:
                    z = WebDriverWait(self.driver, 3).until(ec.visibility_of_element_located(locator))
                    z.click()
                except TimeoutException:
                    break
                except ElementNotInteractableException as err:
                    print(err)
                    print(err.__traceback__)
                else:
                    if "multi_capture_script" in sub_funcs:
                        self.driver.execute_script(sub_funcs['multi_capture_script'])
                        trg = self.driver.find_element_by_xpath(xpath)
                        captures.append(Image.open(BytesIO(trg.screenshot_as_png)))
                max_iter -= 1
            return captures, e, self.driver.page_source
    
        if 'image_fetch' in sub_funcs:
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

    # TODO: Kill this.
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

    # TODO : -> FSPlayerLISt (Comes from league, not team.)
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

    # TODO: rewrite,
    def parse_bracket(self, url):
        url += "/draw/"
        xp = './/div[@id="box-table-type--1"]'
        multi = (By.LINK_TEXT, 'scroll right »')
        clicks = [(By.XPATH, ".//span[@class='button cookie-law-accept']")]
        delete = [(By.XPATH, './/div[@class="seoAdWrapper"]'), (By.XPATH, './/div[@class="banner--sticky"]')]
        script = "document.getElementsByClassName('playoff-scroll-button')[0].style.display = 'none';" \
                 "document.getElementsByClassName('playoff-scroll-button')[1].style.display = 'none';"
        captures, e, src = self.get_html(url, xpath=xp, clicks=clicks, multi_capture=multi,
                                         multi_capture_script=script, delete_elements=delete)
    
        e.title = "Bracket"
        e.description = "Please click on picture -> open original to enlarge"
        e.timestamp = datetime.datetime.now()
        # Captures is a list of opened PIL images.
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
        canvas.save('canvas.png', "png")
        file = discord.File(fp=output, filename="img.png")
        return file, e

    # TODO: Re-write
    @commands.command(aliases=['draw'])
    async def bracket(self, ctx, *, qry: commands.clean_content = None):
        """ Get btacket for a tournament """
        async with ctx.typing():
            await ctx.send("Searching...", delete_after=5)
            fsr = await self._search(ctx, qry, mode="league")
            if fsr is None:
                return  # rip.
        
            url = fsr.link
        
            async with sl_lock:
                file, e = await self.bot.loop.run_in_executor(None, self.parse_bracket, url)
        
            e.set_image(url="attachment://img.png")
            e.title = f"Bracket for {qry}"
            await ctx.send(file=file, embed=e)


def setup(bot):
    bot.add_cog(Fixtures(bot))
