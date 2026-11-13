EXPIRES_MINUTES = 30


def request_reset(users, mailer, address):
    if address in users:
        mailer.send(address, f"Reset link, valid {EXPIRES_MINUTES} minutes")
    return "If the address is known, a link is on its way."
