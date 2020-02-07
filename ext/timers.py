from copy import deepcopy

from discord.ext import commands
import datetime
import discord

from ext.utils.embed_paginator import paginate
from ext.utils.timed_events import parse_time, spool_reminder


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_module = True
        self.bot.reminders = []  # A list of tasks.
        self.bot.loop.create_task(self.spool_initial)
        
    def cog_unload(self):
        for i in self.bot.reminders:
            i.cancel()
    
    async def spool_initial(self):
        connection = self.bot.db.acqurie()
        records = await connection.fetch("""SELECT * FROM reminders""")
        for r in records:
            self.bot.reminders.append(self.bot.loop.create_task(spool_reminder(self.bot, r)))
            
    @commands.command(aliases=['reminder', 'remind', 'remindme'])
    async def timer(self, ctx, time, *, message: commands.clean_content):
        """ Remind you of something at a specified time.
            Format is remind 1d2h3m4s <note>, e.g. remind 1d3h Kickoff."""
        delta = await parse_time(time.lower())
        
        remind_at = datetime.datetime.now() + delta
        human_time = datetime.datetime.strftime(remind_at, "%H:%M:%S on %a %d %b")
        
        connection = await self.bot.db.acquire()
        record = await connection.execute(""" INSERT INTO reminders (message_id, channel_id, guild_id,
        reminder_content,
        created_time, target_time. user_id) VALUES ($1, $2, $3, $4, $5, $6, %7) RETURNING *""", ctx.message.id,
                                          ctx.channel.id, ctx.guild.id, message, datetime.datetime.now(), remind_at,
                                          ctx.author.id)
        await self.bot.db.release(connection)
        self.bot.reminders.append(self.bot.loop.create_task(spool_reminder(ctx.bot, record)))
        
        e = discord.Embed()
        e.title = "⏰ Reminder Set"
        e.description = f"{ctx.author.mention} You will be reminded about \n{message}\nat\n {human_time}"
        e.colour = 0x00ffff
        e.timestamp = remind_at
        await ctx.send(embed=e)
    
    @commands.command(aliases=["timers"])
    async def reminders(self, ctx):
        """ Check your active reminders """
        connection = await self.bot.db.acquire()
        records = await connection.fetch(""" SELECT * FROM reminders WHERE user_id = $1 """, ctx.author.id)
        await self.bot.db.release(connection)
        
        embeds = []
        e = discord.Embed()
        e.description = ""
        e.colour = 0x7289DA
        e.title = f"⏰ {ctx.author.name}'s reminders"
        for r in records:
            delta = r['target_time'] - datetime.datetime.now()
            this_string = "**`" + str(delta).split(".")[0] + "`** " + r['reminder_content'] + "\n"
            if len(e.description) + len(this_string) > 2000:
                embeds.append(deepcopy(e))
                e.description = ""
            else:
                e.description += this_string
        embeds.append(e)
        await paginate(ctx, embeds)

# TODO: timed poll.


def setup(bot):
    bot.add_cog(Reminders(bot))
