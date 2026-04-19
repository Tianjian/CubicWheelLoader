# AI 系统设计文档

## 1. 架构概览

AI 系统采用 **评分驱动状态机** 架构，核心类为 `AIController`（`arena/ai_ctrl.py`）。

```
┌─────────────┐     update()      ┌──────────────┐   _apply_ai_command()   ┌──────────┐
│  AIController│ ───────────────► │ Player Entity │ ◄───────────────────── │GameManager│
│ (纯计算层)   │   返回决策字典    │  (执行层)     │    统一应用移动/射击     │ (调度层)  │
└─────────────┘                   └──────────────┘                         └──────────┘
```

**关键设计原则：**
- **纯计算分离**：`AIController.update()` 只返回决策字典，不直接操作游戏实体
- **统一执行**：`GameManager._apply_ai_command()` 集中应用所有 AI 决策，避免并发问题
- **帧间隔节流**：每 3 帧完整决策 1 次，非决策帧复用上次结果，降低 CPU 开销

---

## 2. 决策字典格式

`update()` 返回的决策字典结构：

```python
{
    'look_at': (x, z) | None,        # 朝向目标坐标（XZ 平面）
    'rotate_y': float | None,         # Y 轴旋转增量（侧步走位/队友分离用）
    'move_fwd': float,                # -1.0 ~ 1.0 前进量
    'request_raycast': bool,          # 移动前是否需要碰撞检测
    'shoot_dir': (dx, dy, dz) | None  # 射击方向（含随机散布）
}
```

---

## 3. 状态机

AI 有 6 个行为状态，按优先级排列：

| 状态 | 入口方法 | 优先级 | 说明 |
|------|---------|--------|------|
| `reload` | `_reload()` | 最高（强制） | 弹药耗尽时强制返回基地装填 |
| `shoot_goal` | `_shoot_goal()` | 评分决定 | 在射程内且有 LOS 时射击 Goal |
| `attack` | `_attack()` | 评分决定 | 在攻击范围内与敌人交火（带侧步走位） |
| `chase` | `_chase()` | 评分决定 | 追击攻击范围外的敌人 |
| `patrol` | `_patrol()` / `_patrol_toward()` | 最低（默认） | 沿巡逻点移动，优先前往未占领 Goal |
| `navigate` | `_navigate()` | 绕行优先 | 碰撞障碍物后的绕行状态 |

### 状态转换流程

```
update()
  │
  ├─ 死亡？ → 返回 {}
  │
  ├─ 正在绕行(navigating)？ → _navigate()
  │     ├─ 超时/到达waypoint/目标方向通畅 → _end_navigate() → _state_machine()
  │     └─ 否 → 继续绕行
  │
  └─ _state_machine()
        ├─ 弹药=0？ → _reload()
        ├─ _evaluate_targets() 评分
        │     ├─ 无候选 → _patrol()
        │     ├─ 最佳=goal 且 射程+LOS → _shoot_goal()
        │     ├─ 最佳=goal 但 不在射程 → _patrol_toward(goal)
        │     ├─ 最佳=player 且 <attack_range → _attack()
        │     └─ 最佳=player 且 ≥attack_range → _chase()
```

---

## 4. 统一目标评分系统

`_evaluate_targets()` 是 AI 决策的核心，将所有可能目标（Goal / 敌方 Player）统一评分后排序。

### 4.1 Goal 评分公式

```
score = GOAL_SCORE × GOAL_PRIORITY_WEIGHT / (d + 1)
      × (1 + PROXIMITY_BOOST_K / (d + 1))
```

| 修饰因子 | 条件 | 效果 |
|----------|------|------|
| 射程内+有LOS | `d ≤ BULLET_MAX_DISTANCE × 0.9` 且 LOS 通过 | `score × SHOOTABLE_GOAL_MULT` |
| 队友已锁定（远距离） | `goal_id ∈ teammate_goal_ids` 且 `d ≥ ATTACK_RANGE` | `score × TEAMMATE_TARGET_PENALTY`（0.3） |
| 队友已锁定（近距离） | `goal_id ∈ teammate_goal_ids` 且 `d < ATTACK_RANGE` | `score × TEAMMATE_TARGET_PENALTY × 0.2`（0.06，极度降权） |
| 己方已占领 | `goal.owner == my_team` | 排除，不参与评分 |

