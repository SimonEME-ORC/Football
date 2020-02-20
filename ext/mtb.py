import asyncio
import datetime
import asyncpg
import discord
import praw
from discord.ext import tasks
from discord.ext import commands
from lxml import html
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from ext.utils.embed_utils import paginate
from ext.utils.selenium_driver import spawn_driver

import ext.utils.football


def get_goals(tree, xpath):
    goals = dict()
    for item in tree.xpath(xpath):
        strings = item.xpath('.//span/text()')
        player = strings[0]
        goals.update({player: "".join(strings[1:]).replace(' minutes', "")})
    return goals


async def get_ref_link(bot, refname):
    refname = refname.strip() # clean up nbsp.
    surname = refname.split(' ')[0]
    url = 'http://www.transfermarkt.co.uk/schnellsuche/ergebnis/schnellsuche'
    p = {"query": surname, "Schiedsrichter_page": "0"}
    async with bot.session.get(url, params=p) as ref_resp:
        if ref_resp.status != 200:
            return refname
        tree = html.fromstring(await ref_resp.text())
    matches = f".//div[@class='box']/div[@class='table-header'][contains(text(),'referees')]" \
              f"/following::div[1]//tbody/tr"
    trs = tree.xpath(matches)
    if trs:
        link = trs[0].xpath('.//td[@class="hauptlink"]/a/@href')[0]
        link = f"http://www.transfermarkt.co.uk/{link}"
        return f"[{refname}]({link})"

    p = {"query": refname, "Schiedsrichter_page": "0"}
    async with bot.session.get(url, params=p) as ref_resp:
        if ref_resp.status != 200:
            return refname
        tree = html.fromstring(await ref_resp.text())
        matches = f".//div[@class='box']/div[@class='table-header'][contains(text(),'referees')]" \
                  f"/following::div[1]//tbody/tr"
        trs = tree.xpath(matches)
        if trs:
            link = trs[0].xpath('.//td[@class="hauptlink"]/a/@href')[0]
            link = f"http://www.transfermarkt.co.uk/{link}"
            return f"[{refname}]({link})"
        else:
            return refname
    
