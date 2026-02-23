# Ursina Engine 架构分析文档

## 1. 概述

Ursina 是一个基于 Python 的轻量级 3D 游戏引擎，底层封装了 Panda3D 引擎。它采用简洁的 API 设计，使开发者能够用最少的代码快速构建游戏。

### 核心特点
- **单文件导入**: 所有核心功能通过 `from ursina import *` 一键导入
- **Entity 组件系统**: 统一的实体管理，类似 Unity 的 GameObject
- **Python 原生**: 无需额外语言，完全使用 Python 开发
- **模块化设计**: 清晰的模块划分和职责分离
- **单例模式**: 核心类采用单例模式确保全局唯一

---

## 2. 整体架构

### 2.1 目录结构

```
ursina/
├── __init__.py              # 统一入口，导出所有公共 API
├── main.py                  # Ursina 主类，引擎核心
├── application.py           # 全局应用状态和配置
├── entity.py                # Entity 核心类
├── window.py                # 窗口管理
├── camera.py                # 相机系统
├── scene.py                 # 场景管理
├── mouse.py                 # 鼠标输入
├── input_handler.py         # 输入处理
├── collider.py              # 碰撞检测（基础）
├── raycast.py               # 射线检测
├── boxcast.py               # 盒射线检测
├── physics.py               # 物理引擎（Bullet）
├── audio.py                 # 音频系统
├── text.py                  # 文本渲染
├── mesh.py                  # 网格系统
├── mesh_importer.py         # 模型导入
├── mesh_exporter.py         # 模型导出
├── texture.py               # 纹理系统
├── texture_importer.py      # 纹理导入
├── color.py                 # 颜色系统
├── shader.py                # 着色器系统
├── lights.py                # 光照系统
├── sequence.py              # 序列/动画系统
├── curve.py                 # 曲线和缓动
├── destroy.py               # 对象销毁
├── duplicate.py             # 对象复制
├── hit_info.py              # 碰撞信息
├── ursinamath.py            # 数学工具
├── vec2.py                  # Vec2 向量
├── vec3.py                  # Vec3 向量
├── vec4.py                  # Vec4 向量
├── gamepad.py               # 手柄支持
├── networking.py            # 网络功能
├── build.py                 # 构建系统
├── trigger.py               # 触发器
├── terraincast.py           # 地形检测
├── music_system.py          # 音乐系统
├── array_tools.py           # 数组工具
├── string_utilities.py      # 字符串工具
├── ursinastuff.py           # 通用工具类
├── cmd_tool_maker.py        # 命令行工具
├── video_recorder.py        # 视频录制
│
├── prefabs/                 # 预制体库
│   ├── button.py            # 按钮
│   ├── text_field.py        # 文本框
│   ├── input_field.py       # 输入框
│   ├── slider.py            # 滑块
│   ├── sprite.py            # 精灵
│   ├── animation.py         # 2D 动画
│   ├── sprite_sheet_animation.py  # 精灵表动画
│   ├── frame_animation_3d.py       # 3D 帧动画
│   ├── first_person_controller.py # 第一人称控制器
│   ├── platformer_controller_2d.py # 2D 平台控制器
│   ├── editor_camera.py     # 编辑器相机
│   ├── particle_system.py   # 粒子系统
│   ├── sky.py               # 天空盒
│   ├── dropdown_menu.py     # 下拉菜单
│   ├── color_picker.py      # 颜色选择器
│   ├── file_browser.py      # 文件浏览器
│   └── ...更多预制体
│
├── editor/                  # 编辑器
│   └── level_editor.py      # 关卡编辑器
│
├── scripts/                 # 脚本工具
│   ├── every_decorator.py   # @every 装饰器
│   ├── smooth_follow.py     # 平滑跟随
│   ├── grid_layout.py       # 网格布局
│   ├── scrollable.py        # 滚动容器
│   ├── hot_reloader.py      # 热重载
│   └── ...更多工具脚本
│
├── models/                  # 内置模型
├── textures/                # 内置纹理
├── fonts/                   # 内置字体
├── shaders/                 # 内置着色器
├── audio/                   # 内置音效
└── models_compressed/       # 压缩模型
```

