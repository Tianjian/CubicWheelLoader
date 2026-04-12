# 升级设计文档

## 1. 比赛间状态残留问题

### 1.1 问题描述

第二局开始时，第一局的游戏实体和 UI 仍然残留在场景中，导致视觉重叠和数据混乱。

### 1.2 根因分析

`_restart()`（`game_manager.py:179-201`）是唯一的局间清理入口，但存在大量遗漏。

#### 泄漏清单（对照代码逐项确认）

| # | 泄漏项 | 代码位置 | 原因 | 跨局影响 |
|---|--------|----------|------|----------|
| 1 | **GameMap 全部实体** | `game_map.py:10-24` 创建，`_restart()` 未销毁 `self.game_map` | 地面+12 掩体+4 边界墙+2 基地每局翻倍 |
| 2 | **Base 子实体**（地面标记、4 柱子、标签） | `base.py:20-39`，子实体**无 `parent=self`** | 即使 `destroy(base)` 也不递归清理，装饰实体每局翻倍 |
| 3 | **4 个边界墙** | `game_map.py:60-67`，匿名 Entity 无引用 | 永久泄漏，无法清理 |
| 4 | **HUD 7 个元素** | `hud.py:21-85` 创建，`_restart()` 未调用任何 HUD 清理 | 每局翻倍重叠显示 |
| 5 | **end_match() 4 个 UI 元素** | `game_manager.py:140-177`，仅 `result_bg` 有引用，3 个 Text + 1 个 Button 无引用 | 结果画面残留 |
| 6 | **CameraController Entity** | `camera_ctrl.py:5` 继承 Entity，`_restart():196` 仅设 None 未 `destroy()` | 场景残留 Entity，`update()` 继续被引擎调用 |
| 7 | **飞行中的 Bullet** | `bullet.py:24-63`，比赛结束时空中子弹未清理 | 继续飞行、raycast，可能命中已销毁实体 |

#### 延迟回调隐患（对照代码逐项确认）

| # | 回调 | 代码位置 | 延迟 | 当前保护 | Gap |
|---|------|----------|------|----------|-----|
| 1 | `player.respawn()` | `player.py:115` invoke 3s | 3s | `player.py:120` 检查 `self.enabled` | **不足**：Ursina `destroy()` 后 `enabled` 属性可能仍存在，改为 `destroyed` 标志位更可靠 |
| 2 | `player._end_invincibility()` | `player.py:134` invoke 2s | 2s | `player.py:138` 同上 | 同上 |
| 3 | `weapon.muzzle_flash.disable` | `weapon.py:45` invoke 0.05s | 0.05s | 无 | 对已销毁子对象操作，可能抛异常 |
| 4 | `setattr(weapon, 'on_cooldown', False)` | `weapon.py:52` invoke 0.15s | 0.15s | 无 | 对已销毁对象 setattr，可能抛异常 |
| 5 | `_on_human_respawn` | `game_manager.py:114` invoke 3s | 3s | `game_manager.py:118` 检查 `human_player` | 如果 camera_controller 已销毁则 `set_third_person()` 崩溃 |
| 6 | 倒计时 `Text` | `game_manager.py:75-81` invoke 递归 | 0.9s-3s | 无 | 如果在倒计时期间重启，Text 可能残留 |

#### GameMap 不是 Entity

**设计文档中的 Gap**：`GameMap` 是普通 Python 类（不是 `Entity`），不能直接 `destroy()`。需要手动调用其 `destroy()` 方法逐个销毁内部实体。

#### Base 不是 Entity 的子类行为

`base.py:16` — `Base(Entity)` 的 `__init__` 调用 `super().__init__(position=pos)`，Base 本身**是 Entity**。但子实体（地面标记、柱子、标签）没有 `parent=self`，而是放在场景根级。当前：
- `base.py:20-23`：地面标记 — 无 parent（挂在场景根级）
- `base.py:25-30`：柱子 — 无 parent，position 用 `pos + Vec3(dx, 0, dz)`（绝对坐标）
- `base.py:32-39`：标签 — 无 parent，position 用 `pos + Vec3(0, 6, 0)`（绝对坐标）

改为 `parent=self` 后，position 需改为**相对于 Base 的局部坐标**：
- 地面标记：`position=Vec3(0, 0.05, 0)` + `parent=self`
- 柱子：`position=Vec3(dx, 0, dz)` + `parent=self`（去掉 `pos +`）
- 标签：`position=Vec3(0, 6, 0)` + `parent=self`（去掉 `pos +`）

#### end_match() UI 引用问题

`game_manager.py:140-177` 中：
- `self.result_bg` — 有引用（`game_manager.py:140`）
- 3 个 `Text`（MATCH OVER、比分、winner）— **无引用**，匿名创建
- 1 个 `Button`（RESTART）— **无引用**，匿名创建

设计文档说 `_result_ui = []` 保存引用，正确。但需注意 `_result_ui` 是首次使用，`_restart()` 中用 `getattr(self, '_result_ui', [])` 防止首次调用时 AttributeError。

#### KillFeed._remove_message 延迟回调

`kill_feed.py:24` — `invoke(self._remove_message, msg, delay=5.0)`。`clear()` 销毁 msg 后，5s 后 `_remove_message` 仍会执行 `destroy(msg)` 对已销毁实体操作。当前 `_remove_message` 先检查 `if msg in self.messages`，`clear()` 已清空 messages，所以不会二次 destroy。**但 `destroy(msg)` 对已销毁实体可能抛异常**。

### 1.3 修复方案（细化）

#### 1.3.1 Base 改造（parent=self + 局部坐标）

```python
# base.py — 改造后
class Base(Entity):
    """队伍基地（重生区域）"""

    def __init__(self, team, position, radius=6,
                 pillars=None, pillar_height=5):
        base_color = get_team_color(team)

        super().__init__(position=Vec3(position))
        self.team = team

        # 地面标记（parent=self，局部坐标）
        self.ground_marker = Entity(
            parent=self, model='circle', scale=radius, y=0.05,
            color=base_color, alpha=0.3
        )
        # 基地柱子（parent=self，局部坐标）
        self.pillars_entities = []
        for dx, dz in (pillars or [(-2, -2), (2, -2), (-2, 2), (2, 2)]):
            p = Entity(
                parent=self, model='cube',
                scale=(0.5, pillar_height, 0.5),
                position=Vec3(dx, 0, dz),
                color=base_color
            )
            self.pillars_entities.append(p)
        # 队伍名标签（parent=self，局部坐标）
        self.name_label = Text(
            text=f'{team.value.upper()} BASE',
            parent=self,
            position=Vec3(0, 6, 0),
            origin=(0, 0),
            scale=30,
            color=base_color,
            billboard=True
        )
```

