import asyncio
import discord


async def paginate(ctx, embeds):
    # Paginator
    page = 0
    try:
        m = await ctx.send(embed=embeds[page])
    except IndexError:
        await ctx.send("Couldn't find anything.")

    # Add reactions
    if len(embeds) > 1:
        if len(embeds) > 2:
            ctx.bot.loop.create_task(m.add_reaction("⏮")) # first
        ctx.bot.loop.create_task(m.add_reaction("◀"))  # prev
        ctx.bot.loop.create_task(m.add_reaction("▶"))  # next
        if len(embeds) > 2:
            ctx.bot.loop.create_task(m.add_reaction("⏭"))  # last
    ctx.bot.loop.create_task(m.add_reaction("🚫")) # Delete

    def check(reaction, user):
        if reaction.message.id == m.id and user == ctx.author:
            e = str(reaction.emoji)
            return e.startswith(('⏮', '◀', '▶', '⏭','🚫'))

    while not ctx.bot.is_closed():
        remind_once = False
        try:
            reaction, user = await ctx.bot.wait_for("reaction_add", check=check, timeout=60)
        except asyncio.TimeoutError:
            try:
                await m.clear_reactions()
            except discord.Forbidden:
                pass
            return
        try:
            if reaction.emoji == "⏮":  # first
                page = 0
                await m.remove_reaction("⏮", ctx.author)
            if reaction.emoji == "◀":  # prev
                if page > 0:
                    page += -1
                await m.remove_reaction("◀", ctx.author)
            if reaction.emoji == "▶":  # next
                if page < len(embeds) - 1:
                    page += 1
                await m.remove_reaction("▶", ctx.author)
            if reaction.emoji == "⏭":  # last
                page = len(embeds) - 1
                await m.remove_reaction("⏭", ctx.author)
            if reaction.emoji == "🚫":  # Delete:
                return await m.delete()
        except discord.Forbidden:
            if not remind_once:
                await ctx.send("I don't have the manage reactions permissions to remove your reactions,"
                               " so you'll need to click twice to change page.")
                remind_once = True
        await m.edit(embed=embeds[page])