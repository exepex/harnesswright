"""Store an uploaded file for a user."""


class QuotaFull(Exception):
    pass


def store(user, name, data):
    if user.used + len(data) > user.quota:
        raise QuotaFull(f"QUOTA_EXCEEDED uid={user.id} used={user.used} quota={user.quota}")
    user.files[name] = data
    user.used += len(data)
