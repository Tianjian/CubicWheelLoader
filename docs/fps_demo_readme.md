# FPS Demo - Ursina 射击游戏示例

## 概述

这是一个基于 Ursina 引擎的第一人称射击游戏示例，包含完整的游戏循环、敌人AI、射击系统和编辑器切换功能。

## 运行方法

```bash
cd d:/Code/CubicWheelLoader
python fps_demo.py
```

## 游戏控制

### 玩家控制
- `W` `A` `S` `D` - 移动
- `空格` - 跳跃
- `鼠标移动` - 视角控制
- `左键`（按住）- 射击
- `Tab` - 切换编辑/游玩模式

### 编辑器模式
- `右键`（按住）+ `WASD` - 编辑器相机移动
- `右键`（按住）+ `鼠标` - 编辑器相机旋转
- `鼠标滚轮` - 缩放

## 核心功能分析

### 1. 初始化设置

```python
app = Ursina()  # 创建 Ursina 实例

# 设置随机种子，确保每次运行场景一致
random.seed(0)

# 设置默认着色器为带阴影的光照着色器
Entity.default_shader = lit_with_shadows_shader
```

### 2. 玩家控制器

```python
player = FirstPersonController(
    model='cube',           # 玩家模型（仅用于调试）
    z=-10,                  # 初始位置
    color=color.orange,     # 颜色
    origin_y=-.5,          # 原点设置（使模型底部对齐地面）
    speed=8,               # 移动速度
    collider='box'         # 碰撞器类型
)

# 自定义碰撞器尺寸
player.collider = BoxCollider(player, Vec3(0,1,0), Vec3(1,2,1))
```

**FirstPersonController 功能**:
- 自动处理 WASD 移动
- 自动处理鼠标视角
- 自动处理跳跃
- 自动处理碰撞

### 3. 武器系统

```python
# 武器模型（作为相机的子对象，跟随视角移动）
gun = Entity(
    model='cube',
    parent=camera,
    position=(.5,-.25,.25),   # 在相机右下角
    scale=(.3,.2,1),
    origin_z=-.5,
    color=color.red,
    on_cooldown=False         # 射击冷却状态
)

# 枪口闪光
gun.muzzle_flash = Entity(
    parent=gun,
    z=1,
    world_scale=.5,
    model='quad',
    color=color.yellow,
    enabled=False  # 默认禁用，射击时启用
)
```

**射击机制**:

```python
def shoot():
    if not gun.on_cooldown:
        gun.on_cooldown = True

        # 1. 显示枪口闪光
        gun.muzzle_flash.enabled = True

        # 2. 播放射击音效（程序生成）
        from ursina.prefabs.ursfx import ursfx
        ursfx([...], volume=0.5, ...)

        # 3. 0.05秒后隐藏闪光
        invoke(gun.muzzle_flash.disable, delay=.05)

        # 4. 0.15秒后解除冷却
        invoke(setattr, gun, 'on_cooldown', False, delay=.15)

        # 5. 检测是否击中
        if mouse.hovered_entity and hasattr(mouse.hovered_entity, 'hp'):
            mouse.hovered_entity.blink(color.red)
            mouse.hovered_entity.hp -= 10
```

**射线检测**:
- `mouse.hovered_entity` - 自动检测鼠标指向的实体
- `shootables_parent` - 限制射线检测的目标范围
- `mouse.traverse_target = shootables_parent` - 设置遍历目标

### 4. 敌人系统

```python
class Enemy(Entity):
    def __init__(self, **kwargs):
        super().__init__(
            parent=shootables_parent,  # 添加到可射击目标
            model='cube',
            scale_y=2,
            origin_y=-.5,
            color=color.light_gray,
            collider='box',
            **kwargs
        )

        # 血条（作为子对象）
        self.health_bar = Entity(
            parent=self,
            y=1.2,
            model='cube',
            color=color.red,
            world_scale=(1.5,.1,.1)
        )

        self.max_hp = 100
        self.hp = self.max_hp
```

