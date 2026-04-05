from ursina import *
import random
from arena.constants import Config, Team
from arena.base import Base


class GameMap:
    """对称竞技地图"""

    def __init__(self):
        # 地面
        self.ground = Entity(
            model='plane', collider='box', scale=Config.MAP_SIZE,
            texture='grass', texture_scale=(8, 8)
        )

        # 红蓝基地
        self.red_base = Base(team=Team.RED, position=Config.RED_BASE_POS)
        self.blue_base = Base(team=Team.BLUE, position=Config.BLUE_BASE_POS)

        # 掩体
        self._generate_cover()
        # 边界墙
        self._generate_boundaries()

    def _generate_cover(self):
        """生成对称掩体"""
        cover_positions = [
            # 左侧
            (-12, 0, -10), (-12, 0, 10),
            # 右侧
            (12, 0, -10), (12, 0, 10),
            # 中央
            (-5, 0, 0), (5, 0, 0),
            # 中场
            (-8, 0, -5), (8, 0, 5),
            # 基地前沿（与基地保持安全距离）
            (-6, 0, -14), (6, 0, -14),
            (-6, 0, 14), (6, 0, 14),
        ]
        self.walls = []
        for x, y, z in cover_positions:
            wall = Entity(
                model='cube', origin_y=-.5,
                scale=(2, random.uniform(2, 3), 1),
                texture='brick', texture_scale=(1, 2),
                position=(x, y, z),
                collider='box',
                color=color.hsv(0, 0, random.uniform(.9, 1))
            )
            self.walls.append(wall)

    def _generate_boundaries(self):
        """生成边界墙"""
        half = Config.MAP_SIZE / 2
        t = 1  # 厚度
        h = 5  # 高度
        c = color.clear

        Entity(model='cube', scale=(half*2, h, t),
               position=(0, h/2, -half), collider='box', color=c)
        Entity(model='cube', scale=(half*2, h, t),
               position=(0, h/2, half), collider='box', color=c)
        Entity(model='cube', scale=(t, h, half*2),
               position=(-half, h/2, 0), collider='box', color=c)
        Entity(model='cube', scale=(t, h, half*2),
               position=(half, h/2, 0), collider='box', color=c)
