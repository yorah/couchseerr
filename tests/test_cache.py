import os
import shutil

import pytest

from couchseerr.cache import TTL_DISCOVER, TTL_PROGRESS, FileCache

# geteuid() is POSIX-only; anything without it cannot be root either.
_IS_ROOT = getattr(os, "geteuid", lambda: -1)() == 0


class FakeClock(object):
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def test_miss_returns_none(tmp_path):
    assert FileCache(str(tmp_path)).get("absent") is None


def test_roundtrip(tmp_path):
    cache = FileCache(str(tmp_path), clock=FakeClock())
    cache.set("k", {"a": [1, 2]}, ttl=60)
    assert cache.get("k") == {"a": [1, 2]}


def test_entry_expires(tmp_path):
    clock = FakeClock()
    cache = FileCache(str(tmp_path), clock=clock)
    cache.set("k", "v", ttl=30)
    clock.now += 29
    assert cache.get("k") == "v"
    clock.now += 1
    assert cache.get("k") is None


def test_each_key_is_its_own_file(tmp_path):
    cache = FileCache(str(tmp_path), clock=FakeClock())
    cache.set("one", 1, ttl=60)
    cache.set("two", 2, ttl=60)
    assert len(list(tmp_path.iterdir())) == 2
    assert cache.get("one") == 1


def test_keys_with_path_characters_are_safe(tmp_path):
    cache = FileCache(str(tmp_path), clock=FakeClock())
    cache.set("/discover/trending?language=fr", "v", ttl=60)
    assert cache.get("/discover/trending?language=fr") == "v"
    assert len(list(tmp_path.iterdir())) == 1


def test_purge_removes_only_expired(tmp_path):
    clock = FakeClock()
    cache = FileCache(str(tmp_path), clock=clock)
    cache.set("short", 1, ttl=10)
    cache.set("long", 2, ttl=1000)
    clock.now += 100
    assert cache.purge_expired() == 1
    assert cache.get("long") == 2


def test_corrupt_entry_is_treated_as_a_miss(tmp_path):
    cache = FileCache(str(tmp_path), clock=FakeClock())
    cache.set("k", "v", ttl=60)
    entry = next(tmp_path.iterdir())
    entry.write_text("{ not json")
    assert cache.get("k") is None


def test_progress_ttl_is_much_shorter_than_discover_ttl():
    """Progress is live data; serving it stale defeats the point of showing it."""
    assert TTL_PROGRESS <= 60 < TTL_DISCOVER


def test_repeat_set_same_key_keeps_one_file_last_wins(tmp_path):
    """Proxy for two concurrent writers to the same key: no splicing, no leftovers."""
    cache = FileCache(str(tmp_path), clock=FakeClock())
    cache.set("k", "first", ttl=60)
    cache.set("k", "second", ttl=60)
    assert len(list(tmp_path.iterdir())) == 1
    assert cache.get("k") == "second"


@pytest.mark.skipif(
    _IS_ROOT,
    reason="root bypasses the 0o500 mode, so the write succeeds and the test asserts "
    "a condition that cannot occur -- a red that says nothing about the code",
)
def test_set_on_unwritable_root_does_not_raise(tmp_path):
    cache = FileCache(str(tmp_path), clock=FakeClock())
    os.chmod(str(tmp_path), 0o500)
    try:
        cache.set("k", "v", ttl=60)
    finally:
        os.chmod(str(tmp_path), 0o700)
    assert cache.get("k") is None


def test_purge_expired_returns_zero_if_root_is_gone(tmp_path):
    cache = FileCache(str(tmp_path), clock=FakeClock())
    shutil.rmtree(str(tmp_path))
    assert cache.purge_expired() == 0


def test_delete_removes_only_the_named_key(tmp_path):
    """A request invalidates one title's detail. Taking neighbours with it would cost a
    refetch of every other title already on screen."""
    cache = FileCache(str(tmp_path), clock=FakeClock())
    cache.set("a", "first", ttl=60)
    cache.set("b", "second", ttl=60)

    cache.delete("a")

    assert cache.get("a") is None
    assert cache.get("b") == "second"


def test_delete_of_an_absent_key_does_not_raise(tmp_path):
    """Absent is not a failure: the postcondition is "not cached", and a key that was
    never written already satisfies it."""
    cache = FileCache(str(tmp_path), clock=FakeClock())
    cache.delete("never-written")
    assert cache.get("never-written") is None
