import os

root_path = os.path.dirname(os.path.dirname(__file__))


class Settings(object):
    def __init__(self):
        self.foe_url = "https://us0.forgeofempires.com/page/"
        self.user = None  # Add your username instead, e.g. "Foo"
        self.password = None  # Add your username instead, e.g. "Bar"
        self.foe_world = None  # Add your foe world, e.g. "Zorskog"
        self.host = "0.0.0.0"
        self.proxy_binary = os.path.join(os.path.dirname(root_path), 'node/index.js')
        self.proxy_port = 8080
        self.server_port = 8090
        # wait between 1 to 2 hours
        self.cron_min = 300
        self.cron_max = 600
        self.idle_time_to_reopen = 20
        self.min_idle = 900
        self.max_idle = 1200
        self.idle_limit = 3600
        self.max_daily_abort = 2000  # max number of quests that can be aborted on a given day
        self.foe_data = FoeQuestsData()
        # Add a slack hook if you want your daily rewards post to slack
        # The hook should have this form 'https://hooks.slack.com/services/***/***/***'
        self.slack_api = None
        self.test_url = 'https://duckduckgo.com'

    @property
    def proxy_url(self):
        return "{}:{}".format(self.host, self.proxy_port)


class FoeQuestsData:
    def __init__(self):
        self.abort_for_help_quests = False
        # self.game_height = 754  # 900
        self.open_quests = (15, 160)
        self.abort = {
            'up': [(300, 260), (300, 500), None],
            # 'down': [None, (300, 284), (300, 524)],
            'continue': [None, (300, 305), (300, 550)]
        }
        # positions on continue position
        self.ubq = {
            'up': {
                'money': [(465, 200), (465, 440), None],
                'supplies': [(465, 270), (465, 510), None]
            },
            'continue': {
                'money': [None, (465, 220), (465, 460)],
                'supplies': [None, (465, 290), (465, 530)]
            }
        }
        self.collect = {
            'up': [(560, 230), None, None],
            # 'down': [None, (560, 250), (560, 470)],
            'continue': [None, (560, 270), (560, 470)]
        }
        self.close_quests = (15, 50)
        self.close_box = (15, 100)
        self.ubq_title = 'Unbirthday Party'
        self.y_offset = {
            'radius': 90,
            'step': 15
        }
        self.doubledip_quests = {
            'money': 'Fnord',
            'supplies': 'The Spink'
        }


