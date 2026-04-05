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
