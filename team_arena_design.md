# Team Arena — TPS 团队竞技对战游戏设计文档

## 1. 项目概述

### 1.1 游戏定位

Team Arena 是一款基于 Ursina 引擎开发的 **第三人称视角（TPS）团队竞技对战游戏**。以 `fps_demo_v4.py` 为技术基础，将其从单人打怪模式重构为 4 人对战模式。

### 1.2 核心玩法

- **4 名 Player**，分为 **红队 × 2** 和 **蓝队 × 2**
- 人类玩家可选择操控任意一个 Player，其余 3 个由 AI 控制
- 红蓝两队互为敌对关系，**无公共 Enemy**
- 击杀对方 Player 每次得 **3 分**，被击杀后在**本方基地重生**
- 比赛时长 **5 分钟**，时间结束后总分高的队伍获胜

### 1.3 技术基础

| 模块 | 来源 | 复用说明 |
|------|------|----------|
| Bullet 类 | fps_demo_v4 | 子弹实体飞行、碰撞检测、击中特效、音效 |
| Weapon 类 | fps_demo_v4 | 武器发射、冷却、枪口闪光 |
| CameraController | fps_demo_v4 | FPS/TPS 视角切换（主视角用于人类玩家） |
| TPSMovementController | fps_demo_v4 | 坦克式移动（A/D 旋转、W/S 前后） |
| 地图与地面 | fps_demo_v4 | 需重新设计为对称竞技地图 |

---

## 2. 游戏架构设计

### 2.1 核心类继承关系

```
Entity
├── PlayerController (新)        — 统一玩家控制器，人类/AI 共用接口
│   ├── HumanPlayer (新)         — 人类玩家，接收输入
│   └── AIPlayer (新)            — AI 玩家，自动决策
├── Player (新)                  — 游戏角色实体（4 个实例）
│   ├── HP 系统
│   ├── 武器系统
│   ├── 队伍标识（红/蓝）
│   └── 状态机（alive / dead / respawning）
├── Bullet (复用)                — 子弹实体
├── Weapon (复用)                — 武器类
├── Base (新)                    — 队伍基地（重生点）
├── GameMap (新)                 — 对称竞技地图
├── TeamScore (新)               — 队伍计分系统
├── MatchTimer (新)              — 比赛计时器
└── GameManager (重构)           — 游戏流程控制
```

### 2.2 游戏状态机

```
[主菜单] → [选择角色] → [倒计时 3-2-1] → [比赛进行中] → [比赛结束]
                                              ↑                │
                                              └── 5分钟 ──────┘
```

| 状态 | 说明 |
|------|------|
| MENU | 显示操作说明、队伍分配、开始按钮 |
| CHARACTER_SELECT | 玩家选择操控 1-4 号角色 |
| COUNTDOWN | 3 秒倒计时，所有玩家就位 |
| PLAYING | 比赛进行，计分、计时 |
| MATCH_END | 显示结果、比分统计、重新开始选项 |

---

## 3. Player 系统

### 3.1 Player 实体设计

