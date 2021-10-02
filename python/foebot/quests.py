import json
import sys
from datetime import datetime as dt
import foebot.asyncio_helpers as ah


class QuestsHelper:
    def __init__(self, bot):
        self.bot = bot
        self.all_quests = {}
        self.stats = Stats()
        self.data = bot.s_.foe_data
        self.quests = Quests(self.data)
        self.fetch = None
        self.n_abort_left = bot.s_.max_daily_abort
        self.n_cons_abort = 0

    def add_quests(self):
        for q in self.quests:
            if q.rq:
                self.all_quests[q.title] = q

    def reset(self, max_daily_abort=None):
        self.all_quests = {}
        self.stats.max = {}
        if max_daily_abort:
            self.reset_abort_left(max_daily_abort)

    def reset_abort_left(self, max_daily_abort):
        self.n_abort_left = max_daily_abort
        self.n_cons_abort = 0

    def can_abort(self):
        return self.n_abort_left > 0

    async def process(self, quests, sort_quests):
        # parse quests
        self.quests.add(quests, sort_quests)

        # add them to all_quests
        self.add_quests()

        # if fetching, check if present
        if self.fetch is not None:
            if not self.quests.contains(self.fetch):
                if await self.abort_first():
                    return True

        # check if any quest to collect
        if await self.try_collect():
            return True

        # if not being able to connect with fetch present -> reset fetch
        self.fetch = None

        # check if UBQ present and try to do it
        p = self.quests.contains(self.data.ubq_title)
        if p and await self.ubq(p[0], p[1]):
            return True

        # otherwise, abort all quests to fetch UBQ abort_all_available
        if await self.abort_first():
            return True

        # if not able to abort, force collection
        return await self.try_collect(False)

    async def try_collect(self, fetching=True):
        to_collect = self.quests.can_be_collected()
        if not to_collect:
            return False

        indices = None
        # check if there are any quests that can be aborted and is not in progress
        abortable_quests = [q for q in self.quests
                            if not q.can_be_collected() 
                            and q.abortable
                            and not q.in_progess()]
        # if not fetching and fetching enable
        if self.fetch is None and fetching:
            # check the one that meet a condition
            indices = self.quests.meet_conditions(to_collect, self.all_quests)
            # check the one that help a condition and there are any abortable quests
            if self.data.abort_for_help_quests and not indices and abortable_quests:
                indices = self.quests.help_conditions(to_collect, self.all_quests)
        # if none, put all of them
        if not indices:
            indices = [(c, None) for c in to_collect]

        # collect first indices
        for p in indices:
            # if no quest condition to meet/help
            # or has not been able to fetch quest
            # -> collect immediately
            if p[1] is None or self.fetch:
                if await self.collect_quest(p[0]):
                    return True
            # if quest to fetch already there, check if:
            # 1- the quest is completed -> collect this quest and then fetch it
            # 2- the quest is already there
            p2 = self.quests.contains(p[1])
            if p2:
                if p2[1].can_be_collected():
                    if await self.collect_quest(p2[0]):
                        self.fetch = p2[1].title
                        return True
                elif await self.collect_quest(p[0]):
                    return True

            # otherwise fetch the quest
            else:
                if await self.abort_first():
                    self.fetch = p[1]
                    return True
        return False

    async def collect_quest(self, i):
        if await self.bot.collect_quest(i, self.quests):
            self.fetch = None
            self.stats.collect_reward(self.quests.get(i))
            self.quests.remove(i)
            self.n_cons_abort = 0
            return True

    async def ubq(self, i, q):
        if await self.bot.ubq(i, self.quests):
            self.stats.pay(q.conditions)
            self.n_cons_abort = 0
            return True
        return False

    def check_if_abort(self):
        ah.info("There are %d aborts left." % self.n_abort_left)
        # if too many consecutive abort, clear and return
        if self.n_cons_abort > 2*len(self.all_quests) + 1:
            self.quests.quests = []
            self.n_abort_left += self.n_cons_abort
            self.n_cons_abort = 0
            return False
        # if too many abort
        return self.can_abort()

    async def abort_quests(self, indices):
        if not isinstance(indices, list):
            indices = [indices]
        indices = await self.bot.abort_quests(indices, self.quests)
        if indices:
            for i in indices:
                self.quests.remove(i)
            self.n_cons_abort += len(indices)
            self.n_abort_left -= len(indices)
            return True
        return False

    async def abort_first(self):
        quests = list(enumerate(self.quests))
        return await self.abort_first_quest(quests)

    async def abort_last(self):
        quests = list(enumerate(self.quests))
        quests.reverse()
        return await self.abort_first_quest(quests)

    async def abort_first_quest(self, quests):
        # check if can abort
        if not self.check_if_abort():
            return False
        second_try = []
        third_try = {}
        for (i, q) in quests:
            if not q.can_be_collected() and q.abortable:
                if q.in_progess():
                    third_try[i] = q
                elif q.title in self.data.doubledip_quests.values():
                    amount = find_quantity(q.conditions[0]['description'])
                    second_try.append((i, q, amount))
                elif await self.abort_quests(i):
                    return True
        second_try = sorted(second_try, key=lambda e: e[2])
        for i, q, a in second_try:
            if await self.abort_quests(i):
                return True
        for i, q in third_try.items():
            if await self.abort_quests(i):
                return True
        return False

    async def abort_all_available(self, include_in_progress=False):
        # check if can abort
        if not self.check_if_abort():
            return False
        quests_to_abort = [i for i, q in enumerate(self.quests)
                           if not q.can_be_collected() and q.abortable and
                           (include_in_progress or not q.in_progess())]
        quests_to_abort.reverse()  # abort bottom quests first
        aborted = await self.abort_quests(quests_to_abort)
        if not aborted and not include_in_progress:
            return await self.abort_all_available(True)
        return aborted

    def print_stats(self):
        ah.info(self.stats_to_string())

    def stats_to_string(self):
        return '[{}] Stats: {}'.format(dt.now(), self.stats)

    def reset_stats(self):
        self.stats = Stats()


