# 新游戏规则设计方案

## 1. 规则变更概要

| # | 旧规则 | 新规则 |
|---|--------|--------|
| 1 | 击杀敌方 +3 分，时间到比分高者胜 | 击杀不加分，只迫使对方回基地重生 |
| 2 | 无限弹药 | 每人 10 发子弹，仅本方基地可装填 |
| 3 | 子弹伤害 10，射程 100，半径 0.1 | 子弹伤害 30（3倍），射程 5，半径 0.3（3倍） |
| 4 | 12 个掩体 | 4 个对称掩体 |
| 5 | 无目标物件 | 4 个 Goal 圆柱，7 次击中统计占领，每个 10 分 |

**新游戏目标**：占领地图上的 4 个 Goal 圆柱。比赛结束时，每占领一个 Goal 得 10 分，总分高者获胜。

---

## 2. 各模块改动详情

### 2.1 新增 `arena/goal.py` — Goal 圆柱实体

**当前状态**：无此模块，需新建。

```python
from ursina import *
from arena.constants import Team, Config


class Goal(Entity):
    """可占领的圆柱目标"""

    def __init__(self, goal_id, position, **kwargs):
        super().__init__(
            model='cylinder',
            position=Vec3(*position),
            scale=1.5,                 # 半径 1.5
            color=color.white,
            collider='sphere',
            **kwargs
        )
        self.goal_id = goal_id          # 1-4
        self.hit_history = []           # 最近 N 次命中的 Team 记录
        self.owner = None               # 当前占领方 Team / None
        self._hit_window = Config.GOAL_HIT_WINDOW  # 7

    def on_bullet_hit(self, team):
        """子弹命中时调用"""
        self.hit_history.append(team)
        if len(self.hit_history) > self._hit_window:
            self.hit_history.pop(0)
        self._update_owner()
        # 命中闪白反馈
        original = self.color
        self.color = color.white
        self.animate_color(original, duration=0.1)

    def _update_owner(self):
        """根据 hit_history 统计占领方"""
        red_count = self.hit_history.count(Team.RED)
        blue_count = self.hit_history.count(Team.BLUE)
        old_owner = self.owner
        if red_count > blue_count:
            self.owner = Team.RED
        elif blue_count > red_count:
            self.owner = Team.BLUE
        else:
            self.owner = None
        self._update_visual()
        # 占领方变化时通知比分系统更新
        if self.owner != old_owner:
            from arena.game_manager import game_manager
            game_manager.on_goal_owner_changed()

    def _update_visual(self):
        """根据占领方更新圆柱颜色"""
        if self.owner == Team.RED:
            self.color = color.red
        elif self.owner == Team.BLUE:
            self.color = color.azure
        else:
            self.color = color.white

    def reset(self):
        """重置占领状态"""
        self.hit_history.clear()
        self.owner = None
        self.color = color.white
```

**关键设计点**：
- `hit_history` FIFO 列表，最大长度 `Config.GOAL_HIT_WINDOW`（默认 7）
- 占领判定：红多→红占领，蓝多→蓝占领，相等→无人占领
- `collider='sphere'`：当前 Bullet 使用 `raycast` 碰撞检测，Goal 必须有 collider 才能被射线命中
- 占领方变化时通过 `game_manager.on_goal_owner_changed()` 通知比分系统实时更新
- 命中闪白反馈复用已有模式（与 `bullet.py:59-62` 命中玩家闪白一致）

**Goal 的 collider 选择**：
- `sphere`：最简单，Ursina 原生支持，与圆柱形状接近
- 不用 `box`：box 碰撞体是矩形，对圆柱命中判定不自然
- Goal 不需要 `collider` 参与物理碰撞（玩家不会推开 Goal），只需被 raycast 命中

---

### 2.2 `arena/bullet.py` — 子弹命中 Goal 判定 + 参数变更

**当前代码**（`bullet.py:47-71`）：
```python
if hit_info.hit:
    target = hit_info.entity
    hit_player = False
    if hasattr(target, 'team'):
        ...  # 友军过滤 + 命中敌方
    elif hasattr(target, 'hp'):
        ...  # 兼容旧逻辑
    self.on_hit(hit_info, hit_player=hit_player)
```

**改动 1 — 命中链新增 Goal 检测**：
```python
if hit_info.hit:
    target = hit_info.entity
    hit_player = False
    hit_goal = False

    # 优先检测 Goal（hasattr 避免循环导入）
    if hasattr(target, 'on_bullet_hit'):
        target.on_bullet_hit(self.owner.team)
        hit_goal = True
    elif hasattr(target, 'team'):
        ...  # 原有友军过滤逻辑不变
    elif hasattr(target, 'hp'):
        ...  # 原有兼容逻辑不变

    self.on_hit(hit_info, hit_player=hit_player, hit_goal=hit_goal)
```

**改动 2 — `on_hit` 新增 `hit_goal` 参数**：
```python
def on_hit(self, hit_info, hit_player=False, hit_goal=False):
    self.create_impact_effect(hit_info.world_point, hit_info.world_normal)
    from arena.sound_manager import sound_manager
    if hit_goal:
        sound_manager.play_hit_goal()
    elif hit_player:
        sound_manager.play_hit_player()
    else:
        sound_manager.play_hit_wall()
```

