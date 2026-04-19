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
        # 增量计数，避免每次 count() 遍历
        self._red_count = 0
        self._blue_count = 0

    def on_bullet_hit(self, team):
        """子弹命中时调用"""
        # 如果窗口满了，弹出最老的记录并减计数
        if len(self.hit_history) >= self._hit_window:
            oldest = self.hit_history.pop(0)
            if oldest == Team.RED:
                self._red_count -= 1
            elif oldest == Team.BLUE:
                self._blue_count -= 1

        self.hit_history.append(team)
        if team == Team.RED:
            self._red_count += 1
        else:
            self._blue_count += 1

        self._update_owner()
        # 命中闪白反馈
        original = self.color
        self.color = color.white
        self.animate_color(original, duration=0.1)

    def _update_owner(self):
        """根据增量计数判断占领方（避免 count() 遍历）"""
        old_owner = self.owner
        if self._red_count > self._blue_count:
            self.owner = Team.RED
        elif self._blue_count > self._red_count:
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
        self._red_count = 0
        self._blue_count = 0
        self.owner = None
        self.color = color.white