**关键改动**：
- 所有子实体加 `parent=self`，position 改为局部坐标（去掉 `pos +`）
- 子实体保存引用（`ground_marker`, `pillars_entities`, `name_label`），以防 parent 递归销毁失效
- 构造函数参数化（`radius`, `pillars`, `pillar_height`），为独立地图文件做准备

#### 1.3.2 GameMap.destroy()

```python
# game_map.py — 新增方法
def destroy(self):
    """清理地图所有实体"""
    if self.ground:
        destroy(self.ground)
        self.ground = None
    if self.red_base:
        destroy(self.red_base)   # Base 子实体已 parent=self，会递归销毁
        self.red_base = None
    if self.blue_base:
        destroy(self.blue_base)
        self.blue_base = None
    for wall in self.walls:
        destroy(wall)
    self.walls = []
    for wall in self.boundary_walls:
        destroy(wall)
    self.boundary_walls = []
```

**注意**：GameMap 本身不是 Entity，不能直接 `destroy()`，需要手动调用 `self.game_map.destroy()` 后再设 `None`。

#### 1.3.3 HUD.destroy()

```python
# hud.py — 新增方法
def destroy(self):
    """销毁所有 HUD 元素"""
    for attr in ('score_text', 'timer_text', 'hp_bg', 'hp_bar',
                 'stats_text', 'identity_text', 'controls_text',
                 'ground_crosshair'):
        obj = getattr(self, attr, None)
        if obj:
            destroy(obj)
            setattr(self, attr, None)
```

**注意**：`hud` 是全局单例（`hud = HUD()`），`destroy()` 只清理创建的实体，不清除 `hud` 本身。下一局 `create()` 会重新创建所有元素。

#### 1.3.4 完善 `_restart()`

```python
# game_manager.py — 替换现有 _restart()
def _restart(self):
    """重新开始"""
    # 1. 清理 end_match UI（所有元素，包括匿名的）
    for ui in getattr(self, '_result_ui', []):
        destroy(ui)
    self._result_ui = []

    # 2. 销毁输入管理器
    if self.input_manager:
        destroy(self.input_manager)
        self.input_manager = None

    # 3. 销毁相机控制器
    if self.camera_controller:
        destroy(self.camera_controller)
        self.camera_controller = None

    # 4. 销毁地图（包含基地、掩体、边界墙）
    if self.game_map:
        self.game_map.destroy()
        self.game_map = None

    # 5. 标记+销毁玩家（防止延迟回调）
    for p in self.players:
        p.destroyed = True
        destroy(p)

    # 6. 销毁 HUD
    hud.destroy()

    # 7. 清理击杀播报
    kill_feed.clear()

    # 8. 重置状态
    self.players = []
    self.human_player = None
    self.state = GameState.MENU

    # 9. 重新显示角色选择
    from arena.character_select import CharacterSelect
    CharacterSelect()
```

#### 1.3.5 Player.destroyed 标志位

```python
# player.py — __init__ 中添加
self.destroyed = False

# player.py — die() 中不设 destroyed（死亡≠销毁），只有 _restart 销毁时设

# player.py — respawn() 改用 destroyed 标志
def respawn(self):
    if self.destroyed:
        return
    ...

# player.py — _end_invincibility() 改用 destroyed 标志
def _end_invincibility(self):
    if self.destroyed:
        return
    ...
```

#### 1.3.6 end_match() UI 保存引用

```python
# game_manager.py — end_match() 改造
def end_match(self):
    ...
    self._result_ui = []

    self.result_bg = Entity(...)
    self._result_ui.append(self.result_bg)

    t = Text(text='MATCH OVER', ...)
    self._result_ui.append(t)

    t = Text(text=f'RED: {red_score}    BLUE: {blue_score}', ...)
    self._result_ui.append(t)

    t = Text(text=winner, ...)
    self._result_ui.append(t)

    btn = Button(text='RESTART', ...)
    self._result_ui.append(btn)
```

#### 1.3.7 边界墙保存引用

```python
# game_map.py — _generate_boundaries() 改造
def _generate_boundaries(self):
    half = Config.MAP_SIZE / 2
    t = 1
    h = 5
    c = color.clear

    self.boundary_walls = []
    self.boundary_walls.append(Entity(
        model='cube', scale=(half*2, h, t),
        position=(0, h/2, -half), collider='box', color=c))
    self.boundary_walls.append(Entity(
        model='cube', scale=(half*2, h, t),
        position=(0, h/2, half), collider='box', color=c))
    self.boundary_walls.append(Entity(
        model='cube', scale=(t, h, half*2),
        position=(-half, h/2, 0), collider='box', color=c))
    self.boundary_walls.append(Entity(
        model='cube', scale=(t, h, half*2),
        position=(half, h/2, 0), collider='box', color=c))
```

#### 1.3.8 KillFeed 延迟回调安全化

```python
# kill_feed.py — _remove_message 加销毁检查
def _remove_message(self, msg):
    if msg in self.messages:
        self.messages.remove(msg)
        try:
            destroy(msg)
        except Exception:
            pass  # 实体可能已被 clear() 销毁
        self._rearrange()
```

#### 1.3.9 Weapon 延迟回调安全化

```python
# weapon.py — shoot() 中 invoke 改为安全方式
def shoot(self, target_direction=None):
    if self.on_cooldown:
        return
    ...
    self.muzzle_flash.enabled = True
    invoke(self._hide_muzzle_flash, delay=0.05)
    ...
    self.on_cooldown = True
    invoke(self._end_cooldown, delay=self.fire_rate)

def _hide_muzzle_flash(self):
    if self.destroyed:
        return
    self.muzzle_flash.enabled = False

def _end_cooldown(self):
    if self.destroyed:
        return
    self.on_cooldown = False
```

Weapon 需要 `destroyed` 标志位（在 Player 销毁时设 `player.weapon.destroyed = True`）。

#### 1.3.10 游戏结束清理飞行子弹

在 `end_match()` 或 `_restart()` 中，遍历场景清理所有 Bullet：

```python
# game_manager.py — _restart() 中添加
# 清理飞行中的子弹
from arena.bullet import Bullet
for entity in scene.entities[:]:  # 复制列表，遍历时安全
    if isinstance(entity, Bullet):
        destroy(entity)
```

**注意**：Ursina 的 `scene.entities` 可能不包含所有实体。更可靠的方案是 Bullet 维护一个全局列表：

