import discord
from discord.ext import commands
from datetime import datetime

import asyncio
import sqlite3

# Create database connection
conn = sqlite3.connect('quotes.db')
c = conn.cursor()

class quotedb:
	""" Quote Database module """
	def __init__(self,bot):
		self.bot = bot
		
	def __unload(bot):	
		conn.close()
	
	def nufccheck(ctx):
		if ctx.guild:
			return ctx.guild.id in [238704683340922882,332159889587699712]
	
	async def make_embed(self,data):
		# Get data from ids
		# Stored by [id,content,channelid,timestamp,submitterid]
		author = await self.bot.get_user_info(data[1])
		channel = self.bot.get_channel(data[3])
		submitter = await self.bot.get_user_info(data[5])
		submittern = submitter.display_name if submitter is not None else "deleted user"
		
		e = discord.Embed(color=0x7289DA,description=data[2])
		e.set_author(name=f"Quote #{data[0]}",
			icon_url="https://discordapp.com/assets/2c21aeda16de354ba5334551a883b481.png")
		if author:
			e.set_thumbnail(url=author.avatar_url)
			e.title = f"{author.display_name} in #{channel}"
		else:
			e.set_thumbnail(url="https://discordapp.com/assets/2c21aeda16de354ba5334551a883b481.png")
			e.title = f"Deleted user in #{channel}"
		
		e.set_footer(text=f"Added by {submittern}",icon_url=submitter.avatar_url)
		e.timestamp = datetime.strptime(data[4],"%Y-%m-%d %H:%M:%S.%f")
		return e
		
	@commands.group(invoke_without_command=True,aliases=["quotes"])
	async def quote(self,ctx,*,member:discord.Member = None):
		""" Show random quote (optionally from specific user). Use ".help quote" to view subcommands. """
		if ctx.invoked_subcommand is None:
			if member is not None: # If member provided, show random quote from member.
				c.execute(f"SELECT rowid, * FROM quotes WHERE userid = {member.id} ORDER BY RANDOM()")
				x = c.fetchone()
				if x == None:
					return await ctx.send(f"No quotes found from user {member.mention}")
			elif member == None: # Display a random quote.
				c.execute("SELECT rowid, * FROM quotes ORDER BY RANDOM()")
				x = c.fetchone()
				if x == None:
					return await ctx.send("Quote DB appears to be empty.")
				else:
					await ctx.send("Displaying random quote:")
		
		e = await self.make_embed(x)
		await ctx.send(embed=e)

	@quote.command()
	async def search(self,ctx,*,qry):
		with ctx.typing():
			m = await ctx.send('Searching...')
			localconn = sqlite3.connect('quotes.db')
			lc = localconn.cursor()
			lc.execute(f"SELECT rowid, * FROM quotes WHERE quotetext LIKE (?)",(f'%{qry}%',))
			x = lc.fetchall()
			lc.close()
			localconn.close()
		
		numquotes = len(x)
		embeds = []
		for i in x:
			y = await self.make_embed(i)
			embeds.append(y)
		
		# Do we need to paginate?
		if numquotes == 0:
			return await m.edit(content = f'No quotes matching {qry} found.')
		
		if numquotes == 1:
			return await m.edit(content=f"{ctx.author.mention}: 1 quote found",embed=embeds[0])
		else:
			await m.edit(content=f"{ctx.author.mention}: {numquotes} quotes found",embed=embeds[0])
		# Paginate then.
		page = 0
		if numquotes > 2:
			await m.add_reaction("⏮") # first
		if numquotes > 1:
			await m.add_reaction("◀") # prev
		if numquotes > 1:
			await m.add_reaction("▶") # next
		if numquotes > 2:
			await m.add_reaction("⏭") # last
		
		def check(reaction,user):
			if reaction.message.id == m.id and user == ctx.author:
				e = str(reaction.emoji)
				return e.startswith(('⏮','◀','▶','⏭'))
					
		# Reaction Logic Loop.
		while True:
			try:
				res = await self.bot.wait_for("reaction_add",check=check,timeout=30)
			except asyncio.TimeoutError:
				await m.clear_reactions()
				break
			res = res[0]
			if res.emoji == "⏮": #first
				page = 1
				await m.remove_reaction("⏮",ctx.message.author)
			elif res.emoji == "◀": #prev
				await m.remove_reaction("◀",ctx.message.author)
				if page > 1:
					page = page - 1
			elif res.emoji == "▶": #next	
				await m.remove_reaction("▶",ctx.message.author)
				if page < numquotes:
					page = page + 1
			elif res.emoji == "⏭": #last
				page = numquotes
				await m.remove_reaction("⏭",ctx.message.author)	
			await m.edit(embed=embeds[page - 1])
			
		
	@quote.command()
	@commands.is_owner()
	async def export(self,ctx):
		c.execute("SELECT rowid, * from quotes")
		x = c.fetchall()
		with open("out.txt", "wb") as fp:
			fp.write("\n".join([f"#{i[0]} @ {i[4]}: <{i[1]}> {i[2]} (Added by: {i[3]})" for i in x]).encode('utf8'))
		await ctx.send("Quotes exported.",file=discord.File("out.txt","quotes.txt"))

	@quote.command(aliases=["id","fetch"])
	async def get(self,ctx,number):
		""" Get a quote by it's QuoteID number """
		if not number.isdigit():
			return
		c.execute(f"SELECT rowid, * FROM quotes WHERE rowid = {number}")
		x = c.fetchone()
		if x is None:
			return await ctx.send(f"Quote {number} does not exist.")
		e = await self.make_embed(x)
		await ctx.send(embed=e)
				
	@quote.command(invoke_without_command=True)
	@commands.check(nufccheck)
	async def add(self,ctx,target):
		""" Add a quote, either by message ID or grabs the last message a user sent """
		if ctx.message.mentions:
			messages = await ctx.history(limit=123).flatten()
			user = ctx.message.mentions[0]
			if ctx.message.author == user:
				return await ctx.send("You can't quote yourself.")
			m = discord.utils.get(messages,channel=ctx.channel,author=user)
		elif target.isdigit():
			try:
				m = await ctx.channel.get_message(int(target))
			except discord.errors.NotFound:
				return await ctx.send('Message not found. Are you sure that\'s a valid ID?')
		if m is None:
			await ctx.send(f":no_entry_sign: Could not find message with id {target}")
			return
		if m.author.id == ctx.author.id:
			return await ctx.send('You can\'t quote yourself you virgin.')
		n = await ctx.send("Attempting to add quote to db...")
		insert_tuple = (m.author.id,m.clean_content,m.channel.id,m.created_at,ctx.author.id)
		c.execute("INSERT INTO quotes VALUES (?,?,?,?,?)",insert_tuple)
		conn.commit()
		c.execute("SELECT rowid, * FROM quotes ORDER BY rowid DESC")
		x = c.fetchone()
		e = await self.make_embed(x)
		await n.edit(content=":white_check_mark: Successfully added to database",embed=e)
	
	@quote.command()
	async def last(self,ctx,arg : discord.Member = None):
		""" Gets the last saved message (optionally from user) """
		if arg == None:
			c.execute("SELECT rowid, * FROM quotes ORDER BY rowid DESC")
			x = c.fetchone()
			if x == None:
				await ctx.send("No quotes found.")
				return
		else:
			c.execute(f"SELECT rowid, * FROM quotes WHERE userid = {arg.id} ORDER BY rowid DESC")
			x = c.fetchone()
			if x == None:
				await ctx.send(f"No quotes found for user {arg.mention}.")
				return
		e = await self.make_embed(x)
		await ctx.send(embed=e)
	
	@quote.command(name="del")
	@commands.has_permissions(manage_messages=True)
	@commands.check(nufccheck)
	async def _del(self,ctx,id):
		""" Delete quote by quote ID """
		if not id.isdigit():
			await ctx.send("That doesn't look like a valid ID")
		else:
			c.execute(f"SELECT rowid, * FROM quotes WHERE rowid = {id}")
			x = c.fetchone()
			if x is None:
				await ctx.send(f"No quote found with ID #{id}")
				return
			e = await self.make_embed(x)
			m = await ctx.send("Delete this quote?",embed=e)
			await m.add_reaction("👍")
			await m.add_reaction("👎")
			def check(reaction,user):
				if reaction.message.id == m.id and user == ctx.author:
					e = str(reaction.emoji)
					return e.startswith(("👍","👎"))
			try:
				res = await self.bot.wait_for("reaction_add",check=check,timeout=30)
			except asyncio.TimeoutError:
				return await ctx.send("Response timed out after 30 seconds, quote not deleted",delete_after=30)
			res = res[0]
			if res.emoji.startswith("👎"):
				await ctx.send("OK, quote not deleted",delete_after=20)
			elif res.emoji.startswith("👍"):
				c.execute(f"DELETE FROM quotes WHERE rowid = {id}")
				await ctx.send(f"Quote #{id} has been deleted.")
				await m.delete()
				await ctx.message.delete()
				conn.commit()

	@quote.command()
	async def stats(self,ctx,arg:discord.Member = None):
		""" See how many times you've been quoted, and how many quotes you've added"""
		if arg == None:
			arg = ctx.author
		c.execute(f"SELECT COUNT(*) FROM quotes WHERE quoterid = {arg.id}")
		y = c.fetchone()[0]
		c.execute(f"SELECT COUNT(*) FROM quotes WHERE userid = {arg.id}")
		x = c.fetchone()[0]
		await ctx.send(f"{arg.mention} has been quoted {x} times, and has added {y} quotes")
		
def setup(bot):
	bot.add_cog(quotedb(bot))