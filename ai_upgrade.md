# AI 升级方案 — 具体可执行设计

## 1. 架构变更：统一为单架构，移除子进程模式

### 1.1 移除的文件

| 文件 | 说明 |
|------|------|
| `arena/ai_worker.py` | 子进程 AIDecider 类 + 子进程入口 `ai_process_main()` |
| `arena/ai_process.py` | AIProcessManager 类（子进程生命周期 + 共享内存 I/O） |
| `arena/shared_state.py` | ctypes 共享内存结构体定义 |

### 1.2 移除的配置项

`game_settings.json` → `ai` 节：
- `"use_subprocess"` — 删除
- `"subprocess_timeout"` — 删除

`arena/constants.py` → `Config` 类：
- `AI_USE_SUBPROCESS` — 删除
- `AI_SUBPROCESS_TIMEOUT` — 删除

### 1.3 修改 `arena/game_manager.py`

**删除：**
- `self.ai_process_manager` 属性
- `_start_ai_subprocess()` 方法
- `update()` 中子进程模式分支（`if self.ai_process_manager and self.ai_process_manager.is_running` 整块）
- `_restart()` 中 `self.ai_process_manager.stop()` 相关代码

**保留：**
- `update()` 中主线程模式（从 `Player._pending_ai_cmd` 读取并 `_apply_ai_command`）
- `_apply_ai_command()` 不变

**变更后的 `update()` AI 部分简化为：**

```python
# 应用 AI 决策（主线程模式）
for player in self.players:
    if player == self.human_player:
        continue
    cmd = getattr(player, '_pending_ai_cmd', None)
    if cmd:
        self._apply_ai_command(player, cmd)
        player._pending_ai_cmd = None
```

**变更后的 `start_match()` 移除：**
- `if Config.AI_USE_SUBPROCESS:` 分支和 `self._start_ai_subprocess()` 调用
- `self.ai_process_manager = None` 行

**变更后的 `_restart()` 移除：**
- 步骤2（停止AI子进程）整块

### 1.4 移除的导入

`arena/game_manager.py` 顶部的 `from arena.ai_ctrl import AIController` 保留，移除任何对 `ai_process`/`ai_worker`/`shared_state` 的间接引用。

---

## 2. AI 策略升级：统一目标评分系统

### 2.1 评分公式

所有候选目标（Goal + 敌方 Player）放入统一池，计算评分：

```
score = base_score * type_weight / (distance + 1) * proximity_boost * situational_modifiers
```

**各因子定义：**

| 因子 | Goal | Player | 说明 |
|------|------|--------|------|
| `base_score` | `Config.GOAL_SCORE`（10） | `Config.KILL_SCORE`（3） | 对应游戏计分值 |
| `type_weight` | `Config.AI_GOAL_PRIORITY_WEIGHT`（3.3） | 1.0 | Goal 基础权重倍数 |
| `proximity_boost` | `1 + k / (d + 1)` | `1 + k / (d + 1)` | 距离越近越大 |
| `situational_modifiers` | 见下表 | 见下表 | 条件加成 |

**proximity_boost 计算示例**（`k = 5.0`）：

| 距离 d | boost | 效果 |
|--------|-------|------|
| 1 | 3.50 | 极近大幅加权 |
| 3 | 2.25 | 近距离显著 |
| 5 | 1.83 | 中近显著 |
| 10 | 1.45 | 中距离中等 |
| 20 | 1.24 | 远距离轻微 |
| 50 | 1.10 | 很远几乎无 |

**Goal 条件加成：**

| 条件 | 乘数 | 配置项 |
|------|------|--------|
| 在射程内 + 有LOS | `AI_SHOOTABLE_GOAL_MULT`（1.5） | `shootable_goal_multiplier` |
| 队友已在射击此Goal | `AI_TEAMMATE_TARGET_PENALTY`（0.3） | `teammate_target_penalty` |
| 己方已占领 | **0（排除）** | — |

**Player 条件加成：**