```python
# bullet.py — 新增
_all_bullets = []

class Bullet(Entity):
    def __init__(self, ...):
        ...
        _all_bullets.append(self)

    def update(self):
        ...
        if should_destroy:
            self._remove()
            destroy(self)

    def _remove(self):
        if self in _all_bullets:
            _all_bullets.remove(self)

def clear_all_bullets():
    """清理所有飞行中的子弹"""
    for b in _all_bullets[:]:
        destroy(b)
    _all_bullets.clear()
```

### 1.4 文件改动清单

| 文件 | 改动 | 行数估算 |
|------|------|----------|
| `arena/base.py` | parent=self + 参数化 + 局部坐标 + 保存引用 | ~20 行改动 |
| `arena/game_map.py` | boundary_walls 引用 + destroy() | ~15 行新增 |
| `arena/hud.py` | 新增 destroy() | ~8 行新增 |
| `arena/game_manager.py` | _restart() 重写 + end_match() 保存引用 + 清理子弹 | ~30 行改动 |
| `arena/player.py` | destroyed 标志位 + respawn/_end_invincibility 检查 | ~6 行改动 |
| `arena/weapon.py` | destroyed 标志 + _hide_muzzle_flash + _end_cooldown | ~12 行新增 |
| `arena/bullet.py` | _all_bullets 列表 + clear_all_bullets() | ~12 行新增 |
| `arena/kill_feed.py` | _remove_message 异常保护 | ~2 行改动 |

---

## 2. 独立地图文件

### 2.1 问题描述

地图数据硬编码在 `game_map.py` 中：
- 掩体位置：`game_map.py:28-40` 硬编码 12 个坐标
- 掩体高度：`game_map.py:45` `random.uniform(2, 3)` 不可控
- 掩体纹理/颜色：`game_map.py:46-49` 固定
- 基地参数：`base.py:12` 固定 radius=6, pillar_height=5
- 边界参数：`game_map.py:55-57` 固定 thickness=1, height=5
- 地面参数：`game_map.py:13-14` 固定 size=64, texture_scale=(8,8)

### 2.2 设计目标

- 地图数据存放在独立 JSON 文件中，可手工编辑
- 支持多张地图，通过配置或角色选择界面切换
- 向后兼容：无地图文件时退化为内置默认

### 2.3 地图文件格式（JSON）

与设计文档一致，无需修改。

### 2.4 模块设计

#### Gap 1：Config 中硬编码的地图相关常量

`constants.py:42-45` 中：
```python
MAP_SIZE = 64
RED_BASE_POS = (0, 0, -24)
BLUE_BASE_POS = (0, 0, 24)
```

这些值在 `game_manager.py:40-41` 中被引用：
```python
red_spawn = Vec3(Config.RED_BASE_POS)
blue_spawn = Vec3(Config.BLUE_BASE_POS)
```

**解决方案**：这些值改为从地图数据读取，Config 中保留默认值作为 fallback：
```python
# game_manager.py — start_match() 改造
def start_match(self, selected_player_id, map_data=None):
    ...
    from arena.map_loader import load_map
    if map_data is None:
        map_data = load_map(Config.DEFAULT_MAP_NAME)
    self.game_map = GameMap(map_data)

    # 玩家出生点从地图数据读取
    red_spawn = Vec3(map_data.get('red_base', {}).get('position', Config.RED_BASE_POS))
    blue_spawn = Vec3(map_data.get('blue_base', {}).get('position', Config.BLUE_BASE_POS))
    ...
```

#### Gap 2：掩体高度随机值

`game_map.py:45` — `scale=(2, random.uniform(2, 3), 1)` 使掩体高度不可控、不可复现。

**解决方案**：JSON 中每个 cover 的 scale 字段指定精确值。如果 JSON 中省略 scale，则用默认值 `[2, 2.5, 1]`。

#### Gap 3：掩体颜色随机值

`game_map.py:49` — `color=color.hsv(0, 0, random.uniform(.9, 1))` 使颜色不可控。

**解决方案**：JSON 中可指定 `color` 字段（灰度 0-1），省略时用默认 0.95。

#### Gap 4：GameMap 不是 Entity

GameMap 是普通 Python 类，不能 `destroy()`。设计文档中方案正确（添加 `destroy()` 方法），但需注意 GameMap 本身不需要 `destroy()`，只是其内部实体需要。

#### Gap 5：角色选择界面未选择地图

当前 `CharacterSelect` 无地图选择功能。

**解决方案**：Phase 1 先用 Config.DEFAULT_MAP_NAME 自动选择，Phase 2 再加 UI。在 `CharacterSelect` 中添加地图下拉菜单或左右切换。

#### Gap 6：constants.py 新增字段

```python
class Config:
    ...
    # 地图
    DEFAULT_MAP_NAME = 'arena_classic'  # 新增
```

### 2.5 文件改动清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `arena/map_loader.py` | **新增** | 地图加载/默认值/列表 |
| `maps/arena_classic.json` | **新增** | 默认地图数据 |
| `arena/game_map.py` | 修改 | 从 map_data 构建 + boundary_walls 引用 + destroy() |
| `arena/base.py` | 修改 | 参数化 + parent=self（已在 1.3.1 完成） |
| `arena/game_manager.py` | 修改 | start_match 传入 map_data + 出生点从地图读取 |
| `arena/constants.py` | 修改 | 新增 DEFAULT_MAP_NAME |
| `arena/character_select.py` | 修改（Phase 2） | 添加地图选择 UI |

---

## 3. AI 独立进程架构

### 3.1 当前架构分析

```
主线程（渲染 + 游戏逻辑 + AI）
  main.py:23-24 — update() 调用 game_manager.update()
  player.py:159-160 — Player.update() → controller.update()
  ai_ctrl.py:31-44 — AIController.update() 同步执行
```

### 3.2 当前 AI 代码与 Entity 的耦合点

对照 `ai_ctrl.py` 代码逐项确认：

| # | 耦合操作 | 代码位置 | 说明 |
|---|----------|----------|------|
| 1 | `self.player.state.value` | `ai_ctrl.py:32` | 读取玩家状态 |
| 2 | `self.player.rotation_y += ...` | `ai_ctrl.py:38` | 直接修改旋转 |
| 3 | `self.player.position` | `ai_ctrl.py:50,64,100,107,115` | 读取/修改位置 |
| 4 | `self.player.look_at_2d(target, 'y')` | `ai_ctrl.py:73,89,99` | Ursina 内置方法，依赖 Entity |
| 5 | `self.player.forward` | `ai_ctrl.py:77,107,115` | Ursina Entity 属性 |
| 6 | `self.player.team` | `ai_ctrl.py:63` | 读取队伍 |
| 7 | `self.player.spawn_position` | `ai_ctrl.py:119` | 读取出生点 |
| 8 | `self.player.weapon.shoot(dir+spread)` | `ai_ctrl.py:83` | 射击，创建 Bullet Entity |
| 9 | `raycast(self.player.position, ...)` | `ai_ctrl.py:107-108` | 物理射线，必须主线程 |
| 10 | `distance(self.player.position, ...)` | `ai_ctrl.py:50,64,100` | Ursina 辅助函数 |
| 11 | `game_manager.players` | `ai_ctrl.py:62` | 通过延迟导入访问全局单例 |

