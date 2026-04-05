# 第三人称视角升级设计文档

## 1. 升级目标

将当前的"编辑器模式"升级为"第三人称视角模式"，允许玩家从第三人称视角进行游戏，并保持射击功能的正常工作。

### 当前状态

- **Tab 键** → 切换编辑器/游玩模式
- **编辑器模式** → 禁用玩家控制，仅用于场景观察
- **游玩模式** → 第一人称视角，正常游戏

### 升级后状态

- **V 键** → 在第一人称/第三人称视角之间切换
- **第一人称模式** → 当前游戏状态
- **第三人称模式** → 摄像机在玩家身后，可以看到玩家模型，正常游戏

## 2. 第三人称视角实现原理

### 2.1 相机位置设置

```
第一人称 (FPS)：
    相机在玩家头部位置
    player.camera.position ≈ player.head_position

第三人称 (TPS)：
    相机在玩家身后上方
    camera.position = player.position + offset
    camera.look_at(player.head_position)

相机偏移量：
    后方距离: 4-6 单位
    上方高度: 2-3 单位
```

### 2.2 相机跟随模式

```python
# 方式1：固定偏移（简单）
camera.position = player.position + offset
camera.look_at(player.position + Vec3(0, 2, 0))

# 方式2：平滑跟随（推荐）
def update():
    target_pos = player.position + offset
    camera.position = lerp(camera.position, target_pos, 10 * time.dt)
    camera.look_at(player.position + Vec3(0, 2, 0))

# 方式3：轨道相机（高级）
# 支持鼠标旋转相机位置
```

### 2.3 射击方向处理

```python
# FPS 模式：从相机方向射击
direction = camera.forward

# TPS 模式：从相机到准星的方向射击
if mouse.world_position:  # 3D 空间中的鼠标位置
    direction = (mouse.world_position - gun.world_position).normalized()
else:
    direction = camera.forward
```

## 3. 设计方案

### 3.1 视角管理器

```python
class CameraMode(Enum):
    FIRST_PERSON = "first_person"
    THIRD_PERSON = "third_person"

class CameraController(Entity):
    """相机控制器"""
    def __init__(self, target_entity):
        super().__init__()
        self.target = target_entity  # 玩家实体
        self.mode = CameraMode.FIRST_PERSON
        self.tps_offset = Vec3(0, 3, -5)  # TPS 相机偏移
        self.fov = {
            CameraMode.FIRST_PERSON: 90,
            CameraMode.THIRD_PERSON: 60
        }

    def toggle_mode(self):
        """切换视角模式"""
        if self.mode == CameraMode.FIRST_PERSON:
            self.set_third_person()
        else:
            self.set_first_person()

    def set_first_person(self):
        """设置为第一人称"""
        self.mode = CameraMode.FIRST_PERSON

        # 显示玩家模型（武器）
        player.visible = False  # 隐藏玩家身体
        gun.enabled = True      # 显示武器

        # 设置相机位置到玩家头部
        camera.parent = player
        camera.position = (0, 0, 0)
        camera.rotation = (0, 0, 0)

        # FOV
        camera.fov = self.fov[CameraMode.FIRST_PERSON]

    def set_third_person(self):
        """设置为第三人称"""
        self.mode = CameraMode.THIRD_PERSON

        # 显示玩家模型，隐藏武器
        player.visible = True   # 显示玩家身体
        gun.enabled = False     # 隐藏武器（或移到肩膀位置）

        # 相机独立于玩家
        camera.parent = scene
        self.update_camera()

        # FOV
        camera.fov = self.fov[CameraMode.THIRD_PERSON]

    def update(self):
        """每帧更新"""
        if self.mode == CameraMode.THIRD_PERSON:
            self.update_camera()

    def update_camera(self):
        """更新第三人称相机位置"""
        # 目标位置：玩家身后上方
        target_position = self.target.position + self.tps_offset

        # 平滑移动相机
        camera.position = lerp(camera.position, target_position, 10 * time.dt)

        # 相机看向玩家头部
        look_target = self.target.position + Vec3(0, 1.5, 0)
        camera.look_at(look_target)

    def get_shoot_direction(self):
        """获取射击方向"""
        if self.mode == CameraMode.FIRST_PERSON:
            return camera.forward
        else:
            # TPS 模式：从准星射击
            if mouse.world_position:
                return (mouse.world_position - gun.world_position).normalized()
            return camera.forward
```

### 3.2 射击方向修正

