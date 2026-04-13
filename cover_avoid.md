# AI 避障绕行设计方案

## 1. 问题描述

当前 AI 缺乏路线规划能力，前进过程中遇到 cover 等障碍物时不会绕行，有概率卡在 cover 上。

---

## 2. 现有避障机制分析

### 2.1 当前流程

1. **AI 决策**：`ai_ctrl.py` 返回决策字典 `{'look_at': (x,z), 'move_fwd': 1.0, 'request_raycast': True, ...}`
2. **GameManager 执行**：`_apply_ai_command()` 中，先 `look_at_2d()` 朝向目标，再 raycast 前方
3. **碰撞检测**：raycast 检测到障碍物 → 通知 `AIController.avoiding = True`，持续 1 秒
4. **回避模式**：`avoiding` 期间，输出 `{'rotate_y': ±90°/60, 'move_fwd': 1.0}`，即原地旋转 90°/秒 + 前进

### 2.2 关键代码（当前代码行号）

```python
# game_manager.py:359-366 — 碰撞时进入回避
if ray.hit:
    # 通知 AIController 进入回避模式
    if hasattr(player.controller, 'avoiding'):
        import random as _rand
        player.controller.avoiding = True
        player.controller.avoid_end_time = time.time() + Config.AI_AVOID_DURATION
        player.controller.avoid_direction = 1 if _rand.random() > 0.5 else -1
    return  # 不移动
```

```python
# ai_ctrl.py:70-81 — 回避期间行为
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
```

---

## 3. 卡住的3个根本原因

### 3.1 随机方向回避，可能转向障碍物另一侧

```python
# game_manager.py:365
player.controller.avoid_direction = 1 if _rand.random() > 0.5 else -1
```

随机选左或右转，50% 概率转向更深的死角（如两面墙夹角处）。没有检测哪边更通畅。

### 3.2 回避时间固定1秒，不保证绕过障碍物

```python
Config.AI_AVOID_DURATION = 1.0  # constants.py:130
```

Cover 尺寸 `scale=[2, 2.5, 1]`（见 `arena_classic.json:29-33`），宽2深1。AI 速度6，1秒可移动6单位，理论上能绕过。但若碰到转角或边界墙，1秒不够。回避结束后立即重新面对目标，raycast 又命中障碍物，再次进入回避 → **循环卡死**。

### 3.3 回避期间仍朝目标前进，不改变最终朝向

回避结束后 `look_at` 重新指向目标 → 又朝障碍物走去 → 又碰撞 → 又回避 → **无限循环**。AI 没有"绕行路径"的概念，只会反复冲撞同一面墙。

### 3.4 典型卡死场景

```
         Cover(0,0,-8)
         ┌──────┐
    AI──→│  ■■■ │─── Goal(-8,0,-8)
         └──────┘

循环: AI面向Goal → raycast命中Cover → 回避1秒(偏转) → 回避结束
    → look_at重新指向Goal → raycast又命中Cover → 又回避 → 循环卡死
```

---

## 4. 解决方案：避障绕行（Waypoint Navigation）

核心思路：**碰撞后不盲目旋转，而是计算障碍物侧方的绕行路径点（waypoint），AI 先走到 waypoint 再恢复朝目标前进。**

### 4.1 方案概述

```
正常移动 → raycast命中障碍物
                ↓
        记录碰撞信息（障碍物位置 + 目标位置）
                ↓
        计算障碍物左/右侧绕行waypoint
        选择离目标更近的waypoint
                ↓
        ┌─────────────────────┐
        │  navigating         │ ← 绕行状态
        │  朝waypoint移动      │
        │  每帧检测:           │
        │   1. 目标方向通畅?    │→ 退出绕行，恢复朝目标
        │   2. 到达waypoint?   │→ 退出绕行，恢复朝目标
        │   3. 前方又有障碍?    │→ 重新计算waypoint
        │   4. 超时?           │→ 强制退出，放弃当前目标
        └─────────────────────┘
```

### 4.2 为什么不用 A* / NavMesh

- 地图只有 4 个简单掩体（`arena_classic.json:29-33`），障碍物极少
- AI 目标点明确（Goal / 基地 / 敌人位置已知）
- 只需"绕过眼前障碍"而非"全局路径规划"
- A* 需要构建网格、维护开销大，对本项目场景杀鸡用牛刀

