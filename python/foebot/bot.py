import asyncio
import foebot.browser as browser
from foebot.settings import Settings
from foebot.quests import QuestsHelper
from foebot.async_server import AsyncServer, get_IP
import requests
import time
import datetime as dt
import urllib3
from threading import Thread
from subprocess import Popen
import signal
import os
import sys
import tracemalloc
import foebot.asyncio_helpers as ah
import random
import traceback

tracemalloc.start()


class Bot(object):
    def __init__(self, foe_settings=None, browser_name="Firefox", binary_location=None):
        self.s_ = foe_settings if foe_settings else Settings()
        self.last_json_processed_ = 0
        self.json_queue_ = []
        self.quests_helper = QuestsHelper(self)
        self.today = dt.date.today()
        self.processing = False
        self.shutting_down = False
        self.quests_position_top = True  # become false as soon as a quest has been aborted or collected

        self.browser_ = None
        if browser_name == "Firefox":
            self.browser_ = browser.Firefox(binary_location, self.s_.proxy_url, self.s_.foe_data)
        elif browser_name == "Chrome":
            self.browser_ = browser.Chrome(binary_location, self.s_.proxy_url, self.s_.foe_data)

        self.proxy_process = None
        self.proxy_thread = None
        self.start_proxy()

        self.ip = None
        self.update_ip()

        self.register_signals()

    def start_proxy(self):
        def run():
            try:
                self.proxy_process = Popen(['node', self.s_.proxy_binary])
                self.proxy_process.communicate()
            except Exception as err:
                print(err)
            except KeyboardInterrupt:
                pass
            finally:
                self.proxy_process.terminate()
                sys.exit()

        self.proxy_thread = Thread(target=run)
        self.proxy_thread.start()
        while True:
            try:
                requests.get(self.s_.test_url, proxies={'https': self.s_.proxy_url})
                break
            except requests.exceptions.ProxyError:
                time.sleep(1)

    async def start_server(self):
        s = AsyncServer(self)
        await s.start(self.s_.host, self.s_.server_port)

    def register_signals(self):
        def shutdown(signum, frame):
            signal.signal(signum, kill)
            self.shutdown()

        def kill(signum, frame):
            self.kill()

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

    def shutdown(self):
        self.post_stats()
        self.shutting_down = True
        self.browser_.quit()
        self.proxy_process.terminate()
        self.proxy_thread.join()
        sys.exit()

    def kill(self):
        self.proxy_process.kill()
        os.kill(os.getpid(), signal.SIGKILL)
        sys.exit()

    def __call__(self, *args, **kwargs):
        try:
            asyncio.run(self.run())
        except KeyboardInterrupt:
            pass
        except urllib3.exceptions.HTTPError:
            pass

    async def run(self):
        t = ah.defer(self.start_server())
        await self.connect()
        await asyncio.gather(ah.await_task(t), self.control(), self.check_json())

    async def control(self):
        """ Cron job to control the flow. Refresh browser if it has been idle since too long. """
        r = random.randint(self.s_.min_idle, self.s_.max_idle)
        tried_reconnect = False
        while True:
            idle = self.idle_time()
            if idle > self.s_.idle_limit + r:
                await self.connect()
                r = random.randint(self.s_.min_idle, self.s_.max_idle)
            elif idle > r and tried_reconnect:
                self.quests_helper.print_stats()
                await self.reconnect()
                r = random.randint(self.s_.min_idle, self.s_.max_idle)
                tried_reconnect = True
            else:
                tried_reconnect = False
            await ah.random_wait(self.s_.cron_min, self.s_.cron_max)

    async def start_processing(self):
        while self.processing:
            await ah.random_wait()
        self.processing = True

    def end_processing(self):
        self.processing = False

    @browser.retry()
    async def connect(self):
        await self.start_processing()
        try:
            await self.login()
            await self.play()
            await self.open_quests()
        finally:
            self.end_processing()

    @browser.retry(raise_error=False)
    async def reconnect(self):
        await self.start_processing()
        try:
            await self.refresh()
            await self.open_quests()
        finally:
            self.end_processing()

    @browser.retry()
    async def login(self):
        await self.browser_.get(self.s_.foe_url)
        await self.enter_login()
        await ah.wait(10)

    @browser.retry(max_retry=1, raise_error=False)
    async def enter_login(self):
        if not self.s_.user:
            raise ValueError("You must set a user in the settings")
        if not self.s_.password:
            raise ValueError("You must set a password in the settings")
        await self.browser_.switch_to(0)
        try:
            el = await self.browser_.find_id("login_userid")
            el.send_keys(self.s_.user)
            el = await self.browser_.find_id("login_password")
            el.send_keys(self.s_.password)
            await self.browser_.send_return(el)
            return True
        finally:
            await self.browser_.switch_to_parent()

    @browser.retry()
    async def play(self):
        el = await self.browser_.find_id("play_now_button")
        el.click()
        await ah.wait(5)
        if not self.s_.foe_world:
            raise ValueError("You must set a foe world in the settings")
        el = await self.browser_.find_xpath("//*[contains(text(),'{}')]".format(self.s_.foe_world))
        el.click()
        await ah.wait(40)
        self.last_json_processed_ = time.time()

    @browser.retry()
    async def refresh(self):
        await self.browser_.refresh()

    @browser.retry()
    async def open_quests(self):
        action = None
        for i in range(15):
            action = await self.browser_.game_click(self.s_.foe_data.close_quests, action=action, perform=False)
        action.perform()
        await ah.wait()
        await self.browser_.game_click(self.s_.foe_data.open_quests)
        self.quests_position_top = True
        self.quests_helper.quests.reset_counts()

    def append_json(self, data):
        """ Append RQ """
        # if queue non empty, reset timestamp
        self.json_queue_.append(data)

    @browser.retry()
    async def check_json(self, dataq=None):
        # wait a little and then process
        while True:
            self.update_date()
            self.update_ip()

            try:
                await ah.random_wait(2, 3)
                await self.start_processing()

                @browser.retry(max_retry=1, raise_error=False)
                async def check_json_no_error(dataq2):
                    idle = self.idle_time()
                    ah.info('Check json: idle for {} sec.'.format(idle))
                    if idle > self.s_.idle_time_to_reopen:
                        # try to reopen quests menu
                        ah.info('Idle for {} s. => close and open quests menu, '
                                'then collect and abort quests on top of the menu.'.format(idle))
                        await self.open_quests()
                        await ah.wait(5)
                        # try abort to restart loop engine if needed by collecting up
                        if self.quests_helper.can_abort():
                            await self.click_cluster(self.s_.foe_data.collect['up'])
                            await self.click_cluster(self.s_.foe_data.abort['up'])
                            self.quests_position_top = False
                            await ah.wait(5)
                        else:
                            # if no more aborts left, wait until the end of the day
                            tomorrow = dt.date.today() + dt.timedelta(days=1)
                            seconds_left = dt.datetime.combine(tomorrow, time=dt.time.min) - dt.datetime.now()
                            ah.info('Wait until next day (for {})'.format(seconds_left))
                            self.post_stats()
                            await ah.wait(seconds_left.total_seconds())
                        dataq2 = []
                    return await self.process_json(dataq2 if dataq2 else [])

                dataq = await check_json_no_error(dataq)
            finally:
                self.end_processing()

    async def process_json(self, dataq=None):
        """ Append data and process it """
        try:
            reprocessing = True
            if self.json_queue_:
                dataq = self.json_queue_
                self.reset_queue()
                reprocessing = False

            if dataq:
                await self.process_data(dataq[-1], self.quests_position_top or reprocessing)
        except Exception:
            traceback.print_exc()
        finally:
            # recheck queue later on to see if empty
            return dataq

    async def process_data(self, data, just_opened_quests):
        try:
            quests = [q for q in data['responseData']
                      if q['windowTitle'].startswith('Story Quest')
                      or q['windowTitle'].startswith('Recurring Quest')]
            return await self.quests_helper.process(quests, just_opened_quests)
        except KeyError:
            return False

    async def abort_quests(self, indices, quests):
        ah.info('Abort quests in positions %s.' % str(indices))
        return await self.click_for(self.s_.foe_data.abort, indices, quests)

    async def collect_quest(self, i, quests):
        ah.info('Collect quest in position %d.' % i)
        if await self.click_for(self.s_.foe_data.collect, [i], quests):
            await self.browser_.game_click(self.s_.foe_data.close_box)
            return True
        return False

    async def click_for(self, data_positions, indices, quests):
        p = self.positions_prefix()
        # check if click position available
        data_positions = data_positions[p]
        indices = [i for i in indices if data_positions[i] is not None]
        positions = [data_positions[i] for i in indices]
        if not positions:
            return []
        await self.browser_.game_multiple_clicks(positions, self.s_.foe_data.y_offset)
        self.quests_position_top = False
        return indices

    async def click_cluster(self, data_positions):
        action = None
        for p in data_positions:
            if p:
                action = await self.browser_.game_click(p, self.s_.foe_data.y_offset, action=action, perform=False)
        if action:
            action.perform()

    async def ubq(self, i, quests):
        p = self.positions_prefix()
        q = quests.get(i)
        for c in q.conditions:
            if q.unprocess(c):
                # check if click position available
                positions = self.s_.foe_data.ubq[p][c['iconType']][i]
                if positions is None:
                    return False
                await self.browser_.game_click(positions, self.s_.foe_data.y_offset)
        return True

    def reset_queue(self):
        self.last_json_processed_ = time.time()
        self.json_queue_ = []

    def idle_time(self):
        return time.time() - self.last_json_processed_

    def positions_prefix(self):
        return 'up' if self.quests_position_top else 'continue'

    def is_big(self, q):
        return q.title in self.s_.foe_data.big_quests_titles

    def update_date(self):
        if self.today != dt.date.today():
            self.quests_helper.reset_abort_left(self.s_.max_daily_abort)
            self.post_stats()
            self.today = dt.date.today()

    def update_ip(self):
        ip = get_IP()
        if ip is not None and self.ip != ip:
            self.ip = ip
            if self.s_.slack_api:
                requests.post(self.s_.slack_api, json={
                    "text": "Update number of abort on http://{}/abort?n=2000.\n"
                            "Reset quests on http://{}/reset.".format(ip, ip)
                })

    def post_stats(self):
        if self.s_.slack_api:
            requests.post(self.s_.slack_api, json={"text": self.quests_helper.stats_to_string()})
            self.quests_helper.reset_stats()
