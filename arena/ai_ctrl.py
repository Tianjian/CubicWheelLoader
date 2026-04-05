from ursina import *
from arena.constants import Config, Team
import random


class AIController:
    """AI 玩家控制器（状态机：巡逻/追击/攻击）"""

    def __init__(self, player):
        self.player = player
        self.move_speed = Config.AI_MOVE_SPEED
        self.rotation_speed = Config.AI_ROTATION_SPEED
        self.detection_range = Config.AI_DETECTION_RANGE
        self.attack_range = Config.AI_ATTACK_RANGE
        self.shoot_spread = Config.AI_SHOOT_SPREAD

        self.patrol_points = []
        self.current_patrol_idx = 0
        self.state = 'patrol'
        self.target = None

        # 碰撞回避
        self.avoiding = False
        self.avoid_end_time = 0
        self.avoid_direction = 0

        # 射击节流
        self.last_shoot_time = 0
        self.shoot_interval = 0.2

    def update(self):
        if self.player.state.value != 'alive':
            return

        # 碰撞回避优先
        if self.avoiding:
            if time.time() < self.avoid_end_time:
                self.player.rotation_y += self.avoid_direction * 90 * time.dt
                self._try_move_forward()
                return
            else:
                self.avoiding = False

        self.state_machine()

    def state_machine(self):
        """AI 行为状态机"""
        enemy = self._find_nearest_enemy()

        if enemy and distance(self.player.position, enemy.position) < self.attack_range:
            self._attack(enemy)
        elif enemy and distance(self.player.position, enemy.position) < self.detection_range:
            self._chase(enemy)
        else:
            self._patrol()

    def _find_nearest_enemy(self):
        """找到最近的敌方玩家"""
        from arena.game_manager import game_manager
        nearest = None
        min_dist = float('inf')
        for p in game_manager.players:
            if p.team != self.player.team and p.state.value == 'alive':
                d = distance(self.player.position, p.position)
                if d < min_dist:
                    min_dist = d
                    nearest = p
        return nearest

    def _attack(self, target):
        """面向敌人并射击"""
        self.state = 'attack'
        self.player.look_at_2d(target.position, 'y')

        # 射击节流
        if time.time() - self.last_shoot_time > self.shoot_interval:
            shoot_dir = self.player.forward.normalized()
            spread = Vec3(
                random.uniform(-self.shoot_spread, self.shoot_spread),
                random.uniform(-self.shoot_spread, self.shoot_spread),
                random.uniform(-self.shoot_spread, self.shoot_spread)
            )
            self.player.weapon.shoot(shoot_dir + spread)
            self.last_shoot_time = time.time()

    def _chase(self, target):
        """追击目标"""
        self.state = 'chase'
        self.player.look_at_2d(target.position, 'y')
        self._try_move_forward()

    def _patrol(self):
        """巡逻行为"""
        self.state = 'patrol'
        if not self.patrol_points:
            self._generate_patrol_points()

        target = self.patrol_points[self.current_patrol_idx]
        self.player.look_at_2d(target, 'y')
        if distance(self.player.position, target) < 2:
            self.current_patrol_idx = (self.current_patrol_idx + 1) % len(self.patrol_points)
        self._try_move_forward()

    def _try_move_forward(self):
        """尝试向前移动，检测碰撞"""
        move_distance = self.move_speed * time.dt
        ray = raycast(self.player.position, self.player.forward,
                      distance=move_distance, ignore=(self.player,), debug=False)
        if ray.hit:
            # 开始回避
            self.avoiding = True
            self.avoid_end_time = time.time() + 1.0
            self.avoid_direction = 1 if random.random() > 0.5 else -1
        else:
            self.player.position += self.player.forward * move_distance

    def _generate_patrol_points(self):
        """生成巡逻点（基于队伍基地位置）"""
        base = self.player.spawn_position
        z_sign = 1 if self.player.team == Team.RED else -1

        self.patrol_points = [
            Vec3(-10, 0, base.z + z_sign * 5),
            Vec3(10, 0, base.z + z_sign * 5),
            Vec3(-10, 0, base.z + z_sign * 15),
            Vec3(10, 0, base.z + z_sign * 15),
            Vec3(0, 0, base.z + z_sign * 10),
        ]