```python
class Team(Enum):
    RED = "red"
    BLUE = "blue"

class PlayerState(Enum):
    ALIVE = "alive"
    DEAD = "dead"
    RESPawning = "respawning"

class Player(Entity):
    def __init__(self, player_id, team, spawn_position, **kwargs):
        super().__init__(
            model='cube',
            origin_y=-.5,
            scale=1,
            collider='box',
            position=spawn_position,
            **kwargs
        )
        self.player_id = player_id      # 1-4
        self.team = team                # RED / BLUE
        self.state = PlayerState.ALIVE

        # 生命值
        self.max_hp = 100
        self.hp = 100

        # 击杀计分
        self.kills = 0
        self.deaths = 0

        # 武器（每个 Player 自带一把枪）
        self.weapon = Weapon(
            parent=self,
            model='cube',
            position=(0.5, 0.5, 0.25),
            scale=(.3, .2, 1),
            origin_z=-0.5,
            bullet_damage=10,
            bullet_speed=35,
            fire_rate=0.15
        )

        # 血条（头顶显示）
        self.health_bar_bg = Entity(parent=self, y=2, model='quad',
                                     color=color.dark_gray, world_scale=(1.5, 0.15))
        self.health_bar = Entity(parent=self, y=2, model='quad',
                                  color=color.green, world_scale=(1.5, 0.1))

        # 名字标签
        self.name_tag = Text(
            text=f'P{player_id}',
            parent=self,
            y=2.5,
            scale=15,
            origin=(0, 0),
            billboard=True
        )

        # 队伍颜色
        team_colors = {Team.RED: color.red, Team.BLUE: color.azure}
        self.color = team_colors[team]
        self.weapon.color = team_colors[team]

    def take_damage(self, damage, attacker):
        """受到伤害"""
        if self.state != PlayerState.ALIVE:
            return
        self.hp -= damage
        self.health_bar.world_scale_x = max(0, self.hp / self.max_hp * 1.5)

        if self.hp <= 0:
            self.die(attacker)

    def die(self, killer):
        """死亡处理"""
        self.state = PlayerState.DEAD
        self.deaths += 1
        killer.kills += 1
        # 通知计分系统
        game_manager.on_player_killed(killer, self)
        # 延迟重生
        invoke(self.respawn, delay=3.0)

    def respawn(self):
        """在基地重生"""
        self.hp = self.max_hp
        self.state = PlayerState.ALIVE
        self.position = self.spawn_position.copy()
        self.rotation = Vec3(0, 0, 0)
        self.health_bar.world_scale_x = 1.5

    def update(self):
        """每帧更新"""
        if self.state == PlayerState.ALIVE:
            self.update_health_bar()
            self.weapon.update()
```

### 3.2 人类玩家控制

```python
class HumanController:
    """人类玩家控制器"""
    def __init__(self, player):
        self.player = player
        self.move_speed = 8
        self.rotation_speed = 120

    def update(self):
        if self.player.state != PlayerState.ALIVE:
            return

        # 移动（复用 TPSMovementController 的坦克式移动）
        if held_keys['w']:
            self.move_forward()
        elif held_keys['s']:
            self.move_backward()
        if held_keys['a']:
            self.player.rotation_y -= self.rotation_speed * time.dt
        elif held_keys['d']:
            self.player.rotation_y += self.rotation_speed * time.dt

        # 射击
        if held_keys['left mouse']:
            shoot_dir = self.player.forward.normalized()
            self.player.weapon.shoot(shoot_dir)
```

### 3.3 AI 玩家控制

```python
class AIController:
    """AI 玩家控制器"""
    def __init__(self, player):
        self.player = player
        self.move_speed = 6          # AI 移动速度略低于人类
        self.rotation_speed = 90     # AI 旋转速度
        self.detection_range = 40    # 检测范围
        self.attack_range = 25       # 攻击范围
        self.patrol_points = []      # 巡逻点
        self.current_patrol_idx = 0
        self.state = 'patrol'        # patrol / chase / attack
        self.target = None

    def update(self):
        if self.player.state != PlayerState.ALIVE:
            return

        self.state_machine()

    def state_machine(self):
        """AI 状态机"""
        enemy = self.find_nearest_enemy()

        if enemy and distance(self.player.position, enemy.position) < self.attack_range:
            self.attack(enemy)
        elif enemy and distance(self.player.position, enemy.position) < self.detection_range:
            self.chase(enemy)
        else:
            self.patrol()

    def find_nearest_enemy(self):
        """找到最近的敌方玩家"""
        nearest = None
        min_dist = float('inf')
        for p in game_manager.players:
            if p.team != self.player.team and p.state == PlayerState.ALIVE:
                d = distance(self.player.position, p.position)
                if d < min_dist:
                    min_dist = d
                    nearest = p
        return nearest

    def attack(self, target):
        """攻击目标"""
        self.player.look_at_2d(target.position, 'y')
        shoot_dir = self.player.forward.normalized()
        # 添加轻微偏差，让 AI 不至于太精准
        spread = Vec3(
            random.uniform(-0.05, 0.05),
            random.uniform(-0.05, 0.05),
            random.uniform(-0.05, 0.05)
        )
        self.player.weapon.shoot(shoot_dir + spread)

    def chase(self, target):
        """追击目标"""
        self.player.look_at_2d(target.position, 'y')
        self.move_forward()

    def patrol(self):
        """巡逻行为"""
        if not self.patrol_points:
            self.generate_patrol_points()

        target = self.patrol_points[self.current_patrol_idx]
        self.player.look_at_2d(target, 'y')
        if distance(self.player.position, target) < 2:
            self.current_patrol_idx = (self.current_patrol_idx + 1) % len(self.patrol_points)
        self.move_forward()
```

