from ursina import *
from arena.constants import Config


class Weapon(Entity):
    """武器类（复用自 fps_demo_v4，适配多 Player 架构）"""

    def __init__(self, owner, bullet_damage=10, bullet_speed=35, fire_rate=0.15, **kwargs):
        super().__init__(**kwargs)

        self.owner = owner
        self.bullet_damage = bullet_damage
        self.bullet_speed = bullet_speed
        self.fire_rate = fire_rate
        self.on_cooldown = False
        self.last_fire_time = 0
        self.destroyed = False

        # 枪口闪光
        self.muzzle_flash = Entity(
            parent=self,
            z=1,
            world_scale=0.5,
            model='quad',
            color=color.yellow,
            enabled=False
        )

    def shoot(self, target_direction=None):
        """开火"""
        if self.on_cooldown:
            return

        # 创建子弹
        from arena.bullet import Bullet
        Bullet(
            start_position=self.muzzle_flash.world_position,
            direction=target_direction,
            owner=self.owner,
            damage=self.bullet_damage,
            speed=self.bullet_speed
        )

        # 枪口闪光
        self.muzzle_flash.enabled = True
        invoke(self._hide_muzzle_flash, delay=Config.MUZZLE_FLASH_DURATION)

        # 播放射击音效
        from arena.sound_manager import sound_manager
        from arena.game_manager import game_manager
        is_ai = (self.owner != game_manager.human_player)
        sound_manager.play_shoot(
            shooter_pos=self.owner.position,
            listener_pos=game_manager.human_player.position if game_manager.human_player else None,
            is_ai=is_ai,
            player_id=self.owner.player_id,
        )

        # 设置冷却
        self.on_cooldown = True
        invoke(self._end_cooldown, delay=self.fire_rate)

    def _hide_muzzle_flash(self):
        if self.destroyed:
            return
        self.muzzle_flash.enabled = False

    def _end_cooldown(self):
        if self.destroyed:
            return
        self.on_cooldown = False
