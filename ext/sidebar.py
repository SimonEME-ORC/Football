from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By
from ext.utils.selenium_driver import spawn_driver
from discord.ext import commands, tasks
from io import BytesIO
from PIL import Image
from lxml import html
import datetime
import discord
import math
import praw
import re


def build_sidebar(sb, table, fixtures, res, last_result, match_threads):
    sb += table + fixtures + "* Previous Results\n"
    
    timestamp = f"\n#####Sidebar auto-updated {datetime.datetime.now().strftime('%a %d %b at %H:%M')}\n"
    footer = timestamp + last_result + match_threads + "\n\n[](https://discord.gg/TuuJgrA)"
    results_header = "\n W|Home|-|Away\n--:|--:|:--:|:--\n"
    
    # Get length, append more results to max length.
    buffer = len(results_header) + 14  # 14 for "previous results"
    accepted = []
    count = 0
    for i in res:
        # Every 20 rows we buffer the length of  another header.
        if count % 20 == 0:
            buffer += len(results_header)
        
        # Every row we buffer the length of the new result.
        if (len(sb + i + footer) + buffer) < 10220:
            accepted.append(i)
            buffer += len(i)
            count += 1
        else:
            break  # If it's too long, we stop iterating.
    
    fixture_blocks = (len(accepted) // 20) + 1
    per_block = math.ceil(len(accepted) / fixture_blocks)
    
    chunks = []  # Evenly divide between number of blocks
    for i in range(0, len(accepted), per_block):
        chunks.append(accepted[i:i + per_block])
    
    # Reverse due to how the CSS is handled.
    chunks.reverse()
    
    for i in chunks:
        sb += results_header
        sb += "".join(i)
        if len(i) < per_block:
            sb += "||||.\n"  # End the sub-table.
    
    # Build end of sidebar.
    sb += footer
    return sb


class Sidebar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.reddit = praw.Reddit(**bot.credentials["Reddit"])
        self.driver = None
        self.bot.teams = None
        self.bot.sidebar = self.sidebar_loop.start()
        
    def cog_unload(self):
        self.sidebar_loop.cancel()
        if self.driver is not None:
            self.driver.quit()
    
    async def cog_check(self, ctx):
        if ctx.guild is not None:
            return ctx.guild.id in [332159889587699712, 250252535699341312]
    
    @tasks.loop(hours=6)
    async def sidebar_loop(self):
        table = await self.table()
        sb, fixtures, results, last_result, get_match_threads = await self.bot.loop.run_in_executor(None, self.get_data)
        sb = build_sidebar(sb, table, fixtures, results, last_result, get_match_threads)
        await self.bot.loop.run_in_executor(None, self.post_sidebar, sb)

    @sidebar_loop.before_loop
    async def fetch_team_data(self):
        await self.bot.wait_until_ready()
        connection = await self.bot.db.acquire()
        print("Fetching teams...")
        self.bot.teams = await connection.fetch("""SELECT * FROM team_data""")
        await self.bot.db.release(connection)
        print("Fetched!")

    @commands.command(invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def sidebar(self, ctx, *, caption=None):
        """ Force a sidebar update, or use sidebar manual """
        async with ctx.typing():
            # Check if message has an attachment, for the new sidebar image.
            if caption is not None:
                # The wiki on r/NUFC has two blocks of --- surrounding the "caption"
                # We get the old caption, then replace it with the new one, then re-upload all of the data.
                sb = await self.bot.loop.run_in_executor(None, self.get_old_sidebar)
                caption = f"---\n\n> {caption}\n\n---"
                sb = re.sub(r'---.*?---', caption, sb, flags=re.DOTALL)
                await self.bot.loop.run_in_executor(None, self.post_wiki, sb)
            
            if ctx.message.attachments:
                s = self.bot.reddit.subreddit("NUFC")
                await ctx.message.attachments[0].save("sidebar.png")
                s.stylesheet.upload('sidebar', "sidebar.png")
                style = s.stylesheet().stylesheet
                s.stylesheet.update(style, reason=f"{ctx.author.name} Updated sidebar image via discord.")
            
            # Scrape
            sb, fixtures, results, last_result, match_threads = await self.bot.loop.run_in_executor(None, self.get_data)
            table = await self.table()
            sb = build_sidebar(sb, table, fixtures, results, last_result, match_threads)
            # post
            await self.bot.loop.run_in_executor(None, self.post_sidebar, sb)
        
            # Embed.
            e = discord.Embed(color=0xff4500)
            th = "http://vignette2.wikia.nocookie.net/valkyriecrusade/images/b/b5/Reddit-The-Official-App-Icon.png"
            e.set_author(icon_url=th, name="Sidebar updater")
            e.description = f"Sidebar for http://www.reddit.com/r/NUFC updated."
            e.timestamp = datetime.datetime.now()
            await ctx.send(embed=e)
    
    def upload_image(self, image):
        self.bot.reddit.subreddit("NUFC").stylesheet.upload('sidebar', image)
    
    def post_wiki(self, wikisidebar):
        s = self.bot.reddit.subreddit("NUFC")
        s.wiki['sidebar'].edit(wikisidebar, reason="Updated Sidebar Caption")
    
    def get_old_sidebar(self):
        return self.bot.reddit.subreddit("NUFC").wiki['sidebar'].content_md
    
    def post_sidebar(self, sidebar):
        self.bot.reddit.subreddit("NUFC").mod.update(description=sidebar)
    
    def get_data(self):
        self.driver = spawn_driver() if not self.driver else self.driver
        sb = self.get_old_sidebar()
        fixtures = self.fixtures()
        results, last_result, last_opponent = self.results()
        match_threads = self.get_match_threads(last_opponent)
        return sb, fixtures, results, last_result, match_threads
    
    def get_match_threads(self, last_opponent):
        last_opponent = last_opponent.split(" ")[0]
        for i in self.bot.reddit.subreddit('NUFC').search('flair:"Pre-match thread"', sort="new", syntax="lucene"):
            if last_opponent in i.title:
                pre = f"[Pre]({i.url.split('?ref=')[0]})"
                break
        else:
            pre = "Pre"
        for i in self.bot.reddit.subreddit('NUFC').search('flair:"Match thread"', sort="new", syntax="lucene"):
            if not i.title.startswith("Match"):
                continue
            if last_opponent in i.title:
                match = f"[Match]({i.url.split('?ref=')[0]})"
                break
        else:
            match = "Match"
        
        for i in self.bot.reddit.subreddit('NUFC').search('flair:"Post-match thread"', sort="new", syntax="lucene"):
            if last_opponent in i.title:
                post = f"[Post]({i.url.split('?ref=')[0]})"
                break
        else:
            post = "Post"
        
        return f"\n\n### {pre} - {match} - {post}"
    
    async def table(self):
        async with self.bot.session.get('http://www.bbc.co.uk/sport/football/premier-league/table') as resp:
            if resp.status != 200:
                return "Retry"
            tree = html.fromstring(await resp.text())
        
        table_data = ("\n\n* Premier League Table"
                      "\n\n Pos.|Team *click to visit subreddit*|P|W|D|L|GD|Pts"
                      "\n--:|:--|:--:|:--:|:--:|:--:|:--:|:--:\n")
        for i in tree.xpath('.//table[contains(@class,"gs-o-table")]//tbody/tr')[:20]:
            p = i.xpath('.//td//text()')
            rank = p[0].strip()  # Ranking
            movement = p[1].strip()
            if "hasn't" in movement:
                movement = ''
            elif "up" in movement:
                movement = '🔺'
            elif "down" in movement:
                movement = '🔻'
            else:
                movement = "?"
            team = p[2]
            try:
                # Insert subreddit link from db
                team = [i for i in self.bot.teams if i['name'] == team][0]
                team = f"[{team['name']}]({team['subreddit']})"
            except IndexError:
                print(team, "Not found in", [i['name'] for i in self.bot.teams])
            played = p[3]
            won = p[4]
            drew = p[5]
            lost = p[6]
            goal_diff = p[9]
            points = p[10]
            
            if "Newcastle" in team:
                table_data += f"{movement} {rank} | **{team}** | **{played}** | **{won}** | **{drew}** | **{lost}** | "\
                              f"**{goal_diff}** | **{points}**\n"
            else:
                table_data += f"{movement} {rank} | {team} | {played} | {won} | {drew} | {lost} | " \
                              f"{goal_diff} | {points}\n"
        return table_data
    
    def fixtures(self):
        self.driver.get("http://www.flashscore.com/team/newcastle-utd/p6ahwuwJ/fixtures/")
        xpath = './/div[@class="sportName soccer"]'
        WebDriverWait(self.driver, 5).until(ec.visibility_of_element_located((By.XPATH, xpath)))
        tree = html.fromstring(self.driver.page_source)
        
        fixblock = []
        for i in tree.xpath(".//div[contains(@class,'sportName soccer')]/div"):
            # Date
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
            
            matchid = "".join(i.xpath(".//@id")).split('_')[2]
            lnk = f"http://www.flashscore.com/match/{matchid}/#h2h;overall"
            
            h, a = i.xpath('.//div[contains(@class,"event__participant")]/text()')
            if '(' in h:
                h = h.split('(')[0].strip()
            if '(' in a:
                a = a.split('(')[0].strip()
            
            ic = "[](#icon-home)" if "Newcastle" in h else "[](#icon-away)"
            op = h if "Newcastle" in a else a
            
            try:
                op = [i for i in self.bot.teams if i['name'] == op][0]
                op = f"{op['icon']}{op['short_name']}"
            except IndexError:
                print(f"Sidebar - fixtures - No db entry for: {op}")
            fixblock.append(f"[{d}]({lnk})|{ic}|{op}\n")
        
        fixmainhead = "\n* Upcoming fixtures"
        fixhead = "\n\n Date & Time|at|Opponent\n:--:|:--:|:--:|:--|--:\n"
        
        numblocks = (len(fixblock) // 20) + 1
        blocklen = math.ceil(len(fixblock) / numblocks)
        try:
            chunks = [fixblock[i:i + blocklen] for i in range(0, len(fixblock), blocklen)]
        except ValueError:
            return ""
        chunks.reverse()
        for i in chunks:
            if len(i) < blocklen:
                i.append("|||||")
        chunks = ["".join(i) for i in chunks]
        chunks = fixmainhead + fixhead + fixhead.join(chunks)
        return chunks
    
    def results(self):
        self.driver.get("http://www.flashscore.com/team/newcastle-utd/p6ahwuwJ/results/")
        xpath = './/div[@class="sportName soccer"]'
        WebDriverWait(self.driver, 5).until(ec.visibility_of_element_located((By.XPATH, xpath)))
        t = html.fromstring(self.driver.page_source)
        
        resultlist = []
        last_result, last_opponent = "", ""
        
        results = t.xpath(".//div[contains(@class,'sportName soccer')]/div")
        for i in results:
            try:
                match_id = "".join(i.xpath(".//@id")).split('_')[-1]
            except IndexError:
                continue  # Not a match
            
            if not match_id:
                continue  # STILL not a match...
            
            # Hack together link.
            lnk = f"http://www.flashscore.com/match/{match_id}/#match-summary"
            
            # Score
            h, a = i.xpath('.//div[contains(@class,"event__scores")]/span/text()')
            sc = f"[{h} - {a}]({lnk})"
            
            ht, at = i.xpath('.//div[contains(@class,"event__participant")]/text()')
            if '(' in ht:
                ht = ht.split('(')[0]
            if '(' in at:
                at = at.split('(')[0]
            
            ht, at = ht.strip(), at.strip()
            
            # Top of Sidebar Chunk
            if not last_opponent:
                # Fetch badge if required, for the top of the sidebar.
                def get_badge(link, team):
                    self.driver.get(link)
                    frame = self.driver.find_element_by_class_name(f"tlogo-{team}")
                    img = frame.find_element_by_xpath(".//img").get_attribute('src')
                    self.bot.loop.create_task(self.fetch_badge(img))
                
                # last op is for the last game at the top.
                last_opponent = at if "Newcastle" in ht else ht
                
                try:
                    away = [i for i in self.bot.teams if i['name'] == at][0]
                    last_away = f"[{away['short_name']}]({away['subreddit']})"
                except IndexError:
                    get_badge(lnk, "away")
                    last_away = f"[{at}](#temp/)"
                    
                try:
                    home = [i for i in self.bot.teams if i['name'] == ht][0]
                    last_home = f"[{home['short_name']}]({home['subreddit']})"
                except IndexError:
                    get_badge(lnk, "home")
                    last_home = f"[{ht}](#temp/)"
                    
                last_result = f"> {last_home.replace(' (Eng)', '')} {sc} {last_away.replace(' (Eng)', '')}"

            try:
                home = [i for i in self.bot.teams if i['name'] == ht][0]
                home = f"{home['icon']}{home['short_name']})"
            except IndexError:
                home = ht
                
            try:
                away = [i for i in self.bot.teams if i['name'] == at][0]
                away = f"{away['icon']}{away['short_name']})"
            except IndexError:
                away = at
            
            icon = "[D](#icon-draw)"
            icon = "[W](#icon-win)" if ("Newcastle" in home and h > a) or ("Newcastle" in away and a > h) else icon
            icon = "[W](#icon-loss)" if ("Newcastle" in away and h > a) or ("Newcastle" in home and a > h) else icon
            resultlist.append(f"{icon}|{home}|{sc}|{away}\n")
            
        return resultlist, last_result, last_opponent
    
    async def fetch_badge(self, src):
        async with self.bot.session.get(src) as resp:
            if resp.status != 200:
                print("Error {resp.status} downloading image.")
            image = await resp.content.read()
        await self.bot.loop.run_in_executor(None, self.upload_badge, image)
    
    def upload_badge(self, image):
        im = Image.open(BytesIO(image))
        im.save("temporary_badge", "PNG")
        s = self.bot.reddit.subreddit("NUFC")
        s.stylesheet.upload('temp', "temporary_badge")
        style = s.stylesheet().stylesheet
        s.stylesheet.update(style, reason="Update temporary badge image")


def setup(bot):
    bot.add_cog(Sidebar(bot))
