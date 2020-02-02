from discord.ext import commands
import discord
import asyncio
import datetime
import typing
import json

# TODO: Port tempban to new system
# TODO: Port tempmute to new system
# TODO: Time Parser into utils cog
# TODO: Move those to mod cog
# TODO: timed poll.

from ext.utils.time_parser import parse_time


class Timers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_module = True
        
        with open('reminders.json') as f:
            bot.reminders = json.load(f)
        
        for k, v in bot.reminders.items():
            self.bot.loop.create_task(self.spool_reminders(k, v))
    
    async def _save(self):
        with await self.bot.timerlock:
            with open('reminders.json', "w", encoding='utf-8') as f:
                json.dump(self.bot.reminders, f, ensure_ascii=True,
                          indent=4, separators=(',', ':'))
    
    def cog_unload(self):
        self.active_module = False
    
    async def spool_reminders(self, msgid, values):
        dtc = datetime.datetime.strptime(values["time"], '%Y-%m-%d %H:%M:%S.%f')
        time = dtc - datetime.datetime.now()
        
        await asyncio.sleep(time.total_seconds())
        
        if not self.active_module:
            return
        
        destination = self.bot.get_channel(values["destination"])
        member = destination.guild.get_member(values["user"]).mention
        ts = datetime.datetime.strptime(values['ts'], '%Y-%m-%d %H:%M:%S.%f')
        
        e = discord.Embed()
        e.timestamp = ts
        e.colour = 0x00ff00
        
        if "message" in values:
            message = values['message']
            e.title = f"⏰ Reminder"
            e.description = message
            try:  # Jump to message if found.
                e.description += f"\n\n[⬆️ Jump to message.]({values['jumpurl']})"
            except AttributeError as f:
                print(f"Attribute Error {f}")
        if "mode" in values:
            if values["mode"] == "unban":
                try:
                    await self.bot.http.unban(values["target"], self.bot.get_channel(values["destination"]).guild)
                    e.description = f'User id {values["target"]} was unbanned'
                except discord.NotFound:
                    e.description = f"Failed to unban user id {values['target']} - are they already unbanned?"
        
        await destination.send(member, embed=e)
        del self.bot.reminders[msgid]
        await self._save()
    
    @commands.command(aliases=['reminder', 'remind', 'remindme'])
    async def timer(self, ctx, time, *, message: commands.clean_content):
        """ Remind you of something at a specified time.
            Format is remind 1d2h3m4s <note>, e.g. remind 1d3h Kickoff."""
        
        delta = await parse_time(time.lower())
        
        remind_at = datetime.datetime.now() + delta
        human_time = datetime.datetime.strftime(remind_at, "%H:%M:%S on %a %d %b")
        
        e = discord.Embed()
        e.title = "⏰ Reminder Set"
        e.description = message
        e.colour = 0x00ffff
        e.timestamp = remind_at
        
        await ctx.send(embed=e)
        
        reminder = {
            ctx.message.id: {
                "user": ctx.author.id,
                "destination": ctx.channel.id,
                "message": message,
                "time": human_time,
                "ts": str(ctx.message.created_at),
                "jumpurl": ctx.message.jump_url
            }
        }
        
        self.bot.reminders.update(reminder)
        await self._save()
        for k, v in reminder.items():
            self.bot.loop.create_task(self.spool_reminders(k, v))
    
    @commands.command(aliases=["timers"])
    async def reminders(self, ctx):
        """ Check your active reminders """
        
        e = discord.Embed()
        e.description = ""
        e.colour = 0x7289DA
        e.title = f"⏰ {ctx.author.name}'s reminders"
        
        for i in self.bot.reminders.keys():
            if self.bot.reminders[i]["user"] != ctx.author.id:
                continue
            
            delta = datetime.datetime.strptime(self.bot.reminders[i]['time'],
                                               '%Y-%m-%d %H:%M:%S.%f') - datetime.datetime.now()
            # TODO: Paginate this.
            e.description += "**`" + str(delta).split(".")[0] + "`** " + self.bot.reminders[i]['message'] + "\n"
        await ctx.send(embed=e)
    
    @commands.command()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def tempban(self, ctx, arg1: typing.Union[discord.Member, str],
                      arg2: typing.Union[discord.Member, str], *, reason: commands.clean_content = None):
        """ Temporarily ban a member from the server """
        if isinstance(arg1, discord.Member):
            member = arg1
            time = arg2
        elif isinstance(arg2, discord.Member):
            member = arg2
            time = arg1
        else:
            return await ctx.send("That doesn't look right. try again.")
        
        delta = await parse_time(time.lower())
        remindat = datetime.datetime.now() + delta
        human_time = datetime.datetime.strftime(remindat, "%H:%M:%S on %a %d %b")
        try:
            await ctx.guild.ban(member, reason=reason)
        except discord.Forbidden:
            return await ctx.send("🚫 I can't ban that member failed.")
        
        reminder = {
            ctx.message.id: {
                "user": ctx.author.id,
                "destination": ctx.channel.id,
                "message": f"Temporary ban ending for {member}",
                "target": member.id,
                "mode": "unban",
                "time": str(human_time),
                "ts": str(ctx.message.created_at),
                "jumpurl": ctx.message.jump_url
            }
        }
        
        self.bot.reminders.update(reminder)
        await self._save()
        await ctx.send(f'☠️Banned {member.mention} until {human_time}')
        for k, v in reminder.items():
            self.bot.loop.create_task(self.spool_reminders(k, v))


def setup(bot):
    bot.add_cog(Timers(bot))