| 条件 | 乘数 | 配置项 |
|------|------|--------|
| 本方半场 + 敌方弹药≥阈值 | `AI_DEFENDER_URGENCY_MULT`（4.0） | `defender_urgency_multiplier` |
| 超出 detection_range | **0（排除）** | — |
| 非存活状态 | **0（排除）** | — |

### 2.2 新增方法：`_evaluate_targets()`

```python
def _evaluate_targets(self):
    """统一目标评分，返回 [(score, target_type, target), ...] 按评分降序
    
    target_type: 'goal' | 'player'
    target: Goal Entity | Player Entity
    """
    from arena.game_manager import game_manager
    from ursina import Vec3
    
    my_pos = (self.player.x, 0, self.player.z)  # XZ平面距离
    candidates = []
    
    # ---- Goal 候选 ----
    goals = getattr(game_manager.game_map, 'goals', [])
    teammate_target_ids = self._get_teammate_target_ids()
    
    for goal in goals:
        if goal.owner == self.player.team:
            continue  # 己方已占领，排除
        
        goal_pos = (goal.position.x, 0, goal.position.z)
        d = dist_3d(my_pos, goal_pos)
        
        score = Config.GOAL_SCORE * Config.AI_GOAL_PRIORITY_WEIGHT / (d + 1)
        score *= (1 + Config.AI_PROXIMITY_BOOST_K / (d + 1))
        
        # 射程内+有LOS 加成
        if d <= Config.BULLET_MAX_DISTANCE * 0.9:
            if self._has_line_of_sight(goal.position + Vec3(0, 1.5, 0)):
                score *= Config.AI_SHOOTABLE_GOAL_MULT
        
        # 队友已锁定降权
        if goal.goal_id in teammate_target_ids:
            score *= Config.AI_TEAMMATE_TARGET_PENALTY
        
        candidates.append((score, 'goal', goal))
    
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
        
        # attack_range 内的敌人检查LOS（减少对墙外敌人误判）
        if d < self.attack_range and Config.AI_LOS_CHECK_ENABLED:
            if not self._has_line_of_sight(p.position + Vec3(0, 1, 0)):
                continue
        
        score = Config.KILL_SCORE / (d + 1)
        score *= (1 + Config.AI_PROXIMITY_BOOST_K / (d + 1))
        
        # 防守加成：本方半场 + 敌方高弹药
        if self._is_in_our_half(p.position) and \
           p.weapon.current_ammo >= Config.AI_HIGH_AMMO_THRESHOLD:
            score *= Config.AI_DEFENDER_URGENCY_MULT
        
        candidates.append((score, 'player', p))
    
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates
```

### 2.3 新增方法：`_is_in_our_half()`

```python
def _is_in_our_half(self, position):
    """判断 position 是否在本方半场
    
    RED 半场: z < 0
    BLUE 半场: z > 0
    """
    if self.player.team == Team.RED:
        return position.z < 0
    else:
        return position.z > 0
```

### 2.4 新增方法：`_get_teammate_target_ids()`

从原 `_find_shootable_goal` 中提取，复用：

```python
def _get_teammate_target_ids(self):
    """收集队友正在射击的 Goal ID"""
    from arena.game_manager import game_manager
    ids = set()
    for p in game_manager.players:
        if (p != self.player and p.team == self.player.team
                and hasattr(p, 'controller') and hasattr(p.controller, 'current_target_goal_id')
                and p.controller.current_target_goal_id is not None):
            ids.add(p.controller.current_target_goal_id)
    return ids
```

### 2.5 重构 `_state_machine()`

**替换前（硬编码级联）：**
```python
def _state_machine(self):
    my_pos = (self.player.x, self.player.y, self.player.z)
    self.current_target_goal_id = None
    
    if self.player.weapon.current_ammo <= 0:
        return self._reload()
    
    if Config.AI_LOS_CHECK_ENABLED:
        goal_target = self._find_shootable_goal()
        if goal_target:
            return self._shoot_goal(goal_target)
    
    enemy = self._find_nearest_visible_enemy()
    if enemy:
        enemy_pos = (enemy.position.x, enemy.position.y, enemy.position.z)
        d = dist_3d(my_pos, enemy_pos)
        if d < self.attack_range:
            return self._attack(enemy)
        elif d < self.detection_range:
            return self._chase(enemy)
    
    return self._patrol()
```

