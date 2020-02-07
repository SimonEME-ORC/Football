from PIL import Image, ImageDraw, ImageOps, ImageFont
from discord.ext import commands
from discord.ext.commands.cooldowns import BucketType
import datetime
import textwrap
import discord
import asyncio
import random
import json
from io import BytesIO


def draw_tinder(image, av, name):
    # Base Image
    im = Image.open("Images/tinder.png").convert(mode="RGBA")
    # Prepare mask
    msk = Image.open("Images/retardedmask.png").convert('L')
    msk = ImageOps.fit(msk, (185, 185))
    # User Avatar
    avt = Image.open(BytesIO(av)).convert(mode="RGBA")
    avo = ImageOps.fit(avt, (185, 185))
    avo.putalpha(msk)
    im.paste(avo, box=(100, 223, 285, 408), mask=msk)
    # Player
    plt = Image.open(BytesIO(image)).convert(mode="RGBA")
    plo = ImageOps.fit(plt, (185, 185), centering=(0.5, 0.0))
    plo.putalpha(msk)
    im.paste(plo, box=(313, 223, 498, 408), mask=msk)
    # Write "it's a mutual match"
    txt = f"You and {name} have liked each other."
    f = ImageFont.truetype('Whitney-Medium.ttf', 24)
    w, h = f.getsize(txt)
    d = ImageDraw.Draw(im)
    d.text((300 - w / 2, 180), txt, font=f, fill="#ffffff")

    output = BytesIO()
    im.save(output, "PNG")
    output.seek(0)

    df = discord.File(output, filename="tinder.png")
    return df


def draw_bob(image, response):
    """ Pillow Bob Rossifying """
    im = Image.open(BytesIO(image)).convert(mode="RGBA")
    bob = Image.open("Images/rossface.png")
    for coords in response:
        x = int(coords["faceRectangle"]["left"])
        y = int(coords["faceRectangle"]["top"])
        w = int(coords["faceRectangle"]["width"])
        h = int(coords["faceRectangle"]["height"])
        roll = int(coords["faceAttributes"]["headPose"]["roll"]) * -1
        vara = int(x - (w / 4))
        varb = int(y - (h / 2))
        varc = int(x + (w * 1.25))
        vard = int((y + (h * 1.25)))
        xsize = varc - vara
        ysize = vard - varb
        thisbob = ImageOps.fit(bob, (xsize, ysize)).rotate(roll)
        im.paste(thisbob, box=(vara, varb, varc, vard), mask=thisbob)
    output = BytesIO()
    im.save(output, "PNG")
    output.seek(0)
    
    df = discord.File(output, filename="withbob.png")
    return df


def draw_knob(image, response):
    im = Image.open(BytesIO(image)).convert(mode="RGBA")
    knob = Image.open("Images/knob.png")
    
    for coords in response:
        mlx = int(coords["faceLandmarks"]["mouthLeft"]["x"])
        mrx = int(coords["faceLandmarks"]["mouthRight"]["x"])
        lipy = int(coords["faceLandmarks"]["upperLipBottom"]["y"])
        lipx = int(coords["faceLandmarks"]["upperLipBottom"]["x"])
        
        angle = int(coords["faceAttributes"]["headPose"]["roll"] * -1)
        w = int((mrx - mlx)) * 2
        h = w
        tk = ImageOps.fit(knob, (w, h)).rotate(angle)
        im.paste(tk, box=(int(lipx - w / 2), int(lipy)), mask=tk)
    output = BytesIO()
    im.save(output, "PNG")
    output.seek(0)
    df = discord.File(output, filename="withknobs.png")
    return df