---

## 3. 核心模块分析

### 3.1 main.py - Ursina 主类

**职责**: 引擎入口，生命周期管理

**核心特性**:
- 继承自 Panda3D 的 `ShowBase` 类
- 使用单例装饰器 `@singleton` 确保唯一实例
- 管理主循环、输入处理、实体更新

**关键方法**:

```python
@singleton
class Ursina(ShowBase):
    def __init__(self, title='ursina', ...):
        # 初始化窗口
        window._ready(...)
        super().__init__(windowType=application.window_type)
        
        # 设置相机
        camera._cam = self.camera
        camera.reparent_to(camera)
        
        # 设置输入监听
        self.accept('buttonDown', self.input)
        self.accept('buttonUp', self.input_up)
        self.accept('buttonHold', self.input_hold)
        self.accept('keystroke', self.text_input)
        
        # 启动更新任务
        self._update_task = self.taskMgr.add(self._update, "update")
    
    def _update(self, task=None):
        # 每帧更新
        time.dt = globalClock.getDt() * application.time_scale
        mouse.update()
        
        # 调用全局 update 函数
        if hasattr(__main__, 'update'):
            __main__.update()
        
        # 更新所有实体
        for e in scene.entities:
            if e.enabled and callable(e.update):
                e.update()
        
        # 更新音频
        _audio_manager.update()
        
        return Task.cont
    
    def input(self, key, is_raw=False):
        # 输入分发到所有实体
        for e in scene.entities:
            if hasattr(e, 'input') and callable(e.input):
                e.input(key)
```

**关键特性**:
1. 输入名称标准化（将 Panda3D 的输入名映射为友好的名称）
2. 支持热重载（HotReloader）
3. 支持 in-game 控制台
4. 支持 `on_window_ready` 回调

---

### 3.2 application.py - 全局应用状态

**职责**: 存储全局配置和状态

**全局变量**:

```python
paused = False              # 暂停状态
time_scale = 1             # 时间缩放
calculate_dt = True        # 是否计算 delta time
sequences = []             # 活动的序列列表

package_folder             # 引擎包路径
asset_folder              # 资产文件夹路径
blender_paths = dict()    # Blender 路径

development_mode = True    # 开发模式
window_type = 'onscreen'   # 窗口类型
show_ursina_splash = False # 是否显示启动画面
gltf_no_srgb = True        # GLTF 颜色空间

# 文件夹路径
internal_models_folder
internal_textures_folder
internal_fonts_folder
internal_audio_folder
scenes_folder
scripts_folder
fonts_folder

base = None                # Panda3D Base 实例
hot_reloader = None        # 热重载实例
```

**主要功能**:
- `pause()` / `resume()` - 暂停/恢复
- `quit()` - 退出应用
- `load_settings()` - 加载配置文件

---

### 3.3 entity.py - Entity 核心类

**职责**: 游戏对象核心类，所有游戏对象的基类

**继承关系**:
```
Entity (NodePath)
└── 继承自 Panda3D 的 NodePath
```

**核心属性**:

```python
class Entity(NodePath, metaclass=PostInitCaller):
    # 位置、旋转、缩放
    position: Vec3
    rotation: Vec3
    scale: Vec3
    
    # 渲染属性
    model: Mesh | str
    texture: Texture | str
    color: Color
    shader: Shader
    
    # 变换原点
    origin: Vec3
    
    # 状态
    enabled: bool          # 是否启用
    eternal: bool          # 是否永久（不自动销毁）
    ignore: bool           # 是否忽略所有操作
    ignore_paused: bool    # 暂停时是否继续更新
    ignore_input: bool     # 是否忽略输入
    
    # 组件
    collider: Collider     # 碰撞器
    scripts: list          # 附加脚本
    
    # 动画
    animations: list       # 活动的动画序列
    
    # 鼠标
    hovered: bool          # 是否被鼠标悬停
```

**关键方法**:

