"""Tests for core.clock - Time management logic."""


class TestClockSpeed:
    def _make_clock(self):
        """Create a Clock-like object for testing speed logic."""

        # Clock inherits from pyglet.clock.Clock (a MagicMock),
        # so we test the methods directly on a simple namespace
        class FakeClock:
            _time = 0.0
            _speed = 1
            isFastForward = False
            name = "test"

        # Bind Clock methods to our fake
        from core.clock import Clock

        fc = FakeClock()
        fc.increase_speed = Clock.increase_speed.__get__(fc)
        fc.decrease_speed = Clock.decrease_speed.__get__(fc)
        fc.reset_speed = Clock.reset_speed.__get__(fc)
        fc.set_time = Clock.set_time.__get__(fc)
        fc.get_time = Clock.get_time.__get__(fc)
        return fc

    def test_initial_speed(self):
        """Default speed is 1."""
        c = self._make_clock()
        assert c._speed == 1

    def test_increase_speed(self):
        """Increase bumps speed by 1."""
        c = self._make_clock()
        c.increase_speed()
        assert c._speed == 2

    def test_max_speed_cap(self):
        """Speed cannot exceed 10."""
        c = self._make_clock()
        for _ in range(20):
            c.increase_speed()
        assert c._speed == 10

    def test_decrease_speed(self):
        """Decrease drops speed by 1."""
        c = self._make_clock()
        c._speed = 5
        c.decrease_speed()
        assert c._speed == 4

    def test_min_speed_cap(self):
        """Speed cannot go below 1."""
        c = self._make_clock()
        c.decrease_speed()
        assert c._speed == 1  # Can't go below 1

    def test_reset_speed(self):
        """Reset returns speed to 1."""
        c = self._make_clock()
        c._speed = 7
        c.reset_speed()
        assert c._speed == 1


class TestClockTime:
    def _make_clock(self):
        class FakeClock:
            _time = 0.0
            _speed = 1
            isFastForward = False
            name = "test"

        from core.clock import Clock

        fc = FakeClock()
        fc.set_time = Clock.set_time.__get__(fc)
        fc.get_time = Clock.get_time.__get__(fc)
        return fc

    def test_set_and_get_time(self):
        """set_time/get_time round-trip preserves value."""
        c = self._make_clock()
        c.set_time(42.5)
        assert c.get_time() == 42.5

    def test_initial_time(self):
        """Default time is 0.0."""
        c = self._make_clock()
        assert c.get_time() == 0.0


class TestExperimentClock:
    def test_observation_keeps_experiment_and_host_clock_domains_distinct(self):
        """A scenario time must never overwrite its host monotonic observation."""
        from core.experimentclock import ExperimentClock

        readings = iter((5_000_000_000, 5_020_000_000))
        clock = ExperimentClock(monotonic_ns=lambda: next(readings))

        first = clock.observe(1_000_000_000)
        second = clock.observe(1_010_000_000)

        assert first.experiment_time_ns == 1_000_000_000
        assert first.host_monotonic_ns == 5_000_000_000
        assert second.experiment_time_ns == 1_010_000_000
        assert second.host_monotonic_ns == 5_020_000_000

    def test_observation_rejects_clock_regression(self):
        """Regressing either authoritative clock would make event ordering ambiguous."""
        from core.experimentclock import ExperimentClock

        host_readings = iter((100, 99))
        clock = ExperimentClock(monotonic_ns=lambda: next(host_readings))
        clock.observe(10)
        try:
            clock.observe(11)
        except RuntimeError as exc:
            assert "host monotonic clock regressed" in str(exc)
        else:
            raise AssertionError("host clock regression was accepted")

        stable_host = iter((200, 201))
        clock = ExperimentClock(monotonic_ns=lambda: next(stable_host))
        clock.observe(10)
        try:
            clock.observe(9)
        except ValueError as exc:
            assert "experiment time regressed" in str(exc)
        else:
            raise AssertionError("experiment clock regression was accepted")
