# 蓝方相机视角不对称问题

## 问题

当玩家选择蓝方角色时，相机位置和朝向与红方相同，没有沿 z 轴对称。

红方 base 在 z=-17，初始面朝 +z；蓝方 base 在 z=17，初始面朝 -z。相机应在玩家身后跟随，但当前所有偏移量 z 分量的正负号都是硬编码的。

## 涉及代码

文件：`arena/camera_ctrl.py`

### 修改点 1：`__init__` — 添加 `z_sign` 属性

在第 20 行后添加：

```python
from arena.constants import Team

# 根据队伍决定 z 轴偏移方向：红方面朝 +z，蓝方面朝 -z
self.z_sign = 1 if self.target.team == Team.RED else -1
```

同时第 2 行 import 改为：
```python
from arena.constants import CameraMode, Config, Team
```

### 修改点 2：`_update_camera()` — 第 75、78 行

```python
# 原：
target_position = self.target.position + Vec3(0, self.camera_height, -self.camera_distance)
look_target = self.target.position + Vec3(0, 1.5, 10)

# 改为：
target_position = self.target.position + Vec3(0, self.camera_height, -self.camera_distance * self.z_sign)
look_target = self.target.position + Vec3(0, 1.5, 10 * self.z_sign)
```

### 修改点 3：`set_third_person()` — 第 52、54 行

```python
# 原：
target_position = self.target.position + Vec3(0, self.camera_height, -self.camera_distance)
look_target = self.target.position + Vec3(0, 1.5, 10)

# 改为：
target_position = self.target.position + Vec3(0, self.camera_height, -self.camera_distance * self.z_sign)
look_target = self.target.position + Vec3(0, 1.5, 10 * self.z_sign)
```

## 效果验证

| 队伍 | z_sign | 相机位置偏移 z | 看向偏移 z | 效果 |
|------|--------|---------------|-----------|------|
| RED  | +1     | -distance     | +10       | 相机在身后，看向前方（+z） |
| BLUE | -1     | +distance     | -10       | 相机在身后，看向前方（-z） |