**近距离队友冲突强惩罚**：当 AI 距 Goal 小于 `ATTACK_RANGE` 且队友已在射击该 Goal 时，降权倍数从 0.3 进一步降至 0.06，防止两人挤同一 Goal。

### 4.2 Player 评分公式

```
score = KILL_SCORE / (d + 1)
      × (1 + PROXIMITY_BOOST_K / (d + 1))
```

| 修饰因子 | 条件 | 效果 |
|----------|------|------|
| 超出侦测范围 | `d > DETECTION_RANGE` | 排除 |
| LOS 阻挡 | `d < ATTACK_RANGE` 且 LOS 不通 | 排除 |
| 防守紧迫 | 敌人在本方半场 且 敌方弹药 ≥ HIGH_AMMO_THRESHOLD | `score × DEFENDER_URGENCY_MULT` |
| 攻击性加成 | `d ≤ AGGRO_RANGE` 且 敌方弹药 ≥ MAX_AMMO/2 | `score × AGGRO_MULT` |
| 队友已锁定 | `player_id ∈ teammate_player_ids` | `score × TEAMMATE_TARGET_PENALTY` |

### 4.3 半场判定

```python
def _is_in_our_half(position):
    """判断位置是否在本方半场"""
    if self.player.team == Team.RED:
        return position.z < 0
    else:
        return position.z > 0
```

### 4.4 当前参数值

| 参数 | 值 | 说明 |
|------|----|------|
| `GOAL_SCORE` | 10 | Goal 占领得分 |
| `KILL_SCORE` | 2 | 击杀得分 |
| `GOAL_PRIORITY_WEIGHT` | 3.3 | Goal 基础权重倍数 |
| `PROXIMITY_BOOST_K` | 5.0 | 距离加成系数 |
| `HIGH_AMMO_THRESHOLD` | 7 | 防守紧迫判定弹药阈值 |
| `DEFENDER_URGENCY_MULT` | 4.0 | 防守紧迫倍数 |
| `SHOOTABLE_GOAL_MULT` | 1.5 | 可射击 Goal 倍数 |
| `TEAMMATE_TARGET_PENALTY` | 0.3 | 队友已锁定降权倍数 |
| `AGGRO_RANGE` | 35 | 攻击性加成触发距离 |
| `AGGRO_MULT` | 2.5 | 攻击性加成倍数 |

---

## 5. 队友目标协调

`_get_teammate_targets()` 收集同队其他 AI 的当前攻击目标：

- **Goal 协调**：通过 `current_target_goal_id` 避免多个 AI 同时射击同一个 Goal
- **Player 协调**：通过 `current_target_player_id` 避免多个 AI 集中攻击同一个敌人

协调方式为 **软降权**（`× 0.3`），而非硬排除，保证在无其他目标时仍会攻击。近距离 Goal 进一步强惩罚（`× 0.06`）。

---

## 6. 绕行导航系统

当 AI 移动时碰撞到障碍物，`GameManager` 调用 `controller.on_collision()` 触发绕行：

### 6.1 绕行流程

1. **计算绕行点**：在障碍物左右两侧各生成一个 waypoint（距离 3.5 单位）
2. **选择方向**：选离最终目标更近的一侧
3. **卡住检测**：连续碰撞同一障碍物 ≥ 2 次时翻转绕行方向
4. **到达/超时退出**：
   - 到达 waypoint（距离 < 2.0）
   - 目标方向 LOS 恢复通畅
   - 超时（默认 3 秒）

### 6.2 节流策略

绕行状态每 **2 帧** 决策一次（比普通 3 帧更频繁），保证绕行响应性。

---

## 7. 视线检测（LOS）

