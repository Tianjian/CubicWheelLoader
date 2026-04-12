from ursina import *
from arena.constants import Team


class TeamScoreSystem(Entity):
    """队伍计分系统"""

    def __init__(self):
        super().__init__()
        self.scores = {Team.RED: 0, Team.BLUE: 0}

    def add_score(self, team, points):
        self.scores[team] += points
        self.update_ui()

    def get_score(self, team):
        return self.scores.get(team, 0)

    def update_ui(self):
        from arena.hud import hud
        if hud.score_text:
            hud.score_text.text = f'RED: {self.scores[Team.RED]}    BLUE: {self.scores[Team.BLUE]}'

    def reset(self):
        self.scores = {Team.RED: 0, Team.BLUE: 0}
        self.update_ui()

    def update_from_goals(self, goals):
        """从 Goal 占领状态更新实时分数"""
        from arena.constants import Config
        self.scores[Team.RED] = 0
        self.scores[Team.BLUE] = 0
        for goal in goals:
            if goal.owner == Team.RED:
                self.scores[Team.RED] += Config.GOAL_SCORE
            elif goal.owner == Team.BLUE:
                self.scores[Team.BLUE] += Config.GOAL_SCORE
        self.update_ui()