**敌人 AI**:

```python
def update(self):
    # 1. 计算到玩家的距离
    dist = distance_xz(player.position, self.position)
    if dist > 40:
        return  # 太远不更新

    # 2. 血条淡出效果
    self.health_bar.alpha = max(0, self.health_bar.alpha - time.dt)

    # 3. 面向玩家
    self.look_at_2d(player.position, 'y')

    # 4. 检测视线
    hit_info = raycast(
        self.world_position + Vec3(0,1,0),  # 从敌人头部
        self.forward,                        # 向前
        30,                                  # 检测距离
        ignore=(self,)                       # 忽略自己
    )

    # 5. 如果看到玩家且距离足够，则移动
    if hit_info.entity == player:
        if dist > 2:
            self.position += self.forward * time.dt * 5
```

**血量系统**:

```python
@property
def hp(self):
    return self._hp

@hp.setter
def hp(self, value):
    self._hp = value
    if value <= 0:
        destroy(self)  # 死亡销毁
        return

    # 更新血条宽度和透明度
    self.health_bar.world_scale_x = self.hp / self.max_hp * 1.5
    self.health_bar.alpha = 1
```

### 5. 编辑器模式切换

```python
def pause_input(key):
    if key == 'tab':
        # 切换编辑器
        editor_camera.enabled = not editor_camera.enabled

        # 切换玩家可见性
        player.visible_self = editor_camera.enabled
        player.cursor.enabled = not editor_camera.enabled

        # 切换武器可见性
        gun.enabled = not editor_camera.enabled

        # 切换鼠标锁定
        mouse.locked = not editor_camera.enabled

        # 编辑器相机移到玩家位置
        editor_camera.position = player.position

        # 暂停/恢复应用
        application.paused = editor_camera.enabled

# 创建独立的输入处理器（忽略暂停）
pause_handler = Entity(ignore_paused=True, input=pause_input)
```

**设计要点**:
- `ignore_paused=True` - 即使暂停也能接收输入
- `EditorCamera` - Panda3D 内置的编辑器相机
- 切换时同步相机位置

### 6. 环境设置

```python
# 地面
ground = Entity(
    model='plane',
    collider='box',
    scale=64,
    texture='grass',
    texture_scale=(4,4)  # 纹理重复4x4次
)

# 随机墙壁
for i in range(16):
    Entity(
        model='cube',
        origin_y=-.5,
        scale=2,
        texture='brick',
        texture_scale=(1,2),
        x=random.uniform(-8,8),
        z=random.uniform(-8,8) + 8,
        collider='box',
        scale_y = random.uniform(2,3),
        color=color.hsv(0, 0, random.uniform(.9, 1))
    )

# 定向光源
sun = DirectionalLight()
sun.look_at(Vec3(1,-1,-1))

# 天空盒
Sky()
```

## 关键技术点

### 1. 射线检测

Ursina 提供两种射线检测方式：

```python
# 方式1：使用 mouse 自动射线检测（最简单）
if mouse.hovered_entity:
    print("击中:", mouse.hovered_entity)

# 方式2：手动射线检测
hit_info = raycast(
    origin,          # 起点
    direction,       # 方向
    distance=9999,   # 最大距离
    ignore=[],       # 忽略的对象
    debug=False      # 是否绘制射线
)

if hit_info.hit:
    print("击中:", hit_info.entity)
    print("击中点:", hit_info.world_point)
    print("法线:", hit_info.world_normal)
```

### 2. invoke() 延迟执行

```python
# 延迟执行函数
invoke(function, delay=1)

# 延迟执行带参数
invoke(function, arg1, arg2, delay=1)

# 延迟设置属性
invoke(setattr, object, 'property', value, delay=1)
```

### 3. 程序化音效 (ursfx)

```python
from ursina.prefabs.ursfx import ursfx

ursfx(
    [(时间, 音量), ...],  # 音量包络
    volume=0.5,           # 总音量
    wave='noise',         # 波形类型
    pitch=random.uniform(-13,-12),  # 音调
    pitch_change=-12,     # 音调变化
    speed=3.0            # 播放速度
)
```