def draw_eyes(image, response):
    """ Draws the eyes """
    im = Image.open(BytesIO(image))
    for i in response:
        # Get eye bounds
        lix = int(i["faceLandmarks"]["eyeLeftInner"]["x"])
        lox = int(i["faceLandmarks"]["eyeLeftOuter"]["x"])
        lty = int(i["faceLandmarks"]["eyeLeftTop"]["y"])
        # lby = int(i["faceLandmarks"]["eyeLeftBottom"]["y"])
        rox = int(i["faceLandmarks"]["eyeRightOuter"]["x"])
        rix = int(i["faceLandmarks"]["eyeRightInner"]["x"])
        rty = int(i["faceLandmarks"]["eyeRightTop"]["y"])
        # rby = int(i["faceLandmarks"]["eyeRightBottom"]["y"])
        
        lw = lix - lox
        rw = rox - rix
        
        # Inflate
        lix = lix + lw
        lox = lox - lw
        lty = lty - lw
        # lby = lby + lw
        rox = rox + rw
        rix = rix - rw
        rty = rty - rw
        # rby = rby + rw
        
        # Recalculate with new sizes.
        lw = lix - lox
        rw = rox - rix
        
        # Open Eye Image, resize, paste twice
        eye = Image.open("Images/eye.png")
        left = ImageOps.fit(eye, (lw, lw))
        right = ImageOps.fit(eye, (rw, rw))
        im.paste(left, box=(lox, lty), mask=left)
        im.paste(right, box=(rix, rty), mask=right)
    
    # Prepare for sending and return
    output = BytesIO()
    im.save(output, "PNG")
    output.seek(0)
    df = discord.File(output, filename="witheyes.png")
    
    return df


def draw_tard(image, quote):
    """ Draws the "it's retarded" image """
    # Open Files
    im = Image.open(BytesIO(image))
    base = Image.open("Images/retardedbase.png")
    msk = Image.open("Images/retardedmask.png").convert('L')
    
    # Resize avatar, make circle, paste
    ops = ImageOps.fit(im, (250, 250))
    ops.putalpha(msk)
    smallmsk = msk.resize((35, 40))
    small = ops.resize((35, 40))
    largemsk = msk.resize((100, 100))
    large = ops.resize((100, 100)).rotate(-20)
    base.paste(small, box=(175, 160, 210, 200), mask=smallmsk)
    base.paste(large, box=(325, 90, 425, 190), mask=largemsk)
    
    # Drawing tex
    d = ImageDraw.Draw(base)
    
    # Get best size for text
    def get_first_size(quote_text):
        font_size = 72
        ttf = 'Whitney-Medium.ttf'
        font = ImageFont.truetype(ttf, font_size)
        width = 300
        quote_text = textwrap.fill(quote_text, width=wid)
        while font_size > 0:
            # Make lines thinner if too wide.
            while width > 1:
                if font.getsize(quote_text)[0] < 237 and f.getsize(quote)[1] < 89:
                    return width, font
                width -= 1
                quote_text = textwrap.fill(quote, width=wid)
                font = ImageFont.truetype(ttf, font_size)
            font_size -= 1
            font = ImageFont.truetype(ttf, font_size)
            width = 40

    wid, f = get_first_size(quote)
    quote = textwrap.fill(quote, width=wid)
    # Write lines.
    moveup = f.getsize(quote)[1]
    d.text((245, (80 - moveup)), quote, font=f, fill="#000000")
    
    # Prepare for sending
    output = BytesIO()
    base.save(output, "PNG")
    output.seek(0)
    df = discord.File(output, filename="retarded.png")
    return df


async def get_target(ctx, target):
    if ctx.message.mentions:
        target = str(ctx.message.mentions[0].avatar_url_as(format="png"))
    if target is None:
        for i in ctx.message.attachments:
            if i.height is None:  # Not an image.
                continue
            return i.url
        await ctx.send(':no_entry_sign: To use this command either upload an image, tag a user, or specify a url.')
        return None
    else:
        return target