class Stats:
    def __init__(self):
        self.s = {
            'good': {}
        }
        self.max = {}
        self.n_pay = 0
        self.n_collect = {}

    def __str__(self):
        return json.dumps(self.json(), indent=4, sort_keys=True)

    def json(self):
        return {
            'rewards': self.s,
            'n_pay': self.n_pay,
            'n_collect': self.n_collect
        }

    def collect_reward(self, q):
        for r in q.rewards:
            t = r['type']
            if t == 'good':
                add(self.s['good'], r['subType'], r['amount'])
            elif t == 'resource':
                add(self.s, r['subType'], r['amount'])
                if (r['subType'] not in self.max) or (self.max[r['subType']] < r['amount']):
                    self.max[r['subType']] = r['amount']
            else:
                add(self.s, r['type'], r['amount'])
        add(self.n_collect, q.title, 1)

    def pay(self, conditions):
        for c in conditions:
            if Quest.unprocess(c):
                q = find_quantity(c['description'])
                subtract(self.s, c['iconType'], q)
        self.n_pay += 1


class Quests:
    def __init__(self, data):
        self.data = data
        self.quests = []
        self.counts = {}

    def __iter__(self):
        return iter(self.quests)

    def add(self, quests, sort):
        quests = [Quest(q) for q in quests]
        for q in quests:
            if q.title not in self.counts:
                self.counts[q.title] = 1
            else:
                self.counts[q.title] += 1
            q.n = self.counts[q.title]
        if sort:
            self.__sort(quests)
        else:
            self.__push_missing(quests)
        ah.info('Quests: %s' % ', '.join(q.title for q in self.quests))

    def __sort(self, quests):
        def key_comp(q):
            return q.n, \
                   q.can_be_collected(), \
                   q.in_progess(), \
                   not q.rq, \
                   -quests.index(q)  # otherwise keep same order
        self.quests = sorted(quests, key=key_comp, reverse=True)

    def __push_missing(self, quests):
        absent = list(range(len(self.quests)))
        missing = []
        for q in quests:
            p = self.contains(q.title)
            if p:
                absent.remove(p[0])
                self.quests[p[0]] = q
            else:
                missing.append(q)
        for i in reversed(absent):
            self.remove(i)
        self.quests += missing
        if len(self.quests) != len(quests):
            ah.info("WARNING: The quests list has not the right size: "
                    "{} vs {}".format(len(self.quests), len(quests)))
            self.quests = quests

    def remove(self, i):
        self.counts[self.quests[i].title] = 0
        del self.quests[i]

    def reset_counts(self):
        self.counts = {}

    def can_be_collected(self):
        return [i for i, q in enumerate(self.quests) if q.can_be_collected()]

    def meet_conditions(self, indices, all_quests):
        def check(q, rewards):
            return q.meet_condition(rewards, self.data.doubledip_quests)
        return self.check_conditions(indices, all_quests, check)

    def help_conditions(self, indices, all_quests):
        def check(q, rewards):
            return q.help_condition(rewards, self.data.doubledip_quests)
        return self.check_conditions(indices, all_quests, check)

    def check_conditions(self, indices, all_quests, check):
        meet_indices = []
        for i in indices:
            q1 = self.get(i)
            meet_q = None
            for q2 in all_quests.values():
                # check if q2 available
                avail = True
                for j in indices:
                    if self.get(j).title == q2.title:
                        avail = False
                        break
                if not avail:
                    continue
                # check reward against q2 conditions
                for r in q1.rewards:
                    if check(q2, r):
                        meet_q = q2
                        break
                if meet_q:
                    meet_indices.append((i, meet_q.title))
                    break
        return meet_indices

    def contains(self, title):
        for i, q in enumerate(self.quests):
            if title == q.title:
                return i, q
        return None

    def get(self, i):
        return self.quests[i]


class Quest:
    def __init__(self, q):
        self.rq = q['windowTitle'].startswith('Recurring Quest')
        self.title = q['title']
        self.priority = q['priority']
        self.abortable = q['abortable']
        self.state = q['state']  # normally accepted
        self.rewards = q['genericRewards']  # q['rewards'] +
        self.conditions = q['successConditions']
        self.n = 1

    def find_unprocess_condition(self):
        for i, c in enumerate(self.conditions):
            if self.unprocess(c):
                return i
        return -1

    @staticmethod
    def unprocess(c):
        return 'currentProgress' not in c or c['currentProgress'] < c['maxProgress']

    def can_be_collected(self):
        return self.state == 'collectReward'

    def in_progess(self):
        for c in self.conditions:
            if 'currentProgress' in c:
                return True
        return False

    def help_condition(self, reward, doubledip_quests):
        t = reward['subType']
        if t in doubledip_quests and doubledip_quests[t] == self.title:
            return True
        return False

    def meet_condition(self, reward, doubledip_quests):
        t = reward['subType']
        if t in doubledip_quests and doubledip_quests[t] == self.title:
            self.excess_quantity(reward['amount'])
        return False

    def excess_quantity(self, amount):
        q = find_quantity(self.conditions[0]['description'])
        return amount >= q


def add(d, k, v):
    if k in d:
        d[k] += v
    else:
        d[k] = v


def subtract(d, k, v):
    add(d, k, -v)


def find_quantity(s_quant, p=' '):
    qs = [s for s in s_quant.split(p) if s[0].isdigit()]
    # remove any thousands commas
    q = "".join(qs[0].split(','))
    return int(q)
