import asyncio
import datetime

import discord
from discord.ext import commands
from lxml import html

# TODO: Make pre-match thread function.
from ext.utils.selenium_driver import spawn_driver

# TODO: Convert teams to database
# TODO: Migrate every mention of nufc/themagpiescss to database & store values.

def get_goals(tree, xpath):
    goals = dict()
    for item in tree.xpath(xpath):
        strings = item.xpath('.//span/text()')
        player = strings[0]
        g = "".join(strings[1:])
        g = g.replace(' minutes', "").replace(',\xa0', "")
        goals.update({player: g})
    return goals


class MatchThread:
    def __init__(self, bot, bbc_name, subreddit=None, resume=None, fs_link=None):
        self.bot = bot
        self.subreddit = subreddit
        self.driver = None
        self.active = True
        
        # Scrape targets
        self.bbc_name = bbc_name
        self.bbc_link = ""
        self.fs_link = fs_link
        
        # Match Threads
        self.data = dict()
        self.ticker = set()
        
        # Commence loop
        self.task = self.bot.loop.create_task(self.match_thread_loop(resume))

    async def get_driver(self):
        self.driver = await self.bot.loop.run_in_executor(None, spawn_driver)

    # Reddit posting shit.
    def make_post(self, title, markdown):
        return self.bot.reddit.subreddit(self.subreddit).submit(title, selftext=markdown)

    # Fetch an existing reddit post.
    def fetch_post(self, resume):
        try:
            if "://" in resume:
                post = self.bot.reddit.submission(url=resume)
            else:
                post = self.bot.reddit.submission(id=resume)
        except Exception as e:
            print("Error during resume post..")
            print(e)
            post = None
        return post

    def get_pre_match(self):
        thread = self.bot.reddit.subreddit('NUFC').search('flair:"Pre-match thread"', sort="new", syntax="lucene")[0]
        return thread.url

    async def fetch_tv(self):
        tv = {}
        async with self.bot.session.get(f"https://www.livesoccertv.com/") as resp:
            if resp.status != 200:
                print(f"{resp.status} recieved when trying to fetch TV url {resp.url}")
                return None
            tree = html.fromstring(await resp.text())
            for i in tree.xpath(".//tr//a"):
                if self.data["home"]["team"] in "".join(i.xpath(".//text()")):
                    lnk = "".join(i.xpath(".//@href"))
                    tv.update({"link": f"http://www.livesoccertv.com{lnk}"})
                    break
        if not tv:
            return None
    
        async with self.bot.session.get(tv["link"]) as resp:
            if resp.status != 200:
                return tv
            tree = html.fromstring(await resp.text())
            tv_table = tree.xpath('.//table[@id="wc_channels"]//tr')
        
            if not tv_table:
                return tv.update({"uk_tv": ""})
        
            for i in tv_table:
                country = i.xpath('.//td[1]/span/text()')
                if "United Kingdom" not in country:
                    continue
                uk_tv_channels = i.xpath('.//td[2]/a/text()')
                uk_tv_links = i.xpath('.//td[2]/a/@href')
                uk_tv_links = [f'http://www.livesoccertv.com/{i}' for i in uk_tv_links]
                uk_tv = list(zip(uk_tv_channels, uk_tv_links))
                tv.update({"uk_tv": [f"[{i}]({j})" for i, j in uk_tv]})
            return tv
    
    async def scrape(self):
        if not self.bbc_link:
            async with self.bot.session.get(
                    f"http://www.bbc.co.uk/sport/football/teams/{self.bbc_name}/scores-fixtures") as resp:
                tree = html.fromstring(await resp.text(encoding="utf-8"))
                self.bbc_link = "http://www.bbc.co.uk" + tree.xpath(".//a[contains(@class,'sp-c-fixture')]/@href")[-1]
        
        async with self.bot.session.get(self.bbc_link) as resp:
            if resp.status != 200:
                return
            tree = html.fromstring(await resp.text(encoding="utf-8"))
            
            # Date, Time & Competition
            if not self.data["kickoff"]:  # We only need this once.
                ko_date = "".join(tree.xpath('.//div[@class="fixture_date-time-wrapper"]/time/text()'))
                ko_time = "".join(tree.xpath('.//span[@class="fixture__number fixture__number--time"]/text()'))
                self.data["kickoff"] = {"time": ko_time, "date": ko_date}
            
            if not self.data["competition"]:  # We only need this once.
                self.data["competition"] = "".join(tree.xpath(".//span[@class='fixture__title gel-minion']/text()"))
            
            if not self.data["referee"]:  # Also only once.
                referee = "".join(tree.xpath("//dt[contains(., 'Referee')]/text() | "
                                             "//dt[contains(., 'Referee')]/following-sibling::dd[1]/text()"))
                if referee:
                    url = 'http://www.transfermarkt.co.uk/schnellsuche/ergebnis/schnellsuche'
                    p = {"query": referee, "Schiedsrichter_page": "0"}
                    async with self.bot.session.get(url, params=p) as ref_resp:
                        if ref_resp.status == 200:
                            tree = html.fromstring(await resp.text())
                            matches = f".//div[@class='box']/div[@class='table-header'][contains(text(),'referees')]" \
                                      f"/following::div[1]//tbody/tr"
                            trs = tree.xpath(matches)
                            if trs:
                                link = trs[0].xpath('.//td[@class="hauptlink"]/a/@href')[0]
                                link = f"http://www.transfermarkt.co.uk/{link}"
                                self.data["referee"] = f"[{referee}]({link})"
                            else:
                                self.data["referee"] = referee
                else:
                    self.data['referee'] = ""
            
            if not self.data["attendance"]:
                self.data["attendance"] = "".join(
                    tree.xpath("//dt[contains(., 'Attendance')]/text() | //dt[contains(., "
                               "'Attendance')] /following-sibling::dd[1]/text()"))
            
            # Teams
            if not self.data["home"]:  # We only need this once.
                self.data["home"] = {"team": tree.xpath('.//span[@class="fixture__team-name-wrap"]//abbr/@title')[0]}
                self.data["away"] = {"team": tree.xpath('.//span[@class="fixture__team-name-wrap"]//abbr/@title')[1]}
                
                # Get Stadium
                try:
                    stadium = self.bot.teams[self.data["home"]["team"]]['stadium']
                    stadium_link = self.bot.teams[self.data["home"]["team"]]['stadlink']
                    self.data["stadium"] = f"[{stadium}]({stadium_link})"
                except KeyError:
                    self.data["stadium"] = ""
                    
            # Recurring checks.
            self.data["home"]["goals"] = get_goals(tree, './/ul[contains(@class,"fixture__scorers")][1]//li')
            self.data["away"]["goals"] = get_goals(tree, './/ul[contains(@class,"fixture__scorers")][2]//li')
            # Penalty Win Bar
            self.data["penalties"] = "".join(tree.xpath(".//span[contains(@class='fixture__win-message')]/text()"))

            def parse_players(players: list, team_goals: dict):
                squad = {}
                for d in players:
                    name = "".join(d.xpath('.//span[2]/abbr/span/text()')[0])
                    scored = ""
                    for player, g in team_goals.items():
                        if player in name:
                            scored = g
                            break
                    number = "".join(d.xpath('.//span[1]/text()')[0])
                    # Bookings / Sending offs.
                    raw = "".join(d.xpath('.//span[2]/i/@class'))
                    cards = ""
                    if "card--yellow" in raw:
                        cards += " 🟨"
                    if "card--red" in raw:
                        cards += " 🟥"
                    
                    try:
                        subbed = {"replaced_by": "".join(d.xpath('.//span[3]/span//text()')[1]),
                                  "minute": "".join(d.xpath('.//span[3]/span//text()')[3])}
                    except IndexError:
                        subbed = {"minute": "", "replaced_by": ""}
                    squad.update({number: {"name": name, "cards": cards, "subbed": subbed, "goals": scored}})
                return squad
            
            home_xi = tree.xpath('(.//div[preceding-sibling::h2/text()="Line-ups"]//div//ul)[1]/li')
            home_subs = tree.xpath('(.//div[preceding-sibling::h2/text()="Line-ups"]//div//ul)[2]/li')
            away_xi = tree.xpath('(.//div[preceding-sibling::h2/text()="Line-ups"]//div//ul)[3]/li')
            away_subs = tree.xpath('(.//div[preceding-sibling::h2/text()="Line-ups"]//div//ul)[4]/li')
            
            self.data["home"]["xi"] = parse_players(home_xi, self.data["home"]["goals"])
            self.data["home"]["subs"] = parse_players(home_subs, self.data["home"]["goals"])
            self.data["away"]["xi"] = parse_players(away_xi, self.data["away"]["goals"])
            self.data["away"]["subs"] = parse_players(away_subs, self.data["away"]["goals"])
            
            # Stats
            stats = tree.xpath("//dl[contains(@class,'percentage-row')]")
            self.data["stats"] = []
            for i in stats:
                stat = "".join(i.xpath('.//dt/text()'))
                home = "".join(i.xpath('.//dd[1]/span[2]/text()'))
                away = "".join(i.xpath('.//dd[2]/span[2]/text()'))
                self.data["stats"].append((home, stat, away))
            
            ticker = tree.xpath("//div[@class='lx-stream__feed']/article")
            await self.update_ticker(ticker)

    def scrape_flash_score(self, url, mode: str = None):
        # TODO: Scrape stuff...
        # Formations?
        # Match pictures?
        # Goal videos?
        # Injured players?
        # Head to head data?
        pass

    async def update_ticker(self, ticker):
        for i in ticker:
            header = "".join(i.xpath('.//h3//text()')).strip()
            time = "".join(i.xpath('.//time//span[2]//text()')).strip()
            content = "".join(i.xpath('.//p//text()'))
            note = ""
            emoji = ""
        
            key = False
            if "get involved" in header.lower():
                continue  # we don't care.
        
            if "kick off" in header.lower():
                header = "Kick off"
                emoji = "⚽"
        
            elif "goal" in header.lower():
                key = True
                header = "Goal"
                emoji = "⚽"
                if "converts the penalty" in content.lower():
                    note = "Penalty"
            
                elif "own goal" in content.lower():
                    note = "Own Goal"
        
            elif "substitution" in header.lower():
                team, subs = content.replace("Substitution, ", "").split('.', 1)
                on, off = subs.split('replaces')
                note = {"team": team, "on": on, "off": off}
                emoji = "🔄"
                header = "Substitute"
            elif "booking" in header.lower():
                header = "Booking"
                emoji = "🟨"
        
            elif "dismissal" in header.lower():
                key = True
                emoji = "🟥"
                if "second yellow" in content.lower():
                    note = "Second Yellow"
                    emoji = "🟨🟨🟥"
        
            elif "half time" in header.lower().replace('-', ' '):
                header = "Half Time"
                emoji = "⏸"
        
            elif "second half" in header.lower().replace('-', ' '):
                header = "Second Half"
                content = content.replace('Second Half', ' ')
                emoji = "⚽"
        
            elif "full time" in header.lower().replace('-', ' '):
                header = "Full Time"
            elif "penalties in progress" in header.lower().strip():
                key = True
                header = "Penalty Shootout"
                emoji = "⚽"
            elif "penalties over" in header.lower().strip():
                header = "Penalties Over"
            else:
                if header:
                    print(f"MTB: Unhandled header: {header}")
            
                elif "Lineups are announced" in content:
                    continue  # we don't care.
            
                # Format by content.
                elif "First Half Extra Time begins" in content:
                    header = "First Half of Extra Time"
                    content = content.replace("First Half Extra Time begins", "")
                elif "First Half Extra Time ends" in content:
                    header = "End of First Half of Extra Time "
                    content = content.replace("First Half Extra Time ends", "")
                elif "Second Half Extra Time begins" in content:
                    header = "Second Half of Extra Time"
                    content = content.replace("Second Half Extra Time begins", "")
                elif "Second Half Extra Time ends" in content:
                    header = "End of Extra Time"
                    content = content.replace(header + "Second Half Extra Time ends", "")
                elif "injury" in content.lower() or "injured" in content.lower():
                    header = "Injury"
                    emoji = "🚑"
                elif "offside" in content.lower():
                    header = "Offside"
                elif content.lower().startswith("corner"):
                    header = "Corner"
                elif "penalty saved" in content.lower():
                    key = True
                    header = "Penalty Saved"
                elif "match ends" in content.lower():
                    header = "End of Match"
                    self.active = False
                elif "foul" in content.lower():
                    header = "Foul"
                elif "free kick" in content.lower():
                    header = "Free Kick"
                elif "VAR " in content:
                    header = "VAR Decision"
                    emoji = "📹"
                elif "Attempt" in content:
                    header = "Attempt"
                elif "hits the" in content.lower() and "post" in content.lower():
                    header = "Woodwork"
                elif "hand ball" in content.lower():
                    header = "Hand Ball"
                    emoji = "🤾‍"
                else:
                    print(f"Match Thread Bot: No header found for {content}")
            x = {"key": key, "header": header, "emoji": emoji, "content": content, "note": note, "time": time}
            if x not in self.ticker:
                self.ticker.update(x)

    async def write_markdown(self, is_post_match=False):
        # Alias for easy replacing.
        home = self.data["home"]["team"]
        away = self.data["away"]["team"]
    
        # Date and Competition bar
        kickoff = f"{self.data['kickoff']['date']} at {self.data['kickoff']['time']}"
        markdown = "####" + " | ".join([kickoff, self.data['competition']]) + "\n\n"
    
        # Grab Match Icons
        try:
            home_icon = self.bot.teams[home]['icon']
        except KeyError:
            home_icon = ""
        try:
            away_icon = self.bot.teams[away]['icon']
        except KeyError:
            away_icon = ""
    
        try:
            sr = self.bot.teams[home]["subreddit"]
            home_link = f'[{home}]({sr})'
        except KeyError:
            home_link = home
    
        try:
            sr = self.bot.teams[away]["subreddit"]
            away_link = f'[{away}]({sr})'
        except KeyError:
            away_link = away
    
        score = f"{len(self.data['home']['goals'])} - {len(self.data['away']['goals'])}"
        markdown += f"# {home_icon} {home_link} {score} {away_link} {away_icon}\n\n"
    
        if is_post_match:
            title = f"Post-Match Thread: {home} {score} {away}"
        else:
            title = f"Match Thread: {home} vs {away}"
    
        if self.data['penalties']:
            markdown += "####" + self.data['penalties'] + "\n\n"
    
        # Referee and Venue
        referee = f"**🙈 Referee**: {self.data['referee']}" if self.data['referee'] else ""
        stadium = f"**🥅 Venue**: {self.data['stadium']}" if self.data['stadium'] else ""
        attendance = f" (👥 Attendance: {self.data['attendance']})" if self.data['attendance'] else ""

        if any([referee, stadium, attendance]):
            markdown += "####" + " | ".join([i for i in [referee, stadium, attendance] if i]) + "\n\n"
    
        # Match Threads Bar.
        if self.subreddit.lower() in ["nufc", "themagpiescss"]:
            archive = "[Match Thread Archive](https://www.reddit.com/r/NUFC/wiki/archive)"
        else:
            archive = ""
    
        mts = " | ".join([f"[{k}]({v})" for k, v in self.data['threads'].items() if v is not None] + [archive])
        markdown += "---\n\n##" + mts + "\n\n---\n\n"
    
        # Radio, TV.
        if not is_post_match:
            if self.subreddit.lower() in ["nufc", "themagpiescss"]:
                markdown += "[📻 Radio Commentary](https://www.nufc.co.uk/liveAudio.html)\n\n"
                markdown += "[](#icon-discord) [Join the chat with us on Discord](http://discord.gg/tbyUQTV)\n\n"
            if self.data["tv"] is not None:
                markdown += f"📺🇬🇧 **TV** (UK): {self.data['tv']['uk_tv']}\n\n" if self.data["tv"]["uk_tv"] else ""
                markdown += f"📺🌍 **TV** (Intl): [International TV Coverage]({self.data['tv']['link']})"
    
        def format_team(match_data_team: dict, is_home=False):
            formatted_xi = []
            formatted_subs = []
            for p in match_data_team["xi"]:
                # alias
                nm = match_data_team['xi'][p]['name']
                cr = match_data_team['xi'][p]['cards']
                so = match_data_team['xi'][p]['subbed']['replaced_by']
                sm = match_data_team['xi'][p]['subbed']['minute']
                g = match_data_team['xi'][p]['goals']
                g = f"⚽ {g}" if g else ""
                if is_home:
                    s = f"{so} {sm} 🔻" if so and sm else ""
                    output = f"{s} {g} {cr}{nm} **{p}**"
                else:
                    s = f"🔻 {so} {sm}" if so and sm else ""
                    output = f"**{p}** {nm}{cr} {g} {s}"
                formatted_xi.append(output)
        
            for p in match_data_team["subs"]:
                # alias
                nm = match_data_team['subs'][p]['name']
                g = match_data_team['subs'][p]['goals']
                g = f" ⚽ {g}" if g else ""
                cr = match_data_team['subs'][p]['cards']
                so = match_data_team['subs'][p]['subbed']['replaced_by']
                sm = match_data_team['subs'][p]['subbed']['minute']
                s = f" 🔺 {so} {sm}" if so and sm else ""
                output = f"{p} {nm}{cr}{g}{s}"
                formatted_subs.append(output)
            return formatted_xi, formatted_subs
    
        home_xi_markdown, home_sub_markdown = format_team(self.data["home"], is_home=True)
        away_xi_markdown, away_sub_markdown = format_team(self.data["away"])
    
        lineup_md = list(zip(home_xi_markdown, away_xi_markdown))
        lineup_md = "\n".join([f"{a} | {b}" for a, b in lineup_md])
    
        # Lineups & all the shite that comes with it.
        if self.data['home']["xi"] and self.data['away']["xi"]:
            markdown += f"---\n\n### Lineups"
            if self.data["formations"]:
                markdown += f" ([Formations]({self.data['formations']}))"
            markdown += f"\n{home_icon} **{home}** |**{away}**  {away_icon} \n"
            markdown += "--:|:--\n"
            markdown += lineup_md + "\n\n"
            markdown += f"---\n\n#### Subs"
            markdown += f"\n{home_icon} {home} | {away} {away_icon}\n"
            markdown += "--:|:--\n"
            markdown += f"{','.join(home_sub_markdown)} | {', '.join(away_sub_markdown)}\n"
    
        if self.data["stats"]:
            markdown += f"---\n\n### Match Stats	\n"
            markdown += f"{home_icon} {home}|v|{away} {away_icon}\n" \
                        f"--:|:--:|:--\n"
        
            for h, stat, a in self.data["stats"]:
                markdown += f"{h} | {stat} | {a}\n"
    
        if self.data["pictures"]:
            # TODO: Format these, test if [](xyz 'title here') works
            markdown += "###Match Photos\n\n"
            pic_id = 0
            for caption, url in self.data["pictures"]:
                pic_id += 1
                markdown += f"[{pic_id}]({url} '{caption}') "
            markdown += "\n\n"
    
        formatted_ticker = ""
        for i in self.ticker:
            # TODO: Manually parse all these.
            # Discard non-key events for post-match.
            if is_post_match:
                if not i["key"]:
                    continue
                    
            # Alias
            t = i['time']
            h = i['header']
            e = i["emoji"]
            c = i["content"]
            n = i["note"]
            c = c.replace(h, "")  # strip header from content.
        
            if h == "end of match":
                continue
        
            if h == "Substitute":
                on = i["note"]["on"]
                off = i["note"]["off"]
                team = i["note"]["team"]
                c, n = f"{team} 🔺 {on} 🔻 {off}", ""
            if h == "Corner":
                c = c.replace(' ,', "")
        
            c = c.replace(home, f"{home_icon} {home}").replace(away, f"{away_icon} {away}")
            formatted_ticker += f'{t} {e} **{h}**: {c}{n}\n\n'
    
        markdown += "\n\n---\n\n" + formatted_ticker + "\n\n"
        markdown += "\n\n---\n\n^(*Beep boop, I am /u/Toon-bot, a bot coded ^badly by /u/Painezor. " \
                    "If anything appears to be weird or off, please let him know.*)"
        return title, markdown
    
    async def match_thread_loop(self, resume=None):
        # Spawn our driver.
        if self.fs_link:
            await self.get_driver()
            self.driver.get(self.fs_link)
            
        num_iters = 0
        
        # Gather initial data
        await self.scrape()
        self.data["tv"] = await self.fetch_tv()

        pre_match = self.bot.loop.run_in_executor(None, self.get_pre_match)
        self.data['threads'] = {'Pre Match Thread': pre_match}

        title, markdown = await self.write_markdown()
        
        # Post initial thread or resume existing thread.
        if resume is not None:
            post = await self.bot.loop.run_in_executor(None, self.fetch_post, resume)
        else:
            post = await self.bot.loop.run_in_executor(None, self.make_post, title, markdown)

        self.data["threads"].update({"Match thread": post.url})
        while self.active and num_iters > 300:
            await self.scrape()
            title, markdown = await self.write_markdown()
            num_iters += 1
            await self.bot.loop.run_in_executor(None,  post.edit, markdown)
            await asyncio.sleep(60)
        
        # Grab final data
        await self.scrape()
        title, markdown = await self.write_markdown(is_post_match=True)
        
        # Create post match thread, get link.
        post_match_instance = await self.bot.loop.run_in_executor(None, self.make_post, title, markdown)

        self.data['threads'].update({"Post-Match Thread": f"[Post-Match Thread]({post_match_instance.url})"})
        
        # Edit it's markdown to include the link.
        title, markdown = await self.write_markdown(is_post_match=True)
        await self.bot.loop.run_in_executor(None,  post_match_instance.edit, markdown)
        
        # Then edit the match thread.
        title, markdown = await self.write_markdown()
        await self.bot.loop.run_in_executor(None, post.edit, markdown)
        
        # Clean up.
        if self.fs_link:
            self.driver.quit()


