import asyncio
import datetime
import json

import discord
from aiohttp import ServerDisconnectedError
from discord.ext import commands
from imgurpython import ImgurClient
from lxml import html
from prawcore.exceptions import RequestException
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait

# TODO: Convert upcoming matches to dict
# TODO: Convert upcoming matches to get bbc data.
# TODO: convert to tasks extention
# TODO: Grab data from flashscore
# TODO: Make pre-match thread function.
from ext.utils.selenium_driver import spawn_driver


def editpost(post, markdown, retries=0):
    try:
        post.edit(markdown)
    except Exception as e:
        print(e)
        print(e.__name__)


class MatchThreadCommands(commands.Cog):
    """ MatchThread Bot."""
    
    def __init__(self, bot):
        self.bot = bot
        self.scheduled_threads = []
        self.activethreads = []
        self.bot.loop.create_task(self.get_schedule())
        self.active_module = True
        self.stop_match_thread = False
        self.bot.loop.create_task(self.get_driver())
        self.driver = None
    
    async def get_driver(self):
        self.driver = await self.bot.loop.run_in_executor(None, spawn_driver)
    
    def cog_unload(self):
        self.active_module = False
        self.driver.quit()
    
    async def fetch_ref(self, referee):
        url = 'http://www.transfermarkt.co.uk/schnellsuche/ergebnis/schnellsuche'
        p = {"query": referee, "Schiedsrichter_page": "0"}
        async with self.bot.session.get(url, params=p) as resp:
            if resp.status != 200:
                return ""
            else:
                tree = html.fromstring(await resp.text())
                matches = f".//div[@class='box']/div[@class='table-header'][contains(text()," \
                          f"'referees')]/following::div[" \
                          f"1]//tbody/tr"
                trs = tree.xpath(matches)
                if trs:
                    link = trs[0].xpath('.//td[@class="hauptlink"]/a/@href')[0]
                    link = f"http://www.transfermarkt.co.uk/{link}"
                    return f"[{referee}]({link})"
                else:
                    return referee
    
    async def fetch_tv(self, match_data):
        tv = {}
        async with self.bot.session.get(f"https://www.livesoccertv.com/") as resp:
            if resp.status != 200:
                print(f"{resp.status} recieved when trying to fetch TV url {resp.url}")
                return match_data
            tree = html.fromstring(await resp.text())
            for i in tree.xpath(".//tr//a"):
                if match_data["home"]["team"] in "".join(i.xpath(".//text()")):
                    lnk = "".join(i.xpath(".//@href"))
                    tv.update({"link": f"http://www.livesoccertv.com{lnk}"})
                    break
        if not tv:
            return {"uk_tv": "", "link": ""}
        
        async with self.bot.session.get(tv["link"]) as resp:
            if resp.status != 200:
                print("Failed to fetch TV Link.")
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
    
    async def parse_ticker(self, ticker):
        ticks = {}
        tick_id = 0
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
                    self.stop_match_thread = True
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
            
            ticks.update({tick_id: {"key": key, "header": header, "emoji": emoji,
                                    "content": content, "note": note, "time": time}})
            tick_id += 1
        return ticks
    
    async def scrape(self, bbc_link, match_data=None):
        if match_data is None:
            match_data = {}
        async with self.bot.session.get(bbc_link) as resp:
            if resp.status != 200:
                return
            tree = html.fromstring(await resp.text(encoding="utf-8"))
            
            # Date, Time &* Competition
            ko_date = "".join(tree.xpath('.//div[@class="fixture_date-time-wrapper"]/time/text()'))
            ko_time = "".join(tree.xpath('.//span[@class="fixture__number fixture__number--time"]/text()'))
            match_data["kickoff"] = {"time": ko_time, "date": ko_date}
            match_data["competition"] = "".join(tree.xpath(".//span[@class='fixture__title gel-minion']/text()"))
            
            # Teams
            match_data["home"] = {"team": tree.xpath('.//span[@class="fixture__team-name-wrap"]//abbr/@title')[0]}
            match_data["away"] = {"team": tree.xpath('.//span[@class="fixture__team-name-wrap"]//abbr/@title')[1]}
            
            # Get Stadium
            try:
                stadium = self.bot.teams[match_data["home"]["team"]]['stadium']
                stadium_link = self.bot.teams[match_data["home"]["team"]]['stadlink']
                match_data["stadium"] = f"[{stadium}]({stadium_link})"
            except KeyError:
                match_data["stadium"] = ""
            
            # Goals
            match_data["score"] = " - ".join(tree.xpath("//span[contains(@class,'fixture__number')]//text()")[0:2])
            
            def get_goals(xpath:str):
                goals = {}
                for i in tree.xpath(xpath):
                    strings = i.xpath('.//span/text()')
                    player = strings[0]
                    g = "".join(strings[1:])
                    g = g.replace(' minutes', "").replace(',\xa0', "")
                    goals.update({player: g})
                return goals
            
            match_data["home"]["goals"] = get_goals('.//ul[contains(@class,"fixture__scorers")][1]//li')
            match_data["away"]["goals"] = get_goals('.//ul[contains(@class,"fixture__scorers")][2]//li')
            # Penalty Win Bar
            match_data["penalties"] = "".join(tree.xpath(".//span[@class='gel-brevier fixture__win-message']/text()"))
            
            # Referee & Attendance
            match_data["attendance"] = "".join(tree.xpath("//dt[contains(., 'Attendance')]/text() | //dt[contains(., "
                                                          "'Attendance')] /following-sibling::dd[1]/text()"))
            
            referee = "".join(tree.xpath("//dt[contains(., 'Referee')]/text() | "
                                         "//dt[contains(., 'Referee')]/following-sibling::dd[1]/text()"))
            match_data["referee"] = await self.fetch_ref(referee)
            
            def parse_players(players: list, team_goals: dict):
                squad = {}
                for d in players:
                    name = "".join(d.xpath('.//span[2]/abbr/span/text()')[0])
                    scored = ""
                    for p, g in team_goals.items():
                        if p in name:
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
            
            match_data["home"]["xi"] = parse_players(home_xi, match_data["home"]["goals"])
            match_data["home"]["subs"] = parse_players(home_subs, match_data["home"]["goals"])
            match_data["away"]["xi"] = parse_players(away_xi, match_data["away"]["goals"])
            match_data["away"]["subs"] = parse_players(away_subs, match_data["away"]["goals"])
            
            # Stats
            stats = tree.xpath("//dl[contains(@class,'percentage-row')]")
            match_data["stats"] = []
            for i in stats:
                stat = "".join(i.xpath('.//dt/text()'))
                home = "".join(i.xpath('.//dd[1]/span[2]/text()'))
                away = "".join(i.xpath('.//dd[2]/span[2]/text()'))
                match_data["stats"].append((home, stat, away))
            
            ticker = tree.xpath("//div[@class='lx-stream__feed']/article")
            match_data["events"] = await self.parse_ticker(ticker)
        return match_data
    
    # Bonus data if prem.
    def get_pl_link(self, team):
        # TODO EC Presnence of Element.
        self.driver.get("https://www.premierleague.com/")
        src = self.driver.page_source
        tree = html.fromstring(src)
        xp = f".//nav[@class='mcNav']//a[.//abbr[@title='{team}']]"
        
        try:
            return "https://www.premierleague.com/" + tree.xpath(xp)[0].attrib["href"]
        except:
            return ""
    
    def get_pl_data(self, pl_link):
        self.driver.get(pl_link)
        # Get Match pictures.
        # TODO: Use EC presence of element
        try:
            pics = self.driver.find_element_by_xpath('.//ul[@class="matchPhotoContainer"]').get_attribute("innerHTML")
            pics = html.fromstring(pics)
            pics = pics.xpath(".//li")
            
            match_pics = []
            for i in pics:
                url = "".join(i.xpath('.//div[@class="thumbnail"]//img/@src'))
                caption = "".join(i.xpath('.//span[@class="captionBody"]/text()'))
                if not url and not caption:
                    continue
                this_pic = (caption, url)
                if this_pic not in match_pics:
                    match_pics.append(this_pic)
        except:
            match_pics = []
        
        try:
            z = self.driver.find_element_by_xpath(".//ul[@class='tablist']/li[@class='matchCentreSquadLabelContainer']")
            z.click()
            WebDriverWait(self.driver, 2)
            fm = self.driver.find_element_by_xpath(".//div[@class='pitch']").screenshot_as_png
        except NoSuchElementException:
            fm = ""
        return match_pics.reverse(), fm
    
    async def write_markdown(self, match_data, subreddit="", is_post_match=False):
        # Alias for easy replacing.
        home = match_data["home"]["team"]
        away = match_data["away"]["team"]
        
        # Date and Competition bar
        kickoff = f"{match_data['kickoff']['date']} at {match_data['kickoff']['time']}"
        markdown = "####" + " | ".join([kickoff, match_data['competition']]) + "\n\n"
        
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
            home_link = f'[{match_data["home"]["team"]}]({sr})'
        except KeyError:
            home_link = match_data["home"]["team"]
        
        try:
            sr = self.bot.teams[away]["subreddit"]
            away_link = f'[{match_data["away"]["team"]}]({sr})'
        except KeyError:
            away_link = match_data["away"]["team"]
        
        score = match_data['score'] if ":" not in match_data['score'] else "vs"
        markdown += f"# {home_icon} {home_link} {score} {away_link} {away_icon}\n\n"
        
        if not is_post_match:
            title = f"Match Thread: {home} vs {away}"
        else:
            title = f"Post-Match Thread: {home} {score} {away}"
        
        try:
            markdown += "####" + match_data['penalties'] + "\n\n"
        except KeyError:
            pass
        
        # Referee and Venue
        try:
            referee = f"**🙈 Referee**: {match_data['referee']}" if match_data['referee'] else ""
        except KeyError:
            referee = ""
        
        try:
            stadium = f"**🥅 Venue**: {match_data['stadium']}" if match_data['stadium'] else ""
        except KeyError:
            stadium = ""
        try:
            attendance = f" (👥 Attendance: {match_data['attendance']})" if match_data['attendance'] else ""
        except KeyError:
            attendance = ""
        markdown += "####" + " | ".join([i for i in [referee, stadium, attendance] if i]) + "\n\n"
        
        # Match Threads Bar.
        archive = "[Match Thread Archive](https://www.reddit.com/r/NUFC/wiki/archive)" if subreddit.lower() in [
            "nufc", "themagpiescss"] else ""
        
        # Convert our links to
        try:
            mts = " | ".join([f"[{k}]({v})" for k, v in match_data['threads'].items()] + [archive])
        except KeyError:
            mts = archive
        markdown += "---\n\n##" + mts + "\n\n---\n\n"
        
        print("?!")
        
        # Radio, TV.
        if not is_post_match:
            if subreddit.lower() in ["nufc", "themagpiescss"]:
                markdown += "[📻 Radio Commentary](https://www.nufc.co.uk/liveAudio.html)\n\n"
                markdown += "[](#icon-discord) [Join the chat with us on Discord](http://discord.gg/tbyUQTV)\n\n"
                try:
                    markdown += f"📺🇬🇧 **TV** (UK): {match_data['tv']['uk_tv']}\n\n" if match_data["tv"][
                        "uk_tv"] else ""
                    markdown += f"📺🌍 **TV** (Intl): [International TV Coverage]({match_data['tv']['link']})\n\n" \
                        if match_data["tv"]["link"] else ""
                except KeyError:
                    pass
        
        def format_team(match_data_team, align_mode):
            md = []
            smd = []
            for p in match_data_team["xi"]:
                # alias
                nm = match_data_team['xi'][p]['name']
                cr = match_data_team['xi'][p]['cards']
                so = match_data_team['xi'][p]['subbed']['replaced_by']
                sm = match_data_team['xi'][p]['subbed']['minute']
                g = match_data_team['xi'][p]['goals']
                g = f"⚽ {g}" if g else ""
                if align_mode == "home":
                    s = f"{so} {sm} 🔻" if so and sm else ""
                    output = f"{s} {g} {cr}{nm} **{p}**"
                else:
                    s = f"🔻 {so} {sm}" if so and sm else ""
                    output = f"**{p}** {nm}{cr} {g} {s}"
                md.append(output)
            
            for p in match_data_team["subs"]:
                # alias
                nm = match_data_team['subs'][p]['name']
                g = match_data_team['subs'][p]['goals']
                g = f"⚽ {g}" if g else ""
                cr = match_data_team['subs'][p]['cards']
                so = match_data_team['subs'][p]['subbed']['replaced_by']
                sm = match_data_team['subs'][p]['subbed']['minute']
                s = f"🔺 {so} {sm}" if so and sm else ""
                output = f"{p} {nm}{cr} {g} {s}"
                smd.append(output)
            return md, smd
        
        home_xi_markdown, home_sub_markdown = format_team(match_data["home"], "home")
        away_xi_markdown, away_sub_markdown = format_team(match_data["away"], "away")
        
        lineup_md = list(zip(home_xi_markdown, away_xi_markdown))
        lineup_md = "\n".join([f"{a} | {b}" for a, b in lineup_md])
        
        # Lineups & all the shite that comes with it.
        if match_data['home']["xi"] and match_data['away']["xi"]:
            markdown += f"---\n\n### Lineups"
            if match_data["formations"]:
                markdown += f" ([Formations]({match_data['formations']}))"
            markdown += f"\n{home_icon} **{home}** |**{away}**  {away_icon} \n"
            markdown += "--:|:--\n"
            markdown += lineup_md + "\n\n"
            markdown += f"---\n\n#### Subs"
            markdown += f"\n{home_icon} {home} | {away} {away_icon}\n"
            markdown += "--:|:--\n"
            markdown += f"{','.join(home_sub_markdown)} | {','.join(away_sub_markdown)}\n"
        
        if match_data["stats"]:
            markdown += f"---\n\n### Match Stats	\n"
            markdown += f"{home_icon} {home}|v|{away} {away_icon}\n" \
                        f"--:|:--:|:--\n"
            
            for h, stat, a in match_data["stats"]:
                markdown += f"{h} | {stat} | {a}\n"
        
        if match_data["pictures"]:
            # TODO: Format these, test if [](xyz 'title here') works
            markdown += "###Match Photos\n\n"
            pic_id = 0
            for caption, url in match_data["pictures"]:
                pic_id += 1
                markdown += f"[{pic_id}]({url} '{caption}') "
            markdown += "\n\n"
        
        formatted_ticker = ""
        for i in match_data['events']:
            no_replace = False
            # TODO: Manually parse all these.
            # Discard non-key events for post-match.
            if is_post_match:
                if not match_data["events"][i]["key"]:
                    continue
            # Alias
            t = match_data["events"][i]['time']
            h = match_data["events"][i]['header']
            e = match_data["events"][i]["emoji"]
            c = match_data["events"][i]["content"]
            n = match_data["events"][i]["note"]
            c = c.replace(h, "")  # strip header from content.
            
            if h == "end of match":
                continue
            
            if h == "Substitute":
                on = match_data["events"][i]["note"]["on"]
                off = match_data["events"][i]["note"]["off"]
                team = match_data["events"][i]["note"]["team"]
                c, n = f"{team} 🔺 {on} 🔻 {off}", ""
            if h == "Corner":
                c = c.replace(' ,', "")
            
            if not no_replace:
                c = c.replace(home, f"{home_icon} {home}").replace(away, f"{away_icon} {away}")
            formatted_ticker += f'{t} {e} **{h}**: {c}{n}\n\n'
        
        markdown += "\n\n---\n\n" + formatted_ticker + "\n\n"
        markdown += "\n\n---\n\n^(*Beep boop, I am /u/Toon-bot, a bot coded ^badly by /u/Painezor. " \
                    "If anything appears to be weird or off, please let him know.*)"
        return title, markdown
    
    # Reddit posting shit.
    def make_post(self, subreddit, title, markdown):
        try:
            return self.bot.reddit.subreddit(subreddit).submit(title, selftext=markdown)
        except RequestException:
            return None
    
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
    
    async def match_thread(self, bbc_link="", subreddit="themagpiescss", discord_channel=None, resume=None):
        # Try to find bbc sports match page.
        async with self.bot.session.get(
                f"http://www.bbc.co.uk/sport/football/teams/{bbc_link}/scores-fixtures") as resp:
            tree = html.fromstring(await resp.text(encoding="utf-8"))
            bbc_link = tree.xpath(".//a[contains(@class,'sp-c-fixture')]/@href")[-1]
            bbc_link = f"http://www.bbc.co.uk{bbc_link}"
        
        # Scrape our Initial Data
        match_data = {}
        match_data = await self.scrape(bbc_link, match_data)
        
        # Fetch Pre-Match Thread if available
        async with self.bot.session.get(f"https://www.reddit.com/r/{subreddit}/") as resp:
            tree = html.fromstring(await resp.text())
            match_data['threads'] = {}
            for i in tree.xpath(".//p[@class='title']/a"):
                title = "".join(i.xpath('.//text()'))
                if "match" not in title.lower():
                    continue
                if not title.lower().startswith("pre") or "match" not in title.lower():
                    continue
                else:
                    prematch = "".join(i.xpath('.//@href'))
                    match_data['threads'] = {'Pre Match Thread': prematch}
                    break
        
        match_data["pictures"] = ""
        match_data["formations"] = ""
        # TODO: Import imgurify code.
        if "Premier League" in match_data["competition"]:
            try:
                url = await self.bot.loop.run_in_executor(None, self.get_pl_link, match_data["home"]["team"])
            except Exception as e:
                print(e)
                print("During matchthread loop / get pl_link.")
            else:
                if url:
                    print(f"Premier league game detected. Additional Data should be parseable: {url}")
                    match_pictures, fm = await self.bot.loop.run_in_executor(None, self.get_pl_data, url)
                    match_data["pictures"] = match_pictures
                    with open('credentials.json') as f:
                        credentials = json.load(f)
                    imgur = ImgurClient(credentials["Imgur"]["Authorization"], credentials["Imgur"]["Secret"])
                    if fm:
                        res = await self.bot.loop.run_in_executor(None,
                                                                  imgur.upload_from_path("formations.png", anon=True))
                        formation = res["link"]
                    else:
                        formation = ""
                    match_data["formations"] = formation
        
        # Get TV info
        match_data['tv'] = await self.fetch_tv(match_data)
        
        # Write Markdown
        title, markdown = await self.write_markdown(match_data)
        
        # Post initial thread.
        post = None
        while post is None:
            if not resume:
                post = await self.bot.loop.run_in_executor(None, self.make_post, subreddit, title, markdown)
            else:
                post = await self.bot.loop.run_in_executor(None, self.fetch_post, resume)
            await asyncio.sleep(5)
        
        match_data["threads"].update({"Match thread": post.url})
        
        if discord_channel:
            e = discord.Embed(color=0xff4500)
            e.description = f"[{post.title}]({post.url})"
            th = "http://vignette2.wikia.nocookie.net/valkyriecrusade/images/b/b5/Reddit-The-Official-App-Icon.png"
            e.set_author(icon_url=th, name="Toonbot: Match Thread Bot")
            e.timestamp = datetime.datetime.now()
            await discord_channel.send(embed=e)
        
        # Match Thread Loop.
        while self.active_module:
            # Scrape new data
            try:
                match_data = await self.scrape(bbc_link, match_data)
            except ServerDisconnectedError:
                await asyncio.sleep(5)
                continue
            
            # Rebuild markdown
            markdown = await self.write_markdown(match_data, subreddit=subreddit)
            # Edit post
            await self.bot.loop.run_in_executor(None, editpost, post, markdown)
            
            # Repeat
            if self.stop_match_thread:
                break
            
            await asyncio.sleep(60)
        
        # Post Match
        if not self.active_module:
            return
        
        # Grab Final Data.
        match_data = await self.scrape(bbc_link, match_data)
        
        # Get markdown for post-match thread.
        title, markdown = await self.write_markdown(match_data, subreddit=subreddit, is_post_match=True)
        
        post_match_instance = None
        while post_match_instance is None:
            post_match_instance = await self.bot.loop.run_in_executor(None, self.make_post, subreddit, title, markdown)
            await asyncio.sleep(5)
        
        pm = f"[Post-Match Thread]({post_match_instance.url})"
        match_data['threads'].update({"Post-Match Thread": pm})
        
        # One final edit to update postmatch into both threads.
        markdown = await self.write_markdown(match_data, subreddit=subreddit, is_post_match=True)
        await self.bot.loop.run_in_executor(None, editpost, post_match_instance, markdown)
        
        markdown = await self.write_markdown(match_data, subreddit=subreddit)
        await self.bot.loop.run_in_executor(None, editpost, post, markdown)
        
        if discord_channel:
            e.description = f"[{post_match_instance.title}]({post_match_instance.url})."
            await discord_channel.send(embed=e)
    
    async def schedule_thread(self, delta, identifier, subreddit="", discord_channel=None, team_url=""):
        await asyncio.sleep(delta.total_seconds())
        if not self.active_module:
            return
        self.scheduled_threads.remove(identifier)
        await self.match_thread(bbc_link=team_url, subreddit=subreddit, discord_channel=discord_channel)
    
    # Schedule a block of match threads.
    async def get_schedule(self):
        # Number of minutes before the match to post
        mtoffset = 30
        subreddit = "nufc"
        discord_channel = self.bot.get_channel(332167049273016320)
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
            
            now = datetime.datetime.now()
            
            for k, v in fixtures.items():
                k = datetime.datetime.strptime(k, "%d %B %Y %I:%M %p")
                
                # Offset by x mins
                k = k - datetime.timedelta(minutes=mtoffset)
                post_in = k - now
                
                schedule_text = f"**{k}**: {v}"
                self.scheduled_threads.append(schedule_text)
                
                self.bot.loop.create_task(
                    self.schedule_thread(post_in, schedule_text, subreddit=subreddit, discord_channel=discord_channel,
                                         team_url=team_url))
    
    # NUFC-Specific Commands.
    def nufccheck(self, ctx):
        if ctx.guild:
            return ctx.guild.id in [238704683340922882, 332159889587699712]
    
    # Debug command - Force Test
    @commands.command()
    @commands.has_permissions(manage_channels=True)
    @commands.is_owner()
    async def forcemt(self, ctx, *, subreddit="themagpiescss"):
        if "r/" in subreddit:
            subreddit = subreddit.split("r/")[1]
        
        await ctx.send(f'Starting a match thread on r/{subreddit}...')
        await self.match_thread(bbc_link="newcastle-united", subreddit=subreddit, discord_channel=ctx.channel)
    
    @commands.command()
    @commands.has_permissions(manage_channels=True)
    @commands.is_owner()
    async def resume(self, ctx, *, linkorbase64):
        await ctx.send(f'Resuming match thread {linkorbase64}')
        await self.match_thread(bbc_link="newcastle-united", subreddit="themagpiescss", discord_channel=ctx.channel,
                                resume=linkorbase64)
    
    @commands.command(aliases=["mtbcheck"])
    @commands.has_permissions(manage_channels=True)
    @commands.is_owner()
    async def checkmtb(self, ctx):
        e = discord.Embed()
        e.colour = 0x000000
        self.scheduled_threads.sort()
        e.description = "\n".join(self.scheduled_threads)
        e.title = "r/NUFC Scheduled Match Threads"
        await ctx.send(embed=e)
    
    @commands.is_owner()
    @commands.has_permissions(manage_channels=True)
    @commands.is_owner()
    async def override(self, ctx, var, *, value):
        setattr(self, var, value)
        await ctx.send(f'Match Thread Bot: Setting "{var}" to "{value}"')


def setup(bot):
    bot.add_cog(MatchThreadCommands(bot))
