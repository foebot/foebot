import os
import sys
import subprocess as sp
from multiprocessing import Process
import requests
import traceback
import signal

dir_path = os.path.dirname(__file__)
sys.path.insert(0, os.path.dirname(dir_path))


# use to run an infinite loop without the bash script
# should use the bash script in priority
def post(err):
    from foebot.settings import Settings
    s = Settings()
    requests.post(s.slack_api, json={"main error": err})
    print(err)


def infinite_loop():
    
    signal.signal(signal.SIGINT, keyboard_interrupt_handler)
    while True:
        # git pull
        print('git pull ...')
        cmd = "cd {}; git pull".format(dir_path)
        print(sp.run(cmd, capture_output=True, shell=True, text=True).stdout)

        # run bot
        print("Starting bot ...")
        try:
            from foebot.__main__ import run_bot
            p = Process(target=run_bot)
            p.start()
            p.join()
        except KeyboardInterrupt:
            pass
        except Exception as exc:
            tb_str = traceback.format_exception(etype=type(exc), value=exc, tb=exc.__traceback__)
            post("".join(tb_str))
        print("Bot stopped.")


def do_continue(timeout=10):
    class TimeoutExpired(Exception):
        pass

    def interrupted(signum, frame):
        print('Timeout: the program will continue.')
        raise TimeoutExpired

    try:
        # set alarm
        signal.signal(signal.SIGALRM, interrupted)
        signal.alarm(timeout)
        # wait for input
        print('In {} seconds, the program will continue by default.'.format(timeout))
        input('Press ENTER to stop...\n')
        return False
    except TimeoutExpired:
        return True
    finally:
        # disable the alarm after success
        signal.alarm(0)


def keyboard_interrupt_handler(sig, frame):
    print("Bot interrupted.")
    err = "KeyboardInterrupt (ID: {}) has been caught.".format(sig)
    post(err)
    if do_continue():
        infinite_loop()


if __name__ == "__main__":
    infinite_loop()
