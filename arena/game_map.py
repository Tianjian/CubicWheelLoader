from ursina import *
from arena.constants import Config, Team
from arena.base import Base


class GameMap:
    """对称竞技地图，从 map_data 构建"""

    def __init__(self, map_data=None):
        if map_data is None:
            from arena.map_loader import _default_map
            map_data = _default_map()

        self.map_data = map_data

        # 地面
        ground_cfg = map_data.get('ground', {})
        ground_size = ground_cfg.get('size', Config.MAP_SIZE)
        ground_texture = ground_cfg.get('texture', 'grass')
        ground_tex_scale = tuple(ground_cfg.get('texture_scale', [8, 8]))

        self.ground = Entity(
            model='plane', collider='box', scale=ground_size,
            texture=ground_texture, texture_scale=ground_tex_scale
        )

        # 红蓝基地
        red_cfg = map_data.get('red_base', {})
        blue_cfg = map_data.get('blue_base', {})
        self.red_base = Base(
            team=Team.RED,
            position=red_cfg.get('position', Config.RED_BASE_POS),
            radius=red_cfg.get('radius', 6),
            pillars=red_cfg.get('pillars'),
            pillar_height=red_cfg.get('pillar_height', 5),
        )
        self.blue_base = Base(
            team=Team.BLUE,
            position=blue_cfg.get('position', Config.BLUE_BASE_POS),
            radius=blue_cfg.get('radius', 6),
            pillars=blue_cfg.get('pillars'),
            pillar_height=blue_cfg.get('pillar_height', 5),
        )

        # 掩体
        self._generate_cover(map_data.get('cover', []))
        # 边界墙
        self._generate_boundaries(
            ground_size,
            map_data.get('boundary', {})
        )

    def _generate_cover(self, cover_list):
        """从地图数据生成掩体"""
        self.walls = []
        for item in cover_list:
            pos = item.get('position', [0, 0, 0])
            scale = item.get('scale', [2, 2.5, 1])
            gray = item.get('color', 0.95)
            wall = Entity(
                model='cube', origin_y=-.5,
                scale=tuple(scale),
                texture='brick', texture_scale=(1, 2),
                position=tuple(pos),
                collider='box',
                color=color.hsv(0, 0, gray)
            )
            self.walls.append(wall)

    def _generate_boundaries(self, map_size, boundary_cfg):
        """生成边界墙"""
        half = map_size / 2
        t = boundary_cfg.get('thickness', 1)
        h = boundary_cfg.get('height', 5)
        c = color.clear

        self.boundary_walls = [
            Entity(model='cube', scale=(half*2, h, t),
                   position=(0, h/2, -half), collider='box', color=c),
            Entity(model='cube', scale=(half*2, h, t),
                   position=(0, h/2, half), collider='box', color=c),
            Entity(model='cube', scale=(t, h, half*2),
                   position=(-half, h/2, 0), collider='box', color=c),
            Entity(model='cube', scale=(t, h, half*2),
                   position=(half, h/2, 0), collider='box', color=c),
        ]

    def destroy(self):
        """清理地图所有实体"""
        if self.ground:
            destroy(self.ground)
            self.ground = None
        if self.red_base:
            destroy(self.red_base)
            self.red_base = None
        if self.blue_base:
            destroy(self.blue_base)
            self.blue_base = None
        for wall in self.walls:
            destroy(wall)
        self.walls = []
        for wall in self.boundary_walls:
            destroy(wall)
        self.boundary_walls = []
