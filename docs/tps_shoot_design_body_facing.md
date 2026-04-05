# 第三人称射击设计：方向跟随本体

## 1. 问题背景

当前 fps_demo_v3 的第三人称射击存在问题：
- 射击方向使用 `camera.forward`（相机视线方向）
- 玩家本体（橘色方块）有自己的朝向 `player.forward`
- 两者不一致，导致视觉上子弹方向和玩家朝向不匹配

## 2. 核心问题分析

### 2.1 当前实现

```python
def get_shoot_direction(self):
    if self.mode == CameraMode.FIRST_PERSON:
        return camera.forward
    else:
        # TPS 模式：从枪口向相机前方射击
        target_point = camera.world_position + camera.forward * 100
        return (target_point - gun.world_position).normalized()
```

**问题**：
- 射击方向完全由相机视角决定
- 玩家本体（橘色方块）的朝向被忽略
- 玩家面朝北，子弹却向东飞 → 视觉不协调

### 2.2 两种射击模式对比

| 特性 | 方向跟随视角（当前） | 方向跟随本体（目标） |
|------|---------------------|---------------------|
| **射击方向** | `camera.forward` | `player.forward` |
| **操作方式** | 鼠标瞄准相机方向 | 键盘旋转玩家方向 |
| **瞄准方式** | 鼠标指向敌人即可 | 需要转身面对敌人 |
| **视觉一致性** | ❌ 玩家和子弹方向不一致 | ✅ 玩家和子弹方向一致 |
| **操作难度** | ⭐ 简单 | ⭐⭐⭐ 需要转身 |
| **游戏类型** | 街机射击 | 动作游戏/RPG |
| **典型游戏** | Gears of War, 荒野大镖客 | 黑暗之魂, 生化危机 |

### 2.3 视觉效果对比

**当前（方向跟随视角）**：
```
     相机（高处，俯视）
         ↓
    ┌─────────┐
    │   🎯    │  ← 相机看向东边
    └─────────┘

    [橘色方块] ← 玩家面朝北
         ↑
      子弹向东飞
```
**问题**：玩家面朝北，子弹却向东飞，很奇怪！

**目标（方向跟随本体）**：
```
     相机（高处，俯视）
         ↓
    ┌─────────┐
    │   🎯    │  ← 敌人在东边
    └─────────┘

    [橘色方块] →
         ↑
      子弹向东飞（和玩家朝向一致）
```
**改进**：玩家需要转身面朝东边，子弹也向东飞，视觉一致！

## 3. 设计方案

### 3.1 核心修改

```python
def get_shoot_direction(self):
    """获取射击方向"""
    if self.mode == CameraMode.FIRST_PERSON:
        return camera.forward
    else:
        # TPS 模式：从枪口向玩家前方射击（方向跟随本体）
        target_point = player.position + player.forward * 100
        return (target_point - gun.world_position).normalized()
```

**关键改动**：
- `camera.forward` → `player.forward`
- `camera.world_position` → `player.position`

### 3.2 玩家旋转控制

由于玩家需要旋转来瞄准，需要添加玩家旋转控制：

#### 方案 A：使用 Q/E 键旋转

```python
def input(key):
    if key == 'q':
        player.rotation_y -= 90
    elif key == 'e':
        player.rotation_y += 90
```

#### 方案 B：使用 A/D 键 + 鼠标（推荐）

```python
def input(key):
    if key == 'a' or key == 'd':
        # A/D 键控制左右旋转
        rotation_speed = 100
        if key == 'a':
            player.rotation_y -= rotation_speed * time.dt
        elif key == 'd':
            player.rotation_y += rotation_speed * time.dt
```

#### 方案 C：鼠标右键旋转视角（类似 Moba）

```python
def update():
    if mouse.right:
        player.rotation_y += mouse.velocity[0] * 100
```

### 3.3 相机行为设计

#### 方案 A：固定跟随相机（简单）

```python
def update_camera(self):
    """更新第三人称相机位置"""
    # 相机始终在玩家身后固定位置
    target_position = self.target.position + self.tps_offset
    camera.position = lerp(camera.position, target_position, self.transition_speed * time.dt)
    
    # 相机看向玩家
    look_target = self.target.position + Vec3(0, 1.5, 0)
    camera.look_at(look_target)
```

#### 方案 B：自由旋转相机（复杂但灵活）

```python
def update_camera(self):
    """更新第三人称相机位置"""
    # 根据玩家旋转计算相机位置
    # 相机围绕玩家旋转
    angle = radians(self.target.rotation_y)
    x_offset = sin(angle) * self.camera_distance
    z_offset = -cos(angle) * self.camera_distance
    
    target_position = self.target.position + Vec3(x_offset, self.camera_height, z_offset)
    camera.position = lerp(camera.position, target_position, self.transition_speed * time.dt)
    
    # 相机看向玩家
    camera.look_at(self.target.position + Vec3(0, 1.5, 0))
```

### 3.4 准星设计

#### 方案 A：固定屏幕中心准星

