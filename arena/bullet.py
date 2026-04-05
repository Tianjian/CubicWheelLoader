from ursina import *
import random


class Bullet(Entity):
    """实体子弹类（复用自 fps_demo_v4，新增 owner 属性用于友军判定）"""

    def __init__(self, start_position, direction, owner, damage=10, speed=35, **kwargs):
        super().__init__(
            model='sphere',
            scale=0.1,
            color=color.yellow,
            position=start_position,
            collider='sphere',
            **kwargs
        )
        self.owner = owner          # 发射者引用
        self.direction = direction
        self.damage = damage
        self.speed = speed
        self.max_distance = 100
        self.start_position = start_position

    def update(self):
        if distance(self.position, self.start_position) > self.max_distance:
            destroy(self)
            return

        move_distance = self.speed * time.dt * 1.5
        hit_info = raycast(
            self.position,
            self.direction,
            distance=move_distance,
            ignore=(self,)
        )

        if hit_info.hit:
            target = hit_info.entity
            # 友军伤害过滤
            if hasattr(target, 'team'):
                if target == self.owner:
                    pass  # 不伤害自己
                elif target.team == self.owner.team:
                    pass  # 不伤害队友
                elif hasattr(target, 'invincible') and target.invincible:
                    pass  # 无敌状态不受伤
                else:
                    target.take_damage(self.damage, self.owner)
                    original_color = target.color
                    target.color = color.white
                    target.animate_color(original_color, duration=0.1)
            elif hasattr(target, 'hp'):
                # 兼容旧逻辑（非玩家实体）
                target.hp -= self.damage
                original_color = target.color
                target.color = color.red
                target.animate_color(original_color, duration=0.1)

            self.on_hit(hit_info)
            destroy(self)
            return

        self.position += self.direction * self.speed * time.dt

    def on_hit(self, hit_info):
        self.create_impact_effect(hit_info.world_point, hit_info.world_normal)
        self.play_impact_sound()

    def create_impact_effect(self, position, normal):
        for _ in range(5):
            particle = Entity(
                model='cube',
                scale=0.05,
                color=color.orange,
                position=position
            )
            spread = Vec3(
                random.uniform(-1, 1),
                random.uniform(-1, 1),
                random.uniform(-1, 1)
            ).normalized()
            particle.animate_position(
                position + (normal + spread).normalized() * 0.5,
                duration=0.3
            )
            particle.animate_scale(0, duration=0.3)
            destroy(particle, delay=0.3)

    def play_impact_sound(self):
        from ursina.prefabs.ursfx import ursfx
        ursfx(
            [(0.0, 0.0), (0.05, 0.5), (0.1, 0.2), (0.15, 0.1), (0.2, 0.0)],
            volume=0.3,
            wave='noise',
            pitch=random.uniform(-8, -6),
            speed=2.0
        )