### 3.4 角色选择系统

游戏开始前，人类玩家选择操控 1-4 号中的哪个角色。

```python
class CharacterSelect(Entity):
    """角色选择界面"""
    def __init__(self):
        super().__init__(parent=camera.ui)
        # 显示 4 个角色卡片
        self.cards = []
        for i in range(4):
            team = Team.RED if i < 2 else Team.BLUE
            card = Button(
                text=f'P{i+1}\n{team.value.upper()} TEAM',
                position=(-0.3 + i * 0.2, 0),
                scale=(0.18, 0.3),
                color=color.red if team == Team.RED else color.azure,
                on_click=Func(self.select_character, i)
            )
            self.cards.append(card)

        self.selected_id = None
        self.start_btn = Button(
            text='START',
            position=(0, -0.4),
            scale=(0.2, 0.05),
            color=color.green,
            enabled=False,
            on_click=self.start_match
        )

    def select_character(self, idx):
        self.selected_id = idx
        for i, card in enumerate(self.cards):
            card.highlight = Color(255, 255, 0, 100) if i == idx else Color.clear
        self.start_btn.enabled = True
```

---

## 4. 地图设计

### 4.1 地图布局（俯视图）

```
          Z+
          ↑
          │
   ┌──────┼──────┐
   │      │      │
   │  红队 │      │
   │  基地 │      │
   │  ●   │      │
   │      │      │
───┼──────┼──────┼─── X+
   │      │      │
   │      │  蓝队 │
   │      │  基地 │
   │      │  ●   │
   │      │      │
   └──────┼──────┘
          │
          │
          Z-
```

### 4.2 地图参数

| 参数 | 值 |
|------|-----|
| 地图总尺寸 | 64 × 64（与 v4 一致） |
| 红队基地位置 | (0, 0, -28)（Z 轴负方向） |
| 蓝队基地位置 | (0, 0, +28)（Z 轴正方向） |
| 对称轴 | X = 0 |
| 地面纹理 | grass, scale=(8, 8) |

### 4.3 地图结构

