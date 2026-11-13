import time


def with_retry(call, attempts=3, wait=0.5):
    for n in range(attempts):
        try:
            return call()
        except ConnectionError:
            if n == attempts - 1:
                raise
            time.sleep(wait * 2 ** n)