```python
# 生命周期
def __post_init__(self):
    # 添加到场景
    scene.entities.append(self)
    
    # 调用 on_enable / on_disable
    if self.enabled and hasattr(self, 'on_enable'):
        self.on_enable()
    
    # 启动 @every 装饰器方法
    for method in every.decorated_methods:
        ...

def enable(self):  # 启用
    self.enabled = True

def disable(self):  # 禁用
    self.enabled = False

# 鼠标交互
def on_click(self):
    pass

def on_mouse_enter(self):
    pass

def on_mouse_exit(self):
    pass

# 工具方法
def look_at(self, target, axis='forward'):
    # 指向目标
    pass

def has_disabled_ancestor(self):
    # 检查是否有被禁用的祖先
    pass

def intersects(self, other):
    # 碰撞检测
    pass
```

**魔法方法**:
- `on_enable()` - 启用时调用
- `on_disable()` - 禁用时调用
- `on_destroy()` - 销毁时调用
- `update()` - 每帧更新
- `input(key)` - 输入处理
- `text_input(key)` - 文本输入

**属性生成器**:
使用 `@generate_properties_for_class()` 装饰器自动生成属性 getter/setter

---

### 3.4 window.py - 窗口管理

**职责**: 窗口配置和管理

**继承关系**:
```
Window (WindowProperties)
└── Panda3D WindowProperties
```

**核心属性**:

```python
class Window(WindowProperties):
    # 窗口配置
    title: str
    icon: str
    size: Vec2
    position: Vec2
    fullscreen: bool
    borderless: bool
    vsync: bool
    forced_aspect_ratio: float
    
    # 显示器信息
    monitors: list
    main_monitor
    monitor_index: int
    
    # 渲染模式
    render_modes = ('default', 'wireframe', 'colliders', 'normals')
    render_mode: str
    
    # UI 锚点
    top: Vec2
    bottom: Vec2
    center: Vec2
    left: Vec2
    right: Vec2
    top_left: Vec2
    top_right: Vec2
    bottom_left: Vec2
    bottom_right: Vec2
    
    # 编辑器 UI
    editor_ui: Entity
    editor_ui_enabled: bool
    
    # 控制台
    console: Entity
```

**关键功能**:
- 显示器检测和自动居中
- 窗口模式切换（全屏/窗口）
- 渲染模式切换（调试用）
- 编辑器 UI 管理（F12 切换）
- in-game 控制台支持

---

### 3.5 camera.py - 相机系统

**职责**: 相机管理和视口控制

**核心属性**:

```python
class Camera(Entity):
    # 视口设置
    fov: float              # 视场角
    near: float             # 近裁剪面
    far: float              # 远裁剪面
    orthographic: bool      # 是否正交投影
    
    # UI 相机
    ui: Camera              # UI 相机实例
    
    # 渲染相关
    render                  # Panda3D render 方法
    
    # 设置方法
    def _set_up(self):
        # 设置透视投影
        self.lens.setFov(self.fov)
        self.lens.setNearFar(self.near, self.far)
```

**特点**:
- UI 使用独立的正交投影相机
- 支持透视和正交两种投影模式
- 自动处理 aspect ratio

---

### 3.6 scene.py - 场景管理

**职责**: 实体列表管理和场景组织

**核心属性**:

```python
class Scene(Entity):
    entities: list          # 所有实体列表
    _entities_marked_for_removal: set  # 待移除实体
    
    camera: Camera          # 主相机
    
    def _set_up(self):
        # 初始化场景
        pass
```

**功能**:
- 维护所有实体的列表
- 标记和清理待删除实体
- 作为 3D 空间的根节点
- 场景保存/加载

---

### 3.7 mouse.py - 鼠标系统

**职责**: 鼠标输入和射线检测

**核心属性**:

```python
class Mouse(Entity):
    # 位置
    position: Vec2          # 屏幕坐标
    normalized: Vec2        # 归一化坐标 (-.5 到 .5)
    
    # 鼠标状态
    enabled: bool
    locked: bool            # 是否锁定（用于第一人称视角）
    
    # 碰撞检测
    hovered_entity: Entity  # 当前悬停的实体
    point: Vec3             # 命中点（局部）
    world_point: Vec3       # 命中点（世界）
    normal: Vec3            # 法线（局部）
    world_normal: Vec3      # 法线（世界）
    hit: bool               # 是否命中
    
    # Panda3D
    _mouse_watcher
    
    def update(self):
        # 每帧更新鼠标射线检测
        pass
    
    def input(self, key):
        # 处理鼠标输入
        pass
```