### 3.3 方案调整

#### Gap 1：AI 需要的距离计算不依赖 Ursina

`distance(a, b)` 就是 `sqrt((a.x-b.x)² + (a.y-b.y)² + (a.z-b.z)²)`，可以用纯 Python 计算：
```python
import math
def dist_3d(a, b):
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2)
```

#### Gap 2：look_at_2d 无法在子进程执行

`look_at_2d` 是 Ursina Entity 方法，计算旋转角使实体朝向目标。AI 进程只需输出目标坐标，主进程执行旋转。

解耦后 AI 输出：
```python
{
    'look_at': (target_x, target_z),  # 朝向目标坐标
    'move_fwd': float,                 # -1..1
    'shoot': bool,                     # 是否射击
    'shoot_dir': (dx, dy, dz),        # 射击方向+散布（AI 自己算）
}
```

#### Gap 3：射击散布（spread）计算不依赖 Ursina

`ai_ctrl.py:78-82` 的 spread 计算是纯数学（`random.uniform` + `Vec3`），可以在子进程用纯 Python 实现：
```python
import random, math
spread_val = self.shoot_spread
shoot_dir = [
    forward[0] + random.uniform(-spread_val, spread_val),
    forward[1] + random.uniform(-spread_val, spread_val),
    forward[2] + random.uniform(-spread_val, spread_val),
]
```

AI 进程需要知道自己的 forward 向量（从共享内存的 rotation_y 计算）：
```python
def forward_from_rotation(rot_y):
    """从 Y 轴旋转角计算 forward 向量"""
    rad = math.radians(rot_y)
    return (math.sin(rad), 0, math.cos(rad))
```

#### Gap 4：raycast 必须在主线程

设计方案中 raycast 请求/响应通过共享内存排队是正确的，但增加了复杂度。

**更简单的替代方案**：AI 进程不做 raycast，改为**每帧由主进程代为执行**并把结果写入共享内存。AI 根据上一帧的 raycast 结果做决策（1 帧延迟可接受）。

共享内存中添加每个玩家的 raycast 结果字段：
```python
class PlayerShared(ctypes.Structure):
    _fields_ = [
        ...
        # --- 主进程 → AI（raycast 结果）---
        ('ray_hit', ctypes.c_int32),      # 0=无障碍, 1=有障碍
        ('ray_distance', ctypes.c_float),  # 障碍物距离
    ]
```

主进程每帧为每个 AI 玩家执行 raycast 并写入结果。

#### Gap 5：巡逻点生成不依赖 Entity

`ai_ctrl.py:117-128` — `_generate_patrol_points()` 使用 `self.player.spawn_position` 和 `Team` 枚举。在子进程中可以用纯数据（出生点坐标 + 队伍 ID）替代。

#### Gap 6：AI 进程无权访问 game_manager.players

`ai_ctrl.py:59-68` — `_find_nearest_enemy()` 通过 `from arena.game_manager import game_manager` 访问所有玩家。

在子进程中，所有玩家状态已通过共享内存传入，不需要访问 game_manager。AI 直接遍历 `SharedGameState.players` 中非同队的存活玩家。

#### Gap 7：shared_memory 在 Windows 上的可靠性

`multiprocessing.shared_memory` 在 Windows 上需要 `if __name__ == '__main__'` 保护，且 `SharedMemory.unlink()` 必须显式调用否则内存泄漏。当前 `main.py` 有 `if __name__ == '__main__'` 保护。

**额外注意**：Ursina 内部也使用了 multiprocessing（音效等），需要确保不冲突。建议 AI 进程启动前检查 Ursina 的 multiprocessing 使用方式。

#### Gap 8：AI 决策应用需要在 Player.update() 之外

当前 AI 的 update() 由 `player.py:160` 调用。改为共享内存后，AI 决策由 `game_manager.update()` 读取并应用，不再需要 Player 调用 AIController。

需要修改 `player.py:159-160`，让 AI 玩家的 controller 为 None（由 GameManager 统一控制）。

### 3.4 迁移策略（细化）

#### Phase 1：AIController 纯计算重构（仍在主线程）

目标：将 AIController 从"直接操作 Entity"改为"返回决策字典"，由 GameManager 统一应用。

```python
# ai_ctrl.py — 重构后
class AIController:
    """AI 控制器（纯计算，返回决策）"""

    def __init__(self, player):
        self.player = player  # 仍持有引用（Phase 1 简化）
        ...

    def update(self) -> dict:
        """纯计算，返回决策字典"""
        if self.player.state.value != 'alive':
            return {}

        # 碰撞回避优先
        if self.avoiding:
            if time.time() < self.avoid_end_time:
                return {
                    'rotate_y': self.avoid_direction * 90 * time.dt,
                    'move_fwd': 1.0,
                    'request_raycast': True,
                }
            else:
                self.avoiding = False

        return self.state_machine()

    def state_machine(self) -> dict:
        enemy = self._find_nearest_enemy()
        if enemy:
            dist = distance(self.player.position, enemy.position)
            if dist < self.attack_range:
                return self._attack(enemy)
            elif dist < self.detection_range:
                return self._chase(enemy)
        return self._patrol()

    def _attack(self, target) -> dict:
        self.state = 'attack'
        shoot_dir = None
        if time.time() - self.last_shoot_time > self.shoot_interval:
            fwd = self.player.forward.normalized()
            spread = Vec3(random.uniform(-self.shoot_spread, self.shoot_spread), ...)
            shoot_dir = fwd + spread
            self.last_shoot_time = time.time()
        return {
            'look_at': (target.position.x, target.position.z),
            'shoot_dir': (shoot_dir.x, shoot_dir.y, shoot_dir.z) if shoot_dir else None,
        }

    def _chase(self, target) -> dict:
        self.state = 'chase'
        return {
            'look_at': (target.position.x, target.position.z),
            'move_fwd': 1.0,
            'request_raycast': True,
        }

    def _patrol(self) -> dict:
        self.state = 'patrol'
        if not self.patrol_points:
            self._generate_patrol_points()
        target = self.patrol_points[self.current_patrol_idx]
        if distance(self.player.position, target) < 2:
            self.current_patrol_idx = (self.current_patrol_idx + 1) % len(self.patrol_points)
        return {
            'look_at': (target.x, target.z),
            'move_fwd': 1.0,
            'request_raycast': True,
        }
```

