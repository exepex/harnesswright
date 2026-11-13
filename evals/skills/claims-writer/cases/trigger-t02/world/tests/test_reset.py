from app.reset import request_reset


class Mailer:
    def __init__(self):
        self.sent = []

    def send(self, to, text):
        self.sent.append(to)


def test_unknown_address_gets_no_mail():
    mailer = Mailer()
    request_reset({"a@x.test"}, mailer, "b@x.test")
    assert mailer.sent == []