**功能**:
- 自动射线检测
- 支持 3D 和 UI 空间
- 提供鼠标按钮输入

---

### 3.8 input_handler.py - 输入处理

**职责**: 键盘输入处理和按键状态

**核心属性**:

```python
# 全局按键状态
held_keys = {
    'w': True,
    'a': False,
    ...
}

# 按键映射
rebinds = {
    'original_key': 'new_key'
}

class InputHandler:
    def input(self, key):
        # 处理输入
        pass
    
    def get_combined_key(self, key):
        # 获取组合键（如 'control-w'）
        pass
```

**功能**:
- 跟踪按键按下/抬起状态
- 支持组合键
- 支持按键重绑定

---

### 3.9 collider.py - 碰撞系统（基础）

**职责**: 基于 Panda3D CollisionNode 的基础碰撞检测

**碰撞器类型**:

```python
class Collider(NodePath):
    # 基类
    shape                   # 碰撞形状
    collision_node          # Panda3D 碰撞节点
    node_path               # 附着到实体的节点
    
    def remove(self):
        # 移除碰撞器

class BoxCollider(Collider):
    # 盒碰撞器
    center: Vec3
    size: Vec3

class SphereCollider(Collider):
    # 球碰撞器
    center: Vec3
    radius: float

class CapsuleCollider(Collider):
    # 胶囊碰撞器
    center: Vec3
    height: float
    radius: float

class MeshCollider(Collider):
    # 网格碰撞器
    center: Vec3
    mesh: Mesh
    collision_polygons: list
```

**功能**:
- 基于 Panda3D 的碰撞检测系统
- 支持多种基本形状
- 支持网格精确碰撞
- 碰撞可视化（调试用）

---

### 3.10 physics.py - 物理引擎

**职责**: 基于 Bullet Physics 的物理模拟

**核心组件**:

```python
class PhysicsHandler(Entity):
    world: BulletWorld       # Bullet 物理世界
    active: bool            # 是否激活
    show_debug: bool        # 是否显示调试信息
    _debug_node: BulletDebugNode
    debug_node_path
    
    def update(self):
        if self.active:
            self.world.doPhysics(time.dt)
    
    def gravity_setter(self, value):
        self.world.setGravity(value)

physics_handler = PhysicsHandler()  # 全局单例
```

**物理碰撞器**:

```python
# Bullet 碰撞器（与 collider.py 不同）
def PlaneCollider(normal, offset):
    return BulletPlaneShape(normal, offset)

def BoxCollider(size):
    return BulletBoxShape(Vec3(*size)/2)

def SphereCollider(radius):
    return BulletSphereShape(radius)

def CapsuleCollider(radius, height, axis='y'):
    return BulletCapsuleShape(radius, height-1, axis)

def MeshCollider(mesh):
    output = BulletTriangleMesh()
    output.addGeom(mesh)
    return BulletTriangleMeshShape(output, dynamic=False)
```

**射线检测（物理版）**:

```python
def raycast(origin, direction, distance=9999, 
             traverse_target=None, ignore=None, debug=False, 
             color=color.white, return_hit_only=False):
    # 使用 Bullet 物理世界的射线检测
    world.rayTestClosest(from_pos, to_pos)
    ...
```

**特点**:
- 完整的物理模拟
- 支持刚体动力学
- 支持调试渲染
- 与基础碰撞系统并存

---

### 3.11 audio.py - 音频系统

**职责**: 音频播放和管理

**核心类**:

```python
class Audio(Entity):
    # 音频属性
    volume: float
    pitch: float
    balance: float
    loop: bool
    loops: int
    autoplay: bool
    auto_destroy: bool
    group: str             # 'music', 'ambient', 'sfx', 'dialogue'
    clip: str              # 音频文件路径
    _clip                  # Panda3D AudioSound
    
    def play(self):
        pass
    
    def stop(self, destroy=False):
        pass
    
    def pause(self):
        pass
    
    def resume(self):
        pass
```

**音频组**:

