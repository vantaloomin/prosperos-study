import hashlib

ALGORITHM = "sha256-counter-rejection-v1"


class Draws:
    def __init__(self, seed):
        self.seed = seed
        self.counters = {}
        self.log = []

    def die(self, sides, stream, purpose):
        counter = self.counters.get(stream, 0)
        limit = (1 << 256) - ((1 << 256) % sides)
        while True:
            digest = hashlib.sha256(f"{ALGORITHM}:{self.seed}:{stream}:{counter}".encode()).digest()
            counter += 1
            number = int.from_bytes(digest, "big")
            if number < limit:
                break
        self.counters[stream] = counter
        result = number % sides + 1
        self.log.append({"stream": stream, "counter": counter, "purpose": purpose,
                         "sides": sides, "result": result})
        return result