**替换后（评分驱动）：**
```python
def _state_machine(self):
    """AI 行为状态机（评分驱动）"""
    self.current_target_goal_id = None

    # 1. 弹药耗尽 → 强制回基地（不可覆盖）
    if self.player.weapon.current_ammo <= 0:
        return self._reload()

    # 2. 统一目标评分
    candidates = self._evaluate_targets()

    if not candidates:
        return self._patrol()

    best_score, best_type, best_target = candidates[0]

    # 3. 根据最高分目标决定行为
    if best_type == 'goal':
        goal = best_target
        goal_pos = (goal.position.x, 0, goal.position.z)
        my_pos = (self.player.x, 0, self.player.z)
        d = dist_3d(my_pos, goal_pos)

        # 在射程内+有LOS → 射击Goal
        if d <= Config.BULLET_MAX_DISTANCE * 0.9 and \
           self._has_line_of_sight(goal.position + Vec3(0, 1.5, 0)):
            return self._shoot_goal(goal)
        else:
            # 不在射程 → 巡逻前往该Goal（接近后自然进入射程再射击）
            return self._patrol_toward(goal.position)

    else:  # best_type == 'player'
        enemy = best_target
        my_pos = (self.player.x, self.player.y, self.player.z)
        enemy_pos = (enemy.position.x, enemy.position.y, enemy.position.z)
        d = dist_3d(my_pos, enemy_pos)

        if d < self.attack_range:
            return self._attack(enemy)
        else:
            return self._chase(enemy)
```

### 2.6 新增方法：`_patrol_toward()`

当最佳目标是 Goal 但不在射程内时，直接前往该 Goal 而非随机巡逻：

```python
def _patrol_toward(self, target_position):
    """前往指定目标位置（通常是不在射程内的Goal）"""
    self.state = 'patrol'
    return {
        'look_at': (target_position.x, target_position.z),
        'move_fwd': 1.0,
        'request_raycast': True,
        'shoot_dir': None,
    }
```

### 2.7 保留的方法

以下方法不变，供 `_evaluate_targets()` 和状态行为方法内部复用：

| 方法 | 用途 |
|------|------|
| `_find_shootable_goal()` | 可删除，逻辑已融入 `_evaluate_targets()` |
| `_find_nearest_visible_enemy()` | 可删除，逻辑已融入 `_evaluate_targets()` |
| `_shoot_goal(goal)` | 保留，行为不变 |
| `_attack(target)` | 保留，行为不变 |
| `_chase(target)` | 保留，行为不变 |
| `_reload()` | 保留，行为不变 |
| `_patrol()` | 保留，作为无目标时的默认行为 |
| `_generate_patrol_points()` | 保留 |
| `_has_line_of_sight()` | 保留 |
| `_navigate()` / `on_collision()` / `_compute_detour_waypoint()` | 保留，绕行逻辑不变 |

### 2.8 可删除的方法

| 方法 | 原因 |
|------|------|
| `_find_shootable_goal()` | 逻辑完全融入 `_evaluate_targets()` |
| `_find_nearest_visible_enemy()` | 逻辑完全融入 `_evaluate_targets()` |

---

## 3. 配置变更

### 3.1 `game_settings.json` — `ai` 节

**删除：**
```json
"use_subprocess": false,
"subprocess_timeout": 0.005,
```

**新增：**
```json
"proximity_boost_k": 5.0,
"goal_priority_weight": 3.3,
"high_ammo_threshold": 7,
"defender_urgency_multiplier": 4.0,
"shootable_goal_multiplier": 1.5,
"teammate_target_penalty": 0.3
```

