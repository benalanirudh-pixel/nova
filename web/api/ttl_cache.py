"""Tiny per-process TTL cache shared by the per-symbol routes. Bounded so a scraper cannot grow memory."""
import time

CAP = 300  # entries per cache; each stock payload is ~100 KB


def get(cache: dict, key, ttl: float):
    hit = cache.get(key)
    return hit[1] if hit and time.monotonic() - hit[0] < ttl else None


def put(cache: dict, key, value, ttl: float) -> None:
    now = time.monotonic()
    for k in [k for k, (t, _) in cache.items() if now - t >= ttl]:
        del cache[k]
    while len(cache) >= CAP:
        del cache[next(iter(cache))]  # dicts keep insertion order: oldest first
    cache[key] = (now, value)