```python
audio_groups = DotDict(
    music = DotDict(volume_multiplier=1),
    ambient = DotDict(volume_multiplier=1),
    sfx = DotDict(volume_multiplier=1),
    dialogue = DotDict(volume_multiplier=1),
)

_audio_manager = AudioManager.create_AudioManager()
```

**功能**:
- 支持多种音频格式
- 音频分组和分组音量
- 音频缓存
- 音调、音量、声道平衡控制

---

### 3.12 text.py - 文本渲染

**职责**: 文本显示和字体管理

**核心属性**:

```python
class Text(Entity):
    text: str               # 文本内容
    font: str               # 字体文件
    origin: Vec2            # 文本原点
    color: Color            # 文本颜色
    background: bool        # 是否有背景
    background_color: Color
    resolution: int         # 文本分辨率
    
    # 全局设置（类属性）
    default_font: str
    default_resolution: int
    size: float             # 默认文本大小
```

**功能**:
- 支持颜色标签（`<red>text</red>`）
- 支持换行和对齐
- 支持多语言字体
- 可调分辨率以适应不同屏幕

---

### 3.13 mesh.py - 网格系统

**职责**: 网格数据和程序化几何体

**核心属性**:

```python
class Mesh:
    vertices: list[Vec3]    # 顶点
    uvs: list[Vec2]         # UV 坐标
    normals: list[Vec3]     # 法线
    colors: list[Color]     # 顶点颜色
    triangles: list[int]    # 三角形索引
    
    mode: str               # 'triangle', 'line', 'ngon', 'point'
    static: bool            # 是否静态
    
    generated_vertices      # 生成的顶点数据
    generated_uvs            # 生成的 UV 数据
    generated_normals       # 生成的法线数据
    
    def generate(self):
        # 生成网格
        pass
    
    def clear(self):
        # 清空网格
        pass
```

**MeshModes**:
```python
class MeshModes:
    triangle = 'triangle'
    line = 'line'
    ngon = 'ngon'
    point = 'point'
```

**功能**:
- 程序化生成网格
- 支持多种网格模式
- 动态网格更新
- 支持顶点属性（位置、UV、法线、颜色）

---

### 3.14 mesh_importer.py - 模型导入

**职责**: 从外部文件加载模型

**支持的格式**:
- `.obj` - Wavefront OBJ
- `.bam` - Panda3D 二进制
- `.blend` - Blender（自动转换）
- `.gltf` / `.glb` - GLTF
- `.ursinamesh` - 自定义格式

**核心函数**:

```python
def load_model(name):
    # 加载模型
    # 搜索顺序：
    # 1. 项目文件夹
    # 2. 内部 models 文件夹
    # 3. 内部 models_compressed 文件夹
    pass

def load_blender_scene(path):
    # 导入 Blender 场景
    pass
```

---

### 3.15 texture.py - 纹理系统

**职责**: 纹理加载和管理

**核心类**:

```python
class Texture:
    path: str               # 纹理路径
    _texture                # Panda3D Texture
    
    def set(self, texture):
        # 设置纹理
        pass
    
    def apply(self, entity):
        # 应用到实体
        pass
```

**功能**:
- 支持多种图片格式
- 支持视频纹理
- 支持程序生成纹理
- 纹理压缩

---

### 3.16 color.py - 颜色系统

**职责**: 颜色管理和转换

**核心函数**:

```python
# 预设颜色
class color:
    white = Color(1, 1, 1, 1)
    black = Color(0, 0, 0, 1)
    red = Color(1, 0, 0, 1)
    green = Color(0, 1, 0, 1)
    blue = Color(0, 0, 1, 1)
    # ... 更多预设

# 颜色转换
def hsv(h, s, v, a=1):
    # HSV 转 RGB
    pass

def rgb(r, g, b, a=1):
    # RGB 颜色 (0-1)
    pass

def rgb32(r, g, b, a=255):
    # RGB 颜色 (0-255)
    pass

def lerp(c1, c2, t):
    # 颜色插值
    pass

def random_color():
    # 随机颜色
    pass
```

**功能**:
- 丰富的预设颜色
- 多种颜色格式支持
- 颜色操作（插值、混合等）

