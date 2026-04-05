from ursina import *
from arena.constants import Config


class HumanController:
    """人类玩家控制器（坦克式移动 + 射击）"""

    def __init__(self, player):
        self.player = player
        self.move_speed = Config.HUMAN_MOVE_SPEED
        self.rotation_speed = Config.HUMAN_ROTATION_SPEED

    def update(self):
        if self.player.state.value not in ('alive', 'respawning'):
            return

        # A/D 控制左右旋转
        if held_keys['a']:
            self.player.rotation_y -= self.rotation_speed * time.dt
        elif held_keys['d']:
            self.player.rotation_y += self.rotation_speed * time.dt

        # W/S 控制前后移动
        move_speed = self.move_speed * time.dt
        if held_keys['w']:
            ray = raycast(self.player.position, self.player.forward,
                          distance=move_speed, ignore=(self.player,))
            if not ray.hit:
                self.player.position += self.player.forward * move_speed
        elif held_keys['s']:
            ray = raycast(self.player.position, -self.player.forward,
                          distance=move_speed, ignore=(self.player,))
            if not ray.hit:
                self.player.position -= self.player.forward * move_speed

        # 射击（按住左键连射）
        if held_keys['left mouse']:
            shoot_dir = self.player.forward.normalized()
            self.player.weapon.shoot(shoot_dir)
