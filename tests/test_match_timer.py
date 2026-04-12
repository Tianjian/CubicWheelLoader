"""MatchTimer 单元测试（Layer 2 — Mock time.dt）"""
import pytest
from unittest.mock import patch


class TestMatchTimer:
    """比赛计时器测试"""

    @pytest.fixture
    def timer(self, ursina_app):
        from arena.match_timer import MatchTimer
        t = MatchTimer()
        yield t
        from ursina import destroy
        destroy(t)

    def test_initial_state(self, timer):
        assert timer.remaining == 300
        assert timer.is_running is False

    def test_start(self, timer):
        timer.start()
        assert timer.is_running is True

    def test_stop(self, timer):
        timer.start()
        timer.stop()
        assert timer.is_running is False

    def test_reset(self, timer):
        timer.start()
        timer.remaining = 100
        timer.reset()
        assert timer.remaining == 300
        assert timer.is_running is False

    def test_countdown(self, timer):
        timer.start()
        with patch('ursina.time.dt', 1.0):
            timer.update()
        assert timer.remaining == pytest.approx(299.0)

    def test_no_countdown_when_stopped(self, timer):
        with patch('ursina.time.dt', 1.0):
            timer.update()
        assert timer.remaining == 300

    def test_time_reaches_zero_stops(self, timer):
        timer.start()
        timer.remaining = 0.5
        # Mock the delayed import inside update()
        with patch('ursina.time.dt', 1.0):
            with patch('arena.game_manager.game_manager') as mock_gm:
                timer.update()
        assert timer.remaining == 0
        assert timer.is_running is False

    def test_multiple_updates(self, timer):
        timer.start()
        for _ in range(5):
            with patch('ursina.time.dt', 1.0):
                timer.update()
        assert timer.remaining == pytest.approx(295.0)