```python
class Weapon(Entity):
    def shoot(self, target_direction=None):
        if self.on_cooldown:
            return

        # 获取射击方向
        if target_direction is None:
            # 从相机控制器获取方向
            if camera_controller.mode == CameraMode.THIRD_PERSON:
                # 射线检测到准星位置
                if mouse.world_position:
                    target_direction = (mouse.world_position - self.world_position).normalized()
                else:
                    target_direction = camera.forward
            else:
                target_direction = camera.forward

        # 创建子弹
        bullet = Bullet(
            start_position=self.muzzle_flash.world_position,
            direction=target_direction,
            damage=self.bullet_damage,
            speed=self.bullet_speed
        )

        # ... 其余射击逻辑
```

### 3.3 准星系统

```python
class Crosshair(Entity):
    """准星"""
    def __init__(self):
        super().__init__(
            parent=camera.ui,
            model='quad',
            scale=0.02,
            color=color.white,
            origin=(0, 0)
        )
        self.active = True

    def update(self):
        # 更新准星位置到鼠标位置
        if self.active:
            self.position = mouse.normalized

    def show(self):
        self.enabled = True
        self.active = True

    def hide(self):
        self.enabled = False
        self.active = False
```

### 3.4 输入处理

```python
def input(key):
    # V 键切换视角
    if key == 'v':
        camera_controller.toggle_mode()

    # Tab 键切换编辑器模式（保留原有功能）
    if key == 'tab':
        editor_camera.enabled = not editor_camera.enabled
        player.visible_self = editor_camera.enabled
        player.cursor.enabled = not editor_camera.enabled
        gun.enabled = not editor_camera.enabled
        mouse.locked = not editor_camera.enabled
        editor_camera.position = player.position
        application.paused = editor_camera.enabled
```

## 4. 实现步骤

### 第一步：创建相机控制器

- [ ] 定义 `CameraMode` 枚举
- [ ] 创建 `CameraController` 类
- [ ] 实现第一人称模式设置
- [ ] 实现第三人称模式设置
- [ ] 实现视角切换方法

### 第二步：实现相机跟随

- [ ] 实现第三人称相机位置更新
- [ ] 实现相机看向玩家
- [ ] 实现平滑过渡（lerp）
- [ ] 调整相机偏移参数

### 第三步：修正射击方向

- [ ] 修改 `Weapon.shoot()` 方法
- [ ] 添加射击方向计算逻辑
- [ ] 实现准星射线检测
- [ ] 测试两种模式的射击精度

### 第四步：实现准星系统

- [ ] 创建 `Crosshair` 类
- [ ] 实现准星跟随鼠标
- [ ] 在 TPS 模式启用，FPS 模式隐藏

### 第五步：更新输入处理

- [ ] 添加 V 键切换视角
- [ ] 更新操作提示文字
- [ ] 保留 Tab 键编辑器功能

### 第六步：测试和调优

- [ ] 测试第一人称模式射击
- [ ] 测试第三人称模式射击
- [ ] 测试视角切换平滑度
- [ ] 调整相机偏移和 FOV
- [ ] 调整射击精度

## 5. 关键技术点

### 5.1 相机父子关系

```python
# FPS 模式：相机是玩家的子对象
camera.parent = player
camera.position = (0, 0, 0)  # 玩家头部位置

# TPS 模式：相机是场景的子对象
camera.parent = scene
camera.position = player.position + offset  # 玩家身后
```

### 5.2 坐标空间转换

```python
# 局部坐标 → 世界坐标
world_position = entity.world_position

# 相对方向 → 世界方向
world_forward = entity.world_forward

# 鼠标 3D 位置（射线检测）
if mouse.hovered_entity:
    world_point = mouse.world_point
```

### 5.3 射击方向计算

```python
# FPS：简单
direction = camera.forward

# TPS：复杂（需要准星）
if mouse.world_position:
    # 从枪口到鼠标指向的 3D 位置
    direction = (mouse.world_position - gun.world_position).normalized()
else:
    direction = camera.forward
```

### 5.4 平滑过渡

```python
# 位置平滑
camera.position = lerp(
    camera.position,
    target_position,
    lerp_speed * time.dt
)

# FOV 平滑过渡
camera.animate_fov(target_fov, duration=0.3)
```

## 6. UI 更新

### 6.1 操作提示更新

```
Controls:

WASD - Move
Space - Jump
Mouse - Look around
Left Click - Shoot
V - Toggle FPS/TPS View
Tab - Toggle Editor Mode
```

### 6.2 当前视角指示

```python
view_mode_text = Text(
    text='View: FPS',
    position=(0, .45),
    parent=camera.ui,
    color=color.yellow
)

def update():
    if camera_controller.mode == CameraMode.FIRST_PERSON:
        view_mode_text.text = 'View: FPS'
    else:
        view_mode_text.text = 'View: TPS'
```

## 7. 高级功能

### 7.1 轨道相机（可选）

