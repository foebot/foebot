import asyncio
import random


import logging

logging.basicConfig(format="[Bot][%(asctime)-15s] %(message)s",
                    level=logging.INFO,
                    datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


def debug(s):
    logger.info(s)


def info(s):
    logger.info(s)


async def wait(delay=1):
    await asyncio.sleep(delay)


async def random_wait(t_min=1, t_max=2):
    await wait(random.uniform(t_min, t_max))


def defer(coco):
    return asyncio.create_task(coco)


async def await_task(t):
    await t


def sleep(t=0):
    def sleep_decorator(func):
        async def decorated_func(*args, **kwargs):
            await asyncio.sleep(t)
            return await func(*args, **kwargs)
        return decorated_func
    return sleep_decorator


