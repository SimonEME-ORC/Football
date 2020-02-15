from concurrent.futures import TimeoutError

import pycountry
import discord
import asyncio
from lxml import html

# Manual Country Code Flag Dict
country_dict = {
    "American Virgin Islands": "vi",
    "Antigua and Barbuda": "ag",
    "Bolivia": "bo",
    "Bosnia-Herzegovina": "ba",
    "Bosnia and Herzegovina": "ba",
    "Botsuana": "bw",
    "British Virgin Islands": "vg",
    "Cape Verde": "cv",
    "Cayman-Inseln": "ky",
    "Chinese Taipei (Taiwan)": "tw",
    "Congo DR": "cd",
    "Curacao": "cw",
    "DR Congo": "cd",
    "Cote d'Ivoire": "ci",
    "CSSR": "cz",
    "Czech Republic": "cz",
    "England": "gb",
    "Faroe Island": "fo",
    "Federated States of Micronesia": "fm",
    "Hongkong": "hk",
    "Iran": "ir",
    "Ivory Coast": "ci",
    "Korea, North": "kp",
    "Korea, South": "kr",
    "Kosovo": "xk",
    "Laos": "la",
    "Macedonia": "mk",
    "Mariana Islands": "mp",
    "Moldova": "md",
    "N/A": "x",
    "Netherlands Antilles": "nl",
    "Neukaledonien": "nc",
    "Northern Ireland": "gb",
    "Osttimor": "tl",
    "Palästina": "ps",
    "Russia": "ru",
    "Scotland": "gb",
    "Sint Maarten": "sx",
    "Southern Sudan": "ss",
    "South Korea": "kr",
    "St. Kitts & Nevis": "kn",
    "St. Louis": "lc",
    "St. Vincent & Grenadinen": "vc",
    "Tahiti": "fp",
    "Tanzania": "tz",
    "The Gambia": "gm",
    "Trinidad and Tobago": "tt",
    "Turks- and Caicosinseln": "tc",
    "USA": "us",
    "Venezuela": "ve",
    "Vietnam": "vn",
    "Wales": "gb"}

unidict = {
    "a": "🇦", "b": "🇧", "c": "🇨", "d": "🇩", "e": "🇪",
    "f": "🇫", "g": "🇬", "h": "🇭", "i": "🇮", "j": "🇯",
    "k": "🇰", "l": "🇱", "m": "🇲", "n": "🇳", "o": "🇴",
    "p": "🇵", "q": "🇶", "r": "🇷", "s": "🇸", "t": "🇹",
    "u": "🇺", "v": "🇻", "w": "🇼", "x": "🇽", "y": "🇾", "z": "🇿"
}


def get_flag(country):
    # Check if pycountry has country
    if not country:
        return
    if country.lower() in ["england", "scotland", "wales"]:
        country = f":{country.lower()}:"
        return country

    try:
        country = pycountry.countries.get(name=country.title()).alpha_2
    except (KeyError, AttributeError):
        try:
            # else revert to manual dict.w
            country = country_dict[country]
        except KeyError:
            print(f"Fail for: {country}")
    country = country.lower()

    for key, value in unidict.items():
        country = country.replace(key, value)
    return country


async def parse_players(trs):
    output, targets = [], []
    for i in trs:
        pname = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/text()'))
        player_link = "".join(i.xpath('.//a[@class="spielprofil_tooltip"]/@href'))
        player_link = f"http://transfermarkt.co.uk{player_link}"
        team = "".join(i.xpath('.//td[3]/a/img/@alt'))
        tlink = "".join(i.xpath('.//td[3]/a/img/@href'))
        tlink = f"http://transfermarkt.co.uk{tlink}"
        age = "".join(i.xpath('.//td[4]/text()'))
        ppos = "".join(i.xpath('.//td[2]/text()'))
        flag = get_flag("".join(i.xpath('.//td/img[1]/@title')))

        output.append(f"{flag} [{pname}]({player_link}) {age}, {ppos} [{team}]({tlink})")
        targets.append(player_link)
    return output, targets


