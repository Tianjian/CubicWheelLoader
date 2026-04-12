"""AI 玩家控制器（状态机：巡逻/追击/攻击）

Phase 1 重构：返回决策字典，不直接操作 Entity。
GameManager 通过 _apply_ai_command() 统一应用决策。
"""
import time
import math
import random
from arena.constants import Config, Team


def forward_from_rotation(rot_y):
    """从 Y 轴旋转角计算 forward 向量（纯函数，可测试）"""
    rad = math.radians(rot_y)
    return (math.sin(rad), 0, math.cos(rad))


def dist_3d(a, b):
    """纯 Python 3D 距离计算（不依赖 Ursina distance）"""
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2)


class AIController:
    """AI 玩家控制器（状态机：巡逻/追击/攻击）

    update() 返回决策字典，由 GameManager 统一应用：
        {
            'look_at': (x, z) | None,       # 朝向目标坐标
            'rotate_y': float | None,        # 旋转增量
            'move_fwd': float,               # -1..1 前进量
            'request_raycast': bool,          # 是否需要碰撞检测
            'shoot_dir': (dx, dy, dz) | None # 射击方向（含散布）
        }
    """

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
        self.shoot_interval = Config.AI_SHOOT_INTERVAL

    def update(self):
        """纯计算，返回决策字典"""
        if self.player.state.value != 'alive':
            return {}

        # 碰撞回避优先
        if self.avoiding:
            if time.time() < self.avoid_end_time:
                return {
                    'rotate_y': self.avoid_direction * 90 * 1/60,  # approx time.dt
                    'move_fwd': 1.0,
                    'request_raycast': True,
                }
            else:
                self.avoiding = False

        return self._state_machine()

    def _state_machine(self):
        """AI 行为状态机"""
        enemy = self._find_nearest_enemy()
        my_pos = (self.player.x, self.player.y, self.player.z)

        if enemy:
            enemy_pos = (enemy.position.x, enemy.position.y, enemy.position.z)
            d = dist_3d(my_pos, enemy_pos)
            if d < self.attack_range:
                return self._attack(enemy)
            elif d < self.detection_range:
                return self._chase(enemy)

        return self._patrol()

    def _find_nearest_enemy(self):
        """找到最近的敌方玩家"""
        from arena.game_manager import game_manager
        nearest = None
        min_dist = float('inf')
        my_pos = (self.player.x, self.player.y, self.player.z)
        for p in game_manager.players:
            if p.team != self.player.team and p.state.value == 'alive':
                p_pos = (p.position.x, p.position.y, p.position.z)
                d = dist_3d(my_pos, p_pos)
                if d < min_dist:
                    min_dist = d
                    nearest = p
        return nearest

    def _attack(self, target):
        """面向敌人并射击"""
        self.state = 'attack'
        result = {
            'look_at': (target.position.x, target.position.z),
            'move_fwd': 0.0,
            'request_raycast': False,
            'shoot_dir': None,
        }

        # 射击节流
        if time.time() - self.last_shoot_time > self.shoot_interval:
            fwd = self.player.forward.normalized()
            spread = (
                random.uniform(-self.shoot_spread, self.shoot_spread),
                random.uniform(-self.shoot_spread, self.shoot_spread),
                random.uniform(-self.shoot_spread, self.shoot_spread),
            )
            shoot_dir = (fwd.x + spread[0], fwd.y + spread[1], fwd.z + spread[2])
            result['shoot_dir'] = shoot_dir
            self.last_shoot_time = time.time()

        return result

    def _chase(self, target):
        """追击目标"""
        self.state = 'chase'
        return {
            'look_at': (target.position.x, target.position.z),
            'move_fwd': 1.0,
            'request_raycast': True,
            'shoot_dir': None,
        }

    def _patrol(self):
        """巡逻行为"""
        self.state = 'patrol'
        if not self.patrol_points:
            self._generate_patrol_points()

        target = self.patrol_points[self.current_patrol_idx]
        my_pos = (self.player.x, self.player.y, self.player.z)
        if dist_3d(my_pos, (target.x, target.y, target.z)) < Config.AI_PATROL_ARRIVE_DISTANCE:
            self.current_patrol_idx = (self.current_patrol_idx + 1) % len(self.patrol_points)

        return {
            'look_at': (target.x, target.z),
            'move_fwd': 1.0,
            'request_raycast': True,
            'shoot_dir': None,
        }

    def _generate_patrol_points(self):
        """生成巡逻点（基于队伍基地位置）"""
        from ursina import Vec3
        base = self.player.spawn_position
        z_sign = 1 if self.player.team == Team.RED else -1

        self.patrol_points = [
            Vec3(-10, 0, base.z + z_sign * 5),
            Vec3(10, 0, base.z + z_sign * 5),
            Vec3(-10, 0, base.z + z_sign * 15),
            Vec3(10, 0, base.z + z_sign * 15),
            Vec3(0, 0, base.z + z_sign * 10),
        ]