class MatchThread:
    def __init__(self, bot, kick_off, subreddit, fs_link, **kwargs):
        self.bot = bot
        self.active = True
        self.driver = None
        self.kick_off = kick_off  # We use this for timing when to post things.
        self.__dict__.update(kwargs)
        
        # Reddit stuff.
        self.subreddit = subreddit
        self.pre_match_url = None
        self.match_thread_url = None
        self.post_match_url = None
        
        # Scrape targets & triggers
        self.fs_link = fs_link
        self.bbc_link = None
        self.old_markdown = None
        
        # Match Thread Data
        self.data = dict()
        self.ticker = set()
        
        # Commence loop
        self.task = self.bot.loop.create_task(self.match_thread_loop())
    
    async def get_driver(self):
        self.driver = await self.bot.loop.run_in_executor(None, spawn_driver)
    
    # Reddit posting shit.
    def make_post(self, title, markdown):
        post = self.bot.reddit.subreddit(self.subreddit).submit(title, selftext=markdown)
        if hasattr(self, "announcement_channel_id"):
            self.bot.loop.create_task(self.send_notification(self.announcement_channel_id, post))
        return post
    
    # Fetch an existing reddit post.
    def fetch_post(self, resume):
        try:
            if "://" in resume:
                post = self.bot.reddit.submission(url=resume)
            else:
                post = self.bot.reddit.submission(id=resume)
        except Exception as e:
            print("Error during fetch post..")
            print(e)
            post = None
        return post
    
    async def make_pre_match(self):
        # TODO: Actually write the code.
        # self.pre_match_url = post.url
        title = "blah"
        markdown = "blah"
        return title, markdown
    
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
        if not self.bbc_link and hasattr(self, "bbc_name"):
            async with self.bot.session.get(
                    f"http://www.bbc.co.uk/sport/football/teams/{self.bbc_name}/scores-fixtures") as resp:
                tree = html.fromstring(await resp.text(encoding="utf-8"))
                self.bbc_link = "http://www.bbc.co.uk" + tree.xpath(".//a[contains(@class,'sp-c-fixture')]/@href")[-1]
        else:
            return
        
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
                            tree = html.fromstring(await ref_resp.text())
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
            
            # TODO: Backup Scrape stadium info.
            
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
    
    def scrape_flash_score(self, mode: str = None):
        # TODO: Scrape stuff...
        tree = self.driver.page_source
        # Formations?
        # Match pictures?
        # Goal videos?
        if mode == "pre":
            # Injured players?
            # Head to head data?
            pass
        pass
    
    async def send_notification(self, channel_id, post: praw.Reddit.post):
        # Announce new posts to designated channels.
        channel = await self.bot.get_channel(channel_id)
        if channel is None:
            return  # Rip
        
        e = discord.Embed()
        e.colour = 0xFF4500
        e.title = post.title
        e.url = post.url
        await channel.send(embed=e)
    
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
        
        # Grab DB data
        if home in self.bot.teams:
            home_icon = self.bot.teams[home]['icon']
            home_link = home + " " + self.bot.teams[home]['subreddit']
        else:
            home_icon = ""
            home_link = home
        
        if away in self.bot.teams:
            away_icon = self.bot.teams[away]['icon']
            away_link = away + " " + self.bot.teams[away]['subreddit']
        else:
            away_icon = ""
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
        
        archive = f"[Match Thread Archive]({self.archive_link}" if hasattr(self, "archive_link") else ""
        pre = f"[Pre-Match Thread]({self.pre_match_url})" if self.pre_match_url else ""
        match = f"[Match Thread]({self.match_thread_url})" if self.match_thread_url else ""
        post = f"[Post-Match Thread]({self.post_match_url})" if self.post_match_url else ""
        
        threads = [i for i in [pre, match, post, archive] if i]
        if threads:
            markdown += "---\n\n##" + " | ".join(threads) + "\n\n---\n\n"
        
        # Radio, TV.
        if not is_post_match:
            if hasattr(self, "radio_link"):
                markdown += f"[📻 Radio Commentary]({self.radio_link})\n\n"
            if hasattr(self, "invite_link"):
                markdown += f"[](#icon-discord) [Join the chat with us on Discord]({self.invite_link})\n\n"
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
            markdown += "#### Match Photos\n\n"
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
    
    async def match_thread_loop(self):
        # Dupe check.
        connection = await self.bot.db.acquire()
        r = await connection.fetchrow("""SELECT FROM mtb_history WHERE (subreddit, fs_link) = ($1, $2)""",
                                      self.subreddit, self.fs_link)
        if r is not None:
            self.post_match_url = r['post_match_url']
            self.match_thread_url = r['match_thread_url']
            self.pre_match_url = r['pre_match_url']
        else:
            await connection.execute("""INSERT INTO mtb_history (fs_link, subreddit)
                                       VALUES ($1, $2)""", self.fs_link, self.subreddit)
        
        await self.bot.db.release(connection)
        
        await self.get_driver()
        self.driver.get(self.fs_link)

        if hasattr(self, "pre_match_offset"):
            await discord.utils.sleep_until(self.kick_off - datetime.timedelta(minutes=self.pre_match_offset))
            
            if self.pre_match_url is None:
                title, markdown = await self.make_pre_match()
                pre_match_instance = await self.bot.loop.run_in_executor(None, self.make_post, title, markdown)
                self.pre_match_url = pre_match_instance.url
                connection = await self.bot.db.acquire()
                await connection.execute("""UPDATE mtb_history
                                            SET pre_match_url = $1
                                            WHERE (subreddit, fs_link) = ($2, $3)""",
                                         self.pre_match_url, self.subreddit, self.fs_link)
                await self.bot.db.release(connection)
            else:
                pre_match_instance = await self.bot.loop.run_in_executor(self.fetch_post(self.pre_match_url))
                self.pre_match_url = pre_match_instance.url
        else:
            pre_match_instance = None

        # Gather initial data
        await self.scrape_flash_score()
        await self.scrape()
        self.data["tv"] = await self.fetch_tv()
        title, markdown = await self.write_markdown()
        
        # Sleep until ready to post.
        if hasattr(self, "match_offset"):
            await discord.utils.sleep_until(self.kick_off - datetime.timedelta(minutes=self.match_offset))
        
        # Post initial thread or resume existing thread.
        if self.match_thread_url is None:
            post = await self.bot.loop.run_in_executor(None, self.make_post, title, markdown)
            connection = await self.bot.db.acquire()
            await connection.execute("""UPDATE mtb_history
                                        SET match_thread_url = $1
                                        WHERE (subreddit, fs_link) = ($2, $3)""",
                                     post.url, self.subreddit, self.fs_link)
            await self.bot.db.release(connection)
        else:
            post = await self.bot.loop.run_in_executor(None, self.fetch_post, self.match_thread_url)
            
        self.match_thread_url = post.url
        
        for i in range(300):  # Maximum number of loops.
            await self.scrape()
            title, markdown = await self.write_markdown()
            
            # Only need to update if something has changed.
            if markdown != self.old_markdown:
                await self.bot.loop.run_in_executor(None, post.edit, markdown)
                self.old_markdown = markdown
            
            if not self.active:  # Set in self.scrape.
                break
            
            await asyncio.sleep(60)
        
        # Grab final data
        await self.scrape()
        # Create post match thread, get link.
        if self.post_match_url is None:
            post_match_instance = await self.bot.loop.run_in_executor(None, self.make_post, title, markdown)
            post = await self.bot.loop.run_in_executor(None, self.make_post, title, markdown)
            connection = await self.bot.db.acquire()
            await connection.execute("""UPDATE mtb_history
                                        SET post_match_url = $1
                                        WHERE (subreddit, fs_link) = ($2, $3)""",
                                     self.post_match_url, self.subreddit, self.fs_link)
            await self.bot.db.release(connection)
        else:
            post_match_instance = await self.bot.loop.run_in_executor(self.fetch_post(self.post_match_url))
        self.post_match_url = post_match_instance.url
        
        # Edit it's markdown to include the link.
        title, markdown = await self.write_markdown(is_post_match=True)
        await self.bot.loop.run_in_executor(None, post_match_instance.edit, markdown)
        
        # Then edit the match thread with the link too.
        title, markdown = await self.write_markdown()
        await self.bot.loop.run_in_executor(None, post.edit, markdown)
        
        # and finally, edit pre_match to include links
        title, markdown = self.make_pre_match()
        if hasattr(self, "pre_match_offset"):
            if pre_match_instance is not None:
                self.bot.loop.run_in_executor(None, pre_match_instance.edit, markdown)
        
        # Clean up.
        if self.driver is not None:
            self.driver.quit()


