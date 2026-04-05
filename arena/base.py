from ursina import *
from arena.constants import Team


def get_team_color(team):
    return color.red if team == Team.RED else color.azure


class Base(Entity):
    """队伍基地（重生区域）"""

    def __init__(self, team, position):
        base_color = get_team_color(team)
        pos = Vec3(position)

        super().__init__(position=pos)
        self.team = team

        # 地面标记
        Entity(
            model='circle', scale=6, y=0.05,
            color=base_color, alpha=0.3
        )
        # 基地柱子（纯装饰，无碰撞体）
        for dx, dz in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
            Entity(
                model='cube', scale=(0.5, 5, 0.5),
                position=pos + Vec3(dx, 0, dz),
                color=base_color
            )
        # 顶部横梁
        Entity(
            model='cube', scale=(5, 0.5, 5),
            position=pos + Vec3(0, 5, 0),
            color=base_color
        )
        # 队伍名标签
        Text(
            text=f'{team.value.upper()} BASE',
            position=pos + Vec3(0, 7, 0),
            origin=(0, 0),
            scale=30,
            color=base_color,
            billboard=True
        )