GameManager 统一应用：
```python
# game_manager.py — update() 中
if self.state == GameState.PLAYING:
    for player in self.players:
        if player == self.human_player:
            continue
        if player.controller and player.state.value == 'alive':
            cmd = player.controller.update()
            self._apply_ai_command(player, cmd)

@staticmethod
def _apply_ai_command(player, cmd):
    if not cmd:
        return
    if 'look_at' in cmd:
        tx, tz = cmd['look_at']
        player.look_at_2d(Vec3(tx, player.y, tz), 'y')
    if 'rotate_y' in cmd:
        player.rotation_y += cmd['rotate_y']
    if cmd.get('move_fwd') and abs(cmd['move_fwd']) > 0.05:
        move_distance = cmd['move_fwd'] * Config.AI_MOVE_SPEED * time.dt
        ray_hit = cmd.get('ray_hit', False)
        if 'request_raycast' in cmd and not ray_hit:
            ray = raycast(player.position, player.forward,
                          distance=move_distance, ignore=(player,))
            ray_hit = ray.hit
        if not ray_hit:
            player.position += player.forward * move_distance
    if cmd.get('shoot_dir'):
        dx, dy, dz = cmd['shoot_dir']
        player.weapon.shoot(Vec3(dx, dy, dz))
```

**Phase 1 注意事项**：
- `player.py:159-160` 不需要改（AIController.update() 仍由 Player 调用，只是返回值不同）
- Phase 1 中 `_apply_ai_command` 由 AIController 自己调用（保持现有调用路径）
- 真正的解耦在 Phase 2，由 GameManager 调用

#### Phase 2：共享内存 + AI 子进程

（与设计文档一致，补充了 Gap 分析后的调整）

### 3.5 文件改动清单

| 阶段 | 文件 | 改动类型 | 说明 |
|------|------|----------|------|
| Phase 1 | `arena/ai_ctrl.py` | 修改 | 改为返回决策字典 |
| Phase 1 | `arena/game_manager.py` | 修改 | 新增 `_apply_ai_command()` |
| Phase 2 | `arena/ai_process.py` | **新增** | AI 进程管理器 |
| Phase 2 | `arena/ai_worker.py` | **新增** | AI 子进程主循环 |
| Phase 2 | `arena/ai_ctrl.py` | 修改 | 不再持有 player 引用，纯数据输入 |
| Phase 2 | `arena/player.py` | 修改 | AI 玩家 controller=None |
| Phase 2 | `arena/constants.py` | 修改 | 新增 AI 进程配置 |

---

## 4. 单元测试设计

### 4.1 现状分析

当前项目**零测试覆盖**。所有关键类（XInput、InputManager、AIController、Player、GameMap、HUD、ScoreSystem、MatchTimer、KillFeed）均无单元测试。

核心挑战：项目深度依赖 Ursina 引擎（`from ursina import *`），多数类继承 `Entity`，直接实例化需要完整的 Ursina 运行时。需要分层测试策略。

### 4.2 测试分层

```
┌─────────────────────────────────────┐
│ Layer 3: 集成测试（需要 Ursina 运行时）│  ← 少量，CI 用 headless
├─────────────────────────────────────┤
│ Layer 2: 接口 Mock 测试              │  ← 中量，mock Entity/time
├─────────────────────────────────────┤
│ Layer 1: 纯逻辑单元测试              │  ← 大量，无任何依赖
└─────────────────────────────────────┘
```

### 4.3 各模块测试设计

#### 4.3.1 `arena/xinput.py` — Layer 1（纯逻辑）

**可测试性**：高。核心逻辑是 ctypes 结构体解析 + 数学归一化，不依赖任何引擎。

**测试策略**：mock `_dll`（XInput DLL），直接构造 `XINPUT_STATE` 结构体作为输入。

```python
# tests/test_xinput.py
import ctypes
import pytest
from arena.xinput import (
    XINPUT_STATE, XINPUT_GAMEPAD, BUTTONS,
    MAX_AXIS, STICK_DEADZONE, TRIGGER_THRESHOLD,
)

def make_state(wButtons=0, bLeftTrigger=0, bRightTrigger=0,
               thumbLX=0, thumbLY=0, thumbRX=0, thumbRY=0):
    """构造测试用的 XINPUT_STATE"""
    gamepad = XINPUT_GAMEPAD(
        wButtons=wButtons,
        bLeftTrigger=bLeftTrigger,
        bRightTrigger=bRightTrigger,
        thumbLX=thumbLX, thumbLY=thumbLY,
        thumbRX=thumbRX, thumbRY=thumbRY,
    )
    state = XINPUT_STATE(dwPacketNumber=1, Gamepad=gamepad)
    return state

class TestXInputGetState:
    """测试 get_state() 的归一化和死区逻辑"""

    def test_no_dll_returns_none(self, monkeypatch):
        """_dll 为 None 时返回 None"""
        import arena.xinput as xi
        monkeypatch.setattr(xi, '_dll', None)
        assert xi.get_state() is None

    def test_disconnected_returns_none(self, monkeypatch):
        """XInputGetState 返回非 0（未连接）时返回 None"""
        import arena.xinput as xi
        dll_mock = ctypes.windll.kernel32  # 任意有效的 DLL
        monkeypatch.setattr(xi, '_dll', dll_mock)
        # kernel32 没有 XInputGetState，会返回非 0
        result = xi.get_state()
        assert result is None

    def test_deadzone_filters_small_stick(self, monkeypatch):
        """死区内摇杆值归零"""
        import arena.xinput as xi
        # 构造一个 mock DLL，XInputGetState 写入已知数据
        ...

    def test_stick_normalization(self, monkeypatch):
        """摇杆值归一化到 -1..1"""
        # thumbLX = MAX_AXIS → lx = 1.0
        # thumbLX = -MAX_AXIS → lx = -1.0
        ...

    def test_trigger_normalization(self, monkeypatch):
        """扳机值归一化到 0..1"""
        # bLeftTrigger = 255 → lt = 1.0
        # bLeftTrigger = TRIGGER_THRESHOLD + 1 → lt ≈ (THRESHOLD+1)/255
        ...

    def test_trigger_below_threshold(self, monkeypatch):
        """扳机低于阈值归零"""
        # bLeftTrigger = TRIGGER_THRESHOLD → lt = 0.0
        # bLeftTrigger = TRIGGER_THRESHOLD + 1 → lt > 0
        ...

    def test_buttons_bitmask(self, monkeypatch):
        """按键位掩码正确解析"""
        # wButtons = 0x1000 | 0x4000 → buttons = {'A', 'X'}
        ...

    def test_no_buttons(self, monkeypatch):
        """无按键按下时 buttons 为空集"""
        # wButtons = 0 → buttons = set()
        ...
```

