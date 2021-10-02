import os
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.common.exceptions import WebDriverException
import http.client
import socket
import foebot.asyncio_helpers as ah
import time


def retry(error=WebDriverException, max_retry=10, raise_error=True):
    def retry_decorator(func):
        async def decorated_func(*args, **kwargs):
            count = 0
            while True:
                try:
                    return await func(*args, **kwargs)
                except error:
                    if count < max_retry:
                        count += 1
                    elif raise_error:
                        raise
                    else:
                        return
        return decorated_func
    return retry_decorator


class Browser(object):
    def __init__(self, driver, foe_positions):
        self.foe_positions = foe_positions
        self.driver_ = driver
        time.sleep(1)
        driver.maximize_window()

    def quit(self):
        self.driver_.quit()

    @ah.sleep()
    async def alive(self):
        try:
            self.driver_.execute(webdriver.remote.command.Command.STATUS)
            return True
        except (socket.error, http.client.CannotSendRequest):
            return False

    @ah.sleep()
    async def get(self, url):
        self.driver_.get(url)

    @ah.sleep()
    async def switch_to(self, query):
        self.driver_.switch_to.frame(query)

    @ah.sleep()
    async def switch_to_parent(self):
        self.driver_.switch_to.parent_frame()

    @ah.sleep()
    async def find_id(self, el_id):
        return self.driver_.find_element_by_id(el_id)

    @ah.sleep()
    async def find_name(self, el_name):
        return self.driver_.find_element_by_name(el_name)

    @ah.sleep()
    async def find_xpath(self, xpath):
        return self.driver_.find_element_by_xpath(xpath)

    @ah.sleep()
    async def get_log(self):
        return self.driver_.get_log("browser")

    @ah.sleep()
    async def refresh(self):
        self.driver_.refresh()

    @ah.sleep()
    async def get_dimensions(self):
        return self.driver_.get_window_size()

    async def get_width(self):
        return (await self.get_dimensions())['width']

    async def get_height(self):
        return (await self.get_dimensions())['height']

    @ah.sleep()
    async def get_top_left_corner(self):
        return self.driver_.get_window_position(windowHandle='current')

    async def get_bottom_left_corner(self):
        c = await self.get_top_left_corner()
        c['y'] += await self.get_height()
        return c

    async def get_game_element(self):
        return await self.find_id('game_body')

    async def get_game_rectangle(self):
        """ returns {'height': ..., 'width': ..., 'x': ..., 'y': ...} """
        return (await self.get_game_element()).rect

    async def game_multiple_clicks(self, coords, y_offset=None):
        action = None
        for c in coords:
            action = await self.game_click(c, y_offset, action, False)
        action.perform()

    async def game_click(self, coord, y_offset=None, action=None, perform=True):
        # compute x
        r = await self.get_game_rectangle()
        rel_y = coord[1]  # round(coord[1] * r['height'] / self.foe_positions.game_height)
        el = await self.get_game_element()
        ah.info('Clicking around ({},{})'.format(coord[0] + r['x'], rel_y + r['y']))
        if not action:
            action = ActionChains(self.driver_)
        if not y_offset:
            action = action.move_to_element_with_offset(el, coord[0], rel_y).click()
        # then click on a range if y_offset
        else:
            start_y = rel_y - y_offset['radius'] - 1
            stop_y = rel_y + y_offset['radius']
            step_y = -y_offset['step']
            if not action:
                action = ActionChains(self.driver_)
            for y in range(stop_y, start_y, step_y):
                # await self.click(el, coord[0], y)
                action = action.move_to_element_with_offset(el, coord[0], y).click()
        if perform:
            action.perform()
        else:
            return action

    async def click(self, el, x_offset, y_offset):
        ActionChains(self.driver_). \
            move_to_element_with_offset(el, x_offset, y_offset). \
            click(). \
            perform()

    @staticmethod
    async def send_return(el):
        el.send_keys(Keys.RETURN)

    @staticmethod
    def add_default_options(options):
        options.add_argument("--ignore-certificate-errors")

    @staticmethod
    def add_binary_location(options, path, suggested_paths):
        if path is None:
            path = Browser.try_paths(suggested_paths)
        if not path:
            raise ValueError("Binary location not found.")
        options.binary_location = path

    @staticmethod
    def try_paths(paths):
        for p in paths:
            if os.path.isfile(p):
                return p
        return None


class Chrome(Browser):
    suggested_paths = ["/usr/bin/google-chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]

    def __init__(self, binary_path=None, proxy=None, foe_positions=None):
        options = webdriver.ChromeOptions()
        self.add_default_options(options)
        self.add_binary_location(options, binary_path, self.suggested_paths)
        # enable browser logging
        d = DesiredCapabilities.CHROME
        d['goog:loggingPrefs'] = {'browser': 'ALL'}
        if proxy:
            d['proxy'] = {
                "httpProxy": proxy,
                "ftpProxy": proxy,
                "sslProxy": proxy,
                "proxyType": "MANUAL",
            }
        driver = webdriver.Chrome(chrome_options=options, desired_capabilities=d)
        super().__init__(driver, foe_positions)


class Firefox(Browser):
    suggested_paths = ["/usr/bin/firefox", "/Applications/Firefox.app/Contents/MacOS/firefox"]

    def __init__(self, binary_path=None, proxy=None, foe_positions=None):
        options = webdriver.FirefoxOptions()
        self.add_default_options(options)
        self.add_binary_location(options, binary_path, self.suggested_paths)
        # enable browser logging
        d = DesiredCapabilities.FIREFOX
        d['loggingPrefs'] = {'browser': 'ALL'}
        if proxy:
            d['proxy'] = {
                "httpProxy": proxy,
                "ftpProxy": proxy,
                "sslProxy": proxy,
                "proxyType": "MANUAL",
            }
        driver = webdriver.Firefox(firefox_options=options, desired_capabilities=d)
        super().__init__(driver, foe_positions)
