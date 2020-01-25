import asyncio
import discord
from discord.ext import commands

# Scraping
from ext.utils.embed_paginator import paginate
from ext.utils.selenium_driver import spawn_driver
from lxml import html
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, WebDriverException, TimeoutException, \
    ElementNotInteractableException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

import json

# Imaging.
from colorthief import ColorThief
from copy import deepcopy
from PIL import Image
from io import BytesIO

# Misc utils
import datetime


def build_embeds(au, e, z, header):
    embeds = []
    p = [z[i:i + 10] for i in range(0, len(z), 10)]
    pages = len(p)
    count = 1
    for i in p:
        j = "\n".join([j for j, k in i])
        k = "\n".join([k for j, k in i])
        e.add_field(name="Date", value=j, inline=True)
        e.add_field(name=header, value=k, inline=True)
        iu = "http://pix.iemoji.com/twit33/0056.png"
        e.set_footer(text=f"Page {count} of {pages} ({au})", icon_url=iu)
        te = deepcopy(e)
        embeds.append(te)
        e.clear_fields()
        count += 1
    return embeds


class Fixtures(commands.Cog):
    """ Rewrite of fixture & result lookups. """

    def __init__(self, bot):
        self.bot = bot
        self.driver = None
        self.bot.loop.create_task(self.get_driver())

    def cog_unload(self):
        self.driver.quit()

    async def get_driver(self):
        self.driver = await self.bot.loop.run_in_executor(None, spawn_driver)

    async def get_color(self, url):
        url = url.strip('"')
        async with self.bot.session.get(url) as resp:
            r = await resp.content()
        # Convert to base 16 int.
        b = BytesIO(r).seek(0)
        c = ColorThief(b).get_color(quality=1)
        return int('%02x%02x%02x' % c, 16)

    def get_html(self, url):
        self.driver.get(url)
        e = discord.Embed()
        try:
            xp = ".//div[contains(@class,'logo')]"
            th = WebDriverWait(self.driver, 10).until(ec.presence_of_element_located((By.XPATH, xp)))
            self.driver.execute_script("window.stop();")
            th = th.value_of_css_property('background-image')
            th = th.strip("url(").strip(")")
            e.set_thumbnail(url=th.strip('"'))
        except Exception as e:
            print("Bare except - get_html")
            print(e.__name__)
            print(e)
            print("Please fix.")
            pass

        e.url = url
        t = html.fromstring(self.driver.page_source)
        return t, e

    def parse_table(self, url):
        url += "/standings/"
        self.driver.get(url)

        try:
            xp = './/div[@class="glib-stats-box-table-overall"]'
            tbl = WebDriverWait(self.driver, 10).until(ec.presence_of_element_located((By.XPATH, xp)))
            self.driver.execute_script("window.stop();")
            # Kill cookie disclaimer.
            try:
                z = self.driver.find_element_by_xpath(".//span[@class='button cookie-law-accept']")
                z.click()
            except (NoSuchElementException, ElementNotInteractableException):
                pass

            self.driver.execute_script("arguments[0].scrollIntoView();", tbl)
            im = Image.open(BytesIO(tbl.screenshot_as_png))
            output = BytesIO()
            im.save(output, "PNG")
            output.seek(0)
            df = discord.File(output, filename="table.png")
            return df
        except TimeoutException:
            print("Timed out during parse_table..")
        except Exception as e:
            print("parse_table")
            print(e.__name__)
            print(e)

    def parse_results(self, url, au):
        url += "/results"
        t, e = self.get_html(url)
        matches = []
        results = t.xpath(".//div[contains(@class,'sportName soccer')]/div")

        title = "".join(t.xpath('.//div[@class="teamHeader__name"]/text()')).strip()
        e.title = f"≡ Results for {title}"
        for i in results:
            d = "".join(i.xpath('.//div[@class="event__time"]//text()')).strip("Pen")
            if not d:
                continue
            try:
                d = datetime.datetime.strptime(d, "%d.%m. %H:%M")
                d = d.replace(year=datetime.datetime.now().year)
                d = datetime.datetime.strftime(d, "%a %d %b")
            except ValueError:
                # Fix older than a year games.
                d = datetime.datetime.strptime(d, "%d.%m.%Y")
                d = datetime.datetime.strftime(d, "%d/%m/%Y")

            # Score
            h, a = i.xpath('.//div[contains(@class,"event__scores")]/span/text()')
            sc = f"{h} - {a}"

            # Teams
            ht, at = i.xpath('.//div[contains(@class,"event__participant")]/text()')
            ht, at = ht.strip(), at.strip()

            if "(" in ht:
                ht = ht.split('(')[0].strip()
            if "(" in at:
                at = at.split('(')[0].strip()

            if "/team/" in url:
                # if we're actually the away team.
                if title in ht:
                    wh, op = "A", at
                    w = "L" if h < a else "D" if h == a else "W"
                else:
                    wh, op = "H", ht
                    w = "W" if h < a else "D" if h == a else "L"

                matches.append((f"`{wh}: {d}`", f"`{w}: {sc} v {op}`"))
            else:
                matches.append((f"`{d}`", f"`{ht} {sc} {at}`"))

        embeds = build_embeds(au, e, matches, "Result")
        return embeds

    def parse_fixtures(self, url, au):
        url = f"{url}/fixtures"
        t, e = self.get_html(url)

        title = "".join(t.xpath('.//div[@class="teamHeader__name"]/text()')).strip()
        e.title = f"≡ Fixtures for {title}"

        fixtures = t.xpath(".//div[contains(@class,'sportName soccer')]/div")
        matches = []
        for i in fixtures:
            d = "".join(i.xpath('.//div[@class="event__time"]//text()'))

            if not d:
                continue

            try:
                d = datetime.datetime.strptime(d, "%d.%m. %H:%M")
                d = d.replace(year=datetime.datetime.now().year)

                if d.month < datetime.datetime.now().month:
                    d = d.replace(year=datetime.datetime.now().year + 1)
                elif d.month == datetime.datetime.now().month:
                    if d.day < datetime.datetime.now().day:
                        d = d.replace(year=datetime.datetime.now().year + 1)

                d = datetime.datetime.strftime(d, "%a %d %b: %H:%M")
            except ValueError:  # Fuck this cant be bothered to fix it.
                d = "Tue 31 Feb: 15:00"

            tv = i.xpath(".//div[contains(@class,'tv')]")
            if tv:
                tv = i.xpath("./@id")[0].split("_")[-1]
                tv = f" [`📺`](http://www.flashscore.com/match/{tv}/)"
            else:
                tv = ""

            h, a = i.xpath('.//div[contains(@class,"event__participant")]/text()')

            if "team" in url:
                op, wh = h, "A"
                if title in op:
                    op, wh = a, "H"
                matches.append((f"`{d}`", f"`{wh}: {op}`{tv}"))
            else:
                matches.append((f"`{d}`", f"`{h} v {a}` {tv}"))
        embeds = build_embeds(au, e, matches, "Fixture")
        return embeds

    def parse_bracket(self, bracket):
        self.driver.get(bracket)

        xp = './/div[@class="viewport"]'
        # Generate our base image.
        scrolling = True
        images = []
        while scrolling:
            bkt = self.driver.find_element_by_xpath(xp)
            # Try to delete dem ugly arrows.
            try:
                self.driver.execute_script(
                    "document.getElementsByClassName('playoff-scroll-button')[0].style.display = 'none';")
            except WebDriverException as e:
                print(f"Error'd.\n {e}")
            im = Image.open(BytesIO(bkt.screenshot_as_png))
            images.append(im)

            try:
                z = self.driver.find_element_by_link_text("scroll right »")
                z.click()
            except NoSuchElementException:
                scrolling = False

        width = sum(i.width for i in images)
        height = images[0].height

        # Create new base image and paste old, new.
        canvas = Image.new('RGB', (width, height))
        x = 0
        for i in images:
            canvas.paste(canvas, (x, 0))
            x += i.width

        output = BytesIO()
        canvas.save(output, "PNG")
        output.seek(0)
        df = discord.File(output, filename="bracket.png")
        return df

    def parse_injuries(self, url, au):
        t, e = self.get_html(url)
        url += "/squad"
        self.driver.get(url)
        WebDriverWait(self.driver, 2)

        tree = html.fromstring(self.driver.page_source)
        rows = tree.xpath('.//div[contains(@id,"overall-all-table")]/div[contains(@class,"profileTable__row")]')
        matches = []
        position = ""

        for i in rows:
            pos = "".join(i.xpath('./text()')).strip()
            if pos:
                try:
                    position = pos.rsplit('s')[0]
                except IndexError:
                    position = pos

            injury = "".join(i.xpath('.//span[contains(@class,"absence injury")]/@title'))
            if not injury:
                continue

            player = "".join(i.xpath('.//div[contains(@class,"")]/a/text()'))
            link = "".join(i.xpath('.//div[contains(@class,"")]/a/@href'))
            if link:
                link = "http://www.flashscore.com" + link

            # Put name in the right order.
            try:
                playersplit = player.split(' ', 1)
                player = f"{playersplit[1]} {playersplit[0]}"
            except IndexError:
                pass
            matches.append(f"[{player}]({link}) ({position}): {injury}")
        e.set_footer(text=au)
        title = "".join(t.xpath('.//div[@class="teamHeader__name"]/text()')).strip()
        e.title = f"Injuries for {title}"
        e.url = url
        if matches:
            e.description = "\n".join(matches)
        else:
            e.description = "No injuries found!"
        return e

    def parse_scorers(self, url, au):
        t, e = self.get_html(url)

        if "team" in url:
            # For individual Team
            scorerdict = {}
            team = "".join(t.xpath('.//div[@class="team-name"]/text()'))
            e.title = f"≡ Top Scorers for {team}"
            players = t.xpath('.//table[contains(@class,"squad-table")]/tbody/tr')
            for i in players:
                p = "".join(i.xpath('.//td[contains(@class,"player-name")]/a/text()'))

                if not p:
                    continue
                g = "".join(i.xpath('.//td[5]/text()'))
                if g == "0" or not g:
                    continue
                link = "".join(i.xpath('.//td[contains(@class,"player-name")]/a/@href'))
                if g in scorerdict.keys():
                    scorerdict[g].append(f"[{' '.join(p.split(' ')[::-1])}](http://www.flashscore.com{link})")
                else:
                    scorerdict.update({g: [f"[{' '.join(p.split(' ')[::-1])}](http://www.flashscore.com{link})"]})
            sclist = [[f"{k} : {i}" for i in v] for k, v in scorerdict.items()]
            sclist = [i for sublist in sclist for i in sublist]
            tmlist = [f"[{team}]({url})" for i in sclist]
        else:
            # For cross-league.
            sclist = []
            tmlist = []
            comp = "".join(t.xpath('.//div[@class="tournament-name"]/text()'))
            e.title = f"≡ Top Scorers for {comp}"
            # Re-scrape!

            url += "/standings/"
            self.driver.get(url)
            WebDriverWait(self.driver, 2)
            try:
                x = self.driver.find_element_by_link_text("Top Scorers")
                x.click()
                players = self.driver.find_element_by_id("table-type-10")
                t = players.get_attribute('innerHTML')
                tree = html.fromstring(t)
                players = tree.xpath('.//tbody/tr')
                for i in players:
                    p = "".join(i.xpath('.//td[contains(@class,"player_name")]//a/text()'))
                    p = ' '.join(p.split(' ')[::-1])
                    if not p:
                        continue
                    pl = "".join(i.xpath(
                        './/td[contains(@class,"player_name")]/span[contains(@class,"team_name_span")]/a/@onclick'))
                    pl = pl.split("'")[1]
                    pl = f"http://www.flashscore.com{pl}"
                    g = "".join(i.xpath('.//td[contains(@class,"goals_for")]/text()'))
                    if g == "0":
                        continue
                    tm = "".join(i.xpath('.//td[contains(@class,"team_name")]/span/a/text()'))
                    tml = "".join(i.xpath('.//td[contains(@class,"team_name")]/span/a/@onclick'))
                    tml = tml.split("\'")[1]
                    tml = f"http://www.flashscore.com{tml}"
                    sclist.append(f"{g} [{p}]({pl})")
                    tmlist.append(f"[{tm}]({tml})")
            except WebDriverException:
                self.driver.save_screenshot('scorers_fail.png')

        z = list(zip(sclist, tmlist))
        # Make Embeds.
        embeds = []
        p = [z[i:i + 10] for i in range(0, len(z), 10)]
        pages = len(p)
        count = 1
        for i in p:
            j = "\n".join([j for j, k in i])
            k = "\n".join([k for j, k in i])
            e.add_field(name="Goals / Player", value=j, inline=True)
            e.add_field(name="Team", value=k, inline=True)
            iu = "http://pix.iemoji.com/twit33/0056.png"
            e.set_footer(text=f"Page {count} of {pages} ({au})", icon_url=iu)
            te = deepcopy(e)
            embeds.append(te)
            e.clear_fields()
            count += 1

        return embeds

    async def _search(self, ctx, m, qry, preferred=None, mode=None):
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
            # TODO: Paginate.
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
        await m.edit(content=f"Grabbing data...")

        try:
            await match.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        return f'https://www.flashscore.com/{resdict[mcontent]["url"]}'

    @commands.command()
    async def table(self, ctx, *, qry: commands.clean_content = None):
        """ Get table for a league """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            url = await self._search(ctx, m, qry, preferred="league")
            if url is None:
                return  # rip.

            await m.edit(content=f"Grabbing table from <{url}>...")
            p = await self.bot.loop.run_in_executor(None, self.parse_table, url)
            try:
                await ctx.send(file=p)
            except discord.HTTPException:
                await ctx.send(f"Failed to grab table from <{url}>")

    @commands.command()
    async def bracket(self, ctx, *, qry: commands.clean_content = None):
        """ Get btacket for a tournament """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            url = await self._search(ctx, m, qry, preferred="league")
            if url is None:
                return  # rip.

            m = await m.edit(content=f'Grabbing competition bracket for {qry}...')
            p = await self.bot.loop.run_in_executor(None, self.parse_bracket, url)

            try:
                await ctx.send(file=p)
            except discord.HTTPException:
                await m.edit(content=f"Failed to grab table from <{url}>")
            else:
                await m.delete()

    @commands.command(aliases=["fx"])
    async def fixtures(self, ctx, *, qry: commands.clean_content = None):
        """ Displays upcoming fixtures for a team or league.
            Navigate with reactions.
        """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            url = await self._search(ctx, m, qry, preferred="team")
            if url is None:
                return  # rip.

            await m.edit(content=f'Grabbing fixtures data from <{url}>...')
            pages = await self.bot.loop.run_in_executor(None, self.parse_fixtures, url, ctx.author.name)
            await paginate(ctx, pages)

    @commands.command(aliases=['sc'])
    async def scorers(self, ctx, *, qry: commands.clean_content = None):
        """ Displays top scorers for a team or league.
            Navigate with reactions.
        """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            url = await self._search(ctx, m, qry, preferred="team")
            if url is None:
                return  # rip.

            await m.edit(content=f'Grabbing Top Scorers scorers data from <{url}>...')
            pages = await self.bot.loop.run_in_executor(None, self.parse_scorers, url, ctx.author.name)

            await paginate(ctx, pages)

    @commands.command(aliases=["rx"])
    async def results(self, ctx, *, qry: commands.clean_content = None):
        """ Displays previous results for a team or league.
            Navigate with reactions.
        """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            url = await self._search(ctx, m, qry, preferred="team")
            if url is None:
                return  # rip.

            await m.edit(content=f'Grabbing results data from <{url}>...')
            pages = await self.bot.loop.run_in_executor(None, self.parse_results, url, ctx.author.name)

            await paginate(ctx, pages)

    @commands.command(aliases=["suspensions"])
    async def injuries(self, ctx, *, qry: commands.clean_content = None):
        """ Get a team's current injuries """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            url = await self._search(ctx, m, qry, preferred="team")
            if url is None:
                return  # rip.

            await m.edit(content=f'Grabbing injury data from <{url}>...')
            e = await self.bot.loop.run_in_executor(None, self.parse_injuries, url, ctx.author.name)
            await ctx.send(embed=e)

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
            url = await self._search(ctx, m, qry, mode=mode)
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