**改动 3 — 子弹参数变更**（通过 `game_settings.json` 配置，代码无需改动）：
- `bullet.max_distance`: 100 → 5
- `bullet.scale`: 0.1 → 0.3
- `weapon.bullet_damage`: 10 → 30

> **注意**：射程 5 意味着子弹在 5 个单位后自毁。当前 `bullet.py:34` 用 `distance(self.position, self.start_position) > self.max_distance` 判断，改为 5 后子弹飞行很短距离就会消失。这是期望行为——鼓励近战。

---

### 2.3 `arena/weapon.py` — 弹药系统

**当前代码**（`weapon.py:29-57`）：`shoot()` 只检查冷却，无限弹药。

**改动**：
```python
class Weapon(Entity):
    def __init__(self, owner, bullet_damage=10, bullet_speed=35, fire_rate=0.15, **kwargs):
        super().__init__(**kwargs)
        self.owner = owner
        self.bullet_damage = bullet_damage
        self.bullet_speed = bullet_speed
        self.fire_rate = fire_rate
        self.on_cooldown = False
        self.destroyed = False

        # 弹药系统（新增）
        self.max_ammo = Config.WEAPON_MAX_AMMO      # 10
        self.current_ammo = self.max_ammo

        # 枪口闪光（原有，不变）
        self.muzzle_flash = Entity(...)

    def shoot(self, target_direction=None):
        """开火"""
        if self.on_cooldown:
            return
        if self.current_ammo <= 0:          # 新增：弹药检查
            return

        self.current_ammo -= 1              # 新增：扣弹药

        # 以下原有逻辑不变...
        from arena.bullet import Bullet
        Bullet(...)
        self.muzzle_flash.enabled = True
        invoke(self._hide_muzzle_flash, delay=Config.MUZZLE_FLASH_DURATION)
        # 播放射击音效（原有，不变）
        ...
        self.on_cooldown = True
        invoke(self._end_cooldown, delay=self.fire_rate)

    def reload(self):                       # 新增
        """装填弹药（在基地内调用）"""
        self.current_ammo = self.max_ammo
```

**`destroyed` 字段**：当前代码中有 `self.last_fire_time = 0`（第17行），但实际未使用（冷却用 `invoke` 实现）。保持不变，不清理。

---

### 2.4 `arena/player.py` — 弹药可视化 + 基地装填 + 重生装填

**改动 1 — 弹药可视化**（在 `__init__` 血条下方新增）：
```python
# 弹药显示（血条下方）
self.ammo_text = Text(
    text='●' * self.weapon.max_ammo,
    parent=self,
    y=1.7,
    scale=8,
    origin=(0, 0),
    billboard=True,
    color=color.yellow
)
```

**改动 2 — 基地装填检测**（在 `update()` 中 ALIVE 分支内）：
```python
def update(self):
    ...
    if self.state == PlayerState.ALIVE and self.controller:
        # 基地装填检测（新增）
        self._check_base_reload()
        # 控制器逻辑（原有）
        result = self.controller.update()
        ...

def _check_base_reload(self):
    """在本方基地内自动装填弹药"""
    if self.weapon.current_ammo >= self.weapon.max_ammo:
        return
    from arena.game_manager import game_manager
    base_cfg = game_manager.map_data.get('red_base', {}) \
        if self.team == Team.RED \
        else game_manager.map_data.get('blue_base', {})
    base_pos = Vec3(*base_cfg.get('position', [0, 0, 0]))
    reload_radius = base_cfg.get('reload_radius', base_cfg.get('radius', 6))
    if distance(self.position, base_pos) < reload_radius:
        self.weapon.reload()
        self._update_ammo_display()
        # 播装填音效
        from arena.sound_manager import sound_manager
        sound_manager.play_reload()

def _update_ammo_display(self):
    """更新弹药显示"""
    ammo = self.weapon.current_ammo
    self.ammo_text.text = '●' * ammo + '○' * (self.weapon.max_ammo - ammo)
    self.ammo_text.color = color.yellow if ammo > 3 else color.red
```

**改动 3 — 重生时装填弹药**（在 `respawn()` 中）：
```python
def respawn(self):
    ...
    self.hp = self.max_hp
    self.health_bar.world_scale_x = 1.5
    self.health_bar.color = color.green
    self.weapon.reload()                # 新增：重生时装填弹药
    self._update_ammo_display()         # 新增：更新弹药显示
    ...
```

**改动 4 — 射击后更新弹药显示**：
在 `weapon.shoot()` 中扣弹药后，需要通知 Player 更新显示。有两种方案：
- **方案 A**：Player 在 `update()` 中每帧检查弹药数并更新 → 简单但有冗余
- **方案 B**：`weapon.shoot()` 扣弹药后调用 `self.owner._update_ammo_display()` → 精确但增加耦合