### 4.3 Waypoint 计算方法

碰撞时，根据障碍物位置和 AI 当前位置，计算障碍物两侧的绕行点：

```python
def _compute_detour_waypoint(self, obstacle_pos, target_pos):
    """计算障碍物两侧的绕行路径点，选择离目标更近的一侧"""
    from ursina import Vec3

    my_pos = self.player.position

    # AI→障碍物 方向（XZ平面）
    to_obs = Vec3(obstacle_pos.x - my_pos.x, 0, obstacle_pos.z - my_pos.z)
    d = to_obs.length()
    if d < 0.1:
        # 极端情况：AI 在障碍物正上方，基于朝向偏移
        fwd = self.player.forward
        to_obs = Vec3(fwd.x, 0, fwd.z)
        if to_obs.length() < 0.1:
            to_obs = Vec3(1, 0, 0)
    to_obs_norm = to_obs.normalized()

    # 垂直方向（左/右绕行）
    left_dir = Vec3(-to_obs_norm.z, 0, to_obs_norm.x)
    right_dir = Vec3(to_obs_norm.z, 0, -to_obs_norm.x)

    # 绕行距离 = 障碍物半宽 + 安全边距
    # cover scale=[2, 2.5, 1]，最大半宽=1，加边距→detour_dist=2.5
    detour_dist = 2.5

    left_wp = Vec3(obstacle_pos.x, 0, obstacle_pos.z) + left_dir * detour_dist
    right_wp = Vec3(obstacle_pos.x, 0, obstacle_pos.z) + right_dir * detour_dist

    # 选择离目标更近的waypoint
    left_d = dist_3d((left_wp.x, 0, left_wp.z),
                     (target_pos[0], 0, target_pos[2]))
    right_d = dist_3d((right_wp.x, 0, right_wp.z),
                      (target_pos[0], 0, target_pos[2]))

    return left_wp if left_d < right_d else right_wp
```

**图示**：

```
                     Goal
                      ★
                       \
    left_wp ●───────────\─────── obstacle
                       /■■■■■|
    right_wp ●────────/───────|
                  /           |
    AI ────────→ /
                ↑
          raycast命中点

选择 left_wp（离Goal更近的一侧）
```

---

## 5. 改动详情

### 5.1 `arena/ai_ctrl.py` — 替换 avoiding 为 navigating

#### 5.1.1 `__init__` 属性变更

**删除**（`ai_ctrl.py:49-52`）：
```python
# 碰撞回避
self.avoiding = False
self.avoid_end_time = 0
self.avoid_direction = 0
```

**替换为**：
```python
# 绕行导航（替换原有 avoiding）
self.navigating = False           # 是否在绕行中
self.nav_waypoint = None          # 绕行目标点 Vec3
self.nav_start_time = 0           # 绕行开始时间
self.nav_target_pos = None        # 绕行的最终目标位置 tuple (x, y, z)
self.nav_stuck_count = 0          # 连续碰撞同一障碍物计数
self.nav_last_obstacle_pos = None # 上次碰撞的障碍物位置（防循环）
```

#### 5.1.2 `update()` 变更

**删除**（`ai_ctrl.py:70-81`）：
```python
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
```

**替换为**：
```python
# 绕行优先
if self.navigating:
    return self._navigate()
```

#### 5.1.3 新增 `_navigate()` 方法

```python
def _navigate(self):
    """绕行障碍物（朝 waypoint 移动，每帧检测目标方向是否通畅）"""
    now = time.time()

    # 超时保护（3秒仍未绕过则放弃）
    if now - self.nav_start_time > Config.AI_AVOID_NAVIGATE_TIMEOUT:
        self._end_navigate()
        return self._patrol()  # 放弃当前目标，切换巡逻

    # 检测目标方向是否已通畅（绕行成功）
    if self.nav_target_pos:
        from ursina import Vec3
        target_vec = Vec3(self.nav_target_pos[0], 1, self.nav_target_pos[2])
        if self._has_line_of_sight(target_vec):
            self._end_navigate()
            return self._state_machine()  # 恢复正常决策

    # 到达 waypoint（绕行完成）
    if self.nav_waypoint:
        my_pos = (self.player.x, 0, self.player.z)
        wp = (self.nav_waypoint.x, 0, self.nav_waypoint.z)
        if dist_3d(my_pos, wp) < 1.5:
            self._end_navigate()
            return self._state_machine()

    # 朝 waypoint 移动
    return {
        'look_at': (self.nav_waypoint.x, self.nav_waypoint.z),
        'move_fwd': 1.0,
        'request_raycast': True,
        'shoot_dir': None,
    }
```

