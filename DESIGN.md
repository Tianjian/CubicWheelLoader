# CubicWheelLoader 设计文档

本文件合并了项目所有设计文档，涵盖游戏系统设计、升级计划、引擎参考等内容。

---

## 目录

1. [游戏系统设计](#1-游戏系统设计)
2. [手柄操控设计](#2-手柄操控设计)
3. [升级计划（P0-P3）](#3-升级计划p0-p3)
4. [FPS Demo 设计参考](#4-fps-demo-设计参考)
5. [Ursina 引擎架构与参考](#5-ursina-引擎架构与参考)

---

# 1. 游戏系统设计

## 1.1 核心玩法

- **4 名 Player**，分为红队 x2 和蓝队 x2
- 人类玩家可选择操控任意一个 Player，其余 3 个由 AI 控制
- 击杀对方 Player 每次得 3 分，被击杀后在本方基地重生
- 比赛时长 5 分钟，时间结束后总分高的队伍获胜

## 1.2 游戏状态机

```
[主菜单] → [选择角色] → [倒计时 3-2-1] → [比赛进行中] → [比赛结束]
```

| 状态 | 说明 |
|------|------|
| MENU | 显示操作说明、队伍分配、开始按钮 |
| CHARACTER_SELECT | 玩家选择操控 1-4 号角色 |
| COUNTDOWN | 3 秒倒计时 |
| PLAYING | 比赛进行，计分、计时 |
| MATCH_END | 显示结果、比分统计、重新开始 |

## 1.3 玩家系统

### 玩家实体

```python
class Player(Entity):
    player_id       # 1-4
    team            # RED / BLUE
    state           # ALIVE / DEAD / RESPAWNING
    max_hp = 100
    hp = 100
    kills = 0
    deaths = 0
    destroyed       # 销毁标志位，防止延迟回调操作已销毁实体
    invincible      # 重生无敌
    weapon          # Weapon 实例（parent=self）
    health_bar      # 头顶血条（parent=self）
    name_tag        # 头顶名字（parent=self）
```

### 伤害与重生

| 参数 | 值 |
|------|-----|
| 最大 HP | 100 |
| 子弹伤害 | 10 |
| 重生时间 | 3 秒 |
| 重生 HP | 100 |
| 重生无敌 | 2 秒 |
| 射击冷却 | 0.15 秒 |

### AI 行为状态机

```
[发现敌人]
     ↓
[PATROL] → [CHASE] → [ATTACK]
  ↑            ↑          │
  └── [丢失目标] ←── [脱离射程]
```

| 状态 | 触发条件 | 行为 |
|------|----------|------|
| PATROL | 无敌人视野内 | 在预设巡逻点间移动 |
| CHASE | 敌人进入检测范围（40 单位） | 朝敌人移动 |
| ATTACK | 敌人进入攻击范围（25 单位） | 面向敌人射击 |

AI 返回决策字典，由 GameManager 统一应用：
```python
{'look_at': (x, z), 'move_fwd': float, 'request_raycast': bool, 'shoot_dir': (dx, dy, dz)}
```

## 1.4 地图设计

### 地图布局（俯视）

```
          Z+
          ↑
   ┌──────┼──────┐
   │  红队 │      │
   │  基地 │      │
   │  ●   │      │
───┼──────┼──────┼─── X+
   │      │  蓝队 │
   │      │  基地 │
   │      │  ●   │
   └──────┼──────┘
          │
          Z-
```

### 地图参数

| 参数 | 值 |
|------|-----|
| 地图总尺寸 | 64 x 64 |
| 红队基地位置 | (0, 0, -24) |
| 蓝队基地位置 | (0, 0, 24) |
| 对称轴 | X = 0 |
| 掩体数量 | 12 个（对称放置） |

### 地图数据外部化

地图数据存放在 `maps/` 目录下的 JSON 文件中，通过 `map_loader.py` 加载：

```python
from arena.map_loader import load_map, list_maps
map_data = load_map('arena_classic')  # 加载 maps/arena_classic.json
available = list_maps()                # 列出所有可用地图
```

JSON 格式包含 ground、red_base、blue_base、covers（12 个）、boundaries 配置。

## 1.5 计分与计时

- 击杀敌方 +3 分（给击杀者所在队伍）
- 比赛时长 300 秒（5 分钟）
- 最后 30 秒计时器变红闪烁
- 时间到判定胜负，平局显示 DRAW

## 1.6 相机系统

| 特性 | 值 |
|------|-----|
| 默认视角 | TPS（第三人称） |
| 相机距离 | 近 8 / 远 40 单位（V 键切换） |
| 相机高度 | 近 4 / 远 15 单位 |
| 相机跟随方式 | 平滑跟随 + 围绕玩家旋转 |

### 射击方向：跟随本体

射击方向 = `player.forward`（玩家朝向），而非相机方向。相机仅作为观察者，不控制射击。

### 地面准星

在玩家前方投射地面准星（黄色圆圈），指示当前朝向。

## 1.7 HUD 布局

```
┌─────────────────────────────────────────────┐
│  [RED: 0] ──── 05:00 ──── [BLUE: 0]        │  顶部：比分 + 时间
│                                             │
│                 游戏画面                      │
│                                             │
│  [HP ████████░░]  [K:0 D:0]  [P1 RED]      │  底部：血条、战绩、身份
│          ○ 地面准星                          │  中心
└─────────────────────────────────────────────┘
```

## 1.8 子弹系统

- 实体子弹，每帧飞行并做前方 raycast 碰撞检测
- 友军伤害过滤（`bullet.owner.team` 检查）
- 全局 `_all_bullets` 列表追踪，比赛结束时 `clear_all_bullets()` 批量清理
- 子弹属性：damage=10, speed=35, max_distance=100

---

# 2. 手柄操控设计

## 2.1 输入架构

```
键盘 held_keys ──┐
                  ├──→ InputManager.update() ──→ move_forward / move_sideways / shoot
XInput 状态  ────┘         (归一化、死区处理、杆量映射)

input(key) ────────→ InputManager.input() ──→ action (切换视角)
```

### InputManager 输出接口

| 属性 | 类型 | 范围 | 说明 |
|------|------|------|------|
| move_forward | float | -1..1 | 正=前进，杆量=速度比例 |
| move_sideways | float | -1..1 | 正=右转，杆量=速度比例 |
| shoot | float | 0..1 | >0 射击，扳机压力=射速比例 |
| action | bool | | 瞬时动作（消费型，读取后重置） |

### 手柄按键映射

| 操作 | 键盘/鼠标 | 手柄 |
|------|-----------|------|
| 前进 | W | 左摇杆 ↑ (thumbLY > 0) |
| 后退 | S | 左摇杆 ↓ (thumbLY < 0) |
| 左转 | A | 右摇杆 ← (thumbRX < 0) |
| 右转 | D | 右摇杆 → (thumbRX > 0) |
| 射击 | 鼠标左键 | 左扳机 LT (bLeftTrigger > 阈值) |
| 切换视角 | V | X 键 |

## 2.2 XInput 封装

通过 `ctypes` 直接调用 Windows `xinput1_4.dll`，绕过 Panda3D 的 InputDevice API（该 API 在 Windows 上无法正常读取 Xbox 手柄数据）。

核心函数：
- `_parse_state(state)` — 纯函数，从 XINPUT_STATE 结构体解析出归一化摇杆/扳机/按键值
- `get_state(controller=0)` — 读取手柄状态，返回 dict 或 None
- `vibrate(controller, left, right)` — 震动控制

常量：
- `STICK_DEADZONE = 7849`（XInput 推荐死区）
- `TRIGGER_THRESHOLD = 30`

## 2.3 纯函数提取（可测试性）

| 模块 | 纯函数 | 说明 |
|------|--------|------|
| xinput.py | `_parse_state(state)` | ctypes 结构体 → dict |
| input_manager.py | `merge_inputs(kb_val, gp_val)` | 键盘/手柄输入合并（取绝对值较大） |
| input_manager.py | `parse_gamepad_state(state)` | 手柄状态 → (fwd, side, shoot) |

---

# 3. 升级计划（P0-P3）

## P0: 比赛间状态残留修复 ✅ 已完成

### 问题

第二局开始时，第一局的游戏实体和 UI 残留在场景中。

### 泄漏清单

| # | 泄漏项 | 原因 |
|---|--------|------|
| 1 | GameMap 全部实体 | _restart() 未销毁 game_map |
| 2 | Base 子实体 | 子实体无 parent=self，destroy 不递归 |
| 3 | 4 个边界墙 | 匿名 Entity 无引用 |
| 4 | HUD 7 个元素 | _restart() 未调用 HUD 清理 |
| 5 | end_match() 4 个 UI 元素 | 3 个 Text + 1 个 Button 无引用 |
| 6 | CameraController Entity | 仅设 None 未 destroy() |
| 7 | 飞行中的 Bullet | 比赛结束时未清理 |

### 延迟回调隐患

| # | 回调 | 延迟 | 修复 |
|---|------|------|------|
| 1 | player.respawn() | 3s | 检查 destroyed 标志 |
| 2 | player._end_invincibility() | 2s | 检查 destroyed 标志 |
| 3 | weapon._hide_muzzle_flash() | 0.05s | 检查 destroyed 标志 |
| 4 | weapon._end_cooldown() | 0.15s | 检查 destroyed 标志 |
| 5 | KillFeed._remove_message() | 5s | try/except 包裹 destroy() |

### 修复方案

1. **Base**: 子实体加 `parent=self`，position 改局部坐标，构造函数参数化
2. **GameMap**: 添加 `destroy()` 方法，boundary_walls 保存引用
3. **HUD**: 添加 `destroy()` 方法
4. **Player**: 添加 `destroyed` 标志，respawn/_end_invincibility 检查
5. **Weapon**: 添加 `destroyed` 标志，_hide_muzzle_flash/_end_cooldown 检查
6. **Bullet**: `_all_bullets` 全局列表 + `clear_all_bullets()`
7. **GameManager**: `_restart()` 11 步完整清理，`end_match()` UI 保存到 `_result_ui`

---

## P1: 独立地图文件 ✅ 已完成

### 改动

| 文件 | 类型 | 说明 |
|------|------|------|
| arena/map_loader.py | 新增 | 地图加载/默认值/列表 |
| maps/arena_classic.json | 新增 | 默认地图数据 |
| arena/game_map.py | 修改 | 从 map_data 构建 + destroy() |
| arena/base.py | 修改 | 参数化 + parent=self |
| arena/game_manager.py | 修改 | start_match 传入 map_data |
| arena/constants.py | 修改 | 新增 DEFAULT_MAP_NAME |

### Vec3 修复

JSON 中 position 为 list `[0, 0, -24]`，Ursina 的 `Vec3` 不接受单个 list 参数，需 `Vec3(*position)` 解包。

---

## P2: AI 纯计算重构 ✅ 已完成

### 改动

| 文件 | 说明 |
|------|------|
| arena/ai_ctrl.py | 改为返回决策字典，添加 `forward_from_rotation()`, `dist_3d()` 纯函数 |
| arena/game_manager.py | 新增 `_apply_ai_command(player, cmd)` 统一应用 AI 决策 |

### AI 决策字典

```python
{
    'look_at': (target_x, target_z),    # 朝向目标坐标
    'rotate_y': float,                   # 旋转增量（碰撞回避时使用）
    'move_fwd': float,                   # -1..1 前进量
    'request_raycast': bool,             # 是否需要 raycast
    'shoot_dir': (dx, dy, dz) | None,   # 射击方向+散布
}
```

### _apply_ai_command 统一应用

```python
if 'look_at' in cmd:
    player.look_at_2d(Vec3(tx, player.y, tz), 'y')
if 'rotate_y' in cmd:
    player.rotation_y += cmd['rotate_y']
if cmd.get('move_fwd'):
    # raycast + 移动
if cmd.get('shoot_dir'):
    player.weapon.shoot(Vec3(dx, dy, dz))
```

---

## P3: AI 独立进程 ✅ 已完成

### 架构

```
主进程                              AI 子进程
┌──────────────────┐               ┌──────────────────┐
│ GameManager      │               │ AIDecider         │
│   │              │   SharedMemory │   │               │
│   ├── write ─────┼──────────────→│   ├── read        │
│   │  PlayerInput │               │   │  PlayerInput   │
│   │              │               │   │                │
│   │←── read ─────┼───────────────│   ├── decide      │
│   │  PlayerCmd   │               │   │                │
│   │              │               │   └── write        │
│   └── apply      │               │      PlayerCmd     │
└──────────────────┘               └──────────────────┘
```

### 共享内存结构

```python
class PlayerInput(Structure):
    player_id, team_id, state, pos_x/y/z, rotation_y, hp, spawn_x/z, ray_hit, ray_distance

class PlayerCommand(Structure):
    look_at_x/z, rotate_y, move_fwd, request_raycast, shoot_dir_x/y/z, avoiding, avoid_direction

class SharedGameState(Structure):
    running, frame_number, ai_frame_done, players[4], player_count, commands[4], dt
```

### 双模式切换

```python
# constants.py
AI_USE_SUBPROCESS = False  # True=独立进程, False=主线程
AI_SUBPROCESS_TIMEOUT = 0.005
```

### 文件清单

| 文件 | 说明 |
|------|------|
| arena/shared_state.py | ctypes 结构定义 + AIDecider（纯 Python，无 Ursina） |
| arena/ai_worker.py | 子进程入口 `ai_process_main(shm_name)` |
| arena/ai_process.py | AIProcessManager：start/stop/read/write |

### AIDecider（纯 Python AI）

- 不依赖 Ursina，可独立运行于子进程
- 读取 PlayerInput → 状态机决策 → 写入 PlayerCommand
- 使用 `forward_from_rotation()` 和 `dist_3d()` 纯函数计算朝向和距离

---

## 单元测试 ✅ 已完成

### 测试分层

```
Layer 1: 纯逻辑（无依赖）  ← 大量，最快
Layer 2: Mock Entity/time   ← 中量
Layer 3: 集成（需 Ursina）  ← 少量
```

### 测试文件

| 文件 | 层 | 测试数 | 覆盖模块 |
|------|-----|--------|----------|
| test_xinput.py | L1 | 22 | _parse_state |
| test_map_loader.py | L1 | 15 | load_map, _default_map, list_maps |
| test_input_manager.py | L1 | 17 | merge_inputs, parse_gamepad_state |
| test_score_system.py | L2 | 7 | TeamScoreSystem |
| test_match_timer.py | L2 | 8 | MatchTimer |
| test_ai_ctrl.py | L1+2 | 20 | forward_from_rotation, dist_3d, AIController |
| test_shared_state.py | L1 | 21 | 结构读写, AIDecider, dict_to_command |

---

# 4. FPS Demo 设计参考

> 以下内容来自 `fps_demo_v4.py` 的设计分析，为项目演进提供参考。

## 4.1 实体子弹系统

原始 fps_demo 使用射线检测（`mouse.hovered_entity`）实现即时命中。升级为实体子弹后：

- 子弹具有物理飞行轨迹（每帧移动 + 前方 raycast 碰撞检测）
- 支持击中效果（粒子、音效）和自动销毁（射程限制）
- 增加游戏策略性：需要预判敌人移动、考虑子弹飞行时间

### 性能优化方向

- 对象池（BulletPool）减少内存分配
- 限制同屏最大子弹数
- LOD（远距离低模）
- 实例化渲染

## 4.2 第三人称视角

### 相机跟随

```python
# TPS：相机在玩家身后上方
target_position = player.position + offset
camera.position = lerp(camera.position, target_position, speed * time.dt)
camera.look_at(player.position + Vec3(0, 1.5, 0))
```

### 射击方向：方向跟随本体

核心改动：射击方向 = `player.forward`，而非 `camera.forward`。

```python
# 唯一的核心改动
target_point = player.position + player.forward * 100
return (target_point - gun.world_position).normalized()
```

这样设计：
- 视觉一致性最好 — 子弹方向和玩家朝向一致
- 符合动作游戏直觉
- 玩家需要转身瞄准（A/D 旋转），操作感更强

配合地面准星（投射到玩家前方地面）提供朝向反馈。

## 4.3 武器扩展方向

| 武器 | 伤害 | 射速 | 子弹速度 | 特殊 |
|------|------|------|---------|------|
| 手枪 | 10 | 0.3s | 50 | - |
| 突击步枪 | 8 | 0.1s | 60 | - |
| 霰弹枪 | 6x5 | 0.8s | 40 | 散射 5 发 |
| 狙击枪 | 50 | 1.0s | 100 | - |

---

# 5. Ursina 引擎架构与参考

## 5.1 架构概览

Ursina 是基于 Python 的轻量级 3D 游戏引擎，底层封装 Panda3D。

核心特点：
- **单文件导入**: `from ursina import *`
- **Entity 组件系统**: 统一的游戏对象基类
- **Python 原生**: 无需额外语言
- **单例模式**: camera, mouse, scene, window 等全局唯一

## 5.2 核心模块

| 模块 | 职责 |
|------|------|
| main.py | Ursina 主类，引擎入口和生命周期管理 |
| entity.py | Entity 核心类，所有游戏对象的基类 |
| application.py | 全局应用状态和配置 |
| window.py | 窗口管理 |
| camera.py | 相机系统 |
| scene.py | 场景管理和实体列表 |
| mouse.py | 鼠标输入和射线检测 |
| input_handler.py | 键盘输入处理和 held_keys |
| collider.py | 碰撞检测（Box/Sphere/Mesh/Capsule） |
| raycast.py | 射线检测 |
| physics.py | Bullet Physics 物理引擎 |
| audio.py | 音频系统 |
| text.py | 文本渲染 |
| mesh.py | 网格系统和程序化几何体 |
| shader.py | 着色器系统 |
| sequence.py | 序列和动画系统 |
| curve.py | 缓动曲线 |

## 5.3 主循环流程

```
每帧执行:
1. 计算 delta time (time.dt)
2. 更新鼠标 (mouse.update())
3. 调用全局 update 函数
4. 更新所有序列 (sequence.update())
5. 清理待删除实体
6. 更新所有实体:
   - 跳过禁用/忽略/暂停的实体
   - 调用 entity.update()
7. 更新着色器
8. 更新音频
```

## 5.4 Entity 核心属性

```python
# 变换
position: Vec3     # 位置
rotation: Vec3     # 旋转
scale: Vec3        # 缩放

# 渲染
model: str/Mesh    # 模型
texture: str       # 纹理
color: Color       # 颜色
shader: Shader     # 着色器

# 状态
enabled: bool      # 是否启用
collider: Collider # 碰撞器

# 魔法方法
update()           # 每帧更新
input(key)         # 输入处理
on_enable()        # 启用时
on_disable()       # 禁用时
on_destroy()       # 销毁时
```

## 5.5 坐标系

```
    y (up)
    |
    | (forward) z
   \|
    *---------- x (right)
```

UI 坐标系：中心 (0,0)，范围 (-0.5 到 0.5)

## 5.6 碰撞检测

```python
# raycast
hit_info = raycast(origin, direction, distance=9999, ignore=[], debug=False)
# 返回 HitInfo: .hit, .entity, .world_point, .distance, .world_normal

# boxcast（有宽度的射线）
hit_info = boxcast(origin, direction, thickness=(1,1), ...)

# intersects（相交检测）
if player.intersects(trigger_box).hit: ...
```

碰撞器类型：`'box'`（最快）→ `'sphere'` → `'mesh'`（最慢）

## 5.7 关键 API 速查

```python
# 动画
entity.animate('attribute', value, duration=1, curve=curve.linear)
entity.animate_position(target, duration=1)
entity.animate_color(color.red, duration=0.3)

# 延迟执行
invoke(function, delay=1)

# 销毁
destroy(entity)  # 递归销毁子实体

# 数学
lerp(a, b, t)          # 线性插值
distance(a, b)         # 距离
clamp(value, min, max) # 限制范围

# 输入
held_keys['w']         # 按键状态（True/False）
mouse.hovered_entity   # 鼠标悬停的实体
mouse.world_point      # 鼠标指向的 3D 点

# 全局
time.dt                # 帧时间
application.paused     # 暂停状态
```

## 5.8 设计模式

1. **单例模式**: Ursina, camera, mouse, scene, window
2. **实体组件系统**: Entity + collider/scripts 组件
3. **观察者模式**: input/update 方法回调
4. **工厂模式**: load_model(), load_texture()
5. **策略模式**: 不同 collider 类型、shader 实现

## 5.9 安装

```bash
pip install ursina
# 或开发版
pip install https://github.com/pokepetter/ursina/archive/master.zip
```

## 5.10 参考资料

- 官方文档: https://www.ursinaengine.org/documentation.html
- API 参考: https://www.ursinaengine.org/api_reference.html
- GitHub: https://github.com/pokepetter/ursina