**推荐方案 A**：在 `_check_base_reload` 旁边加一个弹药变化检测，避免每帧更新 Text：
```python
def _update_ammo_display(self):
    """更新弹药显示（仅在实际变化时调用）"""
    new_text = '●' * self.weapon.current_ammo + '○' * (self.weapon.max_ammo - self.weapon.current_ammo)
    if self.ammo_text.text != new_text:
        self.ammo_text.text = new_text
        self.ammo_text.color = color.yellow if self.weapon.current_ammo > 3 else color.red
```

然后在 `update()` 的 ALIVE 分支中调用 `self._update_ammo_display()`。

---

### 2.5 `arena/game_manager.py` — 得分规则变更

**当前代码**（`game_manager.py:129-137`）：
```python
def on_player_killed(self, killer, victim):
    self.score_system.add_score(killer.team, Config.KILL_SCORE)  # 击杀加分
    if killer == self.human_player:
        sound_manager.play_kill()
        sound_manager.play_hit_goal()
    kill_feed.add_kill(...)
    if victim == self.human_player:
        self._on_human_dead()
```

**改动 1 — 删除击杀加分**：
```python
def on_player_killed(self, killer, victim):
    # 击杀不再加分（删除 add_score 调用）
    # 击杀音效保留（仍需反馈）
    if killer == self.human_player:
        sound_manager.play_kill()
    kill_feed.add_kill(...)
    if victim == self.human_player:
        self._on_human_dead()
```

**改动 2 — 新增 Goal 占领变化回调**：
```python
def on_goal_owner_changed(self):
    """Goal 占领方变化时更新实时比分"""
    self.score_system.update_from_goals(self.game_map.goals)
```

**改动 3 — 比赛结算从 Goal 计分**（`end_match()` 第155行起）：
```python
def end_match(self):
    self.state = GameState.MATCH_END
    self.timer.stop()
    sound_manager.play_match_end()

    # 从 Goal 计算结算分数（替代原有的 score_system.get_score）
    red_score = 0
    blue_score = 0
    for goal in self.game_map.goals:
        if goal.owner == Team.RED:
            red_score += Config.GOAL_SCORE
        elif goal.owner == Team.BLUE:
            blue_score += Config.GOAL_SCORE

    # 胜负判定逻辑不变，只是分值来源变了
    if red_score > blue_score:
        winner = "RED TEAM WINS!"
        winner_color = color.red
    ...
```

**改动 4 — Goal 在 game_map 中管理**（见 2.7），`game_manager` 通过 `self.game_map.goals` 访问。

---

### 2.6 `arena/score_system.py` — 新增从 Goal 更新分数

**当前代码**：`add_score(team, points)` 加分 + `update_ui()` 更新 HUD。

**改动 — 新增 `update_from_goals()` 方法**：
```python
def update_from_goals(self, goals):
    """从 Goal 占领状态更新实时分数"""
    from arena.constants import Config
    self.scores[Team.RED] = 0
    self.scores[Team.BLUE] = 0
    for goal in goals:
        if goal.owner == Team.RED:
            self.scores[Team.RED] += Config.GOAL_SCORE
        elif goal.owner == Team.BLUE:
            self.scores[Team.BLUE] += Config.GOAL_SCORE
    self.update_ui()
```

`add_score()` 保留但不再由击杀触发，可用于其他得分来源。`reset()` 不变。

---

### 2.7 `arena/game_map.py` — 新增 Goal 构建/销毁

**当前代码**：从 JSON 构建 ground + red_base + blue_base + cover + boundaries。

**改动 1 — 新增 Goal 构建**（`__init__` 中，cover 之后）：
```python
# Goal 圆柱（新增）
from arena.goal import Goal
self.goals = []
for i, g in enumerate(map_data.get('goals', [])):
    goal = Goal(goal_id=g.get('id', i+1), position=g['position'])
    self.goals.append(goal)
```

**改动 2 — Goal 销毁**（`destroy()` 中新增）：
```python
# 清理 Goal（新增）
for goal in self.goals:
    destroy(goal)
self.goals = []
```

**改动 3 — Base 记录 reload_radius**：
当前 `Base.__init__` 接收 `position, radius, pillars, pillar_height`。需新增 `reload_radius` 参数：
```python
class Base(Entity):
    def __init__(self, team, position, radius=6,
                 pillars=None, pillar_height=5,
                 reload_radius=None):      # 新增
        ...
        self.reload_radius = reload_radius or radius  # 默认等于视觉半径
```

`GameMap.__init__` 传参时新增：
```python
self.red_base = Base(
    team=Team.RED,
    position=red_cfg.get('position', [0, 0, -24]),
    radius=red_cfg.get('radius', 6),
    pillars=red_cfg.get('pillars'),
    pillar_height=red_cfg.get('pillar_height', 5),
    reload_radius=red_cfg.get('reload_radius'),  # 新增
)
```

> **注意**：`reload_radius` 不传则默认等于 `radius`，保持向后兼容。

---

### 2.8 `arena/ai_ctrl.py` — AI 行为重构

