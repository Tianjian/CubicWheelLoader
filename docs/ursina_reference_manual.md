# Ursina 引擎参考手册

本文档为 Ursina 游戏引擎的核心功能参考手册，基于官方文档整理。

## 目录

1. [安装与环境配置](#安装与环境配置)
2. [Entity 基础](#entity-基础)
3. [坐标系](#坐标系)
4. [碰撞检测](#碰撞检测)
5. [文本渲染](#文本渲染)
6. [动画系统](#动画系统)

---

## 安装与环境配置

### 安装 Python

1. 安装 Python 3.12 或更新版本: https://www.python.org/downloads/
2. 验证安装: `python --version`

### 安装 Ursina

```bash
# 从 PyPI 安装稳定版
python -m pip install ursina

# 从 GitHub 安装开发版
python -m pip uninstall ursina
python -m pip install https://github.com/pokepetter/ursina/archive/master.zip

# 克隆源码安装（便于修改源码）
git clone https://github.com/pokepetter/ursina.git
python -m pip install --editable .
```

### 安装可选依赖

```bash
pip install ursina[extras]
```

---

## Entity 基础

Entity 是 Ursina 中的核心类，类似于 Unity 的 GameObject 或 Unreal 的 Actor。

### 基本属性

```python
from ursina import *

app = Ursina()

# 创建基本实体
e = Entity(
    model='cube',        # 模型
    texture='brick',     # 纹理
    color=color.red,     # 颜色
    position=(0,0,0),    # 位置
    rotation=(0,0,0),    # 旋转
    scale=(1,1,1)        # 缩放
)
```

### Model（模型）

内置模型：'quad', 'plane', 'cube', 'sphere'

支持的文件格式：
- `.obj`
- `.bam` (二进制格式)
- `.blend` (自动转换为 obj)
- `.ursinamesh` (自定义格式)

```python
Entity(model='name_of_your_model')
```

### Texture（纹理）

```python
e1 = Entity(model='cube', texture='texture_name')
e2 = Entity(model='cube', texture=e1.texture)  # 共享纹理
e3 = Entity(model='cube', texture=Texture(PIL.Image.new(mode="RGBA", size=(854,480))))
e4 = Entity(model='cube', texture='movie_name.mp4')  # 视频纹理

# 2D 图像使用 Sprite 类
s = Sprite('texture_name')
print(s.aspect_ratio)
```

### Color（颜色）

```python
e.color = color.red                    # 预设颜色
e.color = hsv(120, .5, .5)            # HSV 颜色
e.color = rgb(.8, .1, 0)              # RGB 颜色 (0-1)
e.color = rgb32(16, 128, 255)         # RGB 颜色 (0-255)
e.color = '#aabbcc'                   # 十六进制
e.color = e.color.tint(.1)            # 调整色调
e.color = color.random_color()        # 随机颜色
e.color = lerp(color.red, color.green, .5)  # 颜色插值
```

### Position（位置）

```python
# 相对位置
e = Entity()
e.position = Vec3(0,0,0)
e.position = Vec2(0,0)
e.position = (0,0,0)

# 单独设置轴
e.x = 0
e.y = 0
e.z = 0

# 世界坐标（忽略父对象位置）
e.world_position = Vec3(0,0,0)
e.world_x = 0
e.world_y = 0
e.world_z = 0
```

### Rotation（旋转）

```python
e.rotation = (0,0,0)
e.rotation_y = 90

# 指向目标
other_entity = Entity(position=(10,1,8))
e.look_at(other_entity)                    # z 轴（前方）指向目标
e.look_at(other_entity, axis='up')        # 指定轴向
```

### Scale（缩放）

```python
e = Entity(model='cube', scale=(3,1,1))
```

### Update（更新循环）

三种方式实现更新逻辑：

**方法1：赋值 update 属性**
```python
e = Entity()
def my_update():
    e.x += 1 * time.dt
e.update = my_update
```

**方法2：继承 Entity 类**
```python
class Player(Entity):
    def update(self):
        self.x += 1 * time.dt
```

**方法3：全局 update 函数**
```python
def update():
    print('update')
```

### Input（输入处理）

```python
class Player(Entity):
    def input(self, key):
        if key == 'w':
            self.position += self.forward
        if key == 'd':
            self.animate('rotation_y', self.rotation_y + 90, duration=.1)
        if key == 'a':
            self.animate('rotation_y', self.rotation_y - 90, duration=.1)
```

### Mouse Input（鼠标交互）

```python
# 获取鼠标悬停的实体
print(mouse.hovered_entity)

# 检查实体是否被悬停
print(my_entity.hovered)

# 鼠标事件处理
def action():
    print('Ow! That hurt!')

Entity(
    model='quad',
    parent=camera.ui,
    scale=.1,
    collider='box',
    on_click=action
)

# 鼠标进出事件
b = Button(scale=(.5, .25), text='zzz')
b.on_mouse_enter = Func(setattr, b, 'text', 'Hi, friend :D')
b.on_mouse_exit = Func(setattr, b, 'text', 'No! Don\'t leave me ;-;')
```

### 其他魔法方法

```python
on_enable()    # 启用实体时调用
on_disable()   # 禁用实体时调用
on_destroy()   # 销毁实体时调用
```

---

## 坐标系

### Entity 坐标系

```
       y (up)
       |
       | (forward) z
      \ |
       \|
        *---------- x (right)
```

- x: 向右为正
- y: 向上为正
- z: 向前为正

### UI 坐标系

```
                (-.5, .5)           (.5, .5)

(window.top_left)_______|__(window.top)____|_______(window.top_right)
                  |       '                  '       |
                  |       '                  '       |
                  |       '        (0, 0)    '       |
                  |       '                  '       |
                  |_______'__________________'_______|
(window.bottom_left)|  (window.bottom)     | (window.bottom_right)
                   (-.5, -.5)            (.5, -.5)
```

### 旋转

正向旋转表示从外向内看时顺时针旋转（z 轴除外，为逆时针）。

```python
entity.look_at(position)         # 3D 朝向
entity.look_at_2d(position)      # 2D 朝向
entity.rotate(amount)            # 持续旋转
entity.quaternion                # 四元数操作
```

### Origin（原点）

```python
# 设置原点（尤其对 UI 有用）
Text('Hello\nWorld!', origin=(-.5,.5))   # 左上角
Text('Hello\nWorld!', origin=(0,0))      # 中心
```

---

## 碰撞检测

### 添加碰撞器

```python
e = Entity(model='sphere', x=2)

# 基于边界自动添加
e.collider = 'box'      # BoxCollider
e.collider = 'sphere'   # SphereCollider
e.collider = 'mesh'     # MeshCollider

# 自定义碰撞器
e.collider = BoxCollider(e, center=Vec3(0,0,0), size=Vec3(1,1,1))
e.collider = SphereCollider(e, center=Vec3(0,0,0), radius=.75)
e.collider = MeshCollider(e, mesh=e.model, center=Vec3(0,0,0))

# 创建时添加
e = Entity(model='cube', collider='box')
```

### raycast（射线检测）

```python
hit_info = raycast(
    origin,
    direction=(0,0,1),
    distance=inf,
    traverse_target=scene,
    ignore=list(),
    debug=False
)
```

**示例：墙壁碰撞检测**
```python
class Player(Entity):
    def update(self):
        self.direction = Vec3(
            self.forward * (held_keys['w'] - held_keys['s'])
            + self.right * (held_keys['d'] - held_keys['a'])
        ).normalized()

        origin = self.world_position + (self.up*.5)
        hit_info = raycast(
            origin,
            self.direction,
            ignore=(self,),
            distance=.5,
            debug=False
        )

        if not hit_info.hit:
            self.position += self.direction * 5 * time.dt
```

### boxcast（盒射线检测）

类似 raycast，但射线有宽度和高度：

```python
hit_info = boxcast(
    origin,
    direction=(0,0,1),
    distance=9999,
    thickness=(1,1),
    traverse_target=scene,
    ignore=list(),
    debug=False
)
```

### intersects（相交检测）

```python
if player.intersects(trigger_box).hit:
    trigger_box.color = color.lime
    print('player is inside trigger box')
```

### HitInfo 对象

所有碰撞函数返回 HitInfo 对象：

```python
hit = None          # 是否命中
entity = None       # 命中的实体
point = None        # 命中点（局部坐标）
world_point = None  # 命中点（世界坐标）
distance = math.inf    # 距离
normal = None        # 法线（局部）
world_normal = None  # 法线（世界）
hits = []            # 所有命中
entities = []        # 所有命中的实体
```

### Distance Check（距离检查）

```python
if distance(player, pickup) < pickup.scale_x / 2:
    print('pickup')
```

### Mouse Collision（鼠标碰撞）

```python
mouse.hovered_entity  # 鼠标悬停的实体
mouse.normal          # 法线（局部坐标）
mouse.world_normal    # 法线（世界坐标）
mouse.point           # 命中点（局部坐标）
mouse.world_point     # 命中点（世界坐标）
```

---

## 文本渲染

### Text Size（文本大小）

```python
# 单个实体
text_entity = Text('hello', world_scale=2)

# 全局设置
Text.size = .05  # 默认: .025

# 非均匀缩放的 Button
button = Button(scale=(.2,.1), text='Start')
button.text_entity.world_scale = 2
```

### Font and Resolution（字体与分辨率）

```python
# 单个实体
text = Text(font='VeraMono.ttf', resolution=100*Text.size)

# 全局设置
Text.default_font = 'VeraMono.ttf'
Text.default_resolution = 100 * Text.size
```

### Text Alignment（文本对齐）

```python
Text('Hello\nWorld!', origin=(-.5,.5))  # 左上角（默认）
Text('Hello\nWorld!', origin=(0,0))     # 居中
```

### Text Colors（文本颜色）

```python
# 整体颜色
t = Text('This is some text', color=color.blue)

# 部分颜色（标签）
t = Text('This is some <pink>colored text. <default>Reset color.', color=color.blue)
```

### Changing Text of Prefabs（修改预制体文本）

```python
# 访问预制体的 text_entity
button = Button()
button.text_entity.color = color.red
```

---

## 动画系统

### SpriteSheetAnimation (2D)

使用精灵表制作动画。

```python
animator = SpriteSheetAnimation(
    'sprite_sheet.png',
    grid=(4, 4),      # 4x4 网格
    animations={
        'idle': (0, 4),     # 帧 0-4
        'run': (4, 8)
    }
)
animator.play('idle')
```

### Animation (2D)

加载图像序列或 GIF 作为动画。

```python
animator = Animation('animation.gif')
animator.loop = True
```

### Actor (3D)

骨骼动画，使用 Panda3D 的 Actor。

```python
from direct.actor.Actor import Actor

actor = Actor("model.gltf")
actor.loop("animation_name")   # 循环播放
actor.play("animation_name")   # 播放一次
```

**推荐格式**: `.glb` / `.gltf`（包含网格、纹理、动画等）

### FrameAnimation3D (3D)

加载模型序列实现动画（内存占用较大）。

```python
FrameAnimation3d('run_cycle_')  # 加载 run_cycle_000.obj, run_cycle_001.obj, ...
```

---

## 实用函数与属性

### 全局变量

```python
time.dt            # 帧时间（秒）
time.time          # 运行时间
held_keys          # 按键状态字典
mouse.position     # 鼠标位置
mouse.normalized   # 鼠标归一化位置 (-.5 到 .5)
```

### 常用函数

```python
lerp(a, b, t)                    # 线性插值
distance(a, b)                   # 计算距离
destroy(entity)                  # 销毁实体
duplicate(entity)                # 复制实体
instantiate(entity)              # 实例化预制体
```

### Entity 生命周期

```python
e.enable()     # 启用实体
e.disable()    # 禁用实体
e.enabled      # 是否启用
```

---

## 常用预设实体

```python
Button()           # 按钮
InputField()        # 输入框
Slider()           # 滑块
Text()             # 文本
Sprite()           # 2D 精灵
EditorCamera()     # 编辑器相机
FirstPersonController()  # 第一人称控制器
```

---

## 快速示例

### 基本场景

```python
from ursina import *

app = Ursina()

# 创建地面
ground = Entity(
    model='plane',
    texture='grass',
    scale=(10, 1, 10),
    collider='box'
)

# 创建玩家
player = Entity(
    model='cube',
    color=color.orange,
    position=(0, 0.5, 0),
    scale=(0.5, 0.5, 0.5),
    collider='box'
)

def update():
    player.x += (held_keys['d'] - held_keys['a']) * time.dt * 5
    player.z += (held_keys['w'] - held_keys['s']) * time.dt * 5

app.run()
```

---

## 参考资料

- 官方文档: https://www.ursinaengine.org/documentation.html
- API 参考: https://www.ursinaengine.org/api_reference.html
- GitHub: https://github.com/pokepetter/ursina