**关键 mock 技术**：需要 mock `_dll.XInputGetState` 使其写入预设数据并返回 0。Python ctypes 不易直接 mock C 函数指针，替代方案：
- 方案 A：将 `get_state` 的核心逻辑（解析 `XINPUT_STATE` → dict）提取为独立函数 `_parse_state(state) -> dict`，对纯函数测试
- 方案 B：使用 `ctypes.windll` 的 mock 包装

**推荐方案 A**：提取解析逻辑为纯函数。

```python
# xinput.py — 重构
def _parse_state(state: XINPUT_STATE) -> dict:
    """从 XINPUT_STATE 解析游戏状态（纯函数，可测试）"""
    g = state.Gamepad
    lx = g.thumbLX / MAX_AXIS if abs(g.thumbLX) > STICK_DEADZONE else 0.0
    ly = g.thumbLY / MAX_AXIS if abs(g.thumbLY) > STICK_DEADZONE else 0.0
    rx = g.thumbRX / MAX_AXIS if abs(g.thumbRX) > STICK_DEADZONE else 0.0
    ry = -g.thumbRY / MAX_AXIS if abs(g.thumbRY) > STICK_DEADZONE else 0.0
    lt = g.bLeftTrigger / 255.0 if g.bLeftTrigger > TRIGGER_THRESHOLD else 0.0
    rt = g.bRightTrigger / 255.0 if g.bRightTrigger > TRIGGER_THRESHOLD else 0.0
    buttons = {name for name, mask in BUTTONS.items() if g.wButtons & mask}
    return {'lx': lx, 'ly': ly, 'rx': rx, 'ry': ry,
            'lt': lt, 'rt': rt, 'buttons': buttons}

def get_state(controller=0):
    if not _dll:
        return None
    state = XINPUT_STATE()
    result = _dll.XInputGetState(controller, ctypes.byref(state))
    if result != 0:
        return None
    return _parse_state(state)
```

这样 `_parse_state` 可以直接用构造的 `XINPUT_STATE` 测试，无需 mock DLL。

#### 4.3.2 `arena/input_manager.py` — Layer 2（Mock 依赖）

**可测试性**：中。依赖 Ursina 的 `Entity`、`held_keys`、`time.dt`。

**测试策略**：
- 提取 `_merge` 为模块级纯函数（可单独测试）
- 提取 `_read_gamepad` 的核心逻辑（解析 state dict → 归一化值）为纯函数
- `_read_keyboard` 依赖 `held_keys`，需要 mock

```python
# tests/test_input_manager.py

class TestMergeFunction:
    """测试 _merge 输入合并逻辑"""

    def test_keyboard_overrides_small_gamepad(self):
        """键盘输入覆盖手柄小量"""
        assert _merge(1.0, 0.3) == 1.0
        assert _merge(-1.0, -0.3) == -1.0

    def test_gamepad_negative_not_swallowed(self):
        """手柄负值不被键盘的 0.0 吞掉"""
        assert _merge(0.0, -0.5) == -0.5
        assert _merge(0.0, -1.0) == -1.0

    def test_keyboard_negative_overrides_gamepad(self):
        """键盘负值覆盖手柄"""
        assert _merge(-1.0, 0.5) == -1.0

    def test_both_zero(self):
        """两者都为零"""
        assert _merge(0.0, 0.0) == 0.0

    def test_gamepad_larger_absolute(self):
        """手柄绝对值更大时取手柄"""
        assert _merge(0.0, 0.8) == 0.8
        assert _merge(0.0, -0.8) == -0.8

class TestReadGamepad:
    """测试 _read_gamepad 解析逻辑"""

    def test_no_gamepad_returns_zeros(self):
        """无手柄时返回全零"""
        # mock get_state 返回 None
        ...

    def test_stick_maps_to_forward(self):
        """左摇杆 Y 映射到前后"""
        # state = {'ly': 0.5, 'rx': 0, 'lt': 0, ...}
        # → fwd = 0.5
        ...

    def test_stick_maps_to_sideways(self):
        """右摇杆 X 映射到旋转"""
        # state = {'ly': 0, 'rx': -0.7, 'lt': 0, ...}
        # → side = -0.7
        ...

    def test_trigger_maps_to_shoot(self):
        """左扳机映射到射击"""
        # state = {'ly': 0, 'rx': 0, 'lt': 0.8, ...}
        # → shoot = 0.8
        ...

    def test_x_button_sets_action(self):
        """X 键设置 action"""
        # state = {..., 'buttons': {'X'}}
        # → action = True
        ...

class TestReadKeyboard:
    """测试 _read_keyboard 逻辑"""

    def test_w_key_forward(self):
        """W 键 → 前进 1.0"""
        # mock held_keys = {'w': True}
        ...

    def test_s_key_backward(self):
        """S 键 → 后退 -1.0"""
        ...

    def test_w_and_s_w_key_wins(self):
        """W 和 S 同时按下，W 优先（elif 逻辑）"""
        # mock held_keys = {'w': True, 's': True}
        # → fwd = 1.0
        ...

    def test_a_key_turn_left(self):
        """A 键 → 左转 -1.0"""
        ...

    def test_d_key_turn_right(self):
        """D 键 → 右转 1.0"""
        ...

    def test_left_mouse_shoot(self):
        """鼠标左键 → shoot 1.0"""
        ...

    def test_no_input_returns_zeros(self):
        """无输入返回全零"""
        ...

class TestInputMethod:
    """测试 input() 方法"""

    def test_v_key_sets_action(self):
        """V 键设置 action"""
        # im.input('v') → im.action == True
        ...

    def test_other_key_no_action(self):
        """其他按键不触发 action"""
        # im.input('a') → im.action == False
        ...
```

**重构建议**：将 `_merge` 提取为模块级函数 `merge_inputs(kb_val, gp_val)`，便于独立测试。

#### 4.3.3 `arena/ai_ctrl.py` — Layer 2（纯计算 + Mock）

**可测试性**：Phase 1 重构后为高（纯计算返回字典）。当前为中（直接操作 Entity）。

**Phase 1 重构后的测试**：

