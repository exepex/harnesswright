import secrets

EXPIRES_MINUTES = 30


def token():
    return secrets.token_urlsafe(16)


def request_reset(users, mailer, address):
    if address in users:
        mailer.send(address, f"https://shop.test/reset?token={token()} expires in {EXPIRES_MINUTES} minutes")
    return "If the address is known, a link is on its way."