`_has_line_of_sight()` 使用 Ursina `raycast` 检测 AI 与目标之间是否有障碍物。

### 优化策略

| 优化 | 说明 |
|------|------|
| 空间量化缓存 | 缓存 key 量化到 2 单位格子，大幅提升命中率 |
| TTL 过期 | 缓存 1.5 秒有效，3 秒清理 |
| 缓存上限 | 超过 40 条时清理过期条目 |
| 忽略列表 | 排除自身和 Goal 实体（Goal 不阻挡视线） |

---

## 8. 射击系统

### 8.1 射击节流

| 状态 | 基础间隔 | 低弹药间隔 |
|------|---------|-----------|
| 攻击 Player | `SHOOT_INTERVAL`（0.4s） | `× 2`（0.8s） |
| 射击 Goal | `SHOOT_INTERVAL × 1.5`（0.6s） | `× 2.5`（1.0s） |

低弹药阈值：`LOW_AMMO_THRESHOLD = 3`

### 8.2 射击散布

```python
spread = random.uniform(-SHOOT_SPREAD, SHOOT_SPREAD)  # 每个轴独立
shoot_dir = forward + (spread_x, spread_y, spread_z)
```

- 攻击 Player：散布范围 = `SHOOT_SPREAD`（0.05）
- 射击 Goal：散布范围 = `SHOOT_SPREAD × GOAL_SHOOT_SPREAD_MULT`（0.025，更精准）

### 8.3 射程限制

子弹最大飞行距离 `BULLET_MAX_DISTANCE = 5`（受速度乘数影响实际更远）。AI 在 `d > BULLET_MAX_DISTANCE × 0.9` 时不射击，节约弹药。

---

## 9. Goal 射击站位

### 9.1 最小站立距离

`_GOAL_MIN_STAND_DIST = 6.0` — AI 射击 Goal 时不会无限靠近，保持至少 6 单位距离：

- `d ≤ _GOAL_MIN_STAND_DIST`：`move_fwd = 0.0`（停止前进）
- `_GOAL_MIN_STAND_DIST < d ≤ PATROL_ARRIVE_DISTANCE`：`move_fwd = 0.0`（维持位置）
- `d > PATROL_ARRIVE_DISTANCE`：`move_fwd = 0.3`（慢速接近）

### 9.2 队友分离旋转

`_compute_teammate_separation()` — 当同队队友距离过近（默认 `min_dist=4.0`）时，返回 `rotate_y` 增量使 AI 侧移：

- 方向由 `player_id % 2` 决定（奇偶交替）
- 返回值作为决策字典的 `rotate_y` 字段

### 9.3 双层防重叠机制

| 层级 | 方法 | 机制 | 调用位置 |
|------|------|------|---------|
| AI 层（旋转） | `_compute_teammate_separation()` | 侧步旋转避让 | `_shoot_goal()` |
| 物理层（位置） | `_separate_teammates()` | XZ 平面硬推开 | `_apply_ai_command()` |

两套机制互补：AI 层主动选择不同站位，物理层兜底防止 collider 重叠。

---

## 10. 侧步走位

攻击状态下，AI 以交替左右旋转模拟侧步移动：

- 方向切换间隔：1.0 ~ 2.5 秒随机
- 旋转速度：`ROTATION_SPEED × 0.3 / 60`
- 前进量：0.3（慢速移动）

通过 `STRAFE_ENABLED` 配置开关。

---

## 11. 巡逻系统

### 11.1 巡逻点生成

`_generate_patrol_points()` 按 Goal 优先级生成巡逻路线：

1. **优先**：未占领 / 敌方占领的 Goal
2. **其次**：己方已占领的 Goal
3. **兜底**：围绕出生点生成 5 个固定巡逻点

### 11.2 巡逻方向差异化

同队第二个 AI 的 `_patrol_direction = -1`（逆序巡逻），由 `GameManager.start_match()` 在创建时分配，避免同队 AI 路线完全重叠。

到达判定距离：`PATROL_ARRIVE_DISTANCE = 5.5`