```python
class OrbitCameraController(CameraController):
    """轨道相机 - 支持鼠标旋转"""
    def __init__(self, target_entity):
        super().__init__(target_entity)
        self.orbit_angle = 0      # 水平旋转角度
        self.orbit_elevation = 30  # 垂直角度
        self.orbit_distance = 5      # 距离

    def update(self):
        if self.mode == CameraMode.THIRD_PERSON:
            # 鼠标右键旋转相机
            if held_keys['right mouse']:
                self.orbit_angle += mouse.velocity[0] * 100 * time.dt
                self.orbit_elevation += mouse.velocity[1] * 100 * time.dt

            # 计算相机位置
            angle_rad = self.orbit_angle * math.pi / 180
            elev_rad = self.orbit_elevation * math.pi / 180

            x = math.sin(angle_rad) * math.cos(elev_rad) * self.orbit_distance
            y = math.sin(elev_rad) * self.orbit_distance
            z = math.cos(angle_rad) * math.cos(elev_rad) * self.orbit_distance

            camera.position = self.target.position + Vec3(x, y, z)
            camera.look_at(self.target.position + Vec3(0, 1.5, 0))
```

### 7.2 玩家模型可见性

```python
# FPS 模式：隐藏玩家身体和头部
if camera_controller.mode == CameraMode.FIRST_PERSON:
    # 仅显示手臂和武器
    player.model = 'invisible'
    player.arms.visible = True
    gun.visible = True

# TPS 模式：显示完整玩家模型
else:
    player.model = 'player'
    player.arms.visible = False
    gun.visible = True  # 或移到肩膀位置
```

### 7.3 相机碰撞检测

```python
def update_camera(self):
    """更新相机并处理碰撞"""
    target_position = self.target.position + self.tps_offset

    # 射线检测相机路径
    hit_info = raycast(
        self.target.position + Vec3(0, 1.5, 0),
        target_position - self.target.position,
        distance=self.tps_offset.length(),
        ignore=(self.target,)
    )

    # 如果有障碍物，相机移动到障碍物前
    if hit_info.hit:
        camera.position = hit_info.world_point
    else:
        camera.position = lerp(camera.position, target_position, 10 * time.dt)
```

## 8. 性能优化

### 8.1 减少射线检测

```python
# 只在射击时检测准星
def update():
    if held_keys['left mouse']:
        # 射击时检测
        pass
    else:
        # 非射击时不检测
        pass
```

### 8.2 优化相机更新频率

```python
# 每隔几帧更新一次相机（可选）
frame_count = 0
def update():
    global frame_count
    frame_count += 1
    if frame_count % 2 == 0:  # 每2帧更新一次
        camera_controller.update()
```

## 9. 调试和测试

### 9.1 调试信息

```python
debug_text = Text(
    text='',
    position=(-.85, -.45),
    parent=camera.ui
)

def update():
    debug_text.text = (
        f'Mode: {camera_controller.mode.value}\n'
        f'Camera Pos: {camera.position}\n'
        f'Player Pos: {player.position}\n'
        f'Shoot Dir: {camera_controller.get_shoot_direction()}'
    )
```

### 9.2 相机位置可视化

```python
# 可视化相机偏移
if application.development_mode:
    camera_offset_marker = Entity(
        model='sphere',
        scale=0.2,
        color=color.blue,
        parent=player,
        position=camera_controller.tps_offset
    )
```

## 10. 已知问题和解决方案

### 问题1：第三人称射击精度低
**解决方案**：
- 使用 `mouse.world_position` 精确计算方向
- 实现准星射线检测
- 考虑子弹下坠补偿

### 问题2：相机穿墙
**解决方案**：
- 相机路径射线检测
- 碰到障碍物时调整位置
- 增加相机防抖动

### 问题3：视角切换时相机跳跃
**解决方案**：
- 使用 `animate_position` 平滑过渡
- FOV 过渡动画
- 延迟父子关系切换

### 问题4：第三人称时武器显示问题
**解决方案**：
- 武器移到玩家肩膀位置
- 或隐藏武器，使用发射动画
- 或使用完整的玩家模型

## 11. 总结

本次升级将简单的编辑器模式切换升级为完整的第一/第三人称视角系统：

1. **更流畅的体验** - 玩家可以自由切换视角
2. **保留所有功能** - 射击、移动、跳跃在两种模式下都正常工作
3. **可扩展性** - 易于添加更多相机模式
4. **视觉提升** - 第三人称提供更好的游戏体验

关键改进：
- 相机控制器统一管理
- 射击方向智能计算
- 准星系统精确瞄准
- 平滑的视角切换

升级后，玩家可以：
- 按 V 键在 FPS/TPS 之间切换
- 在第三人称模式下正常射击
- 享受更丰富的游戏体验
