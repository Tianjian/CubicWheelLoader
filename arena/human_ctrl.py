from ursina import *
from arena.constants import Config


class HumanController:
    """人类玩家控制器（支持键盘 + 手柄，杆量 = 速度）"""

    def __init__(self, player, input_manager):
        self.player = player
        self.im = input_manager
        self.move_speed = Config.HUMAN_MOVE_SPEED
        self.rotation_speed = Config.HUMAN_ROTATION_SPEED

    def update(self):
        if self.player.state.value not in ('alive', 'respawning'):
            return

        im = self.im

        # 旋转（右摇杆 X / 键盘 A/D，杆量 = 速度比例）
        if abs(im.move_sideways) > 0.05:
            rotation = im.move_sideways * self.rotation_speed * time.dt
            self.player.rotation_y += rotation

        # 前后移动（左摇杆 Y / 键盘 W/S，杆量 = 速度比例）
        if abs(im.move_forward) > 0.05:
            move_amount = im.move_forward * self.move_speed * time.dt
            direction = self.player.forward if move_amount > 0 else -self.player.forward
            ray = raycast(self.player.position, direction,
                          distance=abs(move_amount), ignore=(self.player,))
            if not ray.hit:
                self.player.position += direction * abs(move_amount)

        # 射击（左扳机 / 鼠标左键）
        if im.shoot > Config.GAMEPAD_SHOOT_THRESHOLD:
            shoot_dir = self.player.forward.normalized()
            self.player.weapon.shoot(shoot_dir)