**当前代码**（`ai_ctrl.py`）：状态机只有 patrol/chase/attack 三种状态，主要问题：
- 无弹药感知，无限射击浪费子弹
- 无目标意识，不会主动射击 Goal
- 攻击时站立不动（`move_fwd: 0.0`），容易被击杀
- 射击前不做视线检测，可能朝掩体射击
- 巡逻点基于出生点，不会前往 Goal 区域
- 碰到障碍物只回避 1 秒，没有绕路逻辑

**新 AI 设计 — 6 状态机**：

```
            ┌─────────────────────────────────────┐
            │         弹药 == 0？                   │
            │            ↓ 是                      │
            │        ┌─────────┐                   │
            │        │ reload  │ ← 回基地装填       │
            │        └─────────┘                   │
            │            ↓ 装填完成                 │
            ├─────────────────────────────────────┤
            │   有可见 Goal 且在射程内？             │
            │            ↓ 是                      │
            │        ┌─────────┐                   │
            │        │shoot_goal│ ← 射击 Goal       │
            │        └─────────┘                   │
            ├─────────────────────────────────────┤
            │   有可见敌人？                        │
            │       ↓ 近距离       ↓ 远距离         │
            │   ┌─────────┐   ┌─────────┐          │
            │   │ attack  │   │ chase   │          │
            │   └─────────┘   └─────────┘          │
            ├─────────────────────────────────────┤
            │   无目标？                           │
            │       ↓                             │
            │   ┌─────────┐                        │
            │   │ patrol  │ ← 优先前往未占领 Goal   │
            │   └─────────┘                        │
            └─────────────────────────────────────┘
```

#### 2.8.1 完整状态机代码

```python
def _state_machine(self):
    """新 AI 行为状态机（6 状态：reload / shoot_goal / attack / chase / patrol / avoid）"""
    my_pos = (self.player.x, self.player.y, self.player.z)

    # ---- 1. 弹药耗尽 → 强制回基地 ----
    if self.player.weapon.current_ammo <= 0:
        return self._reload()

    # ---- 2. 碰撞回避（最高优先级，已存在） ----
    # （在 update() 中已处理，此处不重复）

    # ---- 3. 射击 Goal（优先级高于射击敌人） ----
    goal_target = self._find_shootable_goal()
    if goal_target:
        return self._shoot_goal(goal_target)

    # ---- 4. 射击敌人 ----
    enemy = self._find_nearest_visible_enemy()
    if enemy:
        enemy_pos = (enemy.position.x, enemy.position.y, enemy.position.z)
        d = dist_3d(my_pos, enemy_pos)
        if d < self.attack_range:
            return self._attack(enemy)
        elif d < self.detection_range:
            return self._chase(enemy)

    # ---- 5. 巡逻（优先前往未占领 Goal） ----
    return self._patrol()
```

#### 2.8.2 视线检测（LOS）

**核心改进**：射击前检测视线，避免朝掩体射击。

```python
def _has_line_of_sight(self, target_pos):
    """检测从自身到目标位置是否有视线（纯计算，使用 game_manager 的 raycast）"""
    my_pos = self.player.position + Vec3(0, 1, 0)  # 玩家腰部高度
    direction = target_pos - my_pos
    d = direction.length()
    if d < 0.1:
        return True
    # raycast: 如果命中了非目标物体（掩体/墙），则无视线
    from ursina import raycast
    hit = raycast(my_pos, direction.normalized(), distance=d,
                  ignore=(self.player,), debug=False)
    if hit.hit and dist_3d(
        (my_pos.x, my_pos.y, my_pos.z),
        (hit.world_point.x, hit.world_point.y, hit.world_point.z)
    ) < d - 0.5:  # 命中点比目标近 → 被遮挡
        return False
    return True
```

> **注意**：`_has_line_of_sight` 调用 `raycast`，但 `AIController.update()` 返回的决策字典由 `_apply_ai_command` 执行时也调用 `raycast`。为避免每帧多次 raycast 影响性能，可用一个简化版本：仅检测到目标的方向上是否有 cover 实体。但简化方案难以实现。**折中方案**：仅在射击决策时做 LOS 检测（不是每帧），且缓存结果 0.2 秒。

```python
def _has_line_of_sight(self, target_pos):
    """检测视线（带缓存，避免频繁 raycast）"""
    now = time.time()
    cache_key = (round(target_pos.x, 1), round(target_pos.z, 1))
    if hasattr(self, '_los_cache') and self._los_cache.get(cache_key, (0, False))[0] > now - 0.2:
        return self._los_cache[cache_key][1]

    my_pos = self.player.position + Vec3(0, 1, 0)
    direction = (target_pos - my_pos)
    d = direction.length()
    if d < 0.1:
        result = True
    else:
        from ursina import raycast
        hit = raycast(my_pos, direction.normalized(), distance=d,
                      ignore=(self.player,), debug=False)
        result = not hit.hit or (hit.distance >= d - 0.5)

    if not hasattr(self, '_los_cache'):
        self._los_cache = {}
    self._los_cache[cache_key] = (now, result)
    return result
```

#### 2.8.3 射击 Goal 状态