```python
crosshair = Entity(
    parent=camera.ui,
    model='quad',
    scale=0.02,
    color=color.white,
    texture='circle'
)
```

**问题**：准星指向相机方向，而不是玩家方向，会产生误导

#### 方案 B：玩家朝向指示器（推荐）

```python
# 在玩家头顶显示箭头指示当前朝向
direction_arrow = Entity(
    parent=player,
    model='arrow',
    scale=0.5,
    y=2,
    color=color.yellow
)

# 在屏幕显示玩家朝向
direction_text = Text(
    parent=camera.ui,
    text='Facing: N',
    position=(0, 0.4),
    origin=(0, 0),
    color=color.yellow
)

def update():
    # 根据玩家朝向显示方向
    angle = player.rotation_y % 360
    if 315 <= angle or angle < 45:
        direction_text.text = 'Facing: North'
    elif 45 <= angle < 135:
        direction_text.text = 'Facing: East'
    elif 135 <= angle < 225:
        direction_text.text = 'Facing: South'
    else:
        direction_text.text = 'Facing: West'
```

#### 方案 C：投射准星（最佳）

```python
# 在玩家前方显示地面准星
ground_crosshair = Entity(
    model='circle',
    color=color.yellow,
    scale=1,
    collider='box'
)

def update():
    # 在玩家前方 10 单位显示准星
    crosshair_pos = player.position + player.forward * 10
    ground_crosshair.position = crosshair_pos
    ground_crosshair.y = 0.1  # 略高于地面
```

### 3.5 输入方案总结

| 方案 | 操作方式 | 难度 | 推荐度 |
|------|----------|------|--------|
| **A: Q/E 旋转** | Q 向左转 90°，E 向右转 90° | ⭐ 简单 | ⭐⭐ 较僵硬 |
| **B: A/D 旋转** | A/D 持续旋转 | ⭐⭐⭐ 中等 | ⭐⭐⭐⭐ 推荐 |
| **C: 鼠标右键** | 按住右键拖动旋转 | ⭐⭐⭐ 较难 | ⭐⭐⭐⭐⭐ 最佳 |
| **D: 混合方案** | 鼠标移动瞄准，键盘移动 | ⭐⭐⭐⭐ 复杂 | ⭐⭐⭐ 需要更多开发 |

## 4. 推荐实现方案

### 4.1 最小改动方案（快速验证）

```python
# 1. 修改射击方向
def get_shoot_direction(self):
    if self.mode == CameraMode.FIRST_PERSON:
        return camera.forward
    else:
        # 使用玩家朝向
        target_point = player.position + player.forward * 100
        return (target_point - gun.world_position).normalized()

# 2. 添加 Q/E 旋转控制
def input(key):
    if key == 'q':
        player.rotation_y -= 90
    elif key == 'e':
        player.rotation_y += 90

# 3. 添加朝向指示器
direction_arrow = Entity(
    parent=player,
    model='arrow',
    scale=0.5,
    y=2,
    color=color.yellow
)
```

### 4.2 最佳体验方案

```python
# 1. 修改射击方向（同上）

# 2. 鼠标右键旋转玩家
def update():
    if mouse.right:
        player.rotation_y += mouse.velocity[0] * 100

# 3. 相机围绕玩家旋转
def update_camera(self):
    angle = radians(self.target.rotation_y)
    x_offset = sin(angle) * 40  # 相机距离
    z_offset = -cos(angle) * 40
    
    target_position = self.target.position + Vec3(x_offset, 15, z_offset)
    camera.position = lerp(camera.position, target_position, self.transition_speed * time.dt)
    camera.look_at(self.target.position + Vec3(0, 1.5, 0))

# 4. 地面准星
ground_crosshair = Entity(
    model='circle',
    color=color.yellow,
    scale=1,
    y=0.1
)

def update():
    ground_crosshair.position = player.position + player.forward * 10
```

## 5. 实现步骤

### 第一步：修改射击方向
- 修改 `get_shoot_direction()` 使用 `player.forward`

### 第二步：添加旋转控制
- 实现玩家旋转机制（建议鼠标右键）
- 更新操作提示 UI

### 第三步：优化相机跟随
- 实现相机围绕玩家旋转
- 或保持固定跟随

### 第四步：添加朝向反馈
- 添加方向指示箭头
- 或地面投射准星
- 更新 UI 显示当前朝向

### 第五步：测试和调优
- 测试瞄准手感
- 调整旋转速度
- 调整相机位置
- 优化准星显示

## 6. 技术要点

### 6.1 玩家朝向计算

```python
# 玩家的 forward 属性是当前朝向的单位向量
player_direction = player.forward  # Vec3

# 获取旋转角度
player_angle = player.rotation_y  # 弧度

# 手动计算朝向向量（如果需要）
from math import sin, cos, radians
angle = radians(player.rotation_y)
forward_x = sin(angle)
forward_z = -cos(angle)
player_forward = Vec3(forward_x, 0, forward_z)
```

### 6.2 相机围绕旋转

