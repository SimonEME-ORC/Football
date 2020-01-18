import discord
from discord.ext import commands
from datetime import datetime

import typing
import asyncio
import asyncpg

class quotedb(commands.Cog):
	""" Quote Database module """
	def __init__(self,bot):
		self.bot = bot
				
	async def make_embed(self,ctx,r):
		# Fetch data.
		channel = self.bot.get_channel(r["channel_id"])
		submitter = await self.bot.fetch_user(r["submitter_user_id"])
		guild = self.bot.get_guild(r["guild_id"])
		message_id = r["message_id"]

		e = discord.Embed(color=0x7289DA)
		quoteimg = "https://discordapp.com/assets/2c21aeda16de354ba5334551a883b481.png"
		try:
			author = await self.bot.fetch_user(r["author_user_id"])
			e.set_author(name=f"{author.display_name} in #{channel}",icon_url=quoteimg)
			e.set_thumbnail(url=author.avatar_url)
		except TypeError:
			e.set_author(name="Deleted User in #{channel}")
			e.set_thumbnail(url=quoteimg)
			

		try:
			jumpurl = f"https://discordapp.com/channels/{guild.id}/{r['channel_id']}/{message_id}"
			e.description = f"**[Quote #{r['quoteid']}]({jumpurl})**\n"
		except AttributeError:
			e.description = f"**Quote #{r['quoteid']}**\n"
		e.description += r["message_content"]
		
		try:
			e.set_footer(text=f"Added by {submitter}",icon_url=submitter.avatar_url)
		except TypeError:
			e.set_footer(text=f"Added by Deleted User")

		e.timestamp =r["timestamp"]
		return e
		
	@commands.group(invoke_without_command=True,aliases=["quotes"])
	@commands.guild_only()
	async def quote(self,ctx,*,member:discord.Member = None):
		""" Show random quote (optionally from specific user). Use ".help quote" to view subcommands. """
		connection = await self.bot.db.acquire()
		if member is not None: # If member provided, show random quote from member.
			r = await connection.fetchrow("SELECT * FROM quotes WHERE (guild_id,author_user_id) = ($1,$2) ORDER BY RANDOM()",ctx.guild.id,member.id)
			if not r:
				return await ctx.send(f"No quotes found from {member} on {ctx.guild.name}")
		else: # Display a random quote.
			r = await connection.fetchrow("SELECT * FROM quotes WHERE (guild_id) = ($1) ORDER BY RANDOM()",ctx.guild.id)
			if not r:
				return await ctx.send(f"{ctx.guild.name} doesn't have any quotes.")
		await self.bot.db.release(connection)
		e = await self.make_embed(ctx,r)
		await ctx.send(f"Displaying random quote from {ctx.guild.name}:",embed=e)

	@quote.command()
	@commands.guild_only()
	async def search(self,ctx,*,qry : commands.clean_content):
		async with ctx.typing():
			connection = await self.bot.db.acquire()
			records = await connection.fetch(f"SELECT * FROM quotes WHERE message_content LIKE $1 AND guild_id = $2",qry,ctx.guild.id)
			await self.bot.db.release(connection)	
			numquotes = len(r)
			embeds = []
			for row in records:
				em = await self.make_embed(ctx,row)
				embeds.append(em)
				
			# Do we need to paginate?
			if numquotes: # 0 is Falsey.
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

	@quote.command(aliases=["id","fetch"])
	async def get(self,ctx,number:int):
		""" Get a quote by it's QuoteID number """
		connection = await self.bot.db.acquire()
		r = await connection.fetchrow(f"SELECT * FROM quotes WHERE quoteid = $1",number)
		await self.bot.db.release(connection)
		if not r:
			return await ctx.send(f"Quote {number} does not exist.")
		e = await self.make_embed(ctx,r)
		await ctx.send(embed=e)
				
	@quote.command(invoke_without_command=True)
	async def add(self,ctx,target : typing.Union[discord.Member,discord.Message]):
		""" Add a quote, either by message ID or grabs the last message a user sent """
		if isinstance(target,discord.Member):
			messages = await ctx.history(limit=123).flatten()
			m = discord.utils.get(messages,channel=ctx.channel,author=user)
		elif isinstance(target,discord.Message):
			m = target

		if m.author.id == ctx.author.id:
			return await ctx.send('You can\'t quote yourself.')
		n = await ctx.send("Attempting to add quote to db...")
		
		connection = await self.bot.db.acquire()
		
		(m.author.id,m.clean_content,m.channel.id,m.created_at,ctx.author.id,m.id,ctx.guild.id)
		await connection.execute("""
		INSERT INTO quotes
		(channel_id,guild_id,message_id,author_user_id,submitter_user_id,message_content,timestamp)
		VALUES ($1,$2,$3,$4,$5,$6,$7)"""
		,m.channel.id,m.guild.id,m.id,m.author.id,ctx.author.id,m.clean_content,m.created_at)
		r = await connection.fetchrow("SELECT * FROM quotes ORDER BY quoteid DESC")
		await self.bot.db.release(connection)	
		e = await self.make_embed(ctx,r)
		await n.edit(content=":white_check_mark: Successfully added quote to database",embed=e)
	
	@quote.command()
	async def last(self,ctx,arg : discord.Member = None):
		""" Gets the last quoted message (optionally from user) """
		connection = await self.bot.db.acquire()
		if arg is None:
			r = await connection.fetchrow("""SELECT * FROM quotes WHERE guild_id = $1 ORDER BY quoteid DESC""",ctx.guild.id)
		else:
			r = await connection.fetchrow( """SELECT * FROM quotes WHERE (user_id,guild_id) = ($1,$2) ORDER BY quoteid DESC""")
			if not r:
				return await ctx.send(f"No quotes found for user {arg.mention}.") 
		e = await self.make_embed(ctx,r)
		await ctx.send(embed=e)
	
	@quote.command(name="del")
	@commands.has_permissions(manage_messages=True)
	async def _del(self,ctx,id:int):
		""" Delete quote by quote ID """
		connection = await self.bot.db.acquire()
		r = await connection.fetchrow(f"SELECT * FROM quotes WHERE quoteid = $1",id)
		if r is None:
			return await ctx.send(f"No quote found with ID #{id}")
		
		if r["guild_id"] != ctx.guild.id:
			if ctx.author.id != bot.owner_id:
				return await ctx.send(f"You can't delete quotes from other servers!")
		
		e = await self.make_embed(ctx,r)
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
			await ctx.send("Quote {id} was not deleted",delete_after=5)
			
		elif res.emoji.startswith("👍"):
			await connection.execute("DELETE FROM quotes WHERE quoteid = $1",id)
			await ctx.send(f"Quote #{id} has been deleted.")
		await self.bot.db.release(connection)
		await m.delete()	

	@quote.command()
	@commands.is_owner()
	async def fix(self,ctx):
		connection = await self.bot.db.acquire()
		e = discord.Embed()
		counter = 0
		failed = 0
		async with connection.transaction():
			records = await connection.fetch("""SELECT * FROM quotes WHERE message_id IS NULL""")
			for r in records:
				messageid = [i.id for i in self.bot.channelhistory if i.created_at == r["timestamp"]]
				try:
					messageid = messageid[0]
				except IndexError:
					print(f"Failed to find a match for {r['message_content']}")
					failed += 1
					await asyncio.sleep(1)
					continue
				await connection.execute("""UPDATE quotes SET message_id = $1 WHERE timestamp = $2""",messageid,r["timestamp"])
				counter += 1
				print(f"Updated: {r['message_content']} : {messageid}")
		e.description = f"I searched through fucking {len(self.bot.channelhistory)} messages for you cunts. Fixed {counter} quotes, failed to fix {failed} quotes."
		await ctx.send(embed=e)
		
	@quote.command()
	async def stats(self,ctx,arg:discord.Member = None):
		""" See how many times you've been quoted, and how many quotes you've added"""
		if arg is None:
			arg = ctx.author
		
		connection = await self.bot.db.acquire()		
		quotes = await connection.fetchrow("SELECT COUNT(*) FROM quotes WHERE (submitter_user_id,guild_id) = ($1,$2)",arg.id,ctx.guild.id)
		quoted = await connection.fetchrow("SELECT COUNT(*) FROM quotes WHERE (author_user_id,guild_id) = ($1,$2)",arg.id,ctx.guild.id)
		await ctx.send(f"In {ctx.guild.name} {arg.mention} has been quoted {quotes} times, and has added {quoted} quotes")
		
def setup(bot):
	bot.add_cog(quotedb(bot))