```python
# tests/test_ai_ctrl.py

class TestAIControllerPatrol:
    """巡逻行为测试"""

    def test_patrol_returns_move_command(self):
        """巡逻时返回移动指令"""
        # 设置 AI 状态（无敌人在检测范围）
        # 验证返回 {'look_at': ..., 'move_fwd': 1.0, 'request_raycast': True}
        ...

    def test_patrol_cycles_points(self):
        """巡逻点循环切换"""
        # 到达当前巡逻点后，切换到下一个
        ...

    def test_patrol_generates_points(self):
        """无巡逻点时自动生成"""
        ...

class TestAIControllerChase:
    """追击行为测试"""

    def test_detects_enemy_in_range(self):
        """检测范围内敌人触发追击"""
        # 敌人在 detection_range 内，不在 attack_range 内
        # → state='chase', look_at=enemy_pos, move_fwd=1.0
        ...

    def test_chase_moves_toward_enemy(self):
        """追击时朝向敌人"""
        ...

class TestAIControllerAttack:
    """攻击行为测试"""

    def test_attacks_in_range(self):
        """攻击范围内触发攻击"""
        # 敌人在 attack_range 内
        # → state='attack', look_at=enemy_pos, shoot_dir=...
        ...

    def test_shoot_throttle(self):
        """射击节流（0.2s 间隔）"""
        # 连续两次 update，第二次不应射击
        ...

    def test_shoot_spread(self):
        """射击散布范围合理"""
        # spread 值在 [-0.05, 0.05] 范围内
        ...

class TestAIControllerCollisionAvoidance:
    """碰撞回避测试"""

    def test_avoid_on_ray_hit(self):
        """前方有障碍时回避"""
        # ray_hit=True → avoiding=True, rotate_y != 0
        ...

    def test_avoid_timeout(self):
        """回避 1 秒后停止"""
        # avoid_end_time 过期后 → avoiding=False
        ...

class TestFindNearestEnemy:
    """敌人搜索测试"""

    def test_finds_closest_enemy(self):
        """找到最近敌人"""
        ...

    def test_ignores_same_team(self):
        """忽略队友"""
        ...

    def test_ignores_dead_enemies(self):
        """忽略死亡敌人"""
        ...

    def test_returns_none_when_no_enemies(self):
        """无存活敌人时返回 None"""
        ...
```

#### 4.3.4 `arena/player.py` — Layer 2（Mock Entity）

**可测试性**：中。Player 继承 Entity，但核心逻辑（状态转换、伤害计算）可提取测试。

```python
# tests/test_player.py

class TestPlayerTakeDamage:
    """受伤逻辑测试"""

    def test_normal_damage(self):
        """正常受伤减少 HP"""
        # player.hp = 100, take_damage(30) → hp = 70
        ...

    def test_dead_player_ignores_damage(self):
        """死亡玩家不受伤害"""
        # player.state = DEAD, take_damage(30) → hp unchanged
        ...

    def test_invincible_player_ignores_damage(self):
        """无敌玩家不受伤害"""
        # player.invincible = True, take_damage(30) → hp unchanged
        ...

    def test_lethal_damage_triggers_die(self):
        """致命伤害触发死亡"""
        # player.hp = 10, take_damage(20) → hp <= 0, state = DEAD
        ...

class TestPlayerDie:
    """死亡逻辑测试"""

    def test_die_increments_stats(self):
        """死亡增加击杀/死亡计数"""
        ...

    def test_die_schedules_respawn(self):
        """死亡后安排重生"""
        ...

    def test_destroyed_player_no_respawn(self):
        """已销毁玩家不重生"""
        # player.destroyed = True, respawn() → no action
        ...

class TestPlayerRespawn:
    """重生逻辑测试"""

    def test_respawn_restores_hp(self):
        """重生恢复满血"""
        ...

    def test_respawn_sets_invincible(self):
        """重生进入无敌状态"""
        ...

    def test_respawn_resets_position(self):
        """重生回到出生点"""
        ...
```

#### 4.3.5 `arena/score_system.py` — Layer 2（Mock Entity）

**可测试性**：高。纯计数逻辑，仅 `update_ui` 依赖 HUD。

```python
# tests/test_score_system.py

class TestTeamScoreSystem:
    def test_add_score(self):
        """加分"""
        # add_score(RED, 3) → get_score(RED) == 3

    def test_add_score_cumulative(self):
        """累计加分"""
        # add_score(RED, 3), add_score(RED, 2) → get_score(RED) == 5

    def test_teams_independent(self):
        """两队独立计分"""
        # add_score(RED, 3) → get_score(BLUE) == 0

    def test_reset(self):
        """重置清零"""
        # add_score(RED, 3), reset() → get_score(RED) == 0

    def test_get_score_default(self):
        """未加分时为 0"""
        # get_score(RED) == 0
```

#### 4.3.6 `arena/match_timer.py` — Layer 2（Mock time.dt）

**可测试性**：高。纯计时逻辑。

```python
# tests/test_match_timer.py

class TestMatchTimer:
    def test_start_sets_running(self):
        """start() 设 is_running=True"""

    def test_stop_clears_running(self):
        """stop() 设 is_running=False"""

    def test_reset_restores_duration(self):
        """reset() 恢复剩余时间"""

    def test_countdown(self):
        """每帧减少 time.dt"""

    def test_time_reaches_zero(self):
        """时间到触发 end_match"""

    def test_no_countdown_when_stopped(self):
        """未启动时不倒计时"""
```

#### 4.3.7 `arena/kill_feed.py` — Layer 2（Mock Entity）

**可测试性**：中。add_kill 创建 Text Entity。

```python
# tests/test_kill_feed.py

class TestKillFeed:
    def test_add_kill_appends_message(self):
        """add_kill 增加一条消息"""

    def test_max_messages_limit(self):
        """超过最大消息数仍可添加（无硬上限，靠自动移除）"""

    def test_clear_removes_all(self):
        """clear() 清空所有消息"""

    def test_remove_message_after_delay(self):
        """5 秒后自动移除"""
```

#### 4.3.8 `arena/map_loader.py`（新增）— Layer 1（纯逻辑）

**可测试性**：最高。纯文件 I/O + JSON 解析，无任何引擎依赖。