---

### 3.17 sequence.py - 序列和动画

**职责**: 动画序列和定时器

**核心类**:

```python
class Sequence:
    duration: float
    loop: bool
    started: bool
    entity: Entity
    
    def __init__(self, *args, loop=False, started=True, entity=None):
        # args 可以是 Func, Wait 等操作
        pass
    
    def start(self):
        pass
    
    def stop(self):
        pass
    
    def finish(self):
        pass
    
    def update(self):
        pass

class Func:
    # 延迟调用函数
    def __init__(self, func, *args, **kwargs):
        pass

class Wait:
    # 等待
    def __init__(self, duration):
        pass

# 实体动画方法
def animate(self, attribute, value, duration=1, curve=curve.linear, delay=0, loop=False):
    # 实体属性动画
    pass
```

**功能**:
- 序列化操作
- 延迟执行
- 属性动画
- 循环动画
- 支持缓动曲线

---

### 3.18 curve.py - 缓动曲线

**职责**: 动画缓动函数

**缓动类型**:

```python
class curve:
    linear              # 线性
    in_sine             # 正弦缓入
    out_sine            # 正弦缓出
    in_out_sine         # 正弦缓入缓出
    in_quad             # 二次缓入
    out_quad            # 二次缓出
    in_out_quad         # 二次缓入缓出
    in_cubic            # 三次缓入
    out_cubic           # 三次缓出
    in_out_cubic        # 三次缓入缓出
    in_quart            # 四次缓入
    out_quart           # 四次缓出
    in_out_quart        # 四次缓入缓出
    in_quint            # 五次缓入
    out_quint           # 五次缓出
    in_out_quint        # 五次缓入缓出
    in_expo             # 指数缓入
    out_expo            # 指数缓出
    in_out_expo         # 指数缓入缓出
    in_circ             # 圆形缓入
    out_circ            # 圆形缓出
    in_out_circ         # 圆形缓入缓出
    in_back             # 回弹缓入
    out_back            # 回弹缓出
    in_out_back         # 回弹缓入缓出
    in_elastic          # 弹性缓入
    out_elastic         # 弹性缓出
    in_out_elastic      # 弹性缓入缓出
    in_bounce           # 弹跳缓入
    out_bounce          # 弹跳缓出
    in_out_bounce       # 弹跳缓入缓出
```

---

### 3.19 shader.py - 着色器系统

**职责**: 着色器管理

**核心类**:

```python
class Shader:
    name: str
    path: str
    
    def set_input(self, key, value):
        pass
    
    def get_input(self, key):
        pass
```

**内置着色器**:

```
shaders/
├── lit_shader.py
├── unlit_shader.py
├── unlit_with_fog_shader.py
├── colored_lit_shader.py
├── terrain_shader.py
└── ...
```

---

## 4. 预制体系统

### 4.1 prefabs/ 目录结构

预制体是预定义的游戏对象，可以直接使用或继承。

**UI 组件**:
- `button.py` - 按钮组件
- `slider.py` - 滑块
- `input_field.py` - 输入框
- `text_field.py` - 文本显示
- `checkbox.py` - 复选框
- `dropdown_menu.py` - 下拉菜单
- `window_panel.py` - 窗口面板
- `tooltip.py` - 工具提示
- `cursor.py` - 自定义光标

**动画组件**:
- `animation.py` - 2D 动画
- `sprite_sheet_animation.py` - 精灵表动画
- `frame_animation_3d.py` - 3D 帧动画
- `animator.py` - 动画控制器

**游戏对象**:
- `sprite.py` - 2D 精灵
- `sky.py` - 天空盒
- `first_person_controller.py` - 第一人称控制器
- `platformer_controller_2d.py` - 2D 平台控制器
- `editor_camera.py` - 编辑器相机

**工具**:
- `particle_system.py` - 粒子系统
- `health_bar.py` - 生命值条
- `trail_renderer.py` - 轨迹渲染器
- `video_recorder.py` - 视频录制
- `file_browser.py` - 文件浏览器
- `color_picker.py` - 颜色选择器

**编辑器**:
- `hot_reloader.py` - 热重载
- `grid_editor.py` - 网格编辑器
- `gradient_editor.py` - 渐变编辑器