**完整 `ai` 节（变更后）：**
```json
"ai": {
    "move_speed": 7,
    "rotation_speed": 100,
    "detection_range": 60,
    "attack_range": 25,
    "shoot_spread": 0.05,
    "shoot_interval": 0.4,
    "patrol_arrive_distance": 2,
    "avoid_duration": 1.0,
    "low_ammo_threshold": 3,
    "strafe_enabled": true,
    "los_check_enabled": true,
    "goal_shoot_spread_multiplier": 0.5,
    "avoid_navigate_timeout": 3.0,
    "proximity_boost_k": 5.0,
    "goal_priority_weight": 3.3,
    "high_ammo_threshold": 7,
    "defender_urgency_multiplier": 4.0,
    "shootable_goal_multiplier": 1.5,
    "teammate_target_penalty": 0.3
}
```

### 3.2 `arena/constants.py` — `Config` 类

**删除：**
```python
AI_USE_SUBPROCESS = _settings['ai']['use_subprocess']
AI_SUBPROCESS_TIMEOUT = _settings['ai']['subprocess_timeout']
```

**新增：**
```python
AI_PROXIMITY_BOOST_K = _settings['ai']['proximity_boost_k']
AI_GOAL_PRIORITY_WEIGHT = _settings['ai']['goal_priority_weight']
AI_HIGH_AMMO_THRESHOLD = _settings['ai']['high_ammo_threshold']
AI_DEFENDER_URGENCY_MULT = _settings['ai']['defender_urgency_multiplier']
AI_SHOOTABLE_GOAL_MULT = _settings['ai']['shootable_goal_multiplier']
AI_TEAMMATE_TARGET_PENALTY = _settings['ai']['teammate_target_penalty']
```

---

## 4. 逐文件变更清单

### 4.1 删除文件

| 文件 | 操作 |
|------|------|
| `arena/ai_worker.py` | 整文件删除 |
| `arena/ai_process.py` | 整文件删除 |
| `arena/shared_state.py` | 整文件删除 |

### 4.2 `arena/ai_ctrl.py` — AI 控制器（核心变更）

| 操作 | 方法/代码 | 说明 |
|------|-----------|------|
| **新增** | `_evaluate_targets()` | 统一目标评分，返回排序后的候选列表 |
| **新增** | `_is_in_our_half(position)` | 判断位置是否在本方半场 |
| **新增** | `_get_teammate_target_ids()` | 收集队友正在射击的 Goal ID |
| **新增** | `_patrol_toward(target_position)` | 前往指定目标位置 |
| **重写** | `_state_machine()` | 从硬编码级联改为评分驱动 |
| **删除** | `_find_shootable_goal()` | 逻辑融入 `_evaluate_targets()` |
| **删除** | `_find_nearest_visible_enemy()` | 逻辑融入 `_evaluate_targets()` |
| 保留 | `__init__()`, `update()`, `_navigate()`, `on_collision()`, `_end_navigate()`, `_compute_detour_waypoint()`, `_has_line_of_sight()`, `_shoot_goal()`, `_attack()`, `_chase()`, `_reload()`, `_patrol()`, `_generate_patrol_points()` | 不变 |

### 4.3 `arena/game_manager.py`

| 操作 | 代码位置 | 说明 |
|------|----------|------|
| **删除** | `self.ai_process_manager = None` | `__init__` 中 |
| **删除** | `_start_ai_subprocess()` 方法 | 整个方法 |
| **删除** | `if Config.AI_USE_SUBPROCESS:` 分支 | `start_match()` 中 |
| **删除** | 子进程模式分支 | `update()` 中 |
| **删除** | AI子进程停止代码 | `_restart()` 中 |
| **删除** | `from arena.ai_process import AIProcessManager` | 如有间接引用 |

### 4.4 `game_settings.json`

