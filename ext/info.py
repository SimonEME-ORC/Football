from discord.ext import commands
from collections import Counter
import datetime
import discord
import typing
import copy


class Info(commands.Cog):
    """ Get information about users or servers. """
    
    def __init__(self, bot):
        self.bot = bot
        self.bot.commands_used = Counter()
    
    @commands.command(aliases=['botstats', "uptime", "hello", "inviteme"])
    async def about(self, ctx):
        """Tells you information about the bot itself."""
        e = discord.Embed(colour=0x2ecc71, timestamp=self.bot.user.created_at)
        owner = await self.bot.fetch_user(self.bot.owner_id)
        e.set_footer(text=f"Toonbot is coded (badly) by {owner} and was created on ")
        e.set_thumbnail(url=ctx.me.avatar_url)
        e.title = f"{ctx.me.display_name} ({ctx.me})" if not ctx.me.display_name == "ToonBot" else "Toonbot"
        
        # statistics
        total_members = sum(len(s.members) for s in self.bot.guilds)
        members = f"{total_members} Members across {len(self.bot.guilds)} servers."
        
        prefixes = f"\nYou can use `.tb help` to see my commands."
        
        e.description = f"I do football lookup related things.\n I have {members}"
        e.description += prefixes
        
        technical_stats = f"{datetime.datetime.now() - self.bot.initialised_at}\n"
        technical_stats += f"{sum(self.bot.commands_used.values())} commands ran since last reload."
        e.add_field(name="Uptime", value=technical_stats, inline=False)
        
        invite_and_stuff = f"[Invite me to your server]" \
                           f"(https://discordapp.com/oauth2/authorize?client_id=250051254783311873" \
                           f"&permissions=67488768&scope=bot)\n"
        invite_and_stuff += f"[Join my Support Server](http://www.discord.gg/a5NHvPx)\n"
        invite_and_stuff += f"[Toonbot on Github](https://github.com/Painezor/Toonbot)"
        e.add_field(name="Using me", value=invite_and_stuff, inline=False)
        await ctx.send(embed=e)
    
    @commands.command()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def permissions(self, ctx, *, member: discord.Member = None):
        """Shows a member's permissions."""
        if member is None:
            member = ctx.author
        permissions = ctx.channel.permissions_for(member)
        permissions = "\n".join([f"{i[0]} : {i[1]}" for i in permissions])
        await ctx.send(f"```py\n{permissions}```")
    
    @commands.command(aliases=["lastmsg", "lastonline", "lastseen"])
    async def seen(self, ctx, t: discord.Member = None):
        """ Find the last message from a user in this channel """
        if t == None:
            return await ctx.send("No user provided")
        
        m = await ctx.send("Searching...")
        with ctx.typing():
            if ctx.author == t:
                return await ctx.send("Last seen right now, being an idiot.")
            
            async for msg in ctx.channel.history(limit=50000):
                if msg.author.id == t.id:
                    if t.id == 178631560650686465:
                        c = (f"{t.mention} last seen being a spacker in "
                             f" {ctx.channel.mention} at {msg.created_at} "
                             f"saying '{msg.content}'")
                        await m.edit(content=c)
                    else:
                        c = (f"{t.mention} last seen in {ctx.channel.mention} "
                             f"at {msg.created_at} saying '{msg.content}'")
                        await m.edit(content=c)
                    return
            await m.edit(content="Couldn't find a recent message from that user.")
    
    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def info(self, ctx, *, member: typing.Union[discord.Member, int] = None):
        """Shows info about a member.
        This cannot be used in private messages. If you don't specify
        a member then the info returned will be yours.
        """
        if member is None:
            member = ctx.author
        elif isinstance(member, int):
            member = await self.bot.fetch_user(member)
        
        e = discord.Embed()
        
        shared = sum(1 for m in self.bot.get_all_members() if m.id == member.id)
        
        e.set_footer(text='Account created').timestamp = member.created_at
        
        try:
            roles = [role.name.replace('@', '@\u200b') for role in member.roles]
            e.add_field(name='Roles', value=', '.join(roles), inline=False)
            voice = member.voice
            if voice is not None:
                voice = voice.channel
                other_people = len(voice.members) - 1
                voice_fmt = f'{voice.name} with {other_people} others' if other_people else f'{voice.name} alone'
                voice = voice_fmt
                e.add_field(name='Voice Chat', value=voice_fmt, inline=False)
            status = str(member.status).title()
            if status == "Online":
                status = "🟢 Online\n"
            elif status == "Offline":
                status = "🔴 Offline\n"
            else:
                status = f"🟡 {status}\n"
            
            activity = member.activity
            try:
                activity = f"{discord.ActivityType[activity.type]} {activity.name}\n"
            except KeyError:  # Fix on custom status update.
                activity = ""
            
            time_delta = member.joined_at - datetime.datetime.now()
            if time_delta.total_seconds() > 600:  # 10 minutes
                coloured_time = f"```glsl\n[{member.joined_at}]```"  # orange
            elif time_delta.total_seconds() > 1440:  # 1 day
                coloured_time = f"```fix\n[{member.joined_at}]```"  # yellow
            elif time_delta.total_seconds() > 604800:  # 1 week
                coloured_time = f"```brainfuck\n[{member.joined_at}]```"  # grey
            elif time_delta.total_seconds() > 2419200:  # 1 month
                coloured_time = f"```yaml\n[{member.joined_at}]```"  # cyan
            elif time_delta.total_seconds() > 15780000:  # 6 months
                coloured_time = f"```CSS\n{member.joined_at}```"  # green
            else:
                coloured_time = f"```ini\n[{member.joined_at}]```"  # blue
                
            e.add_field(name=f'Joined {ctx.guild.name}', value=coloured_time,inline=False)
            e.colour = member.colour
        except AttributeError:
            status = ""
            activity = ""
            pass
        
        field_1_text = f"{status}ID: {member.id}\n{activity}{shared} shared servers"
        e.add_field(name="User info", value=field_1_text)
        e.set_author(name=str(member), icon_url=member.avatar_url or member.default_avatar_url)
        
        if member.bot:
            e.description = "**🤖 This user is a bot**"
        
        if member.avatar:
            e.set_thumbnail(url=member.avatar_url)
        await ctx.send(embed=e)
    
    @info.command(name='guild', aliases=["server"])
    @commands.guild_only()
    async def server_info(self, ctx):
        """ Shows information about the server """
        guild = ctx.guild
        roles = [role.name.replace('@', '@\u200b') for role in guild.roles]
        
        secret_member = copy.copy(guild.me)
        secret_member.roles = [guild.default_role]
        
        # figure out what channels are 'secret'
        secret_channels = 0
        secret_voice = 0
        text_channels = 0
        for channel in guild.channels:
            perms = channel.permissions_for(secret_member)
            is_text = isinstance(channel, discord.TextChannel)
            text_channels += is_text
            if is_text and not perms.read_messages:
                secret_channels += 1
            elif not is_text and (not perms.connect or not perms.speak):
                secret_voice += 1
        
        regular_channels = len(guild.channels) - secret_channels
        voice_channels = len(guild.channels) - text_channels
        mstatus = Counter(str(m.status) for m in guild.members)
        
        e = discord.Embed()
        e.add_field(name="Server Name", value=guild.name)
        e.add_field(name='ID', value=guild.id)
        e.add_field(name='Owner', value=guild.owner.mention)
        emojis = ""
        for emoji in guild.emojis:
            if len(emojis) + len(str(emoji)) < 1024:
                emojis += str(emoji)
        if emojis:
            e.add_field(name="Custom Emojis", value=emojis)
        e.add_field(name="Region", value=str(guild.region).title())
        e.add_field(name="Verification Level", value=str(guild.verification_level).title())
        if guild.icon:
            e.set_thumbnail(url=guild.icon_url)
        
        channels = f'{regular_channels} text_channels ({secret_channels} secret)' \
                   f'\nVoice {voice_channels} ({secret_voice} locked)'
        e.add_field(name='Channels', value=channels)
        
        members = f'Total {guild.member_count} ({mstatus["online"]})'
        e.add_field(name='Members', value=members)
        e.add_field(name='Roles', value=', '.join(roles) if len(roles) < 10 else f'{len(roles)} roles')
        e.set_footer(text='Created').timestamp = guild.created_at
        await ctx.send(embed=e)
    
    @commands.command()
    async def avatar(self, ctx, user: typing.Union[discord.User, discord.Member] = None):
        """ Shows a member's avatar """
        if user is None:
            user = ctx.author
        e = discord.Embed()
        e.colour = user.color
        e.set_footer(text=user.avatar_url)
        e.timestamp = datetime.datetime.now()
        e.description = f"{user.mention}'s avatar"
        e.set_image(url=str(user.avatar_url))
        await ctx.send(embed=e)


def setup(bot):
    bot.add_cog(Info(bot))
