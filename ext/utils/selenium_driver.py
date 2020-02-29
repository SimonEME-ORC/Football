import os
from io import BytesIO

import typing
from PIL import Image
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.common.exceptions import TimeoutException, ElementNotInteractableException, StaleElementReferenceException
from selenium.webdriver import DesiredCapabilities
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.wait import WebDriverWait


def spawn_driver():
    caps = DesiredCapabilities().FIREFOX
    caps["pageLoadStrategy"] = "normal"
    options = Options()
    options.add_argument("--headless")
    driver_path = os.getcwd() + '\\geckodriver.exe'
    driver = webdriver.Firefox(options=options, desired_capabilities=caps, executable_path=driver_path)
    return driver


def fetch(driver, url, xpath, **kwargs):
    # Only fetch if a new page is requested, kills off overhead and also stops annoying "stop refreshing" popups.
    if driver.current_url != url:
        driver.get(url)
    
    try:
        element = WebDriverWait(driver, 5).until(ec.visibility_of_element_located((By.XPATH, xpath)))
    except TimeoutException:
        element = None  # Rip
    
    # Delete floating ad banners or other shit that gets in the way
    if "delete" in kwargs:
        for z in kwargs['delete']:
            try:
                x = WebDriverWait(driver, 3).until(ec.presence_of_element_located(z))
            except TimeoutException:
                continue  # Element does not exist, do not need to delete it.
            scr = """var element = arguments[0];element.parentNode.removeChild(element);"""
            driver.execute_script(scr, x)
    
    # Hide cookie popups, switch tabs, etc.
    if "clicks" in kwargs:
        for z in kwargs['clicks']:
            try:
                x = WebDriverWait(driver, 3).until(ec.presence_of_element_located(z))
                x.click()
            except (TimeoutException, ElementNotInteractableException, StaleElementReferenceException):
                pass  # Can't click on what we can't find.
    
    return element


def get_html(driver, url, xpath, **kwargs) -> str:
    fetch(driver, url, xpath, **kwargs)
    return driver.page_source


def get_element(driver, url, xpath, **kwargs):
    element = fetch(driver, url, xpath, **kwargs)
    return element


def get_image(driver, url, xpath, failure_message, **kwargs) -> typing.Union[BytesIO, typing.List[BytesIO], None]:
    element = fetch(driver, url, xpath, **kwargs)
    
    if "multi_capture" in kwargs:
        max_iter = 10
        captures = [Image.open(BytesIO(element.screenshot_as_png))]
        while max_iter > 0:
            locator = kwargs['multi_capture'][0]
            try:
                z = WebDriverWait(driver, 3).until(ec.visibility_of_element_located(locator))
                z.click()
            except TimeoutException:
                break
            except ElementNotInteractableException as err:
                print(err)
                print(err.__traceback__)
            else:
                if "multi_capture_script" in kwargs:
                    driver.execute_script(kwargs['multi_capture_script'][1])
                    trg = driver.find_element_by_xpath(xpath)
                    captures.append(Image.open(BytesIO(trg.screenshot_as_png)))
            max_iter -= 1
        return captures
    else:
        assert element is not None, failure_message
        try:
            driver.execute_script("arguments[0].scrollIntoView();", element)
            im = Image.open(BytesIO(element.screenshot_as_png))
        except StaleElementReferenceException:
            element = WebDriverWait(driver, 3).until(ec.visibility_of_element_located((By.XPATH, xpath)))
            driver.execute_script("arguments[0].scrollIntoView();", element)
            im = Image.open(BytesIO(element.screenshot_as_png))
        
        output = BytesIO()
        im.save(output, 'PNG')
        output.seek(0)
        return output
