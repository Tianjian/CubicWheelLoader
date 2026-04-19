"""AI 玩家控制器（评分驱动状态机：reload / shoot_goal / attack / chase / patrol / navigate）

升级：统一目标评分系统，距离优先权重 + 防守紧迫加成。
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
        self._patrol_direction = 1  # 1=正序, -1=逆序（同队AI方向相反）
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
        # Player 目标协调（避免队友同时攻击同一个敌人）
        self.current_target_player_id = None

        # 射击节流
        self.last_shoot_time = 0
        self.shoot_interval = Config.AI_SHOOT_INTERVAL

        # 侧步走位
        self._strafe_dir = 1 if random.random() > 0.5 else -1
        self._strafe_change_time = time.time() + random.uniform(1.0, 2.5)

        # 视线检测缓存
        self._los_cache = {}

        # AI 帧间隔节流（降低决策频率，3帧1次）
        # _throttle_offset 由 GameManager 设置，保证各AI错开（0/1/2）
        # _frame_counter 初始值使得第一次 update(+1后) 命中决策帧
        self._throttle_offset = 0
        self._frame_counter = 2  # 首次update: 2+1=3, (3+0)%3==0 → 立即执行
        self._last_decision = {}  # 缓存上一次决策结果

    def update(self):
        """纯计算，返回决策字典（带帧间隔节流）"""
        if self.player.state.value != 'alive':
            return {}

        # 绕行优先（绕行时也需要节流，但间隔短一些）
        if self.navigating:
            self._frame_counter += 1
            if (self._frame_counter + self._throttle_offset) % 2 != 0:
                return self._last_decision if self._last_decision else self._navigate()
            result = self._navigate()
            self._last_decision = result
            return result

        # AI 决策节流：每3帧才完整决策一次
        # 偏移量保证各AI在不同帧执行，避免同时跳过
        self._frame_counter += 1
        if (self._frame_counter + self._throttle_offset) % 3 != 0:
            return self._last_decision if self._last_decision else {}

        result = self._state_machine()
        self._last_decision = result
        return result

    def _state_machine(self):
        """AI 行为状态机（评分驱动）"""
        self.current_target_goal_id = None
        self.current_target_player_id = None

        # 1. 弹药耗尽 → 强制回基地（不可覆盖）
        if self.player.weapon.current_ammo <= 0:
            return self._reload()

        # 2. 统一目标评分（返回评分+LOS快照）
        candidates = self._evaluate_targets()

        if not candidates:
            return self._patrol()

        _, best_type, best_target, best_los = candidates[0]

        # 3. 根据最高分目标决定行为
        if best_type == 'goal':
            goal = best_target
            goal_pos = (goal.position.x, 0, goal.position.z)
            my_pos = (self.player.x, 0, self.player.z)
            d = dist_3d(my_pos, goal_pos)

            # 在射程内+有LOS → 射击Goal（复用 _evaluate_targets 的 LOS 结果）
            if d <= Config.BULLET_MAX_DISTANCE * 0.9 and best_los:
                return self._shoot_goal(goal, los_confirmed=True)
            else:
                # 不在射程 → 巡逻前往该Goal
                return self._patrol_toward(goal.position)

        else:  # best_type == 'player'
            enemy = best_target
            self.current_target_player_id = enemy.player_id
            my_pos = (self.player.x, self.player.y, self.player.z)
            enemy_pos = (enemy.position.x, enemy.position.y, enemy.position.z)
            d = dist_3d(my_pos, enemy_pos)

            if d < self.attack_range:
                return self._attack(enemy)
            else:
                return self._chase(enemy)

    # ==================== 统一目标评分 ====================

    def _evaluate_targets(self):
        """统一目标评分，返回 [(score, target_type, target, los), ...] 按评分降序

        target_type: 'goal' | 'player'
        target: Goal Entity | Player Entity
        los: bool — 该目标是否通过 LOS 检测（复用给 _state_machine 避免重复 raycast）
        """
        from arena.game_manager import game_manager
        from ursina import Vec3

        my_pos = (self.player.x, 0, self.player.z)
        candidates = []

        # ---- Goal 候选 ----
        goals = getattr(game_manager.game_map, 'goals', [])
        teammate_goal_ids, teammate_player_ids = self._get_teammate_targets()

        for goal in goals:
            if goal.owner == self.player.team:
                continue  # 己方已占领，排除

            goal_pos = (goal.position.x, 0, goal.position.z)
            d = dist_3d(my_pos, goal_pos)

            score = Config.GOAL_SCORE * Config.AI_GOAL_PRIORITY_WEIGHT / (d + 1)
            score *= (1 + Config.AI_PROXIMITY_BOOST_K / (d + 1))

            # 射程内+有LOS 加成
            has_los = False
            if d <= Config.BULLET_MAX_DISTANCE * 0.9:
                has_los = self._has_line_of_sight(goal.position + Vec3(0, 1.5, 0))
                if has_los:
                    score *= Config.AI_SHOOTABLE_GOAL_MULT

            # 队友已锁定该Goal → 降权
            if goal.goal_id in teammate_goal_ids:
                score *= Config.AI_TEAMMATE_TARGET_PENALTY

            candidates.append((score, 'goal', goal, has_los))

        # ---- Player 候选 ----
        for p in game_manager.players:
            if p.team == self.player.team:
                continue
            if p.state.value != 'alive':
                continue

            p_pos = (p.position.x, 0, p.position.z)
            d = dist_3d(my_pos, p_pos)

            if d > self.detection_range:
                continue  # 超出侦测范围，排除

            # attack_range 内的敌人检查LOS
            if d < self.attack_range and Config.AI_LOS_CHECK_ENABLED:
                if not self._has_line_of_sight(p.position + Vec3(0, 1, 0)):
                    continue

            score = Config.KILL_SCORE / (d + 1)
            score *= (1 + Config.AI_PROXIMITY_BOOST_K / (d + 1))

            # 防守加成：本方半场 + 敌方高弹药
            if self._is_in_our_half(p.position) and \
               p.weapon.current_ammo >= Config.AI_HIGH_AMMO_THRESHOLD:
                score *= Config.AI_DEFENDER_URGENCY_MULT

            # 攻击性加成：较近距离 + 敌方弹药超过半满 → 优先消灭威胁
            if d <= Config.AI_AGGRO_RANGE and \
               p.weapon.current_ammo >= Config.WEAPON_MAX_AMMO / 2:
                score *= Config.AI_AGGRO_MULT

            # 队友已锁定该敌人 → 降权，避免集中火力
            if p.player_id in teammate_player_ids:
                score *= Config.AI_TEAMMATE_TARGET_PENALTY

            candidates.append((score, 'player', p, True))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates

    def _is_in_our_half(self, position):
        """判断 position 是否在本方半场

        RED 半场: z < 0
        BLUE 半场: z > 0
        """
        if self.player.team == Team.RED:
            return position.z < 0
        else:
            return position.z > 0

    def _get_teammate_targets(self):
        """收集队友正在攻击的目标（Goal ID + Player ID）

        Returns:
            (goal_ids, player_ids) — 两个 set
        """
        from arena.game_manager import game_manager
        goal_ids = set()
        player_ids = set()
        for p in game_manager.players:
            if p == self.player or p.team != self.player.team:
                continue
            ctrl = getattr(p, 'controller', None)
            if ctrl is None:
                continue
            gid = getattr(ctrl, 'current_target_goal_id', None)
            if gid is not None:
                goal_ids.add(gid)
            pid = getattr(ctrl, 'current_target_player_id', None)
            if pid is not None:
                player_ids.add(pid)
        return goal_ids, player_ids

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
        self.current_target_player_id = None

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
        """检测视线（带缓存，避免频繁 raycast）

        优化：缓存key量化到2单位格子，TTL=1.5s，减少raycast次数
        """
        now = time.time()
        # 量化到2单位格子，大幅提升缓存命中率
        cache_key = (round(self.player.x) // 2, round(self.player.z) // 2,
                     round(target_pos.x) // 2, round(target_pos.z) // 2)
        cached = self._los_cache.get(cache_key)
        if cached and cached[0] > now - 1.5:
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
        if len(self._los_cache) > 40:
            self._los_cache = {k: v for k, v in self._los_cache.items() if v[0] > now - 3.0}
        return result

    # ==================== Goal 射击 ====================

    def _shoot_goal(self, goal, los_confirmed=False):
        """射击 Goal"""
        self.state = 'shoot_goal'
        self.current_target_goal_id = goal.goal_id  # 声明目标，供队友协调

        goal_pos = (goal.position.x, 0, goal.position.z)
        my_pos = (self.player.x, 0, self.player.z)
        d = dist_3d(my_pos, goal_pos)

        # 距离够近就停步，避免撞上 Goal 实体引发反复绕行
        move_fwd = 0.3 if d > Config.AI_PATROL_ARRIVE_DISTANCE else 0.0

        result = {
            'look_at': (goal.position.x, goal.position.z),
            'move_fwd': move_fwd,
            'request_raycast': False,
            'shoot_dir': None,
        }

        # 射程检查：超出子弹射程不开火，节约弹药
        goal_pos = (goal.position.x, goal.position.y, goal.position.z)
        my_pos = (self.player.x, self.player.y, self.player.z)
        d = dist_3d(my_pos, goal_pos)
        if d > Config.BULLET_MAX_DISTANCE * 0.9:
            return result

        # LOS 检查（如未在 _evaluate_targets 中确认）
        if not los_confirmed:
            from ursina import Vec3
            if not self._has_line_of_sight(goal.position + Vec3(0, 1.5, 0)):
                return result

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

    # ==================== 前往目标位置 ====================

    def _patrol_toward(self, target_position):
        """前往指定目标位置（通常是不在射程内的Goal）"""
        self.state = 'patrol'
        return {
            'look_at': (target_position.x, target_position.z),
            'move_fwd': 1.0,
            'request_raycast': True,
            'shoot_dir': None,
        }

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

        # 射程检查：超出子弹射程不开火，节约弹药
        target_pos = (target.position.x, target.position.y, target.position.z)
        my_pos = (self.player.x, self.player.y, self.player.z)
        d = dist_3d(my_pos, target_pos)
        if d > Config.BULLET_MAX_DISTANCE * 0.9:
            return result

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
        my_pos = (self.player.x, 0, self.player.z)
        if dist_3d(my_pos, (target.x, 0, target.z)) < Config.AI_PATROL_ARRIVE_DISTANCE:
            self.current_patrol_idx = (self.current_patrol_idx + self._patrol_direction) % len(self.patrol_points)

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