```python
def _find_shootable_goal(self):
    """找到最近的可见且值得射击的 Goal"""
    from arena.game_manager import game_manager
    goals = getattr(game_manager.game_map, 'goals', [])
    my_pos = (self.player.x, self.player.y, self.player.z)
    best = None
    best_dist = float('inf')

    for goal in goals:
        # 优先射击：未占领 > 敌方占领 > 己方占领（己方已占领的不射击）
        if goal.owner == self.player.team:
            continue  # 己方已占领，不需要射击

        goal_pos = goal.position
        d = dist_3d(my_pos, (goal_pos.x, goal_pos.y, goal_pos.z))

        # 射程检测（子弹射程只有 5，需靠近才能射击）
        if d > Config.BULLET_MAX_DISTANCE * 1.5:  # 留余量，先接近
            continue

        # 视线检测
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
        'move_fwd': 0.3,  # 缓慢接近（不像攻击敌人时站立不动）
        'request_raycast': True,
        'shoot_dir': None,
    }

    # 射击节流（弹药宝贵，间隔稍长）
    if time.time() - self.last_shoot_time > self.shoot_interval * 1.5:
        fwd = self.player.forward.normalized()
        spread = (
            random.uniform(-self.shoot_spread * 0.5, self.shoot_spread * 0.5),
            random.uniform(-self.shoot_spread * 0.5, self.shoot_spread * 0.5),
            random.uniform(-self.shoot_spread * 0.5, self.shoot_spread * 0.5),
        )
        # Goal 是固定目标，散布减半提高精度
        shoot_dir = (fwd.x + spread[0], fwd.y + spread[1], fwd.z + spread[2])
        result['shoot_dir'] = shoot_dir
        self.last_shoot_time = time.time()

    return result
```

#### 2.8.4 可见敌人检测（替代 `_find_nearest_enemy`）

```python
def _find_nearest_visible_enemy(self):
    """找到最近的可见敌方玩家（增加了视线检测）"""
    from arena.game_manager import game_manager
    nearest = None
    min_dist = float('inf')
    my_pos = (self.player.x, self.player.y, self.player.z)
    for p in game_manager.players:
        if p.team != self.player.team and p.state.value == 'alive':
            p_pos = (p.position.x, p.position.y, p.position.z)
            d = dist_3d(my_pos, p_pos)
            # 距离过滤
            if d > self.detection_range:
                continue
            # 视线检测（仅在攻击范围内才做，减少 raycast 开销）
            if d < self.attack_range and not self._has_line_of_sight(p.position + Vec3(0, 1, 0)):
                continue
            if d < min_dist:
                min_dist = d
                nearest = p
    return nearest
```

#### 2.8.5 改进的攻击状态

**当前问题**：攻击时 `move_fwd: 0.0`（站立不动），容易被击杀。

**改进**：攻击时横向移动（侧步走位），增加生存率：

```python
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
    if not hasattr(self, '_strafe_dir'):
        self._strafe_dir = 1 if random.random() > 0.5 else -1
        self._strafe_change_time = time.time() + random.uniform(1.0, 2.5)

    if time.time() > self._strafe_change_time:
        self._strafe_dir *= -1
        self._strafe_change_time = time.time() + random.uniform(1.0, 2.5)

    # 射击节流（弹药宝贵，提高间隔）
    effective_interval = self.shoot_interval
    if self.player.weapon.current_ammo <= 3:
        effective_interval = self.shoot_interval * 2  # 弹药少时更谨慎

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

    # 侧步移动（通过 rotate_y 模拟横移）
    result['rotate_y'] = self._strafe_dir * self.rotation_speed * 0.3 / 60
    result['move_fwd'] = 0.3  # 微向前，保持距离

    return result
```

#### 2.8.6 回基地装填状态

```python
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
```

#### 2.8.7 改进的巡逻状态

**当前问题**：巡逻点基于出生点，不前往 Goal。

**改进**：优先前往未占领/敌方占领的 Goal：

```python
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

    # 优先级：未占领 > 敌方占领 > 己方占领
    priority_goals = [g for g in goals if g.owner != self.player.team]
    own_goals = [g for g in goals if g.owner == self.player.team]

    # 按优先级排序的 Goal 位置
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
```

#### 2.8.8 AI 新增配置

```json
"ai": {
    "shoot_interval": 0.4,
    "low_ammo_threshold": 3,
    "strafe_enabled": true,
    "los_check_enabled": true,
    "goal_shoot_spread_multiplier": 0.5
}
```

| 配置 | 说明 | 默认值 |
|------|------|--------|
| `shoot_interval` | 射击间隔（弹药宝贵，从 0.2 提高到 0.4） | 0.4 |
| `low_ammo_threshold` | 低弹药阈值（低于此值加倍射击间隔） | 3 |
| `strafe_enabled` | 攻击时是否侧步走位 | true |
| `los_check_enabled` | 是否做视线检测（避免射击掩体） | true |
| `goal_shoot_spread_multiplier` | 射击 Goal 时的散布倍率（0.5 = 减半） | 0.5 |

---

### 2.8 AI 行为优先级总结

