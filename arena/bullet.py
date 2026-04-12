from ursina import *
import random
from arena.constants import Config

# 全局子弹列表（用于比赛结束时批量清理）
_all_bullets = []


class Bullet(Entity):
    """实体子弹类（复用自 fps_demo_v4，新增 owner 属性用于友军判定）"""

    def __init__(self, start_position, direction, owner, damage=10, speed=35, **kwargs):
        super().__init__(
            model='sphere',
            scale=Config.BULLET_SCALE,
            color=color.yellow,
            position=start_position,
            collider='sphere',
            **kwargs
        )
        self.owner = owner          # 发射者引用
        self.direction = direction
        self.damage = damage
        self.speed = speed
        self.max_distance = Config.BULLET_MAX_DISTANCE
        self.start_position = start_position
        _all_bullets.append(self)

    def _remove_from_list(self):
        if self in _all_bullets:
            _all_bullets.remove(self)

    def update(self):
        if distance(self.position, self.start_position) > self.max_distance:
            self._remove_from_list()
            destroy(self)
            return

        move_distance = self.speed * time.dt * Config.BULLET_SPEED_MULTIPLIER
        hit_info = raycast(
            self.position,
            self.direction,
            distance=move_distance,
            ignore=(self,)
        )

        if hit_info.hit:
            target = hit_info.entity
            hit_player = False
            hit_goal = False

            # 优先检测 Goal（hasattr 避免循环导入）
            if hasattr(target, 'on_bullet_hit'):
                target.on_bullet_hit(self.owner.team)
                hit_goal = True
            # 友军/自己/无敌：子弹穿过，不销毁
            elif hasattr(target, 'team'):
                if target == self.owner:
                    return  # 穿过自己
                elif target.team == self.owner.team:
                    return  # 穿过队友
                elif hasattr(target, 'invincible') and target.invincible:
                    return  # 穿过无敌目标
                else:
                    target.take_damage(self.damage, self.owner)
                    original_color = target.color
                    target.color = color.white
                    target.animate_color(original_color, duration=0.1)
                    hit_player = True
            elif hasattr(target, 'hp'):
                # 兼容旧逻辑（非玩家实体）
                target.hp -= self.damage
                original_color = target.color
                target.color = color.red
                target.animate_color(original_color, duration=0.1)

            self.on_hit(hit_info, hit_player=hit_player, hit_goal=hit_goal)
            self._remove_from_list()
            destroy(self)
            return

        self.position += self.direction * self.speed * time.dt

    def on_hit(self, hit_info, hit_player=False, hit_goal=False):
        self.create_impact_effect(hit_info.world_point, hit_info.world_normal)
        from arena.sound_manager import sound_manager
        if hit_goal:
            sound_manager.play_hit_goal()
        elif hit_player:
            sound_manager.play_hit_player()
        else:
            sound_manager.play_hit_wall()

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


def clear_all_bullets():
    """清理所有飞行中的子弹（比赛结束时调用）"""
    for b in _all_bullets[:]:
        destroy(b)
    _all_bullets.clear()
