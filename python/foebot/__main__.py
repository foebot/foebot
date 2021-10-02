import os
import sys

root_path = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, root_path)


def run_bot():
    from foebot.bot import Bot
    bot = Bot(browser_name="Chrome")
    bot()


if __name__ == "__main__":
    run_bot()
