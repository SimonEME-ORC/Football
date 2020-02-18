import asyncio
from io import BytesIO

import aiohttp
import discord
from PIL import UnidentifiedImageError
from colorthief import ColorThief


async def get_colour(url):
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


async def paginate(ctx, embeds, id_dict=None):
    # Paginator
    page = 0
    try:
        m = await ctx.send(embed=embeds[page])
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
    ctx.bot.loop.create_task(m.add_reaction("🚫"))  # Delete
    
    def react_check(r, u):
        if r.message.id == m.id and u.id == ctx.author.id:
            e = str(r.emoji)
            return e.startswith(('⏮', '◀', '▶', '⏭', '🚫'))
    
    def id_check(message, idd):
        return message.content in idd
    
    while not ctx.bot.is_closed():
        remind_once = False
        
        # If we're passing an id_dict, we want to get the user's chosen result from the dict.
        # But we always want to be able to change page, or cancel the paginator.
        try:
            if id_dict is not None:
                finished, pending = asyncio.wait([ctx.bot.wait_for("message", check=id_check),
                                                  ctx.bot.wait_for("reaction_add", check=react_check)],
                                                 timeout=60,
                                                 return_when=asyncio.FIRST_COMPLETED)
                
                result = finished.pop().result()
            else:
                result = await ctx.bot.wait_for("reaction_add", check=react_check, timeout=60)
                pending = []
        except asyncio.TimeoutError:
            try:
                await m.clear_reactions()
            except discord.Forbidden:
                pass
            finally:
                return None
        else:
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
                if not remind_once:
                    await ctx.send("I don't have the manage_reactions permissions to remove your reactions,"
                                   " so you'll need to click twice to change page.")
                    remind_once = True
            await m.edit(embed=embeds[page])
        else:
            # We actually return something.
            await m.delete()
            return result.content
