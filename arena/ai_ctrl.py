"""AI 玩家控制器（6 状态机：reload / shoot_goal / attack / chase / patrol / avoid）

Phase 4 重构：弹药感知、Goal优先、视线检测、侧步走位、Goal优先巡逻。
返回决策字典，由 GameManager 通过 _apply_ai_command() 统一应用。
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
    """AI 玩家控制器（6 状态机：reload / shoot_goal / attack / chase / patrol / avoid）

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

        # 侧步走位
        self._strafe_dir = 1 if random.random() > 0.5 else -1
        self._strafe_change_time = time.time() + random.uniform(1.0, 2.5)

        # 视线检测缓存
        self._los_cache = {}

    def update(self):
        """纯计算，返回决策字典"""
        if self.player.state.value != 'alive':
            return {}

        # 碰撞回避优先
        if self.avoiding:
            if time.time() < self.avoid_end_time:
                return {
                    'look_at': None,
                    'rotate_y': self.avoid_direction * 90 * 1/60,
                    'move_fwd': 1.0,
                    'request_raycast': True,
                    'shoot_dir': None,
                }
            else:
                self.avoiding = False

        return self._state_machine()

    def _state_machine(self):
        """新 AI 行为状态机（6 状态）"""
        my_pos = (self.player.x, self.player.y, self.player.z)

        # 1. 弹药耗尽 → 强制回基地
        if self.player.weapon.current_ammo <= 0:
            return self._reload()

        # 2. 射击 Goal（优先级高于射击敌人）
        if Config.AI_LOS_CHECK_ENABLED:
            goal_target = self._find_shootable_goal()
            if goal_target:
                return self._shoot_goal(goal_target)

        # 3. 射击敌人
        enemy = self._find_nearest_visible_enemy()
        if enemy:
            enemy_pos = (enemy.position.x, enemy.position.y, enemy.position.z)
            d = dist_3d(my_pos, enemy_pos)
            if d < self.attack_range:
                return self._attack(enemy)
            elif d < self.detection_range:
                return self._chase(enemy)

        # 4. 巡逻（优先前往未占领 Goal）
        return self._patrol()

    # ==================== 视线检测 ====================

    def _has_line_of_sight(self, target_pos):
        """检测视线（带缓存，避免频繁 raycast）"""
        now = time.time()
        cache_key = (round(target_pos.x, 1), round(target_pos.z, 1))
        cached = self._los_cache.get(cache_key)
        if cached and cached[0] > now - 0.2:
            return cached[1]

        from ursina import Vec3, raycast
        my_pos = self.player.position + Vec3(0, 1, 0)
        direction = target_pos - my_pos
        d = direction.length()
        if d < 0.1:
            result = True
        else:
            los_ignore = [self.player]
            from arena.game_manager import game_manager
            if game_manager.game_map:
                los_ignore.extend(game_manager.game_map.goals)
            hit = raycast(my_pos, direction.normalized(), distance=d,
                          ignore=los_ignore, debug=False)
            result = not hit.hit or (hit.distance >= d - 0.5)

        self._los_cache[cache_key] = (now, result)
        # 清理过期缓存
        if len(self._los_cache) > 50:
            self._los_cache = {k: v for k, v in self._los_cache.items() if v[0] > now - 0.5}
        return result

    # ==================== Goal 射击 ====================

    def _find_shootable_goal(self):
        """找到最近的可见且值得射击的 Goal"""
        from arena.game_manager import game_manager
        goals = getattr(game_manager.game_map, 'goals', [])
        my_pos = (self.player.x, self.player.y, self.player.z)
        best = None
        best_dist = float('inf')

        for goal in goals:
            if goal.owner == self.player.team:
                continue

            goal_pos = goal.position
            d = dist_3d(my_pos, (goal_pos.x, goal_pos.y, goal_pos.z))

            # 射程检测（子弹射程短，需靠近）
            if d > Config.BULLET_MAX_DISTANCE * 1.5:
                continue

            # 视线检测
            from ursina import Vec3
            if not self._has_line_of_sight(goal_pos + Vec3(0, 1.5, 0)):
                continue

            if d < best_dist:
                best_dist = d
                best = goal

        return best

    def _shoot_goal(self, goal):
        """射击 Goal"""
        self.state = 'shoot_goal'
        result = {
            'look_at': (goal.position.x, goal.position.z),
            'move_fwd': 0.3,
            'request_raycast': True,
            'shoot_dir': None,
        }

        # 射击节流（弹药宝贵，间隔稍长）
        effective_interval = self.shoot_interval * 1.5
        if self.player.weapon.current_ammo <= Config.AI_LOW_AMMO_THRESHOLD:
            effective_interval = self.shoot_interval * 2.5

        if time.time() - self.last_shoot_time > effective_interval:
            fwd = self.player.forward.normalized()
            spread_mult = Config.AI_GOAL_SHOOT_SPREAD_MULT
            spread = (
                random.uniform(-self.shoot_spread * spread_mult, self.shoot_spread * spread_mult),
                random.uniform(-self.shoot_spread * spread_mult, self.shoot_spread * spread_mult),
                random.uniform(-self.shoot_spread * spread_mult, self.shoot_spread * spread_mult),
            )
            shoot_dir = (fwd.x + spread[0], fwd.y + spread[1], fwd.z + spread[2])
            result['shoot_dir'] = shoot_dir
            self.last_shoot_time = time.time()

        return result

    # ==================== 可见敌人检测 ====================

    def _find_nearest_visible_enemy(self):
        """找到最近的可见敌方玩家（增加了视线检测）"""
        from arena.game_manager import game_manager
        from ursina import Vec3
        nearest = None
        min_dist = float('inf')
        my_pos = (self.player.x, self.player.y, self.player.z)
        for p in game_manager.players:
            if p.team != self.player.team and p.state.value == 'alive':
                p_pos = (p.position.x, p.position.y, p.position.z)
                d = dist_3d(my_pos, p_pos)
                if d > self.detection_range:
                    continue
                # 视线检测（仅在攻击范围内才做，减少 raycast 开销）
                if d < self.attack_range and Config.AI_LOS_CHECK_ENABLED:
                    if not self._has_line_of_sight(p.position + Vec3(0, 1, 0)):
                        continue
                if d < min_dist:
                    min_dist = d
                    nearest = p
        return nearest

    # ==================== 攻击状态（带侧步走位） ====================

    def _attack(self, target):
        """面向敌人并射击（带侧步走位）"""
        self.state = 'attack'
        result = {
            'look_at': (target.position.x, target.position.z),
            'move_fwd': 0.0,
            'request_raycast': False,
            'shoot_dir': None,
        }

        # 侧步走位：每隔一段时间切换方向
        if Config.AI_STRAFE_ENABLED:
            if time.time() > self._strafe_change_time:
                self._strafe_dir *= -1
                self._strafe_change_time = time.time() + random.uniform(1.0, 2.5)
            result['rotate_y'] = self._strafe_dir * self.rotation_speed * 0.3 / 60
            result['move_fwd'] = 0.3

        # 射击节流（弹药宝贵，提高间隔）
        effective_interval = self.shoot_interval
        if self.player.weapon.current_ammo <= Config.AI_LOW_AMMO_THRESHOLD:
            effective_interval = self.shoot_interval * 2

        if time.time() - self.last_shoot_time > effective_interval:
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

    # ==================== 追击 ====================

    def _chase(self, target):
        """追击目标"""
        self.state = 'chase'
        return {
            'look_at': (target.position.x, target.position.z),
            'move_fwd': 1.0,
            'request_raycast': True,
            'shoot_dir': None,
        }

    # ==================== 回基地装填 ====================

    def _reload(self):
        """返回基地装填弹药"""
        self.state = 'reload'
        from arena.game_manager import game_manager
        base_key = 'red_base' if self.player.team == Team.RED else 'blue_base'
        base_cfg = game_manager.map_data.get(base_key, {})
        base_pos = base_cfg.get('position', [0, 0, 0])
        reload_radius = base_cfg.get('reload_radius', base_cfg.get('radius', 6))

        my_pos = (self.player.x, self.player.y, self.player.z)
        d = dist_3d(my_pos, (base_pos[0], base_pos[1], base_pos[2]))

        # 已到达基地范围，等待装填完成
        if d < reload_radius:
            return {
                'look_at': None,
                'move_fwd': 0.0,
                'request_raycast': False,
                'shoot_dir': None,
            }

        # 前往基地
        return {
            'look_at': (base_pos[0], base_pos[2]),
            'move_fwd': 1.0,
            'request_raycast': True,
            'shoot_dir': None,
        }

    # ==================== 巡逻（优先前往未占领 Goal） ====================

    def _patrol(self):
        """巡逻行为（优先前往未占领 Goal）"""
        self.state = 'patrol'
        if not self.patrol_points:
            self._generate_patrol_points()

        target = self.patrol_points[self.current_patrol_idx]
        my_pos = (self.player.x, self.player.y, self.player.z)
        if dist_3d(my_pos, (target.x, target.y, target.z)) < Config.AI_PATROL_ARRIVE_DISTANCE:
            self.current_patrol_idx = (self.current_patrol_idx + 1) % len(self.patrol_points)
            # 到达巡逻点后重新生成（根据最新 Goal 状态）
            self.patrol_points = []
            self._generate_patrol_points()

        return {
            'look_at': (target.x, target.z),
            'move_fwd': 1.0,
            'request_raycast': True,
            'shoot_dir': None,
        }

    def _generate_patrol_points(self):
        """生成巡逻点（优先未占领/敌方占领的 Goal，回退到 Goal 位置）"""
        from ursina import Vec3
        from arena.game_manager import game_manager

        goals = getattr(game_manager.game_map, 'goals', [])

        # 优先级：未占领/敌方占领 > 己方占领
        priority_goals = [g for g in goals if g.owner != self.player.team]
        own_goals = [g for g in goals if g.owner == self.player.team]

        ordered = priority_goals + own_goals

        if ordered:
            self.patrol_points = [Vec3(g.position.x, 0, g.position.z) for g in ordered]
        else:
            # 回退：4 个 Goal 位置轮巡
            if goals:
                self.patrol_points = [Vec3(g.position.x, 0, g.position.z) for g in goals]
            else:
                # 最终回退：原有基于出生点的逻辑
                base = self.player.spawn_position
                z_sign = 1 if self.player.team == Team.RED else -1
                self.patrol_points = [
                    Vec3(-10, 0, base.z + z_sign * 5),
                    Vec3(10, 0, base.z + z_sign * 5),
                    Vec3(-10, 0, base.z + z_sign * 15),
                    Vec3(10, 0, base.z + z_sign * 15),
                    Vec3(0, 0, base.z + z_sign * 10),
                ]
