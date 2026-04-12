from ursina import *
from arena.constants import Team


def get_team_color(team):
    return color.red if team == Team.RED else color.azure


class Base(Entity):
    """队伍基地（重生区域）"""

    def __init__(self, team, position, radius=6,
                 pillars=None, pillar_height=5,
                 reload_radius=None):
        base_color = get_team_color(team)

        super().__init__(position=Vec3(*position))
        self.team = team
        self.reload_radius = reload_radius or radius

        # 地面标记（parent=self，局部坐标）
        Entity(
            parent=self, model='circle', scale=radius, y=0.05,
            color=base_color, alpha=0.3
        )
        # 基地柱子（parent=self，局部坐标）
        for dx, dz in (pillars or [(-2, -2), (2, -2), (-2, 2), (2, 2)]):
            Entity(
                parent=self, model='cube',
                scale=(0.5, pillar_height, 0.5),
                position=Vec3(dx, 0, dz),
                color=base_color
            )
        # 队伍名标签（parent=self，局部坐标）
        Text(
            text=f'{team.value.upper()} BASE',
            parent=self,
            position=Vec3(0, 6, 0),
            origin=(0, 0),
            scale=30,
            color=base_color,
            billboard=True
        )
