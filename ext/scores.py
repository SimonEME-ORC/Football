import asyncio
from collections import defaultdict

import discord
from discord.ext import commands, tasks

# Web Scraping
from lxml import html
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec

# Data manipulation
import datetime
import json

from ext.utils.selenium_driver import spawn_driver

default_leagues = [
    "WORLD: Friendly international",
    "WORLD: Friendly International",
    "EUROPE: Champions League",
    "EUROPE: Euro",
    "ENGLAND: Premier League",
    "ENGLAND: Championship",
    "ENGLAND: League One",
    "ENGLAND: FA Cup",
    "ENGLAND: EFL Cup",
    "FRANCE: Ligue 1",
    "FRANCE: Coupe de France",
    "GERMANY: Bundesliga",
    "ITALY: Serie A",
    "NETHERLANDS: Eredivisie",
    "SCOTLAND: Premiership",
    "SPAIN: Copa del Rey",
    "SPAIN: LaLiga",
    "USA: MLS"
]

# TODO: re-code vidi-printer


class ScoresChannel(commands.Cog):
    """ Live Scores channel module """

    def __init__(self, bot):
        self.whitelist_cache = defaultdict(list)
        self.channel_cache = defaultdict(list)
        self.bot = bot
        self.bot.live_games = {}
        self.msg_dict = {}
        self.bot.loop.create_task(self.update_cache())
        self.bot.scores = self.score_loop.start()
        self.driver = None

    async def update_cache(self):
        # Grab most recent data.
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            channels = await connection.fetch("""SELECT * FROM scores_channels""")
            whitelists = await connection.fetch("""SELECT * FROM scores_channels_leagues""")
        await self.bot.db.release(connection)

        # TODO: Make a better SQL statement to extract this and merge into a single cache.
        
        # Clear out our cache.
        self.channel_cache.clear()
        self.whitelist_cache.clear()
        
        # Repopulate.
        for r in channels:
            self.channel_cache[r["guild_id"]].append(r["channel_id"])
        for r in whitelists:
            self.whitelist_cache[r["channel_id"]].append(r["league"])

    def cog_unload(self):
        self.bot.scores.cancel()

    # Core Loop
    @tasks.loop(minutes=1)
    async def score_loop(self):
        """ Score Checker Loop """
        try:
            games = await self.bot.loop.run_in_executor(None, self.fetch_data)
        except Exception as e:
            print("Exception in score_loop.")
            print(type(e).__name__)
            print(e.args)
        else:
            await self.write_raw(games)
            # Iterate: Check vs each server's individual config settings
            await self.localise_data()
    
            # Send message to server.
            try:
                await self.spool_messages()
            except discord.ConnectionClosed:
                pass

    @score_loop.before_loop
    async def before_score_loop(self):
        await self.bot.wait_until_ready()
        await self.update_cache()
        self.driver = await self.bot.loop.run_in_executor(None, spawn_driver)
        self.driver.get("http://www.flashscore.com/")
        xp = ".//div[@class='sportName soccer']"
        WebDriverWait(self.driver, 10).until(ec.visibility_of_element_located((By.XPATH, xp)))
        
    @score_loop.after_loop
    async def after_score_loop(self):
        self.driver.quit()
        
    def fetch_data(self):
        xp = ".//div[@class='sportName soccer']"
        element = self.driver.find_element_by_xpath(xp)
        
        fixture_list = element.get_attribute('innerHTML')
        fixture_list = html.fromstring(fixture_list)
        fixture_list = fixture_list.xpath("./div")
        games = {}
        lg = "Unknown League"
        for i in fixture_list:
            # Header rows do not have IDs
            if not i.xpath('.//@id'):
                lg = ": ".join(i.xpath('.//span//text()'))
                games[lg] = {}
            else:
                game_id = ''.join(i.xpath('.//@id'))
                games[lg][game_id] = {}

                # Time
                time = i.xpath('.//div[contains(@class,"event__stage--block")]//text()')
                if not time:
                    time = i.xpath('.//div[contains(@class,"event__time")]//text()')

                time = "".join(time).replace('FRO', "").strip("\xa0").strip()
                if "Finished" in time:
                    time = "FT"
                elif "After ET" in time:
                    time = "AET"
                elif "Half Time" in time:
                    time = "HT"
                elif "Postponed" in time:
                    time = "PP"
                elif ":" not in time:
                    time += "'"
                games[lg][game_id]["time"] = time
                games[lg][game_id]["home_team"] = "".join(i.xpath('.//div[contains(@class,"home")]//text()')).strip()
                games[lg][game_id]["away_team"] = "".join(i.xpath('.//div[contains(@class,"away")]//text()')).strip()
                # games[lg][game_id]["aggregate"] = "".join(i.xpath('.//div[@class="event__part"]//text()')).strip()
                score = "".join(i.xpath('.//div[contains(@class,"event__scores")]//text()')).strip()
                score = "vs" if not score else score
                games[lg][game_id]["score"] = score
        return games

    async def write_raw(self, games):
        for league, data in games.items():
            # i is a game_id
            raw = f"**{league}**\n"  # used by live-score channels
            raw_with_link = f"**{league}**\n"  # used by scores command
            for k, v in data.items():
                time = f"{data[k]['time']}"

                time = "✅ FT" if time == "FT" else time
                time = "✅ AET" if time == "AET" else time
                time = "⏸️ HT" if time == "HT" else time
                time = "🚫 PP" if time == "PP" else time
                time = f"🔜 {time}" if ":" in time else time
                time = f"⚽ {time}" if "'" in time else time

                home = data[k]["home_team"]
                away = data[k]["away_team"]
                score = data[k]["score"]
                url = "http://www.flashscore.com/" + k.split('_')[-1]

                raw += f"`{time}` {home} {score} {away}\n"
                raw_with_link += f"`{time}` [{home} {score} {away}]({url})\n"

            games[league]["raw"] = raw
            games[league]["raw_with_link"] = raw_with_link
        self.bot.live_games = games

    async def localise_data(self):
        for g, cl in self.channel_cache.items():
            for c in cl:
                leagues = self.whitelist_cache[c]
                if not leagues:
                    leagues = default_leagues
                
                if c not in self.msg_dict:
                    self.msg_dict[c] = {}
                    self.msg_dict[c]["msg_list"] = []

                self.msg_dict[c]["raw_data"] = []

                today = datetime.datetime.now().strftime(
                    "Live Scores for **%a %d %b %Y** (last updated at **%H:%M:%S**)\n\n")
                rawtext = today
                for j in leagues:
                    if j not in self.bot.live_games:
                        continue
                    if len(rawtext) + len(self.bot.live_games[j]["raw"]) < 1999:
                        rawtext += self.bot.live_games[j]["raw"] + "\n"
                    else:
                        self.msg_dict[c]["raw_data"] += [rawtext]
                        rawtext = self.bot.live_games[j]["raw"] + "\n"

                    if rawtext == today:
                        rawtext += "Either there's no games today, something broke, or you have your list of leagues " \
                                   "set very small\n\n You can add more leagues with `ls add league_name`."
                self.msg_dict[c]["raw_data"] += [rawtext]

    async def spool_messages(self):
        for c, v in self.msg_dict.items():
            # Create messages if none exist.
            # Or if a different number of messages is required.
            if not self.msg_dict[c]["msg_list"] or \
                    len(self.msg_dict[c]["msg_list"]) != len(self.msg_dict[c]["raw_data"]):
                ch = self.bot.get_channel(c)
                try:
                    await ch.purge()
                except discord.Forbidden:
                    await ch.send(
                        "Unable to clean previous messages, please make sure I have manage_messages permissions.")
                except AttributeError:
                    print(f'Live Scores Loop: Invalid channel: {c}')
                    continue
                for d in self.msg_dict[c]["raw_data"]:
                    # Append message ID to our list
                    try:
                        m = await ch.send(d)
                        self.msg_dict[c]["msg_list"].append(m)
                    except (discord.NotFound, discord.Forbidden) as e:
                        print("-- error sending message to scores channel --")
                        print(d)
                        print(e)
            else:
                # Edit message pairs if pre-existing.
                tuples = list(zip(self.msg_dict[c]["msg_list"], self.msg_dict[c]["raw_data"]))
                for x, y in tuples:
                    try:
                        await x.edit(content=y)
                    except (discord.NotFound, discord.Forbidden) as e:
                        print("-- error editing scores channel --")
                        print(x)
                        print(e)

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def ls(self, ctx, channel: discord.TextChannel = None):
        """ View the status of your live scores channels. """
        e = discord.Embed(color=0x0000ff)
        e.set_thumbnail(url=ctx.me.avatar_url)
        e.title = "Live-scores channel config"
        e.description = ""

        score_channels = self.channel_cache[ctx.guild.id]
        if not score_channels:
            return await ctx.send(f"{ctx.guild.name} has no live-scores channel set.")

        if len(score_channels) != 1:
            if not channel:
                channels = ", ".join([self.bot.get_channel(i).mention for i in score_channels])
                return await ctx.send(
                    f"{ctx.guild.name} currently has {len(score_channels)} score channels set: {channels}\n"
                    f"Use {ctx.prefix}ls #channel to get the status of a specific one.")
            elif channel not in score_channels:
                await ctx.send(f'{channel.mention} is not set as one of your score channels.')
        else:
            channel = score_channels[0]

        e.add_field(name="Channel", value=self.bot.get_channel(channel).mention)
        await ctx.send(embed=e)

    @ls.command(usage="ls create")
    @commands.has_permissions(manage_channels=True)
    async def create(self, ctx):
        """ Create a live-scores channel for your server. """
        try:
            ow = {ctx.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True,
                                                      embed_links=True, read_message_history=True),
                  ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False,
                                                                      read_message_history=True)
                  }
            reason = f'{ctx.author} (ID: {ctx.author.id}) creating a live-scores channel.'
            ch = await ctx.guild.create_text_channel(name="live-scores", overwrites=ow, reason=reason)
        except discord.Forbidden:
            return await ctx.send(
                "Unable to create live-scores channel. Please make sure I have the manage_channels permission.")
        except discord.HTTPException:
            return await ctx.send(
                "An unknown error occured trying to create the live-scores channel, please try again later.")

        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute(""" 
                INSERT INTO scores_channels (guild_id,channel_id) VALUES ($1,$2)
                """, ctx.guild.id, ch.id)

        await ctx.send(f"The {ch} channel was created succesfully.")
        await self.bot.db.release(connection)
        await self.update_cache()

    # Delete from Db on delete..
    @commands.Cog.listener()
    async def on_channel_delete(self, channel):
        if channel.id in self.channel_cache:
            connection = await self.bot.db.acquire()
            await connection.execute("""
                DELETE FROM scores_channels WHERE channel_id = $1
                """, channel.id)
            await self.bot.db.release(connection)
            await self.update_cache()
    
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        if guild.id in self.channel_cache:
            await self.update_cache()

    async def _pick_channels(self, ctx, channels):
        # Assure guild has transfer channel.
        guild_cache = self.channel_cache[ctx.guild.id]
        if not guild_cache:
            await ctx.send(f'{ctx.guild.name} does not have any live scores channels set.')
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
                    m = await ctx.send(
                        f"{ctx.guild.name} has multiple live-score channels set: ({mention_list}), please specify "
                        f"which one(s) to check or modify.")
                    try:
                        channels = await self.bot.wait_for("message", check=check, timeout=30)
                        channels = channels.channel_mentions
                        await m.delete()
                    except asyncio.TimeoutError:
                        await m.edit(
                            content="Timed out waiting for you to reply with a channel list. No channels were "
                                    "modified.")
                        channels = []
        return channels

    @ls.command(usage="ls add <(Optional: #channel #channel2)> <search query>")
    @commands.has_permissions(manage_channels=True)
    async def add(self, ctx, channels: commands.Greedy[discord.TextChannel], *, qry: commands.clean_content = None):
        """ Add a league to your live-scores channel """
        channels = await self._pick_channels(ctx, channels)

        if not channels:
            return  # rip

        if qry is None:
            return await ctx.send("Specify a competition name to search for.")

        m = await ctx.send(f"Searching for {qry}...")
        res = await self._search(ctx, m, qry)

        if not res:
            return await ctx.send("Didn't find any leagues. Your channels were not modified.")

        connection = await self.bot.db.acquire()
        replies = []
        async with connection.transaction():
            for c in channels:
                if c.id not in self.channel_cache[ctx.guild.id]:
                    replies.append(f'🚫 {c.mention} is not set as a scores channel.')
                    continue

                leagues = self.whitelist_cache[c.id]
                if not leagues:
                    leagues = default_leagues.copy()

                if res in leagues:
                    replies.append(f"⚠️**{res}** was already in {c.mention}'s tracked leagues.")
                    continue
                else:
                    leagues.append(res)

                async with connection.transaction():
                    for lg in leagues:
                        await connection.execute(""" 
                            INSERT INTO scores_channels_leagues (league,channel_id) 
                            VALUES ($1,$2)
                            ON CONFLICT DO NOTHING
                            """, lg, c.id)
                leagues = ', '.join(leagues)
                replies.append(
                    f"✅ **{res}** added to the tracked leagues for {c.mention},"
                    f" the new tracked leagues list is: {leagues}")
        await self.bot.db.release(connection)
        await self.update_cache()

        await ctx.send("\n".join(replies))

    @ls.group(name="remove", aliases=["del", "delete"],
              usage="ls remove <(Optional: #channel #channel2)> <Country: League Name>")
    @commands.has_permissions(manage_channels=True)
    async def _remove(self, ctx, channels: commands.Greedy[discord.TextChannel], *, target: commands.clean_content):
        """ Remove a competition from your live-scores channels """
        channels = await self._pick_channels(ctx, channels)

        if not channels:
            return  # rip

        replies = []
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            for c in channels:
                if c.id not in self.channel_cache[ctx.guild.id]:
                    replies.append(f'{c.mention} is not set as a scores channel.')
                    continue
                leagues = self.whitelist_cache[c.id]
                if not leagues:
                    leagues = default_leagues.copy()
                    leagues.remove(target)
                    for lg in leagues:
                        await connection.execute("""
                            INSERT INTO scores_channels_leagues (league,channel_id) VALUES ($1,$2)
                            ON CONFLICT DO NOTHING
                        """, lg, c.id)
                elif target not in leagues:
                    replies.append(f"🚫 **{target}** was not in {c.mention}'s tracked leagues.")
                    continue
                else:
                    await connection.execute("""
                        DELETE FROM scores_channels_leagues WHERE (league,channel_id) = ($1,$2)
                    """, target, c.id)

                replies.append(f"✅ **{target}** was deleted from the tracked leagues for {c.mention}.")
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send('\n'.join(replies))

    @ls.command(usage="ls remove <(Optional: #channel #channel2)>")
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx, channels: commands.Greedy[discord.TextChannel]):
        """ Reset live-scores channels to the list of default competitions """
        channels = await self._pick_channels(ctx, channels)

        if not channels:
            return  # rip

        connection = await self.bot.db.acquire()
        replies = []
        async with connection.transaction():
            for c in channels:
                if c.id not in self.channel_cache:
                    replies.append(f"🚫 {c.mention} was not set as a scores channel.")
                    continue
                if c.id not in self.whitelist_cache:
                    replies.append(f"⚠️ {c.mention} is already using the default leagues.")
                    continue
                async with connection.transaction():
                    await connection.execute(""" 
                        DELETE FROM scores_channels_leagues WHERE channel_id = $1
                    """, c.id)
                replies.append(f"✅ {c.mention} had it's tracked leagues reset to the default.")

        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send("\n".join(replies))

    async def _search(self, ctx, m, qry):
        # aiohttp lookup for json.
        qry = qry.replace("'", "")

        qryurl = f"https://s.flashscore.com/search/?q={qry}&l=1&s=1&f=1%3B1&pid=2&sid=1"
        async with self.bot.session.get(qryurl) as resp:
            res = await resp.text()
            res = res.lstrip('cjs.search.jsonpCallback(').rstrip(");")
            res = json.loads(res)

        res_dict = {}
        key = 0
        # Remove irrelevant.
        for i in res["results"]:
            # Format for LEAGUE
            if i["participant_type_id"] == 0:
                # Sample League URL: https://www.flashscore.com/soccer/england/premier-league/
                res_dict[str(key)] = {"Match": i['title']}
                key += 1

        if not res_dict:
            return await m.edit(content=f"No results for query: {qry}")

        if len(res_dict) == 1:
            try:
                await m.delete()
            except discord.Forbidden:
                pass
            return res_dict["0"]["Match"]

        id_strings = ""
        for i in res_dict:
            id_strings += f"{i}: {res_dict[i]['Match']}\n"

        try:
            await m.edit(content=f"Please type matching id: ```{id_strings}```")
        except discord.HTTPException:
            # TODO: Paginate.
            return await m.edit(content=f"Too many matches to display, please be more specific.")

        def check(message):
            if message.author.id == ctx.author.id and message.content in res_dict:
                return True

        try:
            match = await self.bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            return await m.delete()

        match_content = match.content
        try:
            await m.delete()
            await match.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        return res_dict[match_content]["Match"]

def setup(bot):
    bot.add_cog(ScoresChannel(bot))