```python
class GameMap(Entity):
    """对称竞技地图"""
    def __init__(self):
        super().__init__()
        # 地面
        self.ground = Entity(
            model='plane', collider='box', scale=64,
            texture='grass', texture_scale=(8, 8)
        )

        # 红队基地
        self.red_base = Base(team=Team.RED, position=(0, 0, -28))
        # 蓝队基地
        self.blue_base = Base(team=Team.BLUE, position=(0, 0, 28))

        # 生成对称掩体
        self.generate_cover()
        # 生成边界墙
        self.generate_boundaries()

    def generate_cover(self):
        """生成对称掩体"""
        cover_positions = [
            # 左侧掩体
            (-12, 0, -10), (-12, 0, 10),
            # 右侧掩体
            (12, 0, -10), (12, 0, 10),
            # 中央掩体
            (-5, 0, 0), (5, 0, 0),
            # 中场长墙
            (-8, 0, -5), (8, 0, 5),
            # 基地前沿掩体
            (-4, 0, -18), (4, 0, -18),
            (-4, 0, 18), (4, 0, 18),
        ]
        for x, y, z in cover_positions:
            Entity(
                model='cube', origin_y=-.5,
                scale=(2, random.uniform(2, 3), 1),
                texture='brick', texture_scale=(1, 2),
                position=(x, y, z),
                collider='box',
                color=color.hsv(0, 0, random.uniform(.9, 1))
            )

    def generate_boundaries(self):
        """生成边界墙（不可见但可碰撞）"""
        wall_thickness = 1
        half_size = 32
        Entity(model='cube', scale=(half_size*2, 5, wall_thickness),
               position=(0, 2.5, -half_size), collider='box', color=color.clear)
        Entity(model='cube', scale=(half_size*2, 5, wall_thickness),
               position=(0, 2.5, half_size), collider='box', color=color.clear)
        Entity(model='cube', scale=(wall_thickness, 5, half_size*2),
               position=(-half_size, 2.5, 0), collider='box', color=color.clear)
        Entity(model='cube', scale=(wall_thickness, 5, half_size*2),
               position=(half_size, 2.5, 0), collider='box', color=color.clear)
```

### 4.4 基地设计

```python
class Base(Entity):
    """队伍基地（重生区域）"""
    def __init__(self, team, position):
        super().__init__(position=position)
        self.team = team
        self.spawn_position = position

        # 基地标志
        base_color = color.red if team == Team.RED else color.azure
        # 地面标记
        Entity(
            model='circle', scale=6, y=0.05,
            color=base_color, alpha=0.3
        )
        # 基地柱子
        for dx, dz in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
            Entity(
                model='cube', scale=(0.5, 5, 0.5),
                position=(dx, 0, dz),
                color=base_color, collider='box'
            )
        # 顶部横梁
        Entity(
            model='cube', scale=(5, 0.5, 5),
            position=(0, 5, 0),
            color=base_color
        )
        # 队伍名标签
        Text(
            text=f'{team.value.upper()} BASE',
            position=(0, 7),
            origin=(0, 0),
            scale=30,
            color=base_color,
            billboard=True
        )
```

---

## 5. 战斗系统

### 5.1 伤害与生命值

| 参数 | 值 | 说明 |
|------|-----|------|
| 玩家最大 HP | 100 | |
| 子弹伤害 | 10 | 每发 |
| 击杀所需子弹 | 10 发 | 理论值（连续命中） |
| 重生时间 | 3 秒 | 死亡后等待时间 |
| 重生 HP | 100 | 满血重生 |
| 射击冷却 | 0.15 秒 | 与 v4 一致 |

### 5.2 子弹碰撞判定（复用 Bullet 类）

```python
# 复用 fps_demo_v4 的 Bullet 类，需修改以下部分：

class Bullet(Entity):
    def __init__(self, start_position, direction, owner, damage=10, speed=35, **kwargs):
        # ... 原有代码 ...
        self.owner = owner  # 新增：发射者引用，用于判断队友

    def update(self):
        # ... 原有飞行和碰撞检测代码 ...

        if hit_info.hit:
            target = hit_info.entity
            # 不能伤害队友，也不能伤害自己
            if hasattr(target, 'team') and target.team != self.owner.team:
                target.take_damage(self.damage, self.owner)
                # 受击反馈
                original_color = target.color
                target.color = color.white
                target.animate_color(original_color, duration=0.1)
            self.on_hit(hit_info)
            destroy(self)
            return
```

### 5.3 重生保护

```python
# 重生后 2 秒无敌保护
def respawn(self):
    self.hp = self.max_hp
    self.state = PlayerState.RESPawning
    self.position = self.spawn_position.copy()
    self.rotation = Vec3(0, 0, 0)
    self.health_bar.world_scale_x = 1.5

    # 无敌闪烁效果
    self.invincible = True
    self.blink_timer = 0
    invoke(self.end_invincibility, delay=2.0)

def end_invincibility(self):
    self.invincible = False
    self.state = PlayerState.ALIVE
    self.color = self.original_color  # 恢复队伍颜色
```