async def parse_managers(trs):
    output, targets = [], []
    for i in trs:
        mname = "".join(i.xpath('.//td[@class="hauptlink"]/a/text()'))
        mlink = "".join(i.xpath('.//td[@class="hauptlink"]/a/@href'))
        mlink = f"http://transfermarkt.co.uk{mlink}"
        team = "".join(i.xpath('.//td[2]/a/img/@alt'))
        tlink = "".join(i.xpath('.//td[2]/a/img/@href'))
        tlink = f"http://transfermarkt.co.uk{tlink}"
        age = "".join(i.xpath('.//td[3]/text()'))
        job = "".join(i.xpath('.//td[5]/text()'))
        flag = get_flag("".join(i.xpath('.//td/img[1]/@title')))

        output.append(f"{flag} [{mname}]({mlink}) {age}, {job} [{team}]({tlink})")
        targets.append(mlink)
    return output, targets


async def parse_clubs(trs):
    output, targets = [], []
    for i in trs:
        cname = "".join(i.xpath('.//td[@class="hauptlink"]/a/text()'))
        clink = "".join(i.xpath('.//td[@class="hauptlink"]/a/@href'))
        clink = f"http://transfermarkt.co.uk{clink}"
        leagu = "".join(i.xpath('.//tr[2]/td/a/text()'))
        lglin = "".join(i.xpath('.//tr[2]/td/a/@href'))
        flag = get_flag("".join(i.xpath('.//td/img[1]/@title')).strip())
        if leagu:
            club = f"[{cname}]({clink}) ([{leagu}]({lglin}))"
        else:
            club = f"[{cname}]({clink})"

        output.append(f"{flag} {club}")
        targets.append(clink)
    return output, targets


async def parse_refs(trs):
    output, targets = [], []
    for i in trs:
        rname = "".join(i.xpath('.//td[@class="hauptlink"]/a/text()'))
        rlink = "".join(i.xpath('.//td[@class="hauptlink"]/a/@href'))
        rage = "".join(i.xpath('.//td[@class="zentriert"]/text()'))
        flag = get_flag("".join(i.xpath('.//td/img[1]/@title')).strip())

        output.append(f"{flag} [{rname}]({rlink}) {rage}")
        targets.append(rlink)
    return output, targets


async def parse_leagues(trs):
    output, targets = [], []
    for i in trs:
        cupname = "".join(i.xpath('.//td[2]/a/text()'))
        cup_link = "".join(i.xpath('.//td[2]/a/@href'))
        flag = "".join(i.xpath('.//td[3]/img/@title'))
        if flag:
            flag = get_flag(flag)
        else:
            flag = "🌍"

        output.append(f"{flag} [{cupname}]({cup_link})")
        targets.append(cup_link)
    return output, targets


async def parse_int(trs):
    output, targets = [], []
    for i in trs:
        cup_name = "".join(i.xpath('.//td[2]/a/text()'))
        cup_link = "".join(i.xpath('.//td[2]/a/@href'))

        output.append(f"🌍 [{cup_name}]({cup_link})")
        targets.append(cup_link)
    return output, targets


async def parse_agent(trs):
    output, targets = [], []
    for i in trs:
        company = "".join(i.xpath('.//td[2]/a/text()'))
        link = "".join(i.xpath('.//td[2]/a/@href'))

        output.append(f"[{company}]({link})")
        targets.append(link)
    return output, targets