| 优先级 | 状态 | 触发条件 | 行为 |
|--------|------|----------|------|
| 1 | `avoid` | 前方碰撞（已存在） | 回避 1 秒 |
| 2 | `reload` | `current_ammo == 0` | 回基地装填 |
| 3 | `shoot_goal` | 可见未占领/敌方 Goal 在射程 1.5 倍内 | 射击 Goal（散布减半） |
| 4 | `attack` | 可见敌人在 `attack_range` 内 | 射击敌人 + 侧步走位 |
| 5 | `chase` | 可见敌人在 `detection_range` 内 | 追击敌人 |
| 6 | `patrol` | 无目标 | 前往未占领 Goal 巡逻 |

---

### 2.9 `arena/hud.py` — 弹药显示 + Goal 状态

**当前代码**：HUD 有 score_text、timer_text、hp_bg/hp_bar、stats_text、identity_text、ground_crosshair、controls_text。

**改动 1 — 新增弹药显示**（`create()` 中，hp_bar 下方）：
```python
# 弹药显示（血条下方）
self.ammo_text = Text(
    text='AMMO: 10/10',
    position=(0, -0.39),
    origin=(0, 0),
    scale=1,
    color=color.yellow,
    parent=camera.ui
)
```

**改动 2 — `update_player_info()` 中更新弹药**：
```python
def update_player_info(self, player):
    if not player:
    return
    ...  # 原有逻辑不变
    # 弹药（新增）
    if hasattr(player, 'weapon') and hasattr(player.weapon, 'current_ammo'):
        ammo = player.weapon.current_ammo
        max_ammo = player.weapon.max_ammo
        self.ammo_text.text = f'AMMO: {ammo}/{max_ammo}'
        self.ammo_text.color = color.yellow if ammo > 3 else color.red
```

**改动 3 — 新增 Goal 占领状态显示**（可选，在比分旁）：
```python
# Goal 占领状态（比分下方）
self.goal_status_text = Text(
    text='● ○ ● ○',  # 4 个 Goal 状态
    position=(0, 0.40),
    origin=(0, 0),
    scale=1,
    parent=camera.ui
)
```

更新逻辑在 `score_system.update_ui()` 或 `game_manager.on_goal_owner_changed()` 中。

**改动 4 — stats_text 改为显示弹药/KD**：
当前显示 `K: 0  D: 0`。新规则下击杀仍统计，但意义降低。可改为 `K: 0  D: 0  AMMO: 10`，或保留 KD 显示在 ammo_text 单独显示弹药。

**改动 5 — `destroy()` 中新增清理**：
```python
for attr in ('score_text', 'timer_text', 'hp_bg', 'hp_bar',
             'stats_text', 'identity_text', 'controls_text',
             'ground_crosshair', 'ammo_text', 'goal_status_text'):  # 新增
```

---

### 2.10 `arena/constants.py` / `game_settings.json` — 配置变更

**新增/变更配置项**：

```json
{
    "weapon": {
        "bullet_damage": 30,
        "max_ammo": 10
    },
    "bullet": {
        "max_distance": 5,
        "scale": 0.3
    },
    "match": {
        "kill_score": 0,
        "goal_score": 10,
        "goal_hit_window": 7
    }
}
```

**`constants.py` Config 新增属性**：
```python
# 武器（新增）
WEAPON_MAX_AMMO = _settings['weapon'].get('max_ammo', 10)

# 比赛（新增）
GOAL_SCORE = _settings['match'].get('goal_score', 10)
GOAL_HIT_WINDOW = _settings['match'].get('goal_hit_window', 7)
```

> **注意**：`weapon.max_ammo` 和 `match.goal_score`、`match.goal_hit_window` 在当前 `_DEFAULTS` 中不存在，需新增。使用 `.get()` 并提供默认值保持向后兼容。

**变更 `_DEFAULTS` 字典**：
```python
'weapon': {'bullet_damage': 30, 'bullet_speed': 35, 'fire_rate': 0.15,
           'muzzle_flash_duration': 0.05, 'max_ammo': 10},
'bullet': {'max_distance': 5, 'scale': 0.3, 'speed_multiplier': 1.5},
'match': {'duration': 300, 'kill_score': 0, 'timer_warning_seconds': 30,
          'goal_score': 10, 'goal_hit_window': 7},
```

---

### 2.11 `maps/arena_classic.json` — 地图布局变更

```json
{
    "name": "Arena Classic",
    "version": 2,
    "ground": {
        "size": 64,
        "texture": "grass",
        "texture_scale": [8, 8]
    },
    "red_base": {
        "position": [0, 0, -24],
        "radius": 6,
        "reload_radius": 6,
        "pillars": [[-2, -2], [2, -2], [-2, 2], [2, 2]],
        "pillar_height": 5
    },
    "blue_base": {
        "position": [0, 0, 24],
        "radius": 6,
        "reload_radius": 6,
        "pillars": [[-2, -2], [2, -2], [-2, 2], [2, 2]],
        "pillar_height": 5
    },
    "goals": [
        {"id": 1, "position": [-8, 1.5, -8]},
        {"id": 2, "position": [8, 1.5, -8]},
        {"id": 3, "position": [-8, 1.5, 8]},
        {"id": 4, "position": [8, 1.5, 8]}
    ],
    "cover": [
        {"position": [-8, 0, 0], "scale": [2, 2.5, 1]},
        {"position": [8, 0, 0], "scale": [2, 2.5, 1]},
        {"position": [0, 0, -8], "scale": [2, 2.5, 1]},
        {"position": [0, 0, 8], "scale": [2, 2.5, 1]}
    ],
    "boundary": {
        "thickness": 1,
        "height": 5
    }
}
```