---

## 5. 脚本工具系统

### 5.1 scripts/ 目录

脚本工具是可以附加到 Entity 的可复用逻辑。

**常用工具**:

```python
# every_decorator.py - 定时执行装饰器
@every(interval=1)
def my_function(self):
    print("every second")

# smooth_follow.py - 平滑跟随
class SmoothFollow(Script):
    target: Entity
    speed: float = 5
    
    def update(self):
        self.entity.position = lerp(
            self.entity.position,
            self.target.position,
            self.speed * time.dt
        )

# grid_layout.py - 网格布局
def grid_layout(items, padding=0, max_width=0.8):
    # 自动排列实体
    pass

# scrollable.py - 滚动容器
class Scrollable(Script):
    # 使子元素可滚动
    pass

# property_generator.py - 属性生成器
@generate_properties_for_class()
class MyClass:
    # 自动生成属性 getter/setter
    pass
```

---

## 6. 数学工具

### 6.1 向量类

```python
class Vec2:
    x: float
    y: float
    
    # 运算
    def __add__(self, other): pass
    def __sub__(self, other): pass
    def __mul__(self, scalar): pass
    def normalized(self): pass
    def distance(self, other): pass

class Vec3:
    x: float
    y: float
    z: float
    # 同 Vec2，加上 z 轴
    
    # 额外方法
    def forward(self): return Vec3(0, 0, 1)
    def back(self): return Vec3(0, 0, -1)
    def up(self): return Vec3(0, 1, 0)
    def down(self): return Vec3(0, -1, 0)
    def right(self): return Vec3(1, 0, 0)
    def left(self): return Vec3(-1, 0, 0)

class Vec4:
    x: float
    y: float
    z: float
    w: float
```

### 6.2 数学函数 (ursinamath.py)

```python
# 常用函数
def lerp(a, b, t):
    # 线性插值
    return a + (b - a) * t

def clamp(value, min_val, max_val):
    # 限制范围
    pass

def distance(a, b):
    # 计算距离
    pass

# Bounds 类
class Bounds:
    center: Vec3
    size: Vec3
    
    def contains(self, point):
        pass
    
    def intersects(self, other):
        pass
```

---

## 7. 更新循环流程

### 7.1 主循环 (_update)

```
每帧执行流程:
1. 计算 delta time
2. 更新鼠标 (mouse.update())
3. 调用全局 update 函数
4. 更新所有序列 (sequence.update())
5. 清理待删除实体
6. 更新所有实体:
   - 跳过禁用、忽略、暂停的实体
   - 调用 entity.update()
   - 调用 entity.scripts[].update()
7. 更新着色器连续输入
8. 更新音频 (_audio_manager.update())
```

### 7.2 输入流程 (input)

```
输入流程:
1. 接收原始输入
2. 标准化输入名称
3. 应用按键重映射
4. 更新 held_keys 状态
5. 分发到:
   - 全局 input 函数 (__main__.input)
   - 所有实体的 input 方法
   - 所有脚本的 input 方法
6. 如果 input 返回 True，停止分发（吃掉输入）
```

---

## 8. 资源加载系统

### 8.1 模型加载

```python
load_model(name)
# 搜索顺序:
# 1. asset_folder / name
# 2. internal_models_folder / name
# 3. internal_models_compressed_folder / name
# 4. 带扩展名的各种格式尝试
```

### 8.2 纹理加载

```python
load_texture(name)
# 搜索顺序类似模型
# 支持的格式: .png, .jpg, .tga, .bmp
```

### 8.3 音频加载

```python
Audio(filename)
# 搜索路径:
# 1. asset_folder / audio
# 2. internal_audio_folder
```

---

## 9. 网络系统 (networking.py)

**功能**:
- TCP/UDP 网络通信
- 多人游戏支持
- 客户端-服务器架构

**核心类**:

```python
class NetworkClient:
    def connect(self, ip, port):
        pass
    
    def send(self, data):
        pass
    
    def receive(self):
        pass

class NetworkServer:
    def start(self, port, max_clients):
        pass
    
    def broadcast(self, data):
        pass
    
    def receive(self):
        pass
```

