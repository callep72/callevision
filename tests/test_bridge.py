"""Unit tests for bridge.py."""

from callevision import bridge


class _FakeTimer:
    def __init__(self, interval, callback):
        self.interval = interval
        self.callback = callback
        self.started = False
        self.cancelled = False
        self.daemon = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.callback()


class TestParseTopic:
    def test_json_topic(self):
        assert bridge._parse_topic("callevision/pages/200") == (200, False)

    def test_raw_topic(self):
        assert bridge._parse_topic("callevision/pages/200/raw") == (200, True)

    def test_rejects_out_of_range_page(self):
        assert bridge._parse_topic("callevision/pages/99") is None

    def test_rejects_unexpected_suffix(self):
        assert bridge._parse_topic("callevision/pages/200/fastext") is None


class TestServiceReloader:
    def test_immediate_restart_when_debounce_disabled(self):
        restarts = []
        reloader = bridge._ServiceReloader(
            "svc",
            0,
            restart_func=restarts.append,
        )

        reloader.request()

        assert restarts == ["svc"]

    def test_multiple_requests_collapse_to_single_restart(self):
        restarts = []
        timers = []

        def timer_factory(interval, callback):
            timer = _FakeTimer(interval, callback)
            timers.append(timer)
            return timer

        reloader = bridge._ServiceReloader(
            "svc",
            750,
            restart_func=restarts.append,
            timer_factory=timer_factory,
        )

        reloader.request()
        reloader.request()

        assert len(timers) == 2
        assert timers[0].cancelled
        assert timers[1].started
        assert timers[1].interval == 0.75

        timers[1].fire()

        assert restarts == ["svc"]

    def test_close_cancels_pending_timer(self):
        restarts = []
        timers = []

        def timer_factory(interval, callback):
            timer = _FakeTimer(interval, callback)
            timers.append(timer)
            return timer

        reloader = bridge._ServiceReloader(
            "svc",
            750,
            restart_func=restarts.append,
            timer_factory=timer_factory,
        )

        reloader.request()
        reloader.close()

        assert timers[0].cancelled
        assert restarts == []