#### 5.1.4 新增 `_end_navigate()` 方法

```python
def _end_navigate(self):
    """结束绕行状态"""
    self.navigating = False
    self.nav_waypoint = None
    self.nav_target_pos = None
    self.nav_stuck_count = 0
```

#### 5.1.5 新增 `on_collision()` 回调（替代原有 avoiding 触发）

```python
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

    # 计算绕行 waypoint
    waypoint = self._compute_detour_waypoint(obstacle_pos, target_pos)

    # 如果卡住超过2次，翻转方向（左变右）
    if self.nav_stuck_count >= 2:
        to_obs = Vec3(obstacle_pos.x - self.player.x, 0, obstacle_pos.z - self.player.z)
        if to_obs.length() > 0.1:
            to_obs_norm = to_obs.normalized()
            # 翻转：用上次反方向的垂直方向
            flipped_dir = Vec3(to_obs_norm.z, 0, -to_obs_norm.x) * 2.5
            waypoint = Vec3(obstacle_pos.x, 0, obstacle_pos.z) + flipped_dir

    self.navigating = True
    self.nav_waypoint = waypoint
    self.nav_target_pos = target_pos
    self.nav_start_time = now
```

#### 5.1.6 新增 `_compute_detour_waypoint()` 方法

见 4.3 节完整代码。

### 5.2 `arena/game_manager.py` — 传递碰撞信息

**变更位置**：`_apply_ai_command()` 第359-366行

**原代码**：
```python
if ray.hit:
    # 通知 AIController 进入回避模式
    if hasattr(player.controller, 'avoiding'):
        import random as _rand
        player.controller.avoiding = True
        player.controller.avoid_end_time = time.time() + Config.AI_AVOID_DURATION
        player.controller.avoid_direction = 1 if _rand.random() > 0.5 else -1
    return  # 不移动
```

**替换为**：
```python
if ray.hit:
    # 通知 AIController 计算绕行路径
    if hasattr(player.controller, 'on_collision'):
        obstacle_pos = ray.entity.position if hasattr(ray.entity, 'position') else ray.world_point
        look_at = cmd.get('look_at', (0, 0))
        target_pos = (look_at[0], 0, look_at[1])
        player.controller.on_collision(obstacle_pos, target_pos)
    return  # 不移动
```

**关键点**：
- `_apply_ai_command` 是 `@staticmethod`，通过模块级 `game_manager` 访问全局实例
- `ray.entity` 是 Ursina raycast 返回的命中实体，其 `.position` 属性即障碍物位置
- `target_pos` 从决策字典的 `look_at` 字段推断，是 AI 当前的移动目标
- 如果 `ray.entity` 没有 `position`（如命中地面），回退到 `ray.world_point`

### 5.3 `arena/constants.py` — 新增配置

**`_DEFAULTS` ai 部分**（第33-37行），新增 `avoid_navigate_timeout`：

```python
'ai': {'move_speed': 6, 'rotation_speed': 90, 'detection_range': 40, 'attack_range': 25,
       'shoot_spread': 0.05, 'shoot_interval': 0.4, 'patrol_arrive_distance': 2,
       'avoid_duration': 1.0, 'use_subprocess': False, 'subprocess_timeout': 0.005,
       'low_ammo_threshold': 3, 'strafe_enabled': True, 'los_check_enabled': True,
       'goal_shoot_spread_multiplier': 0.5, 'avoid_navigate_timeout': 3.0},
```

**Config 类**（第130行 `AI_AVOID_DURATION` 之后），新增：

```python
AI_AVOID_NAVIGATE_TIMEOUT = _settings['ai'].get('avoid_navigate_timeout', 3.0)
```

> 注意：保留 `AI_AVOID_DURATION`，避免删除后 JSON 加载报错（虽然不再使用）。

### 5.4 `game_settings.json` — 新增配置

在 `ai` 部分（第25-39行）新增：

```json
"ai": {
    ...,
    "avoid_navigate_timeout": 3.0
}
```

---

## 6. 文件改动清单