async def fetch_page(self, ctx, category, query, page):
    p = {"query": query, self.cats[category]["querystr"]: page}
    url = 'http://www.transfermarkt.co.uk/schnellsuche/ergebnis/schnellsuche'
    async with self.bot.session.post(url, params=p) as resp:
        if resp.status != 200:
            await ctx.send(f"HTTP Error connecting to transfermarkt: {resp.status}")
            return None
        tree = html.fromstring(await resp.text())
    categ = self.cats[category]["cat"]

    # Get trs of table after matching header / {categ} name.
    matches = f".//div[@class='box']/div[@class='table-header'][contains(text(),'{categ}')]/following::div[" \
              f"1]//tbody/tr"

    e = discord.Embed()
    e.colour = 0x1a3151
    e.title = "View full results on transfermarkt"
    e.url = str(resp.url)
    e.set_author(name="".join(tree.xpath(f".//div[@class='table-header'][contains(text(),'{categ}')]/text()")))
    e.description = ""
    try:
        total_pages = int("".join([i for i in e.author.name if i.isdigit()])) // 10 + 1
    except ValueError:
        total_pages = 0
    e.set_footer(text=f"Page {page} of {total_pages}")
    return e, tree.xpath(matches), total_pages


def make_embed(e, lines, targets, special):
    if special:
        e.description = "Please type matching ID#\n\n"
    items = {}
    item_id = 0

    if special:
        for i, j in zip(lines, targets):
            items[str(item_id)] = j
            e.description += f"`[{item_id}]`:  {i}\n"
            item_id += 1
        return e, items
    else:
        for i in lines:
            e.description += f"{i}\n"
        return e, items


async def search(self, ctx, qry, category, special=False, whitelist_fetch=False):
    page = 1
    e, tree, total_pages = await fetch_page(self, ctx, category, qry, page)
    if not tree:
        return await ctx.send("No results.")

    lines, targets = await self.cats[category]["parser"](tree)

    if whitelist_fetch:
        return lines, targets

    e, items = make_embed(e, lines, targets, special)

    # Create message and add reactions
    m = await ctx.send(embed=e)

    if total_pages > 2:
        await m.add_reaction("⏮")  # first
    if total_pages > 1:
        await m.add_reaction("◀")  # prev
        await m.add_reaction("▶")  # next
    if total_pages > 2:
        await m.add_reaction("⏭")  # last
        self.bot.loop.create_task(m.add_reaction("🚫"))  # eject

    # Only respond to user who invoked command.
    def page_check(reaction, user):
        if reaction.message.id == m.id and user.id == ctx.author.id:
            ej = str(reaction.emoji)
            if ej.startswith(('⏮', '◀', '▶', '⏭', '🚫')):
                return True

    def reply_check(msg):
        if ctx.message.author.id == msg.author.id:
            return msg.content in items
        
    # Reaction Logic Loop.
    while True:
        try:
            received, dead = await asyncio.wait(
                [ctx.bot.wait_for('message', check=reply_check),
                 ctx.bot.wait_for('reaction_add', check=page_check)],
                timeout=30, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.TimeoutError:
            try:
                await m.edit(content="Timed out waiting for you to reply.", embed=None)
                return await m.clear_reactions()
            except discord.Forbidden:
                return await m.delete()

        for i in dead:
            i.cancel()
        res = received.pop().result()
        if isinstance(res, discord.Message):
            # It's a message.
            await m.delete()
            await self.cats[category]["outfunc"](ctx, e, items[res.content])
            return await res.delete()
        else:
            # it's a reaction.
            reaction, user = res
            if reaction.emoji == "⏮":  # first
                page = 1
            elif reaction.emoji == "◀":  # prev
                page = page - 1 if page > 1 else page
            elif reaction.emoji == "▶":  # next
                page = page + 1 if page < total_pages else page
            elif reaction.emoji == "⏭":  # last
                page = total_pages
            elif reaction.emoji == "🚫":  # eject
                return await m.delete()
            await m.remove_reaction(reaction.emoji, ctx.message.author)

        # Fetch the next page of results.
        e, tree, total_pages = await fetch_page(self, ctx, category, qry, page)
        lines, targets = await self.cats[category]["parser"](tree)
        e, items = make_embed(e, lines, targets, special)  # reassign item dict.
        await m.edit(embed=e)