def ruin(image):
    """ Generates the Image """
    im = Image.open(BytesIO(image))
    base = Image.open("Images/localman.png")
    ops = ImageOps.fit(im, (256, 256))
    base.paste(ops, box=(175, 284, 431, 540))
    output = BytesIO()
    base.save(output, "PNG")
    output.seek(0)
    # output
    df = discord.File(output, filename="retarded.png")
    return df


# TODO: Embedify with local embed upload & source image & author.


class ImageManip(commands.Cog):
    """ Edit images for you """
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command()
    @commands.cooldown(2, 90, BucketType.user)
    async def tinder(self, ctx):
        """ Try to Find your next date. """
        with ctx.typing():
            if ctx.author.id == 272722118192529409:
                return await ctx.send("Nobody will ever swipe right on you, Kegs.")
            match = random.choice([True, False, False])
            if not match:
                return await ctx.send("Nobody swiped right on you.")
            
            async with self.bot.session.get(str(ctx.author.avatar_url_as(format="png"))) as resp:
                av = await resp.content.read()
            match = random.choice(ctx.guild.members)
            name = match.display_name
            
            async with self.bot.session.get(str(match.avatar_url_as(format="png"))) as resp:
                target = await resp.content.read()
                df = await self.bot.loop.run_in_executor(None, draw_tinder, target, av, name)
            
            if match == ctx.author:
                await ctx.send("Congratulations, you matched with yourself. How pathetic.", file=df)
            elif match == ctx.me:
                await ctx.send("Fancy a shag?", file=df)
            else:
                await ctx.send(file=df)  # file name is tinder.png

    async def get_faces(self, ctx, target):
        """ Retrieve face features from Project Oxford """
        # Prepare POST
        oxk = self.bot.credentials['Oxford']['OxfordKey']
        h = {"Content-Type": "application/json", "Ocp-Apim-Subscription-Key": oxk}
        body = {"url": target}
        p = {"returnFaceId": "False", "returnFaceLandmarks": "True", "returnFaceAttributes": "headPose"}
        d = json.dumps(body)
        url = "https://westeurope.api.cognitive.microsoft.com/face/v1.0/detect"

        # Get Project Oxford reply
        async with self.bot.session.post(url, params=p, headers=h, data=d) as resp:
            if resp.status != 200:
                if resp.status == 400:
                    await ctx.send(await resp.json())
                else:
                    await ctx.send(
                        f"HTTP Error {resp.status} recieved accessing project oxford's facial recognition API.")
                return None, None
            response = await resp.json()
        
        # Get target image as file
        async with self.bot.session.get(target) as resp:
            if resp.status != 200:
                await ctx.send(f"{resp.status} code accessing project oxford.")
            image = await resp.content.read()
        return image, response

    @commands.command(aliases=["bob", "ross"])
    async def bobross(self, ctx, *, target=None):
        """ Bob Rossify """
        with ctx.typing():
            target = await get_target(ctx, target)
            if not target:
                return  # rip.
            
            image, response = await self.get_faces(ctx, target)
            if response is None:
                return await ctx.send("No faces were detected in your image.")
            
            df = await self.bot.loop.run_in_executor(None, draw_bob, image, response)
            await ctx.send(file=df)  # file name is withbob.png
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass

    @commands.command()
    async def knob(self, ctx, *, target=None):
        """ Draw knobs in mouth on an image.
        Mention a user to use their avatar.
        Only works for human faces."""
        with ctx.typing():
            target = await get_target(ctx, target)
            if not target:
                return  # rip
            
            image, response = await self.get_faces(ctx, target)
            if response is None:
                return await ctx.send("No faces were detected in your image.")
            
            df = await self.bot.loop.run_in_executor(None, draw_knob, image, response)
            await ctx.send(ctx.author.mention, file=df)
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass

    @commands.command()
    async def eyes(self, ctx, *, target=None):
        """ Draw Googly eyes on an image.
            Mention a user to use their avatar.
            Only works for human faces."""
        with ctx.typing():
            target = await get_target(ctx, target)
            if not target:
                return  # rip
            image, response = await self.get_faces(ctx, target)
            if response is None:
                return await ctx.send("No faces were detected in your image.")
            
            # Pass it off to the executor
            df = await self.bot.loop.run_in_executor(None, draw_eyes, image, response)
            await ctx.send(ctx.author.mention, file=df)
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

    @commands.command(usage='tard <@user> <quote>')
    async def tard(self, ctx, target: discord.Member, *, quote):
        """ Generate an "oh no, it's retarded" image
        with a user's avatar and a quote "
        """
        with ctx.typing():
            if target.id == 210582977493598208:
                target = ctx.author
                quote = "I think I'm smarter than Painezor"
            cs = self.bot.session
            async with cs.get(str(target.get_avatar_url_as(format="png", size=1024))) as resp:
                if resp.status != 200:
                    return await ctx.send(f"Error retrieving avatar for target {target} {resp.status}")
                image = await resp.content.read()
            df = await self.bot.loop.run_in_executor(None, draw_tard, image, quote)
            await ctx.send(file=df)
    
    @tard.error
    async def tard_error(self, ctx, exc):
        if isinstance(exc, commands.BadArgument):
            return await ctx.send("🚫 Bad argument provided: Make sure you're pinging a user or using their ID")

    @commands.command(aliases=["localman", "local", "ruin"], hidden=True)
    async def ruins(self, ctx, *, user: discord.User = None):
        """ Local man ruins everything """
        with ctx.typing():
            if user is None:
                user = ctx.author
            av = str(user.avatar_url_as(format="png", size=256))
            async with self.bot.session.get(av) as resp:
                if resp.status != 200:
                    await ctx.send(f"{resp.status} Error getting {user}'s avatar")
                image = await resp.content.read()
            df = await self.bot.loop.run_in_executor(None, ruin, image)
            await ctx.send(file=df)

    @commands.command(hidden=True)
    async def butter(self, ctx):
        """ What is my purpose? """
        await ctx.send(file=discord.File("Images/butter.png"))
    
    @commands.command(hidden=True)
    async def fixed(self, ctx):
        """ Fixed! """
        await ctx.send(file=discord.File("Images/fixed.png"))
    
    @commands.command(hidden=True)
    async def ructions(self, ctx):
        """ WEW. RUCTIONS. """
        await ctx.send(file=discord.File("Images/ructions.png"))
    
    @commands.command(hidden=True)
    async def helmet(self, ctx):
        """ Helmet"""
        await ctx.send(file=discord.File("Images/helmet.jpg"))
    
    @commands.command(hidden=True, aliases=["f"])
    async def pressf(self, ctx):
        """ Press F to pay respects """
        await ctx.send("https://i.imgur.com/zrNE05c.gif")
    
    @commands.command(hidden=True)
    async def goala(self, ctx):
        """ Party on Garth """
        await ctx.send(file=discord.File('Images/goala.gif'))
    
    @commands.command()
    @commands.cooldown(1, 120, BucketType.user)
    async def cat(self, ctx):
        """ Adopt a random cat """
        await ctx.trigger_typing()
        retries = 0
        while retries < 3:
            async with self.bot.session.get("http://random.cat/meow") as resp:
                if resp.status != 200:
                    await asyncio.sleep(1)
                    retries += 1
                    continue
                else:
                    cat = await resp.json()
                    async with self.bot.session.get(cat["file"]) as new_resp:
                        cat = await new_resp.content.read()
                        fp = discord.File(BytesIO(cat), filename="cat.png")
                        try:
                            return await ctx.author.send("😺 Here's your cat:", file=fp)
                        except discord.Forbidden:
                            return await ctx.send(
                                "Tried to send you your cat, but I can't send you messages."
                                " Guess he's not getting adopted then.")
        await ctx.send("😿 Sorry, no cats want to be adopted by you.")


def setup(bot):
    bot.add_cog(ImageManip(bot))
