import asyncio
from collections import defaultdict
from copy import deepcopy

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

from ext.utils.embed_utils import paginate
from ext.utils.selenium_driver import spawn_driver

default_leagues = [
    "WORLD: Friendly international",
    "EUROPE: Champions League",
    "EUROPE: Euro",
    "EUROPE: Europa League",
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


# TODO: Migrate to FlashScoreFixture
# TODO: re-code vidi-printer

class Scores(commands.Cog):
    """ Live Scores channel module """
    
    def __init__(self, bot):
        self.cache = defaultdict(list)
        self.bot = bot
        self.bot.live_games = {}
        self.msg_dict = {}
        self.bot.loop.create_task(self.update_cache())
        self.bot.scores = self.score_loop.start()
        self.driver = None
   
    def cog_unload(self):
        self.bot.scores.cancel()
    
    async def update_cache(self):
        # Grab most recent data.
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            channels = await connection.fetch("""
            SELECT guild_id, scores_channels.channel_id, league
            FROM scores_channels
            LEFT OUTER JOIN scores_leagues
            ON scores_channels.channel_id = scores_leagues.channel_id""")
        await self.bot.db.release(connection)
        
        # Clear out our cache.
        self.cache.clear()
        
        # Repopulate.
        for r in channels:
            self.cache[(r["guild_id"], r["channel_id"])].append(r["league"])
    
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
                lg = ": ".join(i.xpath('.//span//text()')).split(" - ")[0]
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
                elif "Extra Time" in time:
                    time = time.replace('Extra Time', "ET ") + "'"
                elif "Break Time" in time:
                    time = time.replace('Break Time', "FT, ET Soon") + "'"
                elif "After ET" in time:
                    time = "AET"
                elif "Half Time" in time:
                    time = "HT"
                elif "Postponed" in time:
                    time = "PP"
                elif "After Pen" in time:
                    time = "After Pens"
                elif ":" not in time:
                    time += "'"
                games[lg][game_id]["time"] = time
                games[lg][game_id]["home_team"] = "".join(i.xpath('.//div[contains(@class,"home")]//text()')).strip()
                games[lg][game_id]["home_team"] = games[lg][game_id]["home_team"].replace('GOAL', " **GOAL** ")
                games[lg][game_id]["away_team"] = "".join(i.xpath('.//div[contains(@class,"away")]//text()')).strip()
                games[lg][game_id]["away_team"] = games[lg][game_id]["away_team"].replace('GOAL', " **GOAL** ")
                # games[lg][game_id]["aggregate"] = "".join(i.xpath('.//div[@class="event__part"]//text()')).strip()
                score = "".join(i.xpath('.//div[contains(@class,"event__scores")]//text()')).strip()
                score = "vs" if not score else score.replace("(", " (")
                games[lg][game_id]["score"] = score
        return games
    
    async def write_raw(self, games):
        for league, data in games.items():
            raw = f"**{league}**\n"  # used by live-score channels
            raw_with_link = f"**{league}**\n"  # used by scores command
            for k, v in data.items():  # k is a game_id.
                time = f"{data[k]['time']}"
                
                time = "🟢 After Pens" if time == "After Pens" else time
                time = "🟢 FT" if time == "FT" else time
                time = "🟢 AET" if time == "AET" else time
                time = "🟡️ HT" if time == "HT" else time
                time = "🚫 PP" if time == "PP" else time
                time = f"🔵 {time}" if ":" in time else time
                time = f"⚽ {time}" if "'" in time else time
                
                home = data[k]["home_team"]
                away = data[k]["away_team"]
                score = data[k]["score"]
                url = "http://www.flashscore.com/match/" + k.split('_')[-1]
                
                raw += f"`{time}` {home} {score} {away}\n"
                raw_with_link += f"`{time}` [{home} {score} {away}]({url})\n"
            
            games[league]["raw"] = raw
            games[league]["raw_with_link"] = raw_with_link
        self.bot.live_games = games
    
    async def localise_data(self):
        for (guild_id, channel_id), whitelist in self.cache.items():
            if channel_id not in self.msg_dict:
                self.msg_dict[channel_id] = {}
                self.msg_dict[channel_id]["msg_list"] = []
            
            self.msg_dict[channel_id]["raw_data"] = []
            
            today = datetime.datetime.now().strftime(
                "Live Scores for **%a %d %b %Y** (last updated at **%H:%M:%S**)\n\n")
            output = today
            for league in whitelist:
                if league not in self.bot.live_games:
                    continue

                if len(output) + len(self.bot.live_games[league]["raw"]) < 1999:
                    output += self.bot.live_games[league]["raw"] + "\n"
                else:
                    self.msg_dict[channel_id]["raw_data"] += [output]
                    output = self.bot.live_games[league]["raw"] + "\n"
            
            if output == today:
                output += "No games found for your tracked leagues today!" \
                          "\n\nYou can add more leagues with `.tb ls add league_name`, or reset to the default leagues"\
                          "with `.tb ls default`.\nTo find out which leagues currently have games, use `.tb scores`"
            self.msg_dict[channel_id]["raw_data"] += [output]
    
    async def spool_messages(self):
        for channel_id in self.msg_dict:
            # Create messages if none exist.
            # Or if a different number of messages is required.
            if not self.msg_dict[channel_id]["msg_list"] or \
                    len(self.msg_dict[channel_id]["msg_list"]) != len(self.msg_dict[channel_id]["raw_data"]):
                channel = self.bot.get_channel(channel_id)
                try:
                    await channel.purge()
                except discord.Forbidden:
                    await channel.send(
                        "Unable to clean previous messages, please make sure I have manage_messages permissions.")
                except AttributeError:
                    print(f'Live Scores Loop: Invalid channel: {channel_id}')
                    continue
                for d in self.msg_dict[channel_id]["raw_data"]:
                    # Append message ID to our list
                    try:
                        m = await channel.send(d)
                        self.msg_dict[channel_id]["msg_list"].append(m)
                    except discord.Forbidden:
                        continue  # This is your problem, not mine.
                    except discord.NotFound:
                        # This one, on the other hand, I probably fucked up.
                        print(f"Couldn't find livescores channel {channel_id}")
                    except Exception as e:
                        print("-- error sending message to scores channel --")
                        print(channel.id)
                        print(e)
                    
            else:
                # Edit message pairs if pre-existing.
                tuples = list(zip(self.msg_dict[channel_id]["msg_list"], self.msg_dict[channel_id]["raw_data"]))
                for x, y in tuples:
                    try:
                        if x is not None:
                            if x.content != y:
                                await x.edit(content=y)
                    except (discord.NotFound, discord.Forbidden):
                        self.msg_dict[channel_id]['msg_list'] = [i if i != x else None for
                                                                 i in self.msg_dict[channel_id]['msg_list']]
                        pass

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

    # Delete from Db on delete..
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if (channel.guild.id, channel.id) in self.cache:
            print(f"A live scores channel (Guild: {channel.guild.id}, Channel: {channel.id} was deleted.")
            connection = await self.bot.db.acquire()
            await connection.execute(""" DELETE FROM scores_channels WHERE channel_id = $1 """, channel.id)
            await self.bot.db.release(connection)
            await self.update_cache()
            self.msg_dict.pop(channel.id)
    
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        if guild.id in [i[0] for i in self.cache]:
            await self.update_cache()
    
    async def _pick_channels(self, ctx, channels):
        # Assure guild has transfer channel.
        if ctx.guild.id not in [i[0] for i in self.cache]:
            await ctx.send(f'{ctx.guild.name} does not have any live scores channels set.')
            channels = []
        else:
            # Channel picker for invoker.
            def check(message):
                return ctx.author.id == message.author.id and message.channel_mentions
            
            # If no Query provided we check current whitelists.
            guild_channels = [self.bot.get_channel(i[1]) for i in self.cache if i[0] == ctx.guild.id]
            if not channels:
                channels = guild_channels
            if ctx.channel in guild_channels:
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

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def ls(self, ctx):
        """ View the status of your live scores channels. """
        e = discord.Embed(color=0x2ecc71)
        e.set_thumbnail(url=ctx.me.avatar_url)
        e.title = f"{ctx.guild.name} Live Scores channels"
    
        score_channels = [self.bot.get_channel(i[1]) for i in self.cache if ctx.guild.id in i]
        if not score_channels:
            return await ctx.send(f"{ctx.guild.name} has no live-scores channel set.")
    
        embeds = []
        for i in score_channels:
            e.description = f'{i.mention}'
            # Warn if they fuck up permissions.
            if not ctx.me.permissions_in(i).send_messages:
                e.description += "```css\n[WARNING]: I do not have send_messages permissions in that channel!"
            leagues = self.cache[(ctx.guild.id, i.id)]
            if leagues != [None]:
                leagues.sort()
                leagues = "```yaml\n" + "\n".join(leagues) + "```"
                e.add_field(name="This channel's Tracked Leagues", value=leagues)
            embeds.append(deepcopy(e))
            e.clear_fields()
        await paginate(ctx, embeds)

    @ls.command(usage="ls create (Optional: Channel-name)")
    @commands.has_permissions(manage_channels=True)
    async def create(self, ctx, *, name=None):
        """ Create a live-scores channel for your server. """
        try:
            ow = {ctx.me: discord.PermissionOverwrite(read_messages=True, send_messages=True,
                                                      manage_messages=True, read_message_history=True),
                  ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False,
                                                                      read_message_history=True)}
            reason = f'{ctx.author} (ID: {ctx.author.id}) created a Toonbot live-scores channel.'
            if name is None:
                name = "live-scores"
            ch = await ctx.guild.create_text_channel(name=name, overwrites=ow, reason=reason)
        except discord.Forbidden:
            return await ctx.send(
                "Unable to create live-scores channel. Please make sure I have the manage_channels permission.")
        except discord.HTTPException:
            return await ctx.send(
                "An unknown error occurred trying to create the live-scores channel, please try again later.")
    
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute(
                """ INSERT INTO scores_channels (guild_id, channel_id) VALUES ($1, $2) """, ctx.guild.id, ch.id)
            for i in default_leagues:
                await connection.execute(
                    """ INSERT INTO scores_leagues (channel_id, league) VALUES ($1, $2) """, ch.id, i)
    
        await ctx.send(f"The {ch.mention} channel was created succesfully.")
        await self.bot.db.release(connection)
        await self.update_cache()

    @commands.has_permissions(manage_channels=True)
    @ls.command(usage="ls add <(Optional: #channel #channel2)> <search query>")
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
                if (ctx.guild.id, c.id) not in self.cache:
                    replies.append(f'🚫 {c.mention} is not set as a scores channel.')
                    continue
                leagues = self.cache[(ctx.guild.id, c.id)]
 
                if leagues != [None]:
                    if res in leagues:
                        replies.append(f"⚠️**{res}** was already in {c.mention}'s tracked leagues.")
                        continue
                    else:
                        leagues.append(res)
                else:
                    leagues = [res]
                
                for league in leagues:
                    await connection.execute("""
                        INSERT INTO scores_leagues (league,channel_id)
                        VALUES ($1,$2)
                        ON CONFLICT DO NOTHING
                        """, league, c.id)
                leagues = ', '.join(leagues)
                replies.append(f"✅ **{res}** added to the tracked leagues for {c.mention},"
                               f" the new tracked leagues list is: ```yaml\n{leagues}```")
        await self.bot.db.release(connection)
        await self.update_cache()
        
        await ctx.send("\n".join(replies))
    
    @ls.group(name="remove", aliases=["del", "delete"],
              usage="ls remove <(Optional: #channel #channel2)> <Country: League Name>",
              invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def _remove(self, ctx, channels: commands.Greedy[discord.TextChannel], *, target: commands.clean_content):
        """ Remove a competition from your live-scores channels """
        channels = await self._pick_channels(ctx, channels)
        
        if not channels:
            return  # rip
        
        # Remove quotes, idiot proofing.
        target = target.strip("'\",")
        
        replies = []
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            for c in channels:
                if c.id not in {i[1] for i in self.cache}:
                    replies.append(f'{c.mention} is not set as a scores channel.')
                    continue
                leagues = self.cache[(ctx.guild.id, c.id)]
                
                if target not in leagues:
                    replies.append(f"🚫 **{target}** was not in {c.mention}'s tracked leagues. (Check "
                                   f"capitalisation?)")
                    continue
                else:
                    await connection.execute("""
                        DELETE FROM scores_leagues WHERE (league,channel_id) = ($1,$2)
                    """, target, c.id)
                leagues = ", ".join(leagues)
                replies.append(f"✅ **{target}** was deleted from the tracked leagues for {c.mention},"
                               f" the new tracked leagues list is: ```yaml\n{leagues}```\n")
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send('\n'.join(replies))
    
    @_remove.command()
    @commands.has_permissions(manage_channels=True)
    async def all(self, ctx, channels: commands.Greedy[discord.TextChannel]):
        """Remove ALL competition from your live-scores channels """
        channels = await self._pick_channels(ctx, channels)
        
        if not channels:
            return  # rip
        
        connection = await self.bot.db.acquire()
        replies = []
        async with connection.transaction():
            for c in channels:
                if c.id not in [i[1] for i in self.cache]:
                    replies.append(f"🚫 {c.mention} was not set as a scores channel.")
                    continue
                async with connection.transaction():
                    await connection.execute("""DELETE FROM scores_leagues WHERE channel_id = $1""", c.id)
                replies.append(f"✅ {c.mention} no longer tracks any leagues. Use `ls reset` to undo this.")
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send("\n".join(replies))
    
    @ls.command(usage="ls remove <(Optional: #channel #channel2)>")
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx, channels: commands.Greedy[discord.TextChannel]):
        """ Reset live-scores channel(s) to the list of default competitions """
        channels = await self._pick_channels(ctx, channels)
        
        if not channels:
            return  # rip
        
        connection = await self.bot.db.acquire()
        replies = []
        async with connection.transaction():
            for c in channels:
                if c.id not in [i[1] for i in self.cache]:
                    replies.append(f"🚫 {c.mention} was not set as a scores channel.")
                    continue
                whitelist = self.cache[(ctx.guild.id, c.id)]
                if whitelist is None:
                    replies.append(f"⚠️ {c.mention} is already using the default leagues.")
                    continue
                async with connection.transaction():
                    await connection.execute("""
                        DELETE FROM scores_leagues WHERE channel_id = $1
                    """, c.id)
                for i in default_leagues:
                    await connection.execute("""INSERT INTO scores_leagues (channel_id, league) VALUES ($1, $2)""",
                                             c.id, i)
                replies.append(f"✅ {c.mention} had it's tracked leagues reset to the default.")
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send("\n".join(replies))
    

def setup(bot):
    bot.add_cog(Scores(bot))