---

## 12. 帧间隔节流

### 设计目标

降低 AI 决策频率，减少 CPU 占用，同时保证行为流畅。

### 机制

```
正常决策：每 3 帧执行 1 次 _state_machine()
绕行状态：每 2 帧执行 1 次 _navigate()
非决策帧：复用 _last_decision 缓存结果
```

### 偏移错开

每个 AI 的 `_throttle_offset` 不同（0/1/2），由 `GameManager` 在创建时分配，确保各 AI 在不同帧执行决策，避免同步跳过。

---

## 13. AI 参数配置

所有 AI 参数集中在 `game_settings.json` → `Config` 类，支持热调整：

| 参数 | 值 | 说明 |
|------|----|------|
| `move_speed` | 7 | 移动速度 |
| `rotation_speed` | 140 | 旋转速度 |
| `detection_range` | 60 | 侦测范围 |
| `attack_range` | 25 | 攻击范围 |
| `shoot_spread` | 0.05 | 射击散布 |
| `shoot_interval` | 0.4 | 射击间隔（秒） |
| `patrol_arrive_distance` | 5.5 | 巡逻到达判定距离 |
| `low_ammo_threshold` | 3 | 低弹药阈值 |
| `strafe_enabled` | true | 侧步走位开关 |
| `los_check_enabled` | true | LOS 检测开关 |
| `goal_shoot_spread_multiplier` | 0.5 | Goal 射击散布倍率 |
| `avoid_navigate_timeout` | 3.0 | 绕行超时（秒） |
| `proximity_boost_k` | 5.0 | 距离加成系数 |
| `goal_priority_weight` | 3.3 | Goal 基础权重倍数 |
| `high_ammo_threshold` | 7 | 防守紧迫判定弹药阈值 |
| `defender_urgency_multiplier` | 4.0 | 防守紧迫倍数 |
| `shootable_goal_multiplier` | 1.5 | 可射击 Goal 倍数 |
| `teammate_target_penalty` | 0.3 | 队友已锁定降权倍数 |
| `aggro_range` | 35 | 攻击性加成触发距离 |
| `aggro_multiplier` | 2.5 | 攻击性加成倍数 |

### 硬编码常量（AIController 类变量）

| 常量 | 值 | 说明 |
|------|----|------|
| `_GOAL_MIN_STAND_DIST` | 6.0 | 射击 Goal 时最小站立距离 |

### GameManager 硬编码常量

| 常量 | 值 | 说明 |
|------|----|------|
| `_TEAMMATE_MIN_DIST` | 2.0 | 物理层队友最小间距 |

---

## 14. AI 与 GameManager 的交互

### 调用链

```
Player.update()
  → controller.update()          # AI 返回决策字典
  → player._pending_ai_cmd = result

GameManager.update()
  → _apply_ai_command(player, cmd)
      ├── look_at_2d()            # 转向
      ├── rotation_y +=           # 侧步旋转 / 队友分离旋转
      ├── raycast() → on_collision()  # 碰撞检测 → 触发绕行
      │   └── ignore = [player, goals, 同队队友]
      ├── position += forward     # 移动
      ├── _separate_teammates()   # 物理层队友分离
      └── weapon.shoot()          # 射击
```

### 移动 raycast ignore 列表

| 包含 | 说明 |
|------|------|
| `player` 自身 | 避免射线命中自己 |
| `game_map.goals` | Goal 不阻挡移动 |
| 同队队友 | 避免同队 AI 互相阻挡卡住 |

### 基地装填

`Player._check_base_reload()` 每 10 帧检测一次是否在本方基地内，自动装填弹药（AI 和人类玩家通用）。

---

## 15. AI 移动 ignore vs 人类移动 ignore

| 玩家 | ignore 列表 | 原因 |
|------|------------|------|
| AI | `[player, goals, 同队队友]` | 防止同队 AI 互相阻挡 |
| 人类 | `[player, goals]` | 人类不受同队阻挡问题影响（只有1个人类） |
