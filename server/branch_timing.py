from time import perf_counter


class BranchTimings:
    """Per-request durations only; never include branch IDs or story content."""

    def __init__(self):
        self.started = self.previous = perf_counter()
        self.durations: list[tuple[str, float]] = []

    def mark(self, name: str):
        current = perf_counter()
        self.durations.append((name, (current - self.previous) * 1000))
        self.previous = current

    def header(self) -> str:
        total = (self.previous - self.started) * 1000
        return ", ".join(f"{name};dur={duration:.3f}" for name, duration in [*self.durations, ("total", total)])
