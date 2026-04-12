from ursina import *
from arena.constants import Team, Config


class Goal(Entity):
    """可占领的圆柱目标"""

    def __init__(self, goal_id, position, **kwargs):
        super().__init__(
            model='cube',
            origin_y=-0.5,
            position=Vec3(*position),
            scale=(1.5, 3, 1.5),
            color=color.white,
            collider='box',
            **kwargs
        )
        self.goal_id = goal_id
        self.hit_history = []
        self.owner = None
        self._hit_window = Config.GOAL_HIT_WINDOW

    def on_bullet_hit(self, team):
        """子弹命中时调用"""
        self.hit_history.append(team)
        if len(self.hit_history) > self._hit_window:
            self.hit_history.pop(0)
        self._update_owner()
        # 命中闪白反馈
        original = self.color
        self.color = color.white
        self.animate_color(original, duration=0.1)

    def _update_owner(self):
        """根据 hit_history 统计占领方"""
        red_count = self.hit_history.count(Team.RED)
        blue_count = self.hit_history.count(Team.BLUE)
        old_owner = self.owner
        if red_count > blue_count:
            self.owner = Team.RED
        elif blue_count > red_count:
            self.owner = Team.BLUE
        else:
            self.owner = None
        self._update_visual()
        if self.owner != old_owner:
            from arena.game_manager import game_manager
            game_manager.on_goal_owner_changed()

    def _update_visual(self):
        """根据占领方更新圆柱颜色"""
        if self.owner == Team.RED:
            self.color = color.red
        elif self.owner == Team.BLUE:
            self.color = color.azure
        else:
            self.color = color.white

    def reset(self):
        """重置占领状态"""
        self.hit_history.clear()
        self.owner = None
        self.color = color.white