---

## 6. 计分与胜负判定

### 6.1 计分规则

| 事件 | 分值 | 说明 |
|------|------|------|
| 击杀敌方 Player | +3 分 | 给击杀者所在队伍 |
| 被击杀 | 0 分 | 不扣分 |

### 6.2 计分系统

```python
class TeamScoreSystem(Entity):
    """队伍计分系统"""
    def __init__(self):
        super().__init__()
        self.scores = {Team.RED: 0, Team.BLUE: 0}

    def add_score(self, team, points):
        self.scores[team] += points
        self.update_ui()

    def update_ui(self):
        # 更新 HUD 显示
        score_text.text = (
            f'{color_to_hex(color.red)}RED: {self.scores[Team.RED]}   '
            f'{color_to_hex(color.azure)}BLUE: {self.scores[Team.BLUE]}'
        )
```

### 6.3 计时系统

```python
class MatchTimer(Entity):
    """比赛计时器"""
    def __init__(self, duration=300):  # 300 秒 = 5 分钟
        super().__init__()
        self.duration = duration
        self.remaining = duration
        self.is_running = False

    def start(self):
        self.is_running = True

    def update(self):
        if self.is_running and self.remaining > 0:
            self.remaining -= time.dt
            self.update_display()

            if self.remaining <= 0:
                self.end_match()

    def update_display(self):
        minutes = int(self.remaining) // 60
        seconds = int(self.remaining) % 60
        timer_text.text = f'{minutes:02d}:{seconds:02d}'

        # 最后 30 秒变红闪烁
        if self.remaining <= 30:
            timer_text.color = color.red if int(self.remaining * 2) % 2 == 0 else color.yellow
```

### 6.4 胜负判定

```python
def end_match(self):
    self.is_running = False
    red_score = self.scores[Team.RED]
    blue_score = self.scores[Team.BLUE]

    if red_score > blue_score:
        winner = "RED TEAM"
        winner_color = color.red
    elif blue_score > red_score:
        winner = "BLUE TEAM"
        winner_color = color.azure
    else:
        winner = "DRAW"
        winner_color = color.yellow

    # 显示结果画面
    result_text = Text(
        text=f'MATCH OVER!\n\n'
             f'RED: {red_score}  vs  BLUE: {blue_score}\n\n'
             f'WINNER: {winner}',
        position=(0, 0),
        origin=(0, 0),
        scale=3,
        color=winner_color,
        background=True
    )
```

---

## 7. AI 系统设计

### 7.1 AI 行为状态机

```
        [发现敌人]
 ┌──────────────────────┐
 │                      ↓
[PATROL] ──→ [CHASE] ──→ [ATTACK]
 ↑            ↑            │
 │            │            │
 └── [丢失目标] ←── [脱离射程]
```

| 状态 | 触发条件 | 行为 |
|------|----------|------|
| PATROL | 无敌人视野内 | 在预设巡逻点间移动 |
| CHASE | 敌人进入检测范围（40 单位） | 朝敌人移动 |
| ATTACK | 敌人进入攻击范围（25 单位） | 面向敌人射击 |

### 7.2 AI 难度分级

| 参数 | 简单 | 普通 | 困难 |
|------|------|------|------|
| 移动速度 | 5 | 6 | 7 |
| 旋转速度 | 60 | 90 | 120 |
| 射击精准度 | ±0.15 偏差 | ±0.05 偏差 | ±0.01 偏差 |
| 检测范围 | 25 | 40 | 50 |
| 反应延迟 | 0.5s | 0.2s | 0.05s |
| 射击频率 | 每隔 0.5s | 每隔 0.2s | 持续射击 |