class MatchThreadCommands(commands.Cog):
    """ MatchThread Commands and Spooler."""
    def __init__(self, bot):
        self.bot = bot
        self.scheduled_threads = []
        self.active_threads = []
        self.bot.loop.create_task(self.get_schedule())
    
    # TODO: Make sure this can work on other discords for their subreddits.
    def cog_check(self, ctx):
        if ctx.guild:
            return ctx.guild.id in [238704683340922882, 332159889587699712]
    
    async def schedule_thread(self, post_at, identifier, subreddit, team_url):
        await discord.utils.sleep_until(post_at)
        self.active_threads.append(MatchThread(self.bot, team_url, subreddit=subreddit))
        self.scheduled_threads.remove(identifier)
    
    def cog_unload(self):
        for i in self.scheduled_threads:
            i.cancel()
     
    # Schedule a block of match threads.
    async def get_schedule(self):
        # Number of minutes before the match to post
        match_thread_offset = 30
        subreddit = "nufc"
        team_url = "newcastle-united"
        async with self.bot.session.get("https://www.nufc.co.uk/matches/first-team") as resp:
            if resp.status != 200:
                print(f"{resp.status} error in scheduler.")
                return
            
            tree = html.fromstring(await resp.text())
            blocks = tree.xpath('.//div[@class="fixtures__item__content"]')
            
            fixtures = {}
            
            for i in blocks:
                date = "".join(i.xpath('.//p[@content]//text()')).strip()
                if not date:
                    continue
                date = date.replace("3rd", "3").replace("th", "").replace("1st", "1").replace("2nd", "2")
                venue = "".join(i.xpath('.//h4//text()')).strip()
                opp = "".join(i.xpath('.//h3/span/text()')).strip()
                
                if "St. James'" in venue:
                    fixtures[date] = f"Newcastle United vs {opp}"
                else:
                    fixtures[date] = f"{opp} vs Newcastle United"
            
            for k, v in fixtures.items():
                k = datetime.datetime.strptime(k, "%d %B %Y %I:%M %p")
                
                # Offset by x mins
                post_at = k - datetime.timedelta(minutes=match_thread_offset)
                
                schedule_text = f"**{k}**: {v}"
                self.scheduled_threads.append(schedule_text)
                
                self.bot.loop.create_task(
                    self.schedule_thread(post_at, schedule_text, subreddit=subreddit, team_url=team_url))
    
    # Debug command - Force Test
    @commands.command()
    @commands.is_owner()
    async def forcemt(self, ctx, *, subreddit="themagpiescss"):
        if "r/" in subreddit:
            subreddit = subreddit.split("r/")[1]
        await ctx.send(f'Starting a match thread on r/{subreddit}...')
        self.active_threads.append(MatchThread(bbc_name="newcastle-united", bot=ctx.bot, subreddit=subreddit))
    
    @commands.command()
    @commands.is_owner()
    async def resume(self, ctx, *, linkorbase64):
        m = await ctx.send(f'Resuming match thread {linkorbase64}...')
        self.active_threads.append(MatchThread(bbc_name="newcastle-united", bot=ctx.bot, resume=linkorbase64))
        await m.edit(content='Resumed successfully.')
    
    @commands.command(aliases=["mtbcheck"])
    @commands.is_owner()
    async def checkmtb(self, ctx):
        e = discord.Embed()
        e.colour = 0x000000
        self.scheduled_threads.sort()
        e.description = "\n".join(self.scheduled_threads)
        e.title = "r/NUFC Scheduled Match Threads"
        await ctx.send(embed=e)
    
    @commands.command()
    @commands.is_owner()
    async def override(self, ctx, var, *, value):
        setattr(self, var, value)
        await ctx.send(f'Match Thread Bot: Setting "{var}" to "{value}"')


def setup(bot):
    bot.add_cog(MatchThreadCommands(bot))