### 4. 属性装饰器

```python
@property
def hp(self):
    return self._hp

@hp.setter
def hp(self, value):
    self._hp = value
    # 自动触发副作用（更新UI等）
```

### 5. 时间管理

```python
time.dt              # delta time（帧时间）
time.dt_unscaled     # 未缩放的 delta time
time.time            # 运行总时间

# 帧率无关的移动
self.position += self.forward * time.dt * 5
```

### 6. 相机空间 vs 世界空间

```python
# 作为 camera 的子对象 = 相机空间（UI、武器）
gun = Entity(parent=camera)

# 作为 scene 的子对象 = 世界空间（敌人、墙壁）
enemy = Entity(parent=scene)

# 转换坐标
world_position = entity.world_position
```

## 扩展建议

### 1. 添加武器切换

```python
weapons = ['gun', 'rifle', 'shotgun']
current_weapon = 0

def input(key):
    global current_weapon
    if key == '1': current_weapon = 0
    if key == '2': current_weapon = 1
    if key == '3': current_weapon = 2
```

### 2. 添加弹药系统

```python
class Gun(Entity):
    def __init__(self):
        super().__init__()
        self.ammo = 30
        self.max_ammo = 30

    def shoot(self):
        if self.ammo > 0:
            self.ammo -= 1
        else:
            # 换弹逻辑
            pass
```

### 3. 添加敌人波次

```python
wave = 1
enemies_per_wave = 5 * wave

def check_wave():
    global wave, enemies_per_wave
    if len(enemies) == 0:
        wave += 1
        spawn_enemies(enemies_per_wave)
```

### 4. 添加生命值系统

```python
player.max_hp = 100
player.hp = 100

class Player(FirstPersonController):
    def update(self):
        if self.hp <= 0:
            game_over()
```

### 5. 添加得分系统

```python
score = 0

score_text = Text(
    text=f'Score: {score}',
    position=(-.85, .45),
    parent=camera.ui
)

def on_enemy_killed():
    global score
    score += 10
    score_text.text = f'Score: {score}'
```

## 调试技巧

### 1. 显示碰撞器

```python
# 全局设置
window.render_mode = 'colliders'

# 或者单个实体
entity.collider.visible = True
```

### 2. 射线调试

```python
# 绘制射线
hit_info = raycast(origin, direction, debug=True)
```

### 3. 编辑器模式

按 `Tab` 切换到编辑器模式，可以：
- 自由查看场景
- 检查实体位置
- 调整相机观察角度

### 4. 打印调试信息

```python
print(f"Player pos: {player.position}")
print(f"Enemy count: {len(enemies)}")
```

## 性能优化

### 1. 减少射线检测频率

```python
shoot_timer = 0
def update():
    global shoot_timer
    shoot_timer += time.dt

    if held_keys['left mouse'] and shoot_timer > 0.15:
        shoot()
        shoot_timer = 0
```

### 2. 限制更新范围

```python
def update(self):
    dist = distance(player.position, self.position)
    if dist > 50:  # 超出50米不更新
        return
```

### 3. 使用简单的碰撞器

```python
# 优先使用简单碰撞器
collider='box'      # 最快
collider='sphere'   # 快
collider='mesh'     # 最慢
```

## 总结

这个 FPS 示例展示了 Ursina 引擎的核心功能：

1. **FirstPersonController** - 快速构建第一人称视角
2. **射线检测** - 精确的射击判定
3. **Entity 系统** - 统一的游戏对象管理
4. **组件化设计** - 血条、武器等可复用组件
5. **AI 行为** - 简单的追踪和攻击逻辑
6. **编辑器集成** - 开发时的快速调试

通过这个示例，我们学习了如何用 Ursina 快速构建一个完整的游戏循环，这些知识可以直接应用到 CubicWheelLoader 项目中。