class MatchThreadCommands(commands.Cog):
    """ MatchThread Commands and Spooler."""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_threads = []
        self.driver = None
        self.data = dict()  # TODO: Delete. This is only for test command.
        # self.schedule_threads.start() # TODO: Uncomment when ready.
    
    # TODO: Delete check when finished.
    def cog_check(self, ctx):
        if ctx.guild:
            return ctx.guild.id in [332159889587699712, 250252535699341312]
    
    def get_fixtures(self, url):
        self.driver.get(url)
        try:
            xpath = './/div[@class="sportName soccer"]'
            WebDriverWait(self.driver, 5).until(ec.visibility_of_element_located((By.XPATH, xpath)))
        except TimeoutException:
            return []  # Rip
        
        tree = html.fromstring(self.driver.page_source)
        rows = tree.xpath(".//div[contains(@class,'sportName soccer')]/div")
        matches = []
        for i in rows:
            try:
                url = i.xpath("./@id")[0].split("_")[-1]
                url = "http://www.flashscore.com/match/" + url
            except IndexError:
                continue  # Not all rows have links.
            
            d = "".join(i.xpath('.//div[@class="event__time"]//text()')).strip("Pen").strip('AET')
            if "Postp" not in d:  # Should be dd.mm hh:mm or dd.mm.yyyy
                yn = datetime.datetime.today().year  # Year now
                try:
                    d = datetime.datetime.strptime(d, '%d.%m.%Y')
                except ValueError:
                    # This is ugly but February 29th can suck my dick.
                    d = datetime.datetime.strptime(f"{datetime.datetime.now().year}.{d}", '%Y.%d.%m. %H:%M')
                    
                    if d < datetime.datetime.today():
                        d = d.replace(year=yn + 1)
            
            h, a = i.xpath('.//div[contains(@class,"event__participant")]/text()')
            h, a = h.strip(), a.strip()
            matches.append((d, f"{h} vs {a}", url))
        return matches
    
    async def spool_thread(self, kick_off: datetime.datetime, match: str, url: str, r: asyncpg.Record):
        kwargs = {k: v for k, v in r}
        kwargs.update({"fs_url": url})
        subreddit = kwargs.pop('MatchThread')
        bbc_name = kwargs.pop('bbc_name')
        
        for i in self.active_threads:
            if i.subreddit == subreddit and i.bbc_name == bbc_name:
                print(f'Not spooling duplicate thread: {subreddit} {bbc_name}.')
                return
        
        print(f"Spooling match thread: {subreddit} {bbc_name}")
        mt = MatchThread(self.bot, kick_off, subreddit, bbc_name, **kwargs)
        self.active_threads.append(mt)
    
    @tasks.loop(hours=24)
    async def schedule_threads(self):
        # Number of minutes before the match to post
        connection = await self.bot.db.acquire()
        records = await connection.fetch(""" SELECT * FROM mtb_schedule """)
        await self.bot.db.release(connection)
        
        for r in records:
            # Get upcoming games from flashscore.
            fixtures = await self.bot.loop.run_in_executor(None, self.get_fixtures(r["team_flashscore_link"]))
            for time, match, url in fixtures:
                if time - datetime.datetime.now() > datetime.timedelta(days=3):
                    print(f'Spooling a match thread: {time} | {match} | {url}\n{r}')
                    self.bot.loop.create_task(self.spool_thread(time, match, url, r))
    
    @schedule_threads.before_loop
    async def before_stuff(self):
        self.driver = await self.bot.loop.run_in_executor(None, spawn_driver)
    
    @schedule_threads.after_loop
    async def after_stuff(self):
        self.driver.quit()
    
    def cog_unload(self):
        for i in self.active_threads:
            i.task.cancel()

    def _test(self):
        driver = spawn_driver()
        print("Driver spawned.")
        
        # Finished: https://www.flashscore.com/match/EyG1EdgD (NEW - ARS)
        # Upcoming: https://www.flashscore.com/match/lGuaXAah (NEW - PAL)
        
        driver.get("https://www.flashscore.com/match/EyG1EdgD")
        print('Got page.')
        referee = ""
        venue = ""
        try:
            # Get venue / competition / referee.
            xp = (By.XPATH, ".//div[@class='match-information-data']")
            x = WebDriverWait(driver, 3).until(ec.presence_of_element_located(xp))
        
            tree = html.fromstring(driver.page_source)
            match_info = tree.xpath(f".//div[@class='match-information-data']//text()")
            competition = "".join(tree.xpath(".//span[@class='description__country']//text()"))
            complink = "".join(tree.xpath(".//span[@class='description__country']//a/@onclick"))
            print(f"complink: {complink}")
            try:
                complink = complink.split('\'')[1]
                complink = f"http://www.flashscore.com{complink}"
            except IndexError:
                complink = ""
            
            self.data['competition'] = f"[{competition}]({complink})" if complink else competition
            for i in match_info:
                i = i.replace(',\xa0', '')
                if i.startswith('Referee'):
                    self.data['referee'] = i.split(': ')[-1].split('(')[0]
                if i.startswith('Venue'):
                    self.data['venue'] = i.split(': ')[-1].split('(')[0]
        except Exception as e:
            print(e)
    
        # Get H2H data
        ## H2h data at all venues
        ## H2H data at Home venue
    
        # Get form data
        ## Last 5 games each
        ## Last 5 home games home
        ## Last 5 away games away
    
        # Get Current table
    
        # Get Injury & Suspension data
    
        driver.quit()
        print("Driver closed.")
        return
    
    @commands.command()
    @commands.is_owner()
    async def mtbtest(self, ctx):
        x = await self.bot.loop.run_in_executor(None, self._test)
        


def setup(bot):
    bot.add_cog(MatchThreadCommands(bot))
