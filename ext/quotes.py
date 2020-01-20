from discord.ext import commands
import discord
import asyncio
import typing


class QuoteDB(commands.Cog):
	""" Quote Database module """

	def __init__(self, bot):
		self.bot = bot

	async def make_embed(self, ctx, r):
		# Fetch data.
		channel = self.bot.get_channel(r["channel_id"])
		submitter = await self.bot.fetch_user(r["submitter_user_id"])
		guild = self.bot.get_guild(r["guild_id"])
		message_id = r["message_id"]

		e = discord.Embed(color=0x7289DA)
		quote_img = "https://discordapp.com/assets/2c21aeda16de354ba5334551a883b481.png"
		try:
			author = await self.bot.fetch_user(r["author_user_id"])
			e.set_author(name=f"{author.display_name} in #{channel}", icon_url=quote_img)
			e.set_thumbnail(url=author.avatar_url)
		except TypeError:
			e.set_author(name="Deleted User in #{channel}")
			e.set_thumbnail(url=quote_img)

		try:
			jumpurl = f"https://discordapp.com/channels/{guild.id}/{r['channel_id']}/{message_id}"
			e.description = f"**[Quote #{r['quote_id']}]({jumpurl})**\n\n"
		except AttributeError:
			e.description = f"**Quote #{r['quote_id']}**\n"

		e.description += r["message_content"]

		try:
			e.set_footer(text=f"Added by {submitter}", icon_url=submitter.avatar_url)
		except TypeError:
			e.set_footer(text="Added by Deleted User")

		e.timestamp = r["timestamp"]
		return e

	@commands.group(invoke_without_command=True,
					aliases=["quotes"],
					usage="quote <Optional: quote id> <Optional:  Users to search quotes from> "
						  "<Optional: 'global' to get from all servers>)")
	async def quote(self, ctx, id: typing.Optional[int], users: commands.Greedy[discord.User], global_flag=""):
		""" Get a quote (optionally by ID# or user(s). Use ".tb help quote" to view sub-commands. """
		sql = """SELECT * FROM quotes"""
		if id:
			sql += """ WHERE quote_id = $1"""
			escaped = [id]
			success = f"Displaying quote #{id}"
			failure = f"Quote #{id} was not found."
		else:
			success = "Displaying random quote"
			failure = "Could not find any quotes"
			escaped = []
			if not global_flag == "global":
				sql += """ WHERE guild_id = $1"""
				escaped += [ctx.guild.id]
				success += f" from {ctx.guild.name}"
				failure += f" from {ctx.guild.name}"
			if users:  # Returned from discord.Greedy
				sql += f""" AND author_user_id in (${len(escaped) + 1})"""
				escaped += [i.id for i in users]
				success += " from specified user(s)"
				failure += " from specified user(s)"

		sql += """ ORDER BY random()"""
		print(sql)
		# Fetch.
		connection = await self.bot.db.acquire()
		r = await connection.fetchrow(sql, *escaped)
		await self.bot.db.release(connection)

		if not r:
			return await ctx.send(failure)

		e = await self.make_embed(ctx, r)
		await ctx.send(success, embed=e)

	async def _do_search(self, ctx, qry, all_guilds=False):
		async with ctx.typing():
			m = await ctx.send(f"Searching QuoteDB for quotes matching {qry}...")
			sql = """SELECT * FROM quotes WHERE to_tsvector(message_content) @@ to_tsquery($1)"""
			escaped = [qry]
			if not all_guilds:
				sql += """ AND guild_id = $2"""
				escaped += [ctx.guild.id]

			# Fetch
			connection = await self.bot.db.acquire()
			records = await connection.fetch(sql, *escaped)
			await self.bot.db.release(connection)
			embeds = [await self.make_embed(ctx, row) for row in records]

			# Do we need to paginate?
			if not embeds:
				return await m.edit(content=f'No quotes matching {qry} found.')

			if len(embeds) == 1:
				return await m.edit(content=f"{ctx.author.mention}: 1 quote found", embed=embeds[0])
			else:
				await m.edit(content=f"{ctx.author.mention}: {len(records)} quotes found", embed=embeds[0])
				await self.paginate(m, ctx, embeds)

	async def paginate(self,m, ctx, embeds):
		# Paginate then.
		page = 0
		if len(embeds) > 2:
			await m.add_reaction("⏮")  # first
		if len(embeds) > 1:
			await m.add_reaction("◀")  # prev
			await m.add_reaction("▶")  # next
		if len(embeds) > 2:
			await m.add_reaction("⏭")  # last

		def check(reaction, user):
			if reaction.message.id == m.id and user == ctx.author:
				e = str(reaction.emoji)
				return e.startswith(('⏮', '◀', '▶', '⏭'))

		# Reaction Logic Loop.
		while True:
			try:
				reaction, user = await self.bot.wait_for("reaction_add", check=check, timeout=30)
			except asyncio.TimeoutError:
				await m.clear_reactions()
				break
			if reaction.emoji == "⏮":  # first
				page = 1
				await m.remove_reaction("⏮", ctx.message.author)
			elif reaction.emoji == "◀":  # prev
				await m.remove_reaction("◀", ctx.message.author)
				if page > 1:
					page = page - 1
			elif reaction.emoji == "▶":  # next
				await m.remove_reaction("▶", ctx.message.author)
				if page < len(embeds):
					page = page + 1
			elif reaction.emoji == "⏭":  # last
				page = len(embeds)
				await m.remove_reaction("⏭", ctx.message.author)
			await m.edit(embed=embeds[page - 1])

	@quote.group(usage="quote search [your search query])",invoke_without_command=True)
	async def search(self, ctx, *, qry: commands.clean_content):
		""" Search for a quote by quote text """
		await self._do_search(ctx, qry, all_guilds=False)

	@search.command(name="all")
	async def _all(self,ctx,*, qry: commands.clean_content):
		""" Search for a quote **from any server** by quote text """
		await self._do_search(ctx, qry, all_guilds=True)

	@quote.command(invoke_without_command=True)
	@commands.guild_only()
	async def add(self, ctx, target: typing.Union[discord.Member, discord.Message]):
		""" Add a quote, either by message ID or grabs the last message a user sent """
		if isinstance(target, discord.Member):
			messages = await ctx.history(limit=50).flatten()
			m = discord.utils.get(messages, channel=ctx.channel, author=user)
			if not m:
				await ctx.send("No messages from that user found in last 50 messages, please use message's id or link")
				return
		elif isinstance(target, discord.Message):
			m = target

		if m.author.id == ctx.author.id:
			return await ctx.send('You can\'t quote yourself.')
		n = await ctx.send("Attempting to add quote to db...")

		connection = await self.bot.db.acquire()

		await connection.execute("""
		INSERT INTO quotes (channel_id,guild_id,message_id,author_user_id,submitter_user_id,message_content,timestamp)
		VALUES ($1,$2,$3,$4,$5,$6,$7)""",
								 m.channel.id, m.guild.id, m.id, m.author.id, ctx.author.id, m.clean_content,
								 m.created_at)
		r = await connection.fetchrow("SELECT * FROM quotes ORDER BY quote_id DESC")
		await self.bot.db.release(connection)
		e = await self.make_embed(ctx, r)
		await n.edit(content=":white_check_mark: Successfully added quote to database", embed=e)

	@quote.command()
	async def last(self, ctx, arg: discord.Member = None):
		""" Gets the last quoted message (optionally from user) """
		connection = await self.bot.db.acquire()
		if arg is None:
			r = await connection.fetchrow("""SELECT * FROM quotes WHERE guild_id = $1 ORDER BY quote_id DESC""",
										  ctx.guild.id)
		else:
			r = await connection.fetchrow(
				"""SELECT * FROM quotes WHERE (user_id,guild_id) = ($1,$2) ORDER BY quote_id DESC""")
			if not r:
				return await ctx.send(f"No quotes found for user {arg.mention}.")
		e = await self.make_embed(ctx, r)
		await ctx.send(embed=e)

	@quote.command(name="del")
	@commands.has_permissions(manage_messages=True)
	async def _del(self, ctx, id: int):
		""" Delete quote by quote ID """
		connection = await self.bot.db.acquire()
		r = await connection.fetchrow(f"SELECT * FROM quotes WHERE quote_id = $1", id)
		if r is None:
			return await ctx.send(f"No quote found with ID #{id}")

		if r["guild_id"] != ctx.guild.id:
			if ctx.author.id != bot.owner_id:
				return await ctx.send(f"You can't delete quotes from other servers!")

		e = await self.make_embed(ctx, r)
		m = await ctx.send("Delete this quote?", embed=e)
		await m.add_reaction("👍")
		await m.add_reaction("👎")

		def check(reaction, user):
			if reaction.message.id == m.id and user == ctx.author:
				e = str(reaction.emoji)
				return e.startswith(("👍", "👎"))

		try:
			res = await self.bot.wait_for("reaction_add", check=check, timeout=30)
		except asyncio.TimeoutError:
			return await ctx.send("Response timed out after 30 seconds, quote not deleted", delete_after=30)
		res = res[0]

		if res.emoji.startswith("👎"):
			await ctx.send("Quote {id} was not deleted", delete_after=5)

		elif res.emoji.startswith("👍"):
			await connection.execute("DELETE FROM quotes WHERE quote_id = $1", id)
			await ctx.send(f"Quote #{id} has been deleted.")
		await self.bot.db.release(connection)
		await m.delete()

	@quote.command()
	async def stats(self, ctx, arg: discord.Member = None):
		""" See how many times you've been quoted, and how many quotes you've added"""
		if arg is None:
			arg = ctx.author

		connection = await self.bot.db.acquire()
		quotes = await connection.fetchrow("SELECT COUNT(*) FROM quotes WHERE (submitter_user_id,guild_id) = ($1,$2)",
										   arg.id, ctx.guild.id)
		quoted = await connection.fetchrow("SELECT COUNT(*) FROM quotes WHERE (author_user_id,guild_id) = ($1,$2)",
										   arg.id, ctx.guild.id)
		await ctx.send(
			f"In {ctx.guild.name} {arg.mention} has been quoted {quotes} times, and has added {quoted} quotes")


def setup(bot):
	bot.add_cog(QuoteDB(bot))
