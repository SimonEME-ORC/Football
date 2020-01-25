import os
from selenium.webdriver import DesiredCapabilities
from selenium import webdriver
from selenium.webdriver.firefox.options import Options


def spawn_driver():
    caps = DesiredCapabilities().FIREFOX
    caps["pageLoadStrategy"] = "normal"
    options = Options()
    options.add_argument("--headless")
    driver_path = os.getcwd() + "\\geckodriver.exe"
    driver = webdriver.Firefox(options=options, desired_capabilities=caps, executable_path=driver_path)
    return driver
