import asyncpg
import discord
import datetime
from discord.ext import commands
import traceback
import sys


class aspg(commands.Cog):
	""" async pg debug cog. """
	def __init__(self,bot):
		print(f"{datetime.datetime.now()}: Loaded aspg debug module")
		self.bot = bot
	
	@commands.is_owner()
	@commands.command()
	async def populate(self,ctx):
		# guild_settings
		tf = []
		tfl = []
		for i in self.bot.config:
			try:
				guild_id = self.bot.get_guild(int(i)).id
			except (KeyError,AttributeError):
				continue

			# transfers
			try:
				channel_id = self.bot.get_channel(self.bot.config[i]["transfers"]["channel"]).id
			except (KeyError,AttributeError):
				pass
			else:
				try:
					mode = self.bot.config[i]["transfers"]["mode"]
					if mode != "default":
						await ctx.send(f"A wild mode appeared: {mode}")
					mode = False if mode.lower() == "default" else True

				except KeyError:
					mode = False
				
				tf.append((channel_id,mode,guild_id))
				# transfers whitelist items
				if mode is not None:
					try:
						for item in self.bot.config[i]["transfers"]["whitelist"]:
							tfl.append((channel_id,item))
					except:
						pass
		
		connection = await self.bot.db.acquire()
				await connection.executemany("""
				INSERT INTO transfers
					(channel_id,mode,guild_id)
					
				VALUES
					($1,$2,$3)
					
				ON CONFLICT
					(channel_id)
					
				DO UPDATE SET
						mode = $2,			
						guild_id = $3
					WHERE excluded.channel_id = $1
				""",tf)
				
				em.description += f'Updated {len(tf)} rows in transfers table\n'
				
				await connection.executemany(""" 
				INSERT INTO transfers_whitelists
					(channel_id,whitelist_item)
				VALUES
					($1,$2)
				
				
				ON CONFLICT
					(channel_id,whitelist_item)
				
				DO NOTHING
				""",tfl)

				em.description += f'Updated {len(tfl)} rows in transfers_whitelists table\n'
			except Exception as e:
				await ctx.send((f"{type(e)}: {e}"),embed=em)
				traceback.print_tb(e.__traceback__)
			else:
				await ctx.send("No errors updating tables.",embed=em)
		await self.bot.db.release(connection)
		
		
def setup(bot):
	bot.add_cog(aspg(bot))