### 7.3 AI 巡逻路径

每个 AI 在己方半场预设的巡逻点之间移动：

```python
def generate_patrol_points(self):
    """生成巡逻点（基于队伍基地位置）"""
    base = self.player.spawn_position
    z_sign = 1 if self.player.team == Team.RED else -1

    self.patrol_points = [
        Vec3(-10, 0, base.z + z_sign * 5),
        Vec3(10, 0, base.z + z_sign * 5),
        Vec3(-10, 0, base.z + z_sign * 15),
        Vec3(10, 0, base.z + z_sign * 15),
        Vec3(0, 0, base.z + z_sign * 10),
    ]
```

---

## 8. 相机与视角系统

### 8.1 视角方案

人类玩家使用 **TPS 视角** 作为主视角，复用 `fps_demo_v4` 的 `CameraController`，但做以下调整：

| 特性 | v4（当前） | Team Arena（调整后） |
|------|-----------|---------------------|
| 默认视角 | FPS | TPS |
| 相机距离 | 40 单位 | 15 单位（拉近） |
| 相机高度 | 15 单位 | 8 单位 |
| FOV | 60 | 55（更广角） |
| V 键功能 | FPS/TPS 切换 | TPS 近/远切换 |
| 射击方向 | `player.forward` | `player.forward`（不变） |

### 8.2 相机参数调整

```python
class CameraController(Entity):
    def __init__(self, target_entity):
        super().__init__()
        self.target = target_entity
        self.mode = CameraMode.THIRD_PERSON  # 默认 TPS
        self.camera_distance = 15            # 拉近距离
        self.camera_height = 8               # 降低高度
        self.transition_speed = 15           # 更快的跟随
```

### 8.3 被击杀时的相机处理

```python
def on_controlled_player_dead(self):
    """人类玩家被击杀时的相机处理"""
    # 相机切换为旁观模式，俯视地图
    camera.parent = scene
    camera.position = Vec3(0, 40, 0)
    camera.look_at(Vec3(0, 0, 0))
    camera.animate('fov', 45, duration=0.5)

    # 显示重生倒计时
    respawn_text = Text(
        text='RESPAWNING IN 3...',
        origin=(0, 0),
        scale=2,
        color=color.white,
        background=True
    )

    # 重生后恢复相机
    invoke(self.restore_camera, delay=3.0)

def restore_camera(self):
    """重生后恢复 TPS 相机"""
    camera_controller.set_third_person()
```

---

## 9. HUD（抬头显示）

### 9.1 HUD 布局

```
┌─────────────────────────────────────────────┐
│  [RED: 0] ──── 05:00 ──── [BLUE: 0]        │  ← 顶部：比分 + 时间
│                                             │
│                                             │
│                 游戏画面                      │
│                                             │
│                                             │
│  [HP ████████░░]  [K:0 D:0]  [P1 RED]      │  ← 底部：血条、战绩、身份
│          ○ 地面准星                          │  ← 中心：TPS 准星
└─────────────────────────────────────────────┘
```

### 9.2 HUD 元素实现

```python
# 比分板
score_text = Text(
    text='RED: 0    BLUE: 0',
    position=(0, 0.47),
    origin=(0, 0),
    scale=1.5,
    parent=camera.ui
)

# 倒计时
timer_text = Text(
    text='05:00',
    position=(0, 0.43),
    origin=(0, 0),
    scale=1.2,
    color=color.yellow,
    parent=camera.ui
)

# 玩家血条（底部中央）
player_hp_bg = Entity(
    parent=camera.ui, model='quad',
    position=(0, -0.35), scale=(0.4, 0.025),
    color=color.dark_gray
)
player_hp_bar = Entity(
    parent=camera.ui, model='quad',
    position=(0, -0.35), scale=(0.4, 0.02),
    color=color.green
)

# 击杀/死亡统计
stats_text = Text(
    text='K: 0  D: 0',
    position=(0, -0.42),
    origin=(0, 0),
    scale=1,
    parent=camera.ui
)

# 当前操控角色
identity_text = Text(
    text='P1 - RED TEAM',
    position=(-0.8, -0.42),
    scale=1,
    color=color.red,
    parent=camera.ui
)

# 地面准星（复用 v4 的 ground_crosshair）
ground_crosshair = Entity(
    model='circle', color=color.yellow,
    scale=1, y=0.1
)
```