| 文件 | 行号 | 改动 |
|------|------|------|
| `arena/ai_ctrl.py` | 49-52 | 删除 `avoiding`/`avoid_end_time`/`avoid_direction`，替换为 `navigating` 相关6个属性 |
| `arena/ai_ctrl.py` | 70-81 | 删除 avoiding 分支，替换为 `_navigate()` 调用 |
| `arena/ai_ctrl.py` | 末尾 | 新增 `_navigate()`、`_end_navigate()`、`on_collision()`、`_compute_detour_waypoint()` 4个方法 |
| `arena/game_manager.py` | 359-366 | 删除 `avoiding` 设置逻辑，替换为 `on_collision()` 调用 |
| `arena/constants.py` | 33-37 | `_DEFAULTS` ai 部分新增 `avoid_navigate_timeout: 3.0` |
| `arena/constants.py` | 130 | Config 类新增 `AI_AVOID_NAVIGATE_TIMEOUT` 属性 |
| `game_settings.json` | 25-39 | ai 部分新增 `avoid_navigate_timeout: 3.0` |

---

## 7. 绕行流程图

```
AI 朝目标移动
      ↓
  raycast 命中障碍物？
      │
   是 ↓         否 → 继续前进
  调用 on_collision(obstacle_pos, target_pos)
      ↓
  计算 左/右 绕行 waypoint
  选择离目标更近的 waypoint
      ↓
  进入 navigating 状态
  朝 waypoint 移动
      ↓
  ┌──────────────────────────────────┐
  │ _navigate() 每帧检测:            │
  │  目标方向 LOS 通畅？────是──→ _end_navigate() → _state_machine() │
  │  到达 waypoint？──────是──→ _end_navigate() → _state_machine() │
  │  超时 3秒？──────────是──→ _end_navigate() → _patrol()        │
  │  前方又碰撞？─────────→ on_collision() 重新计算 waypoint       │
  └──────────────────────────────────┘
```

---

## 8. 边界情况处理

| 场景 | 处理 | 代码位置 |
|------|------|----------|
| AI 在障碍物正上方 | 基于玩家朝向 `player.forward` 计算方向，若仍无法计算则默认 `(1,0,0)` | `_compute_detour_waypoint()` |
| 连续2次碰到同一障碍物 | `nav_stuck_count >= 2` 时翻转绕行方向（左↔右） | `on_collision()` |
| 绕行3秒仍未通过 | `nav_start_time + 3.0 < now` 时超时退出，放弃当前目标切换巡逻 | `_navigate()` |
| 绕行途中碰到另一个障碍物 | `on_collision()` 被再次调用，重新计算新障碍物的绕行 waypoint | `on_collision()` |
| waypoint 在地图边界外 | 移动 raycast 命中边界墙时再次触发 `on_collision()`，重新计算 | `_apply_ai_command()` |
| 目标方向已通畅但未到 waypoint | `_navigate()` 每帧用 `_has_line_of_sight()` 检测，通畅则提前退出 | `_navigate()` |
| `ray.entity` 无 `position`（如地面） | 回退到 `ray.world_point` 作为障碍物位置 | `_apply_ai_command()` |
| 决策字典无 `look_at` | `target_pos` 默认 `(0, 0, 0)` | `_apply_ai_command()` |

---

## 9. 性能考虑

- **raycast 调用次数**：绕行期间每帧 1 次 raycast（移动检测，`_apply_ai_command`）+ 1 次 LOS 检测（带 0.2 秒缓存，`_navigate` 中调用 `_has_line_of_sight`），与现有开销一致
- **waypoint 计算**：仅在碰撞时计算一次，纯数学运算，无额外开销
- **不引入寻路库**：无需 numpy、A* 等，纯 Python 数学计算
- **LOS 缓存复用**：`_has_line_of_sight()` 已有 0.2 秒 TTL 缓存，避免每帧重复 raycast

---

## 10. 实施顺序

1. `game_settings.json` — 新增 `avoid_navigate_timeout: 3.0`
2. `constants.py` — `_DEFAULTS` 新增字段 + Config 新增属性
3. `ai_ctrl.py` — 替换 `__init__` 属性 → 替换 `update()` → 新增4个方法
4. `game_manager.py` — 替换碰撞处理逻辑
5. 测试：观察 AI 在 cover 附近是否顺利绕行，不再卡住
