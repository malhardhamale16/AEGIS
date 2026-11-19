import threading

import pytest

from aegis.core.events import WILDCARD, EventBus


def test_publish_delivers_to_topic_subscribers():
    bus = EventBus()
    got = []
    bus.subscribe("a", got.append)
    event = bus.publish("a", {"x": 1})
    assert got == [event]
    assert event.topic == "a" and event.payload == {"x": 1}


def test_other_topics_not_delivered():
    bus = EventBus()
    got = []
    bus.subscribe("a", got.append)
    bus.publish("b")
    assert got == []


def test_wildcard_receives_everything():
    bus = EventBus()
    got = []
    bus.subscribe(WILDCARD, lambda e: got.append(e.topic))
    bus.publish("a")
    bus.publish("b")
    assert got == ["a", "b"]


def test_unsubscribe_via_returned_function():
    bus = EventBus()
    got = []
    unsub = bus.subscribe("a", got.append)
    unsub()
    bus.publish("a")
    assert got == []
    assert bus.subscriber_count("a") == 0


def test_failing_handler_does_not_break_others():
    bus = EventBus()
    got = []

    def bad(_):
        raise RuntimeError("handler bug")

    bus.subscribe("a", bad)
    bus.subscribe("a", got.append)
    bus.publish("a")
    assert len(got) == 1


def test_payload_is_copied():
    bus = EventBus()
    payload = {"k": 1}
    event = bus.publish("a", payload)
    payload["k"] = 2
    assert event.payload == {"k": 1}


@pytest.mark.parametrize("topic", ["", WILDCARD])
def test_invalid_publish_topics(topic):
    with pytest.raises(ValueError):
        EventBus().publish(topic)


def test_empty_subscribe_topic_rejected():
    with pytest.raises(ValueError):
        EventBus().subscribe("", print)


def test_concurrent_publish_is_safe():
    bus = EventBus()
    count = 0
    lock = threading.Lock()

    def inc(_):
        nonlocal count
        with lock:
            count += 1

    bus.subscribe("t", inc)
    threads = [
        threading.Thread(target=lambda: [bus.publish("t") for _ in range(100)]) for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert count == 800
