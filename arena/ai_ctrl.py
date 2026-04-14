"""AI 玩家控制器（6 状态机：reload / shoot_goal / attack / chase / patrol / navigate）

Phase 5 重构：弹药感知、Goal优先、视线检测、侧步走位、Goal优先巡逻、Waypoint绕行。
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
    """AI 玩家控制器（6 状态机：reload / shoot_goal / attack / chase / patrol / navigate）

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

        # 绕行导航（替换原有 avoiding）
        self.navigating = False           # 是否在绕行中
        self.nav_waypoint = None          # 绕行目标点 Vec3
        self.nav_start_time = 0           # 绕行开始时间
        self.nav_target_pos = None        # 绕行的最终目标位置 tuple (x, y, z)
        self.nav_stuck_count = 0          # 连续碰撞同一障碍物计数
        self.nav_last_obstacle_pos = None # 上次碰撞的障碍物位置（防循环）

        # Goal 射击协调（避免队友同时射击同一个 Goal）
        self.current_target_goal_id = None  # 当前正在射击的 Goal ID

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

        # 绕行优先
        if self.navigating:
            return self._navigate()

        return self._state_machine()

    def _state_machine(self):
        """AI 行为状态机"""
        my_pos = (self.player.x, self.player.y, self.player.z)

        # 非射击 Goal 状态时清除目标声明
        self.current_target_goal_id = None

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

    # ==================== 绕行导航 ====================

    def on_collision(self, obstacle_pos, target_pos):
        """碰撞时由 GameManager 调用，计算绕行路径

        Args:
            obstacle_pos: 碰撞障碍物位置（Vec3）
            target_pos: AI当前目标位置 tuple (x, y, z)
        """
        from ursina import Vec3
        now = time.time()

        # 防循环：如果连续碰撞同一障碍物，增加卡住计数
        if (self.nav_last_obstacle_pos and
            dist_3d((obstacle_pos.x, 0, obstacle_pos.z),
                    (self.nav_last_obstacle_pos[0], 0, self.nav_last_obstacle_pos[2])) < 2):
            self.nav_stuck_count += 1
        else:
            self.nav_stuck_count = 0

        self.nav_last_obstacle_pos = (obstacle_pos.x, 0, obstacle_pos.z)

        # 计算绕行 waypoint（用原始目标，不是当前 waypoint）
        effective_target = self.nav_target_pos if self.navigating else target_pos
        waypoint = self._compute_detour_waypoint(obstacle_pos, effective_target)

        # 如果卡住超过2次，翻转方向（左变右）
        if self.nav_stuck_count >= 2:
            to_obs = Vec3(obstacle_pos.x - self.player.x, 0, obstacle_pos.z - self.player.z)
            if to_obs.length() > 0.1:
                to_obs_norm = to_obs.normalized()
                flipped_dir = Vec3(to_obs_norm.z, 0, -to_obs_norm.x) * 3.5
                waypoint = Vec3(obstacle_pos.x, 0, obstacle_pos.z) + flipped_dir

        self.navigating = True
        self.nav_waypoint = waypoint
        # 保留原始目标位置（避免 navigate 中途目标漂移）
        if not self.nav_target_pos:
            self.nav_target_pos = target_pos
        self.nav_start_time = now

    def _navigate(self):
        """绕行障碍物（朝 waypoint 移动，每帧检测目标方向是否通畅）"""
        now = time.time()

        # 超时保护
        if now - self.nav_start_time > Config.AI_AVOID_NAVIGATE_TIMEOUT:
            self._end_navigate()
            return self._patrol()

        # 检测目标方向是否已通畅
        if self.nav_target_pos:
            from ursina import Vec3
            target_vec = Vec3(self.nav_target_pos[0], 1, self.nav_target_pos[2])
            if self._has_line_of_sight(target_vec):
                self._end_navigate()
                return self._state_machine()

        # 到达 waypoint
        if self.nav_waypoint:
            my_pos = (self.player.x, 0, self.player.z)
            wp = (self.nav_waypoint.x, 0, self.nav_waypoint.z)
            if dist_3d(my_pos, wp) < 2.0:
                self._end_navigate()
                return self._state_machine()

        # 朝 waypoint 移动（绕行时不做碰撞 raycast，由 navigate 自身逻辑管理）
        return {
            'look_at': (self.nav_waypoint.x, self.nav_waypoint.z),
            'move_fwd': 1.0,
            'request_raycast': False,
            'shoot_dir': None,
        }

    def _end_navigate(self):
        """结束绕行状态"""
        self.navigating = False
        self.nav_waypoint = None
        self.nav_target_pos = None
        self.nav_stuck_count = 0
        self.current_target_goal_id = None

    def _compute_detour_waypoint(self, obstacle_pos, target_pos):
        """计算障碍物两侧的绕行路径点，选择离目标更近的一侧"""
        from ursina import Vec3

        my_pos = self.player.position

        # AI→障碍物 方向（XZ平面）
        to_obs = Vec3(obstacle_pos.x - my_pos.x, 0, obstacle_pos.z - my_pos.z)
        d = to_obs.length()
        if d < 0.1:
            fwd = self.player.forward
            to_obs = Vec3(fwd.x, 0, fwd.z)
            if to_obs.length() < 0.1:
                to_obs = Vec3(1, 0, 0)
        to_obs_norm = to_obs.normalized()

        # 垂直方向（左/右绕行）
        left_dir = Vec3(-to_obs_norm.z, 0, to_obs_norm.x)
        right_dir = Vec3(to_obs_norm.z, 0, -to_obs_norm.x)

        # 绕行距离 = 障碍物最大半宽(1) + 安全边距(2.5) = 3.5
        detour_dist = 3.5

        left_wp = Vec3(obstacle_pos.x, 0, obstacle_pos.z) + left_dir * detour_dist
        right_wp = Vec3(obstacle_pos.x, 0, obstacle_pos.z) + right_dir * detour_dist

        # 选择离目标更近的waypoint
        left_d = dist_3d((left_wp.x, 0, left_wp.z),
                         (target_pos[0], 0, target_pos[2]))
        right_d = dist_3d((right_wp.x, 0, right_wp.z),
                          (target_pos[0], 0, target_pos[2]))

        return left_wp if left_d < right_d else right_wp

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
        """找到最近的可见且值得射击的 Goal（排除队友正在射击的 Goal）"""
        from arena.game_manager import game_manager
        from ursina import Vec3
        goals = getattr(game_manager.game_map, 'goals', [])
        my_pos = (self.player.x, self.player.y, self.player.z)

        # 收集队友正在射击的 Goal ID
        teammate_target_ids = set()
        for p in game_manager.players:
            if (p != self.player and p.team == self.player.team
                    and hasattr(p, 'controller') and hasattr(p.controller, 'current_target_goal_id')
                    and p.controller.current_target_goal_id is not None):
                teammate_target_ids.add(p.controller.current_target_goal_id)

        best = None
        best_dist = float('inf')

        for goal in goals:
            if goal.owner == self.player.team:
                continue

            # 队友已在射击此 Goal → 跳过，节省弹药
            if goal.goal_id in teammate_target_ids:
                continue

            goal_pos = goal.position
            d = dist_3d(my_pos, (goal_pos.x, goal_pos.y, goal_pos.z))

            # 射程检测：必须在子弹射程内才射击，否则浪费弹药
            if d > Config.BULLET_MAX_DISTANCE * 0.9:
                continue

            # 视线检测
            if not self._has_line_of_sight(goal_pos + Vec3(0, 1.5, 0)):
                continue

            if d < best_dist:
                best_dist = d
                best = goal

        # 如果所有可射击 Goal 都被队友占了，放弃排他（总比不射击好）
        if best is None and goals:
            for goal in goals:
                if goal.owner == self.player.team:
                    continue
                goal_pos = goal.position
                d = dist_3d(my_pos, (goal_pos.x, goal_pos.y, goal_pos.z))
                if d > Config.BULLET_MAX_DISTANCE * 0.9:
                    continue
                if not self._has_line_of_sight(goal_pos + Vec3(0, 1.5, 0)):
                    continue
                if d < best_dist:
                    best_dist = d
                    best = goal

        return best

    def _shoot_goal(self, goal):
        """射击 Goal"""
        self.state = 'shoot_goal'
        self.current_target_goal_id = goal.goal_id  # 声明目标，供队友协调
        result = {
            'look_at': (goal.position.x, goal.position.z),
            'move_fwd': 0.3,
            'request_raycast': True,
            'shoot_dir': None,
        }

        # 射击节流
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
        """找到最近的可见敌方玩家"""
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

        # 侧步走位
        if Config.AI_STRAFE_ENABLED:
            if time.time() > self._strafe_change_time:
                self._strafe_dir *= -1
                self._strafe_change_time = time.time() + random.uniform(1.0, 2.5)
            result['rotate_y'] = self._strafe_dir * self.rotation_speed * 0.3 / 60
            result['move_fwd'] = 0.3

        # 射击节流
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

        if d < reload_radius:
            return {
                'look_at': None,
                'move_fwd': 0.0,
                'request_raycast': False,
                'shoot_dir': None,
            }

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
            self.patrol_points = []
            self._generate_patrol_points()

        return {
            'look_at': (target.x, target.z),
            'move_fwd': 1.0,
            'request_raycast': True,
            'shoot_dir': None,
        }

    def _generate_patrol_points(self):
        """生成巡逻点（优先未占领/敌方占领的 Goal）"""
        from ursina import Vec3
        from arena.game_manager import game_manager

        goals = getattr(game_manager.game_map, 'goals', [])

        priority_goals = [g for g in goals if g.owner != self.player.team]
        own_goals = [g for g in goals if g.owner == self.player.team]

        ordered = priority_goals + own_goals

        if ordered:
            self.patrol_points = [Vec3(g.position.x, 0, g.position.z) for g in ordered]
        else:
            if goals:
                self.patrol_points = [Vec3(g.position.x, 0, g.position.z) for g in goals]
            else:
                base = self.player.spawn_position
                z_sign = 1 if self.player.team == Team.RED else -1
                self.patrol_points = [
                    Vec3(-10, 0, base.z + z_sign * 5),
                    Vec3(10, 0, base.z + z_sign * 5),
                    Vec3(-10, 0, base.z + z_sign * 15),
                    Vec3(10, 0, base.z + z_sign * 15),
                    Vec3(0, 0, base.z + z_sign * 10),
                ]
