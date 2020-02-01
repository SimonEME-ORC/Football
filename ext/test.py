import asyncio
import sys

from discord.ext import commands
from io import BytesIO
import json

from discord.ext.commands import BucketType
from imgurpython import ImgurClient
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from ext.utils.selenium_driver import spawn_driver


class Test(commands.Cog):
    """ Test Commands """
    def __init__(self, bot):
        self.bot = bot
        self.driver = None
        self.bot.loop.create_task(self.get_driver())

    async def get_driver(self):
        self.driver = await self.bot.loop.run_in_executor(None, spawn_driver)
        

    def cog_unload(self):
        self.driver.quit()

    def imgurify(self, image):
        with open('credentials.json') as f:
            credentials = json.load(f)
        imgur = ImgurClient(credentials["Imgur"]["Authorization"], credentials["Imgur"]["Secret"])
        text_obj = image.decode('UTF-8')
        resp = imgur.upload(text_obj)
        return resp

    def get_image(self):
        self.driver.get("https://www.flashscore.com/football/england/premier-league/standings/")
        xp = './/div[@class="glib-stats-box-table-overall"]'
        tbl = WebDriverWait(self.driver, 10).until(ec.presence_of_element_located((By.XPATH, xp)))
        self.driver.execute_script("window.stop();")

        # Kill cookie disclaimer.
        try:
            z = self.driver.find_element_by_xpath(".//div[@class='button cookie-law-accept']")
            z.click()
        except (NoSuchElementException, ElementNotInteractableException):
            pass

        self.driver.execute_script("arguments[0].scrollIntoView();", tbl)
        file = BytesIO(tbl.screenshot_as_png)
        file.seek(0)
        data = file.read()
        return data

    @commands.command()
    @commands.is_owner()
    async def test(self, ctx):
        """ Test command."""
        image = await self.bot.loop.run_in_executor(None, self.get_image)
        resp = await self.bot.loop.run_in_executor(None, self.imgurify, image)
        await ctx.send(resp)
        
    @commands.command(name="test_a")
    async def _test_a(self, ctx, *args):
        await ctx.send(f'Pseudo-command invoked by {ctx.invoked_with} running for 5 seconds.')
        await asyncio.sleep(5)
        await ctx.send(f'Pseudo-command invoked by {ctx.invoked_with} has finished waiting.')

    @commands.command(name="test_b")
    async def _test_b(self, ctx, *args):
        await ctx.send(f'command invoked by {ctx.invoked_with} running for 5 seconds.')
        await asyncio.sleep(5)
        await ctx.send(f'command invoked by {ctx.invoked_with} has finished waiting.')
        
    
def setup(bot):
    bot.add_cog(Test(bot))
    bot.get_command("test_a")._max_concurrency = bot.selenium_queue
    bot.get_command("test_b")._max_concurrency = bot.selenium_queue