**Goal 位置设计**：
- 4 个 Goal 对称分布在 4 象限，距中心约 11 单位
- y=1.5：圆柱中心高度，使底部贴地（scale=1.5 时圆柱高 3，中心 y=1.5 → 底部 y=0）
- 距两方基地各约 20 单位，需要离开基地冒险

---

### 2.12 `arena/kill_feed.py` — 保留但弱化

**当前状态**：右上角击杀播报。

**改动**：
- 击杀仍触发播报（被击杀仍需视觉反馈），但不关联得分
- 新增 Goal 占领变化播报（可选）：
```python
def add_goal_capture(self, team_name, goal_id):
    """Goal 占领变化播报"""
    msg = Text(
        text=f'{team_name} captured Goal {goal_id}!',
        ...
    )
```

---

### 2.13 `arena/sound_manager.py` — 装填音效（已实现）

当前 `play_reload()` 已实现，复用 `match_start.mp3`。无需额外改动。

---

## 3. 文件改动清单

| 文件 | 类型 | 改动点 |
|------|------|--------|
| `arena/goal.py` | **新增** | Goal 圆柱实体（碰撞、7次命中统计、占领判定、视觉更新、占领变化回调） |
| `arena/bullet.py` | 修改 | 命中链新增 Goal 检测（`hasattr(target, 'on_bullet_hit')`）；`on_hit` 新增 `hit_goal` 参数 |
| `arena/weapon.py` | 修改 | 新增 `max_ammo`/`current_ammo`/`reload()`；`shoot()` 扣弹药 + 弹药检查 |
| `arena/player.py` | 修改 | 新增 `ammo_text` 弹药显示；`_check_base_reload()` 基地装填；`_update_ammo_display()`；`respawn()` 装填弹药 |
| `arena/game_manager.py` | 修改 | 删除击杀加分；新增 `on_goal_owner_changed()`；`end_match()` 从 Goal 计分 |
| `arena/game_map.py` | 修改 | 新增 Goal 构建/销毁；Base 传参新增 `reload_radius` |
| `arena/base.py` | 修改 | `__init__` 新增 `reload_radius` 参数 |
| `arena/score_system.py` | 修改 | 新增 `update_from_goals()` 方法 |
| `arena/hud.py` | 修改 | 新增弹药显示、Goal 状态显示；`destroy()` 新增清理 |
| `arena/ai_ctrl.py` | 修改 | 6状态机重构：reload/shoot_goal/attack/chase/patrol/avoid；视线检测；侧步走位；Goal 优先巡逻 |
| `arena/constants.py` | 修改 | `_DEFAULTS` 新增字段；Config 新增 `WEAPON_MAX_AMMO`/`GOAL_SCORE`/`GOAL_HIT_WINDOW` |
| `game_settings.json` | 修改 | 子弹参数变更；新增 `weapon.max_ammo`/`match.goal_score`/`match.goal_hit_window` |
| `maps/arena_classic.json` | 修改 | cover 减为 4 个；新增 `goals` 数组；base 新增 `reload_radius` |
| `arena/sound_manager.py` | ✓ 已完成 | `play_reload()` 已实现 |
| `arena/kill_feed.py` | 可选 | 新增 Goal 占领播报 |

---

## 4. 实施步骤

### Phase 1：子弹参数 + 弹药系统

1. `game_settings.json`：`bullet_damage: 30`、`max_distance: 5`、`scale: 0.3`、新增 `weapon.max_ammo: 10`
2. `constants.py`：`_DEFAULTS` 更新，Config 新增 `WEAPON_MAX_AMMO`
3. `weapon.py`：新增 `current_ammo`/`max_ammo`/`reload()`，`shoot()` 扣弹药 + 弹药检查
4. `player.py`：新增 `ammo_text`、`_check_base_reload()`、`_update_ammo_display()`、`respawn()` 装填
5. `base.py`：新增 `reload_radius` 参数
6. `game_map.py`：Base 传参新增 `reload_radius`
7. `hud.py`：新增 `ammo_text`，`update_player_info()` 更新弹药，`destroy()` 清理

**验证点**：每人 10 发子弹，打完不能射击，回基地自动装填+音效，弹药显示正确。

### Phase 2：Goal 圆柱

8. `arena/goal.py`：新建 Goal 实体
9. `bullet.py`：命中链新增 Goal 检测，`on_hit` 新增 `hit_goal` 参数
10. `game_map.py`：从 JSON 构建 Goal，`destroy()` 清理 Goal
11. `maps/arena_classic.json`：新增 `goals` 数组，cover 减为 4 个

**验证点**：4 个圆柱出现，子弹命中后颜色变化，占领判定正确。

### Phase 3：得分规则变更