```python
def update_camera(self):
    # 将玩家角度转换为弧度
    angle = radians(self.target.rotation_y)
    
    # 计算相机在玩家周围的圆形轨迹
    # 相机始终在玩家背后，随玩家旋转
    camera_x = self.target.x + sin(angle) * self.camera_distance
    camera_z = self.target.z - cos(angle) * self.camera_distance
    
    target_position = Vec3(camera_x, self.camera_height, camera_z)
    camera.position = lerp(camera.position, target_position, self.transition_speed * time.dt)
    
    camera.look_at(self.target.position + Vec3(0, 1.5, 0))
```

### 6.3 射线检测优化

```python
def shoot(self):
    direction = camera_controller.get_shoot_direction()
    
    # 从枪口位置发射射线
    hit_info = raycast(
        gun.world_position,
        direction,
        distance=100,
        ignore=(player, gun)
    )
    
    if hit_info.hit:
        # 创建子弹或直接造成伤害
        pass
```

## 7. 扩展功能

### 7.1 平滑旋转

```python
class SmoothRotation(Entity):
    def __init__(self, target, speed=5):
        super().__init__()
        self.target = target
        self.speed = speed
        self.target_rotation = 0
    
    def update(self):
        current = self.target.rotation_y
        diff = self.target_rotation - current
        self.target.rotation_y += diff * self.speed * time.dt
```

### 7.2 相机碰撞检测

```python
def update_camera(self):
    target_position = calculate_target_position()
    
    # 射线检测相机是否会穿墙
    ray = raycast(
        player.position + Vec3(0, 1.5, 0),
        (target_position - player.position).normalized(),
        distance=distance(target_position, player.position),
        ignore=(player,)
    )
    
    if ray.hit and ray.distance < distance(target_position, player.position):
        # 相机会被墙挡住，拉近相机
        camera.position = ray.world_point - ray.direction * 0.5
    else:
        # 正常跟随
        camera.position = lerp(camera.position, target_position, self.transition_speed * time.dt)
```

### 7.3 多武器支持

```python
class WeaponType:
    def __init__(self, name, damage, speed, rate):
        self.name = name
        self.damage = damage
        self.speed = speed
        self.rate = rate

weapons = {
    'pistol': WeaponType('Pistol', 10, 50, 0.15),
    'rifle': WeaponType('Rifle', 20, 80, 0.1),
    'shotgun': WeaponType('Shotgun', 8, 40, 0.5)  # 散弹枪需要特殊处理
}

def input(key):
    if key == '1':
        equip_weapon('pistol')
    elif key == '2':
        equip_weapon('rifle')
    elif key == '3':
        equip_weapon('shotgun')
```

## 8. 对比分析

### 8.1 优缺点总结

**方向跟随本体（推荐）**：
- ✅ 视觉一致性最好
- ✅ 符合动作游戏直觉
- ✅ 玩家转身可见
- ❌ 操作复杂度较高
- ❌ 需要转身瞄准
- ❌ 可能降低战斗节奏

**方向跟随视角（当前）**：
- ✅ 操作简单
- ✅ 快速瞄准
- ✅ 街机风格
- ❌ 视觉不协调
- ❌ 不符合直觉
- ❌ 玩家朝向无意义

### 8.2 适用场景

| 游戏类型 | 推荐方案 | 原因 |
|----------|----------|------|
| 动作冒险 | 方向跟随本体 | 强调玩家操作 |
| RPG | 方向跟随本体 | 角色朝向重要 |
| 街机射击 | 方向跟随视角 | 快节奏战斗 |
| 射击游戏 | 方向跟随视角 | 精准瞄准 |
| Moba | 方向跟随本体 | 角色控制核心 |

## 9. 实施建议

### 9.1 渐进式实施

1. **第一阶段**：最小改动验证
   - 只修改射击方向使用 `player.forward`
   - 添加简单的 Q/E 旋转
   - 测试视觉效果

2. **第二阶段**：优化输入
   - 实现鼠标右键旋转
   - 添加平滑过渡
   - 优化手感

3. **第三阶段**：完善反馈
   - 添加方向指示器
   - 实现地面准星
   - 优化 UI 显示

4. **第四阶段**：相机优化
   - 实现相机围绕旋转
   - 添加碰撞检测
   - 优化跟随效果

### 9.2 用户测试要点

- 瞄准是否直观
- 旋转是否流畅
- 相机位置是否合适
- 准星是否清晰
- 整体游戏体验

## 10. 总结

方向跟随本体的设计核心是：
1. **射击方向 = 玩家朝向**
2. **相机 = 观察者**，不控制射击
3. **玩家旋转 = 瞄准方式**

这样的设计：
- 视觉一致性最好
- 符合动作游戏直觉
- 玩家能清楚看到自己的朝向
- 更有"我在控制角色"的感觉

关键代码改动：
```python
# 唯一的核心改动
target_point = player.position + player.forward * 100
return (target_point - gun.world_position).normalized()
```

配合合适的输入控制（建议鼠标右键旋转），就能实现优秀的第三人称射击体验！
