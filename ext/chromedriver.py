from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.common.exceptions import TimeoutException

class ChromeDriver(commands.Cog):
	""" Chrome Driver data fetching """
	def __init__(self, bot):
		self.bot = bot
		self.driver = None
	
	def __unload(self):
		if self.driver:
			self.driver.quit()
			
	# Spawn an instance of headerless chrome.
	def spawn_chrome(self):
		if self.driver:
			self.driver.quit()
		caps = DesiredCapabilities().CHROME
		caps["pageLoadStrategy"] = "normal"  #  complete
		chrome_options = Options()
		chrome_options.add_argument('log-level=3')
		chrome_options.add_argument("--headless")
		chrome_options.add_argument("--window-size=1920x1200")
		chrome_options.add_argument('--no-proxy-server')
		
		driver_path = os.getcwd() +"\\chromedriver.exe"
		prefs = {'profile.default_content_setting_values': {'images': 2, 'javascript': 2}}
		chrome_options.add_experimental_option('prefs', prefs)
		self.driver = webdriver.Chrome(desired_capabilities=caps,chrome_options=chrome_options, executable_path=driver_path)
		self.driver.set_page_load_timeout(20)
	
	def fetch_html(self):
		return source
	
	def fetch_image(self):
		return image