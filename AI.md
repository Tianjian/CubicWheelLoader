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
    'rotate_y': float | None,         # Y 轴旋转增量（侧步走位用）
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
| 队友已锁定 | `goal_id ∈ teammate_goal_ids` | `score × TEAMMATE_TARGET_PENALTY` |
| 己方已占领 | `goal.owner == my_team` | 排除，不参与评分 |

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

### 4.3 当前参数值

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

协调方式为 **软降权**（`× 0.3`），而非硬排除，保证在无其他目标时仍会攻击。

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

## 9. 侧步走位

攻击状态下，AI 以交替左右旋转模拟侧步移动：

- 方向切换间隔：1.0 ~ 2.5 秒随机
- 旋转速度：`ROTATION_SPEED × 0.3 / 60`
- 前进量：0.3（慢速移动）

通过 `STRAFE_ENABLED` 配置开关。

---

## 10. 巡逻系统

### 10.1 巡逻点生成

`_generate_patrol_points()` 按 Goal 优先级生成巡逻路线：

1. **优先**：未占领 / 敌方占领的 Goal
2. **其次**：己方已占领的 Goal
3. **兜底**：围绕出生点生成 5 个固定巡逻点

### 10.2 巡逻方向差异化

同队第二个 AI 的 `_patrol_direction = -1`（逆序巡逻），避免同队 AI 路线完全重叠。

到达判定距离：`PATROL_ARRIVE_DISTANCE = 5.5`

---

## 11. 帧间隔节流

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

## 12. AI 参数配置

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

---

## 13. AI 与 GameManager 的交互

### 调用链

```
Player.update()
  → controller.update()          # AI 返回决策字典
  → player._pending_ai_cmd = result

GameManager.update()
  → _apply_ai_command(player, cmd)
      ├── look_at_2d()            # 转向
      ├── rotation_y +=           # 侧步旋转
      ├── raycast() → on_collision()  # 碰撞检测 → 触发绕行
      ├── position += forward     # 移动
      └── weapon.shoot()          # 射击
```

### 基地装填

`Player._check_base_reload()` 每 10 帧检测一次是否在本方基地内，自动装填弹药（AI 和人类玩家通用）。