---

## 10. 构建系统 (build.py)

**功能**:
- 将游戏打包为可执行文件
- 支持多种打包方式:
  - `ursina.build()` - 内置构建
  - Nuitka
  - auto-py-to-exe

**使用**:

```python
from ursina import build

build(
    name='MyGame',
    icon='icon.ico',
    # 更多选项...
)
```

---

## 11. 设计模式和架构特点

### 11.1 使用的设计模式

1. **单例模式** (Singleton)
   - `Ursina` 类
   - `camera`, `mouse`, `scene`, `window`
   - `physics_handler`

2. **实体组件系统** (ECS 变体)
   - `Entity` 作为基础容器
   - `collider`, `scripts` 作为可附加组件

3. **装饰器模式**
   - `@every` - 定时执行
   - `@property_generator` - 属性生成

4. **观察者模式**
   - 输入事件分发
   - update/input 方法回调

5. **工厂模式**
   - `load_model()`, `load_texture()`
   - `Audio()` 创建音频对象

6. **策略模式**
   - 不同的 `collider` 类型
   - 不同的 `shader` 实现

### 11.2 架构特点

**优点**:
1. 简洁的 API - 单文件导入，极简使用
2. 高度封装 - 隐藏 Panda3D 复杂性
3. 统一抽象 - Entity 统一管理所有游戏对象
4. 灵活扩展 - scripts 系统允许任意逻辑附加
5. 热重载支持 - 开发时无需重启

**权衡**:
1. 性能 - Python 解释执行，性能不如 C++
2. 灵活性 - Entity "上帝类" 承担过多职责
3. 调试 - 单例和全局变量增加调试难度
4. 文档 - 某些模块缺少详细文档

---

## 12. 核心数据流

### 12.1 渲染流程

```
Main Loop (Ursina._update)
    ↓
Update Entities
    ↓
Panda3D Render Pipeline
    ↓
Draw to Screen
```

### 12.2 物理流程

```
Update Loop
    ↓
PhysicsHandler.update()
    ↓
BulletWorld.doPhysics(time.dt)
    ↓
Sync Transform to Entities
```

### 12.3 输入流程

```
OS Input
    ↓
Panda3D ButtonThrower
    ↓
Ursina.input()
    ↓
InputHandler.input()
    ↓
Distribute to Entities
```

---

## 13. 扩展点

### 13.1 自定义 Entity

```python
class MyEntity(Entity):
    def update(self):
        # 自定义更新逻辑
        pass
    
    def input(self, key):
        # 自定义输入处理
        pass
```

### 13.2 自定义 Script

```python
class MyScript(Script):
    def __init__(self, entity):
        super().__init__(entity)
    
    def update(self):
        # 附加到实体的逻辑
        pass
```

### 13.3 自定义 Prefab

```python
class MyPrefab(Entity):
    def __init__(self, **kwargs):
        super().__init__(
            model='cube',
            color=color.red,
            **kwargs
        )
        # 自定义初始化
```

---

## 14. 性能优化建议

1. **减少实体数量** - 合并可合并的静态对象
2. **使用烘焙光照** - 避免实时光照计算
3. **优化碰撞器** - 使用简单的碰撞器代替 MeshCollider
4. **使用 LOD** - 距离层次细节
5. **启用批处理** - 合并相同材质的网格
6. **避免每帧创建对象** - 对象池复用

---

## 15. 总结

Ursina 是一个精心设计的 Python 游戏引擎，通过简洁的 API 和统一的 Entity 系统，大大降低了游戏开发的门槛。其架构核心是：

1. **Ursina 主类** - 引擎入口和生命周期管理
2. **Entity 系统** - 统一的游戏对象抽象
3. **组件化设计** - collider、shader、scripts 等可附加组件
4. **预制体库** - 丰富的预定义游戏对象
5. **封装 Panda3D** - 隐藏底层复杂性

这种设计使开发者能够快速原型和开发游戏，同时也保留了足够的灵活性来构建复杂的游戏逻辑。对于 CubicWheelLoader 项目，可以基于这个架构设计类似的结构，根据项目需求调整和扩展。