| 操作 | key | 说明 |
|------|-----|------|
| **删除** | `ai.use_subprocess` | — |
| **删除** | `ai.subprocess_timeout` | — |
| **新增** | `ai.proximity_boost_k` | 值 5.0 |
| **新增** | `ai.goal_priority_weight` | 值 3.3 |
| **新增** | `ai.high_ammo_threshold` | 值 7 |
| **新增** | `ai.defender_urgency_multiplier` | 值 4.0 |
| **新增** | `ai.shootable_goal_multiplier` | 值 1.5 |
| **新增** | `ai.teammate_target_penalty` | 值 0.3 |

### 4.5 `arena/constants.py`

| 操作 | 属性 | 说明 |
|------|------|------|
| **删除** | `AI_USE_SUBPROCESS` | — |
| **删除** | `AI_SUBPROCESS_TIMEOUT` | — |
| **新增** | `AI_PROXIMITY_BOOST_K` | `proximity_boost_k` |
| **新增** | `AI_GOAL_PRIORITY_WEIGHT` | `goal_priority_weight` |
| **新增** | `AI_HIGH_AMMO_THRESHOLD` | `high_ammo_threshold` |
| **新增** | `AI_DEFENDER_URGENCY_MULT` | `defender_urgency_multiplier` |
| **新增** | `AI_SHOOTABLE_GOAL_MULT` | `shootable_goal_multiplier` |
| **新增** | `AI_TEAMMATE_TARGET_PENALTY` | `teammate_target_penalty` |

### 4.6 `tests/test_ai_ctrl.py`

| 操作 | 测试 | 说明 |
|------|------|------|
| **新增** | `TestEvaluateTargets` | 测试 `_evaluate_targets()` 评分逻辑 |
| **新增** | `TestIsInOurHalf` | 测试 `_is_in_our_half()` 半场判断 |
| **新增** | `TestGetTeammateTargetIds` | 测试队友目标ID收集 |
| **修改** | `TestAIControllerDecision` | 更新 mock 以适配新的 `_state_machine()` |
| **保留** | `TestForwardFromRotation`, `TestDist3d`, `TestComputeDetourWaypoint`, `TestOnCollision`, `TestNavigate` | 纯函数和绕行逻辑不变 |

---

## 5. 评分场景验证

以下用实际参数验算评分驱动是否按预期工作：

参数：`proximity_boost_k=5.0`, `goal_priority_weight=3.3`, `defender_urgency_multiplier=4.0`,
`shootable_goal_multiplier=1.5`, `teammate_target_penalty=0.3`, `high_ammo_threshold=7`

### 场景1：远处Goal vs 近处普通敌人

```
AI 位于 (0, 0, -12)，RED 队
Goal2 在 (6, 0, -6)，无人占领，射程内无LOS
敌人P3 在 (2, 0, -9)，BLUE 队，ammo=3

Goal2 距离: sqrt(36 + 36) ≈ 8.49
  score = 10 * 3.3 / 9.49 * (1 + 5/9.49) = 3.478 * 1.527 ≈ 5.31

P3 距离: sqrt(4 + 9) ≈ 3.61
  score = 3 / 4.61 * (1 + 5/4.61) = 0.651 * 2.085 ≈ 1.36

选择：Goal2（5.31 > 1.36）→ 巡逻前往Goal2 ✅
```

### 场景2：近处敌人 vs 远处Goal

```
AI 位于 (0, 0, -5)，RED 队
Goal3 在 (-6, 0, 6)，无人占领
敌人P4 在 (1, 0, -3)，BLUE 队，ammo=2

Goal3 距离: sqrt(36 + 121) ≈ 12.53
  score = 10 * 3.3 / 13.53 * (1 + 5/13.53) = 2.439 * 1.370 ≈ 3.34

P4 距离: sqrt(1 + 4) ≈ 2.24
  score = 3 / 3.24 * (1 + 5/3.24) = 0.926 * 2.543 ≈ 2.35

选择：Goal3（3.34 > 2.35）→ 巡逻前往Goal3
（近处敌人弹药低，威胁不大，Goal价值更高）✅
```

### 场景3：本方半场 + 高弹药敌人（策略2触发）

