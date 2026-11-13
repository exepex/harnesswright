import time


class Limiter:
    def __init__(self, per_second=10):
        self.per_second, self.seen = per_second, {}

    def allow(self, client):
        now = int(time.time())
        key = (client, now)
        self.seen[key] = self.seen.get(key, 0) + 1
        return self.seen[key] <= self.per_second
