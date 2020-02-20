import asyncio
from io import BytesIO

import aiohttp
import discord
from PIL import UnidentifiedImageError
from colorthief import ColorThief


ICON_URL = "http://pix.iemoji.com/twit33/0056.png"

async def get_colour(url=None):
    if url is None:
        return discord.Colour.blurple()
    
    async with aiohttp.ClientSession() as cs:
        async with cs.get(url) as resp:
            r = await resp.read()
            # Convert to base 16 int.
            f = BytesIO(r)
            try:
                c = ColorThief(f).get_color(quality=1)
                return int('%02x%02x%02x' % c, 16)
            except UnidentifiedImageError:
                return discord.Colour.blurple()


async def paginate(ctx, embeds, preserve_footer=False, id_dict=None):
    count = 0
    for e in embeds:
        count += 1
        page_line = f"{ctx.author}: Page {count} of {len(embeds)}"
        if preserve_footer:
            e.add_field(name="Page", value=page_line)
        else:
            e.set_footer(icon_url=ICON_URL, text=page_line)
    
    # Paginator
    page = 0
    try:
        if ctx.me.permissions_in(ctx.channel).add_reactions:
            if not ctx.me.permissions_in(ctx.channel).manage_messages :
                if ctx.guild is None:
                    warn = "I can't remove your reactions in DMs, so you'll have to click twice."
                else:
                    warn = "I don't have manage_messages permissions, so you'll have to click twice."
                m = await ctx.send(warn, embed=embeds[page])
            else:
                m = await ctx.send(embed=embeds[page])
        else:
            if ctx.guild is not None:
                warn = "I don't have add_reaction permissions so I can only show you the first page of results."
                return await ctx.send(warn, embed=embeds[page])
    except IndexError:
        return await ctx.send("Couldn't find anything.")
    
    # Add reactions
    if len(embeds) > 1:
        if len(embeds) > 2:
            ctx.bot.loop.create_task(m.add_reaction("⏮"))  # first
        ctx.bot.loop.create_task(m.add_reaction("◀"))  # prev
        ctx.bot.loop.create_task(m.add_reaction("▶"))  # next
        if len(embeds) > 2:
            ctx.bot.loop.create_task(m.add_reaction("⏭"))  # last
        ctx.bot.loop.create_task(m.add_reaction('🚫'))
    
    def react_check(r, u):
        if r.message.id == m.id and u.id == ctx.author.id:
            e = str(r.emoji)
            return e.startswith(('⏮', '◀', '▶', '⏭', '🚫'))
    
    def id_check(message, idd):
        return message.content in idd
    
    while not ctx.bot.is_closed():
        # If we're passing an id_dict, we want to get the user's chosen result from the dict.
        # But we always want to be able to change page, or cancel the paginator.
        if id_dict is not None:
            finished, pending = asyncio.wait([ctx.bot.wait_for("message", check=id_check),
                                              ctx.bot.wait_for("reaction_add", check=react_check)],
                                             timeout=60,
                                             return_when=asyncio.FIRST_COMPLETED)
            try:
                result = finished.pop().result()
            except KeyError:  # pop from empty set.
                try:
                    await m.clear_reactions()
                except discord.Forbidden:
                    pass
                return None
        else:
            try:
                result = await ctx.bot.wait_for("reaction_add", check=react_check, timeout=60)
            except asyncio.TimeoutError:
                try:
                    await m.clear_reactions()
                except discord.Forbidden:
                    pass
                return None
            else:
                pending = []
        
        # Kill other.
        for i in pending:
            i.cancel()
        
        if len(result) == 2:  # Reaction.
            # We just want to change page, or cancel.
            if result[0].emoji == "⏮":  # first
                page = 0
            if result[0].emoji == "◀":  # prev
                if page > 0:
                    page += -1
            if result[0].emoji == "▶":  # next
                if page < len(embeds) - 1:
                    page += 1
            if result[0].emoji == "⏭":  # last
                page = len(embeds) - 1
            if result[0].emoji == "🚫":  # Delete:
                await m.delete()
                return None
            try:
                await m.remove_reaction(result[0].emoji, ctx.author)
            except discord.Forbidden:
                pass  # swallow this error.
            await m.edit(embed=embeds[page])
        else:
            # We actually return something.
            await m.delete()
            return result.content