```
AI 位于 (0, 0, -5)，RED 队
Goal2 在 (6, 0, -6)，无人占领
敌人P4 在 (1, 0, -3)，BLUE 队，ammo=8，在本方半场(z=-3 < 0)

Goal3 距离 ≈ 12.53
  score ≈ 3.34（同场景2）

P4 距离 ≈ 2.24，高弹药+本方半场 → defender_urgency_mult = 4.0
  score = 3 / 3.24 * (1 + 5/3.24) * 4.0 = 0.926 * 2.543 * 4.0 ≈ 9.42

选择：P4（9.42 > 3.34）→ 攻击敌人 ✅ 防守优先触发！
```

### 场景4：射程内Goal vs 近处普通敌人

```
AI 位于 (5, 0, -7)，RED 队
Goal2 在 (6, 0, -6)，无人占领，射程内+有LOS
敌人P3 在 (2, 0, -5)，BLUE 队，ammo=2

Goal2 距离: sqrt(1 + 1) ≈ 1.41
  score = 10 * 3.3 / 2.41 * (1 + 5/2.41) * 1.5 = 13.69 * 3.075 * 1.5 ≈ 63.2

P3 距离: sqrt(9 + 4) ≈ 3.61
  score = 3 / 4.61 * (1 + 5/4.61) = 0.651 * 2.085 ≈ 1.36

选择：Goal2（63.2 >> 1.36）→ 射击Goal ✅
（Goal极近+射程内+有LOS，加成极大）
```

### 场景5：队友已在射击的Goal

```
AI 位于 (5, 0, -7)，RED 队
Goal2 在 (6, 0, -6)，无人占领，射程内+有LOS，但队友P1已在射击
Goal4 在 (6, 0, 6)，无人占领，远处

Goal2 距离 ≈ 1.41，队友锁定 → teammate_target_penalty = 0.3
  score = 10 * 3.3 / 2.41 * (1 + 5/2.41) * 1.5 * 0.3 = 63.2 * 0.3 ≈ 18.96

Goal4 距离: sqrt(1 + 169) ≈ 13.04
  score = 10 * 3.3 / 14.04 * (1 + 5/14.04) = 2.350 * 1.356 ≈ 3.19

选择：Goal2（18.96 > 3.19）→ 仍射击Goal2
（虽然降权但仍远高于远处的Goal4，合理——队友在射不影响自己也射）
```

---

## 6. 实施步骤（按顺序执行）

### Step 1：配置层变更
1. 修改 `game_settings.json`：删除 `use_subprocess`/`subprocess_timeout`，新增 6 个策略参数
2. 修改 `arena/constants.py`：删除 `AI_USE_SUBPROCESS`/`AI_SUBPROCESS_TIMEOUT`，新增 6 个 Config 属性

### Step 2：移除子进程架构
1. 删除 `arena/ai_worker.py`
2. 删除 `arena/ai_process.py`
3. 删除 `arena/shared_state.py`
4. 修改 `arena/game_manager.py`：移除所有子进程相关代码

### Step 3：AI 策略升级
1. 修改 `arena/ai_ctrl.py`：
   - 新增 `_evaluate_targets()`, `_is_in_our_half()`, `_get_teammate_target_ids()`, `_patrol_toward()`
   - 重写 `_state_machine()`
   - 删除 `_find_shootable_goal()`, `_find_nearest_visible_enemy()`

### Step 4：测试更新
1. 修改 `tests/test_ai_ctrl.py`：更新 mock 和新增测试

### Step 5：验证
1. 运行 `pytest tests/test_ai_ctrl.py` 确认通过
2. 运行游戏观察 AI 行为

---

## 7. 回滚策略

如果评分系统表现不佳，可通过配置参数回退到近似原行为：

| 目标 | 参数调整 |
|------|----------|
| Goal 永远优先于 Player | `goal_priority_weight` 设为 100 |
| 忽略距离加成 | `proximity_boost_k` 设为 0 |
| 禁用防守优先 | `defender_urgency_multiplier` 设为 1.0 |
| 完全恢复原级行为 | 需要回退 `_state_machine()` 代码 |