### 9.3 击杀提示

```python
class KillFeed(Entity):
    """击杀播报"""
    def __init__(self):
        super().__init__(parent=camera.ui)
        self.messages = []  # 存储最近的击杀消息
        self.max_messages = 5

    def add_kill(self, killer_name, killer_team, victim_name, victim_team):
        msg = Text(
            text=f'{killer_name} [{killer_team.value}] → {victim_name} [{victim_team.value}]',
            position=(0.15, 0.2 - len(self.messages) * 0.04),
            scale=0.8,
            color=color.white,
            parent=camera.ui
        )
        self.messages.append(msg)
        # 5 秒后消失
        invoke(self.remove_message, msg, delay=5.0)

    def remove_message(self, msg):
        self.messages.remove(msg)
        destroy(msg)
        # 重新排列剩余消息
```

---

## 10. 游戏流程控制

### 10.1 GameManager 重构

```python
class GameManager(Entity):
    def __init__(self):
        super().__init__()
        self.state = GameState.MENU
        self.players = []
        self.human_player = None
        self.score_system = TeamScoreSystem()
        self.timer = MatchTimer(duration=300)
        self.camera_controller = None

    def start_match(self, selected_player_id):
        """开始比赛"""
        # 创建 4 个玩家
        red_spawn = Vec3(0, 0, -28)
        blue_spawn = Vec3(0, 0, 28)

        self.players = [
            Player(player_id=1, team=Team.RED, spawn_position=red_spawn + Vec3(-3, 0, 0)),
            Player(player_id=2, team=Team.RED, spawn_position=red_spawn + Vec3(3, 0, 0)),
            Player(player_id=3, team=Team.BLUE, spawn_position=blue_spawn + Vec3(-3, 0, 0)),
            Player(player_id=4, team=Team.BLUE, spawn_position=blue_spawn + Vec3(3, 0, 0)),
        ]

        # 设置人类/AI 控制器
        for i, player in enumerate(self.players):
            if i == selected_player_id:
                player.controller = HumanController(player)
                self.human_player = player
            else:
                player.controller = AIController(player)

        # 设置相机跟随人类玩家
        self.camera_controller = CameraController(self.human_player)
        camera_controller = self.camera_controller

        # 倒计时
        self.state = GameState.COUNTDOWN
        self.countdown(3)

    def countdown(self, seconds):
        if seconds > 0:
            countdown_text = Text(
                text=str(seconds), origin=(0, 0),
                scale=5, color=color.yellow
            )
            invoke(destroy, countdown_text, delay=1.0)
            invoke(self.countdown, seconds - 1, delay=1.0)
        else:
            self.state = GameState.PLAYING
            self.timer.start()

    def on_player_killed(self, killer, victim):
        """击杀事件处理"""
        self.score_system.add_score(killer.team, 3)

        # 如果人类玩家被杀
        if victim == self.human_player:
            self.on_controlled_player_dead()

        # 击杀播报
        kill_feed.add_kill(
            f'P{killer.player_id}', killer.team,
            f'P{victim.player_id}', victim.team
        )
```

---

## 11. 文件结构

