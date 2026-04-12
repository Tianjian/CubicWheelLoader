"""ScoreSystem 单元测试（Layer 2 — Mock Entity）"""
import pytest
from arena.constants import Team


class TestTeamScoreSystem:
    """队伍计分系统测试"""

    @pytest.fixture
    def score_system(self, ursina_app):
        from arena.score_system import TeamScoreSystem
        ss = TeamScoreSystem()
        yield ss
        from ursina import destroy
        destroy(ss)

    def test_initial_scores_are_zero(self, score_system):
        assert score_system.get_score(Team.RED) == 0
        assert score_system.get_score(Team.BLUE) == 0

    def test_add_score(self, score_system):
        score_system.add_score(Team.RED, 3)
        assert score_system.get_score(Team.RED) == 3

    def test_add_score_cumulative(self, score_system):
        score_system.add_score(Team.RED, 3)
        score_system.add_score(Team.RED, 2)
        assert score_system.get_score(Team.RED) == 5

    def test_teams_independent(self, score_system):
        score_system.add_score(Team.RED, 3)
        assert score_system.get_score(Team.BLUE) == 0

    def test_both_teams(self, score_system):
        score_system.add_score(Team.RED, 3)
        score_system.add_score(Team.BLUE, 6)
        assert score_system.get_score(Team.RED) == 3
        assert score_system.get_score(Team.BLUE) == 6

    def test_reset(self, score_system):
        score_system.add_score(Team.RED, 3)
        score_system.add_score(Team.BLUE, 6)
        score_system.reset()
        assert score_system.get_score(Team.RED) == 0
        assert score_system.get_score(Team.BLUE) == 0

    def test_get_score_unknown_team(self, score_system):
        assert score_system.get_score("unknown") == 0