```python
# tests/test_map_loader.py
import json
import os
import tempfile
import pytest
from arena.map_loader import load_map, list_maps, _default_map

class TestLoadMap:
    def test_load_valid_map(self, tmp_path):
        """加载有效地图文件"""
        map_file = tmp_path / "test_map.json"
        map_file.write_text(json.dumps({
            "name": "Test", "version": 1,
            "ground": {"size": 48},
            "covers": []
        }))
        # 修改 MAPS_DIR 指向 tmp_path
        data = load_map("test_map", maps_dir=str(tmp_path))
        assert data["name"] == "Test"
        assert data["ground"]["size"] == 48

    def test_missing_map_returns_default(self, tmp_path):
        """不存在的地图返回默认值"""
        data = load_map("nonexistent", maps_dir=str(tmp_path))
        assert "Arena Classic" in data["name"]

    def test_default_map_structure(self):
        """默认地图数据结构完整"""
        data = _default_map()
        assert "ground" in data
        assert "red_base" in data
        assert "blue_base" in data
        assert "covers" in data
        assert "boundaries" in data
        assert len(data["covers"]) == 12

    def test_covers_have_position(self):
        """每个掩体都有位置"""
        data = _default_map()
        for cover in data["covers"]:
            assert "position" in cover
            assert len(cover["position"]) == 3

class TestListMaps:
    def test_lists_json_files(self, tmp_path):
        """列出所有 .json 地图文件"""
        (tmp_path / "map_a.json").write_text("{}")
        (tmp_path / "map_b.json").write_text("{}")
        (tmp_path / "readme.txt").write_text("")
        maps = list_maps(maps_dir=str(tmp_path))
        assert "map_a" in maps
        assert "map_b" in maps
        assert "readme" not in maps

    def test_empty_dir(self, tmp_path):
        """空目录返回空列表"""
        maps = list_maps(maps_dir=str(tmp_path))
        assert maps == []
```

#### 4.3.9 `arena/game_manager.py` — Layer 3（集成测试）

**可测试性**：低。深度依赖 Ursina 运行时。

**测试策略**：仅测试纯逻辑方法（如 `_apply_ai_command` 的计算部分），不测试 Entity 创建/销毁。

```python
# tests/test_game_manager.py

class TestApplyAICommand:
    """测试 AI 决策应用（需要 Ursina 运行时创建 Player）"""

    def test_move_forward_command(self):
        """move_fwd > 0 时前进"""
        ...

    def test_move_backward_command(self):
        """move_fwd < 0 时后退"""
        ...

    def test_look_at_command(self):
        """look_at 旋转朝向"""
        ...

    def test_shoot_command(self):
        """shoot_dir 触发射击"""
        ...

    def test_empty_command_no_action(self):
        """空指令不产生任何操作"""
        ...
```

### 4.4 测试基础设施

#### 目录结构

```
CubicWheelLoader/
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # 公共 fixture（Ursina 启动、mock 工具）
│   ├── test_xinput.py       # Layer 1
│   ├── test_input_manager.py # Layer 2
│   ├── test_ai_ctrl.py      # Layer 2
│   ├── test_player.py       # Layer 2
│   ├── test_score_system.py # Layer 2
│   ├── test_match_timer.py  # Layer 2
│   ├── test_kill_feed.py    # Layer 2
│   ├── test_map_loader.py   # Layer 1
│   └── test_game_manager.py # Layer 3
├── arena/
│   └── ...
```

#### conftest.py 公共 fixture

```python
# tests/conftest.py
import pytest

@pytest.fixture(scope='session')
def ursina_app():
    """会话级 Ursina 实例（Layer 2/3 测试需要）"""
    from ursina import Ursina
    app = Ursina(title='Test', borderless=False, development_mode=False)
    yield app
    app.quit()

@pytest.fixture(autouse=True)
def reset_globals():
    """每个测试后重置全局状态"""
    yield
    # 清理 held_keys、场景实体等
```

**注意**：Layer 2 测试如能通过 mock 避免启动 Ursina，应优先 mock。Ursina 启动开销大（~2s），不适合每个测试都启动。

#### 运行方式

```bash
# Layer 1（纯逻辑，最快）
pytest tests/test_xinput.py tests/test_map_loader.py -v

# Layer 2（需 mock 或 Ursina）
pytest tests/test_input_manager.py tests/test_ai_ctrl.py tests/test_player.py -v

# Layer 3（需 Ursina 运行时）
pytest tests/test_game_manager.py -v

# 全部
pytest tests/ -v
```

### 4.5 重构需求（为可测试性）

| 模块 | 当前问题 | 重构方案 |
|------|----------|----------|
| `xinput.py` | `get_state()` 混合了 DLL 调用和解析逻辑 | 提取 `_parse_state(state) -> dict` 纯函数 |
| `input_manager.py` | `_merge` 是闭包内函数 | 提取为模块级 `merge_inputs()` |
| `input_manager.py` | `_read_gamepad` 混合了 API 调用和映射 | 提取 `_parse_gamepad_state(state) -> (fwd, side, shoot)` 纯函数 |
| `ai_ctrl.py` | 直接操作 Entity | Phase 1：返回决策字典；提取 `_find_nearest_enemy_data()` |
| `player.py` | `die()` 中延迟导入 game_manager | 改为构造函数注入或事件回调 |
| `match_timer.py` | `update()` 中延迟导入 game_manager | 同上 |
| `score_system.py` | `update_ui()` 延迟导入 hud | 同上 |

### 4.6 测试优先级与升级任务绑定

| 升级任务 | 必须先完成的测试 | 原因 |
|----------|------------------|------|
| **P0 状态残留修复** | Player.destroyed、GameMap.destroy()、HUD.destroy() | 防止重构清理逻辑时引入新 bug |
| **P1 独立地图文件** | map_loader（load_map、_default_map、list_maps） | 防止 JSON 解析错误导致崩溃 |
| **P2 AI 纯计算重构** | AIController 全部测试 | 重构调用路径，必须有测试保护 |
| **P3 AI 独立进程** | SharedGameState 读写、AIProcessManager 生命周期 | 多进程稳定性 |

---

## 5. 实施优先级

| 优先级 | 任务 | 依赖 | 风险 |
|--------|------|------|------|
| **P0** | 比赛间状态残留修复 | 无 | 低 — 纯清理逻辑，不改变游戏行为 |
| **P0** | 基础测试框架 + XInput/ScoreSystem/MatchTimer 单元测试 | 无 | 低 — 纯新建，不影响现有代码 |
| **P1** | 独立地图文件 | P0（需要 GameMap.destroy()） | 低 — 纯数据提取 |
| **P1** | map_loader + InputManager 单元测试 | P0 | 低 |
| **P2** | AI 纯计算重构 | 无 | 中 — 改变 AI 调用路径，需充分测试 |
| **P2** | AIController + Player 单元测试 | P0 | 中 — 重构前必须先有测试保护 |
| **P3** | AI 独立进程 | P2 | 高 — 共享内存+多进程，需要稳定性测试 |
