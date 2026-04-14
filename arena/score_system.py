from ursina import *
from arena.constants import Team


class TeamScoreSystem(Entity):
    """队伍计分系统（分别追踪击杀分和目标分）"""

    def __init__(self):
        super().__init__()
        self.kill_scores = {Team.RED: 0, Team.BLUE: 0}
        self.goal_scores = {Team.RED: 0, Team.BLUE: 0}

    def add_score(self, team, points):
        """击杀加分（累加到 kill_scores）"""
        self.kill_scores[team] += points
        self.update_ui()

    def get_score(self, team):
        return self.kill_scores[team] + self.goal_scores[team]

    def update_ui(self):
        from arena.hud import hud
        if hud.score_text:
            hud.score_text.text = f'RED: {self.get_score(Team.RED)}    BLUE: {self.get_score(Team.BLUE)}'

    def reset(self):
        self.kill_scores = {Team.RED: 0, Team.BLUE: 0}
        self.goal_scores = {Team.RED: 0, Team.BLUE: 0}
        self.update_ui()

    def update_from_goals(self, goals):
        """从 Goal 占领状态更新目标分数（不覆盖击杀分）"""
        from arena.constants import Config
        self.goal_scores[Team.RED] = 0
        self.goal_scores[Team.BLUE] = 0
        for goal in goals:
            if goal.owner == Team.RED:
                self.goal_scores[Team.RED] += Config.GOAL_SCORE
            elif goal.owner == Team.BLUE:
                self.goal_scores[Team.BLUE] += Config.GOAL_SCORE
        self.update_ui()