```
team_arena.py              # 主入口（单文件架构，保持与 v4 一致）

# ========== 主要模块 ==========

# 1. 常量与枚举
Team, PlayerState, GameState, CameraMode

# 2. 实体类（复用）
Bullet, Weapon

# 3. 新实体类
Player           # 玩家角色
Base             # 队伍基地
GameMap          # 竞技地图

# 4. 控制器
HumanController  # 人类玩家输入
AIController     # AI 行为逻辑
CameraController # 相机系统（重构自 v4）

# 5. 系统管理器
TeamScoreSystem  # 计分系统
MatchTimer       # 比赛计时
KillFeed         # 击杀播报
GameManager      # 游戏主控

# 6. UI
CharacterSelect  # 角色选择界面
HUD              # 抬头显示

# 7. 主循环
update()
input(key)
```

---

## 12. 操作说明

### 12.1 按键映射

| 按键 | 功能 |
|------|------|
| W | 前进（沿玩家朝向） |
| S | 后退 |
| A | 左旋转 |
| D | 右旋转 |
| 鼠标左键 | 射击（按住连射） |
| V | TPS 远/近视角切换 |
| Tab | 编辑器模式（调试用） |
| Esc | 暂停/退出 |

### 12.2 开始游戏流程

1. 启动游戏 → 显示角色选择界面
2. 点击 P1-P4 任一卡片选择操控角色
3. 点击 START → 3 秒倒计时
4. 比赛开始 → 5 分钟对战
5. 时间到 → 显示结果 → 可重新开始

---

## 13. 实现计划

### Phase 1：基础框架（优先级最高）

- [ ] 定义枚举（Team, PlayerState, GameState）
- [ ] 创建 Player 类（HP、死亡、重生）
- [ ] 创建 GameMap（对称地图、基地、掩体）
- [ ] 创建 Base 类
- [ ] 创建 4 个 Player 实例（2 红 2 蓝）

### Phase 2：战斗系统

- [ ] 修改 Bullet 类，添加 `owner` 属性和友军伤害过滤
- [ ] 为每个 Player 绑定 Weapon
- [ ] 实现击杀判定和得分逻辑

### Phase 3：控制与 AI

- [ ] 实现 HumanController（TPS 坦克式移动 + 射击）
- [ ] 实现 AIController（状态机：巡逻/追击/攻击）
- [ ] 复用/调整 CameraController

### Phase 4：游戏流程

- [ ] 实现 GameManager（状态机：菜单/选择/倒计时/进行/结束）
- [ ] 实现 CharacterSelect 界面
- [ ] 实现 MatchTimer 和 TeamScoreSystem
- [ ] 实现胜负判定和结果画面

### Phase 5：UI 与体验

- [ ] 实现 HUD（比分、时间、血条、战绩）
- [ ] 实现 KillFeed（击杀播报）
- [ ] 实现重生保护（无敌闪烁）
- [ ] 实现死亡/重生过渡效果

### Phase 6：打磨优化

- [ ] AI 难度调优
- [ ] 地图平衡性测试
- [ ] 音效完善
- [ ] 性能优化
- [ ] 操作手感调优

---

## 14. 已知风险与应对

| 风险 | 影响 | 应对方案 |
|------|------|----------|
| AI 控制的 Player 同时射击导致性能问题 | FPS 下降 | 限制 AI 射击频率、优化 raycast |
| Bullet 大量堆积内存泄漏 | 崩溃 | 确保 destroy() 调用、添加子弹数量上限 |
| 友军伤害判定错误 | 游戏逻辑错误 | Bullet 添加 owner.team 检查 |
| 相机切换（死亡/重生）闪烁 | 体验差 | 平滑过渡动画、延迟切换 |
| 地图对称性不平衡 | 公平性问题 | 所有掩体镜像放置、测试验证 |

---

## 15. 扩展方向（未来版本）

- **多个难度等级**：简单/普通/困难 AI
- **武器拾取系统**：地图上随机刷新强力武器
- **回放系统**：记录比赛过程回放
- **小地图**：显示队友和敌人位置
- **技能系统**：每个角色拥有独特技能（冲刺、护盾等）
- **更多地图**：设计不同风格的竞技地图
- **网络多人**：从本地 AI 对战升级为在线多人
