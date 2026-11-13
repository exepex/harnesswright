from src.search.limit import Limiter

LIMITER = Limiter()


def handle(path, client, serve):
    if path == "/search" and not LIMITER.allow(client):
        return 429, {"Retry-After": "1"}, ""
    return serve(path)
