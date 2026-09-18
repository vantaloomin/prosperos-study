import math

from server.database import encode


def token_estimate(prompt, content):
    return math.ceil(len((prompt + encode(content)).encode('utf-8')) / 3)