12. `game_settings.json`：`kill_score: 0`，新增 `goal_score: 10`、`goal_hit_window: 7`
13. `constants.py`：Config 新增 `GOAL_SCORE`/`GOAL_HIT_WINDOW`
14. `game_manager.py`：删除击杀加分，新增 `on_goal_owner_changed()`，`end_match()` 从 Goal 计分
15. `score_system.py`：新增 `update_from_goals()`

**验证点**：击杀不加分，Goal 占领变化实时反映在比分上，比赛结束正确结算。

### Phase 4：AI 重构

16. `ai_ctrl.py`：6 状态机重构（reload / shoot_goal / attack / chase / patrol / avoid）
17. `ai_ctrl.py`：视线检测 `_has_line_of_sight()`（避免射击掩体）
18. `ai_ctrl.py`：Goal 优先射击 `_find_shootable_goal()` + `_shoot_goal()`
19. `ai_ctrl.py`：侧步走位攻击 `_attack()` 改进
20. `ai_ctrl.py`：巡逻点改为优先未占领 Goal `_generate_patrol_points()`
21. `game_settings.json`：AI 新增配置项（`shoot_interval: 0.4` 等）

**验证点**：AI 弹药耗尽后回基地装填，优先射击 Goal 而非敌人，不朝掩体射击，攻击时侧步走位。

### Phase 5：测试调优

18. 手动测试：弹药系统、Goal 占领、基地装填
19. AI 行为测试：弹药管理、Goal 意识
20. 参数调优：Goal 位置、掩体布局、弹药数量、子弹射程
21. 地图平衡性测试：红蓝双方是否对称公平

---

## 5. 核心交互流程

### 5.1 弹药流程

```
玩家射击 → weapon.current_ammo -= 1 → player._update_ammo_display()
    ↓
current_ammo == 0 → weapon.shoot() 直接 return → 无法射击
    ↓
玩家进入本方基地范围（distance < reload_radius）
    ↓
player._check_base_reload() → weapon.reload() → current_ammo = max_ammo
    ↓
sound_manager.play_reload()（复用 match_start.mp3）
    ↓
player._update_ammo_display() → 弹药显示恢复满
```

### 5.2 Goal 占领流程

```
子弹命中 Goal → bullet.py 检测 hasattr(target, 'on_bullet_hit')
    ↓
goal.on_bullet_hit(self.owner.team)
    ↓
hit_history.append(team)，超 7 个则 pop(0)
    ↓
_update_owner()：统计红蓝命中次数，多者占领
    ↓
占领方变化 → game_manager.on_goal_owner_changed()
    ↓
score_system.update_from_goals(goals) → HUD 比分实时更新
    ↓
_update_visual()：圆柱变占领方颜色 + 命中闪白
```

### 5.3 比赛结算流程

```
倒计时归零 → match_timer → game_manager.end_match()
    ↓
遍历 self.game_map.goals → 每个 goal.owner 得 Config.GOAL_SCORE (10) 分
    ↓
red_score / blue_score 比较 → 判定胜负
    ↓
显示结果 UI（RESTART 按钮）
```

---

## 6. Goal 圆柱视觉设计

```
     ┌───┐
     │   │  ← 圆柱体，scale=1.5（半径1.5，高3）
     │   │
     │   │  ← 颜色随占领方变化：
     └───┘     无人占领 = 白色
      ││       红方占领 = 红色
  ────┴┴────   蓝方占领 = 蓝色
  地面         ← 命中时短暂闪白（0.1s）
```

- 模型：`model='cylinder'`（Ursina 内置）
- 碰撞体：`collider='sphere'`（被 raycast 命中）
- 位置：`position=[x, 1.5, z]`，底部贴地
- 不需要 `origin_y` 调整（cylinder 默认中心在原点）

**Ursina cylinder 模型注意**：Ursina 的 `cylinder` 模型可能不可用（取决于版本）。如果运行时报错，降级方案：
```python
# 降级方案：用 cube 近似圆柱
model='cube', scale=(1.5, 3, 1.5), origin_y=-0.5
```

---

## 7. 新地图布局示意

```
               Z+
               │
          BLUE BASE (0,0,24)
               │
    ┌──────────┼──────────┐
    │          │          │
    │  Goal①   │  Goal②   │
    │ (-8,-8)  │ (8,-8)   │
    │          │          │
    │     ┌──┐ │ ┌──┐     │
    │     │C3│ │ │C4│     │  C = Cover
    │     └──┘ │ └──┘     │
    │          │          │
────┤    ┌──┐  │  ┌──┐    ├──── X-
    │    │C1│──┼──│C2│    │
────┤    └──┘  │  └──┘    ├──── X+
    │          │          │
    │  Goal③   │  Goal④   │
    │ (-8,8)   │ (8,8)    │
    │          │          │
    └──────────┼──────────┘
               │
          RED BASE (0,0,-24)
               │
               Z-

坐标系：X 轴左右，Z 轴前后（负=红方半场，正=蓝方半场）
Goal 位置：4 象限对称，距中心 ≈11 单位
Cover 位置：4 个对称掩体，分布在中场十字区域
```
