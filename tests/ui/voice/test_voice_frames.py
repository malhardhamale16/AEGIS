import threading

import pytest

from aegis.ui.voice.frames import BoundedFrameQueue, Reframer


def test_reframer_exact_frames():
    r = Reframer(4)
    assert r.push(b"abcd") == [b"abcd"]
    assert r.pending == 0


def test_reframer_splits_and_carries_remainder():
    r = Reframer(4)
    assert r.push(b"abcdef") == [b"abcd"]
    assert r.pending == 2
    assert r.push(b"ghij") == [b"efgh"]
    assert r.push(b"") == []
    assert r.pending == 2


def test_reframer_rejects_bad_size():
    with pytest.raises(ValueError):
        Reframer(0)


def test_queue_fifo():
    q = BoundedFrameQueue(3)
    q.put(b"a")
    q.put(b"b")
    assert q.get(0) == b"a" and q.get(0) == b"b"
    assert q.get(0) is None


def test_queue_drops_oldest_when_full():
    q = BoundedFrameQueue(2)
    for f in (b"1", b"2", b"3", b"4"):
        q.put(f)
    assert len(q) == 2 and q.dropped == 2 and q.total == 4
    assert [q.get(0), q.get(0)] == [b"3", b"4"]


def test_get_times_out():
    assert BoundedFrameQueue(1).get(timeout=0.01) is None


def test_get_wakes_on_put_from_other_thread():
    q = BoundedFrameQueue(1)
    threading.Timer(0.02, q.put, args=(b"x",)).start()
    assert q.get(timeout=2) == b"x"


def test_clear():
    q = BoundedFrameQueue(2)
    q.put(b"a")
    q.clear()
    assert len(q) == 0


def test_queue_rejects_bad_size():
    with pytest.raises(ValueError):
        BoundedFrameQueue(0)
