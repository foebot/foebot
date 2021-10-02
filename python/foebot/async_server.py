from aiohttp import web
from requests import get
import logging
import json
import re
import foebot.asyncio_helpers as ah
import asyncio


class AsyncServer:
    def __init__(self, bot):
        self.bot = bot
        self.app = web.Application()
        self.runner = None
        self.site = None
        logging.basicConfig(level=logging.INFO)

    async def start(self, host, port):
        async def handle(req):
            if 'json' in req.content_type:
                data = await req.content.read(req.content_length)
                self.bot.append_json(json.loads(data))
            return web.Response()
        self.app.router.add_post('/', handle)

        async def handle_abort(req):
            try:
                n = int(req.query['n'])
                self.bot.s_.max_daily_abort = n
                self.bot.quests_helper.reset_abort_left(n)
                return web.json_response({"abort": self.bot.s_.max_daily_abort})
            except Exception as e:
                return web.json_response({"error": type(e).__name__})
        self.app.router.add_get('/abort', handle_abort)

        async def handle_reset(req):
            try:
                self.bot.quests_helper.reset(self.bot.s_.max_daily_abort)
                return web.json_response({"reset": "Done"})
            except Exception as e:
                return web.json_response({"error": type(e).__name__})
        self.app.router.add_get('/reset', handle_reset)

        async def handle_shutdown(req):
            async def shutdown():
                await ah.wait(1)
                self.bot.shutdown()
            asyncio.ensure_future(shutdown())
            return web.json_response({"shutdown": "kill process in 5 seconds."})
        self.app.router.add_get('/shutdown', handle_shutdown)

        async def start():
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, host, port)
            await self.site.start()
        await start()

    async def stop(self):
        await self.site.stop()


ip_pat = re.compile("^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def get_IP():
    ip = get('https://api.ipify.org').text
    return ip if ip_pat.match(ip) else None
