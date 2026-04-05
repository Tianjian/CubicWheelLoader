# 手柄操控升级设计文档

## 1. 项目现状分析

### 1.1 当前输入架构

当前游戏采用**硬编码键盘+鼠标**的输入方式，输入逻辑分散在多个模块中：

```
输入源                读取位置                    功能
────────────────────────────────────────────────────────
held_keys['w/s']     human_ctrl.py:25-34          前后移动
held_keys['a/d']     human_ctrl.py:18-21          左右旋转
held_keys['left mouse'] human_ctrl.py:37-39       射击
key == 'v'           camera_ctrl.py (无，未接入)   切换视角
key == 'tab'         main.py:28                   编辑器模式
key == 'gamepad ...'  (无)                         未实现
```

### 1.2 问题

| 问题 | 说明 |
|------|------|
| 输入分散 | 移动/旋转/射击的输入读取硬编码在各控制器内部 |
| 不可扩展 | 添加手柄需要修改每个控制器的 `update()` 方法 |
| 无输入抽象 | 没有统一的输入接口（键盘/鼠标/手柄共享） |
| 无死区处理 | 手柄摇杆需要模拟死区，当前没有 |
| 无手柄支持 | Ursina 有 `gamepad.py` 模块但未使用 |

### 1.3 手柄输入方案（已验证）

**实测结论：Panda3D 的 `InputDevice` API 在 Windows 上无法正常读取 Xbox 手柄的摇杆/按键数据**（设备能检测到，但 `getAxis`/`findAxis`/`getButtonEvents` 均不返回有效数据）。

**最终方案：直接调用 Windows XInput API（ctypes）**
- 绕过 Panda3D 和 SDL，完全不冲突
- 仅支持 Xbox 标准手柄（360/One/Series）
- 通过 `xinput1_4.dll` 读取完整状态（摇杆/扳机/按键/震动）
- 已在 `test_gamepad.py` 中验证通过

```python
import ctypes

class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ('wButtons', ctypes.c_ushort),       # 按键 bitmask
        ('bLeftTrigger', ctypes.c_ubyte),     # 0..255
        ('bRightTrigger', ctypes.c_ubyte),
        ('thumbLX', ctypes.c_short),          # -32768..32767
        ('thumbLY', ctypes.c_short),
        ('thumbRX', ctypes.c_short),
        ('thumbRY', ctypes.c_short),
    ]

class XINPUT_STATE(ctypes.Structure):
    _fields_ = [('dwPacketNumber', ctypes.c_uint), ('Gamepad', XINPUT_GAMEPAD)]

xinput = ctypes.windll.xinput1_4
state = XINPUT_STATE()
xinput.XInputGetState(0, ctypes.byref(state))  # 0 = 成功, 1167 = 未连接
```

---

## 2. 设计目标

### 2.1 核心原则

1. **输入抽象层** — 统一键盘/鼠标/手柄的输入读取，控制器只读抽象接口
2. **最小侵入** — 不改变 AI 逻辑，不改变游戏流程，只重构输入部分
3. **热插拔** — 手柄连接/断开时自动切换，无需重启
4. **手感一致** — 摇杆模拟死区、灵敏度可调，与键盘操作体验对齐

### 2.2 手柄按键映射（Xbox 标准布局）

| 操作 | 键盘/鼠标 | 手柄 |
|------|-----------|------|
| 前进 | W | 左摇杆 ↑ (left stick y > 0) |
| 后退 | S | 左摇杆 ↓ (left stick y < 0) |
| 左转 | A | 左摇杆 ← (left stick x < 0) |
| 右转 | D | 左摇杆 → (left stick x > 0) |
| 射击 | 鼠标左键 | 右扳机 (right trigger > 0.3) |
| 切换视角 | V | X 键 (face_x) |
| 开始 | 点击 START | Start 键 |

---

## 3. 架构设计

### 3.1 新增模块

```
arena/
├── input_manager.py      # [新] 输入抽象层，统一键盘/手柄
├── human_ctrl.py          # [改] 改为从 input_manager 读取
├── game_manager.py        # [改] 接入手柄输入回调
└── constants.py           # [改] 新增手柄配置
```

### 3.2 InputManager 架构

```python
class InputManager(Entity):
    """输入管理器 — 统一键盘/鼠标/手柄输入"""

    # ========== 输出接口（控制器只需读这些） ==========
    move_forward: float      # -1 ~ 1，正值前进
    move_sideways: float     # -1 ~ 1，正值右转（坦克式）
    shoot: float             # 0 ~ 1，> 0 表示射击
    action: bool             # 瞬时动作（切换视角等）

    # ========== 内部逻辑 ==========
    gamepad_connected: bool
    gamepad_deadzone: float  # 死区阈值
```

控制器不再直接读取 `held_keys`，而是通过 `input_manager.move_forward` 等属性获取统一输入。

### 3.3 数据流

```
键盘 held_keys ──┐
                   ├──→ InputManager.update() ──→ move_forward / move_sideways / shoot
手柄摇杆 ────────┘         (归一化、死区处理)
                              
input(key) ────────→ InputManager.input() ──→ action (切换视角)
```

---

## 4. 模块详细设计

### 4.1 InputManager（arena/input_manager.py）

```python
from ursina import *
from panda3d.core import InputDevice, InputDeviceManager
from arena.constants import Config


class InputManager(Entity):
    """输入管理器 — 统一键盘/鼠标/手柄输入"""

    def __init__(self):
        super().__init__()
        self.gamepad_connected = False
        self.gamepad_deadzone = Config.GAMEPAD_DEADZONE

        # 手柄灵敏度
        self.gamepad_rotation_speed = Config.GAMEPAD_ROTATION_SPEED
        self.gamepad_move_speed = Config.GAMEPAD_MOVE_SPEED

        # 输出接口（归一化值）
        self.move_forward = 0.0    # -1~1，正=前进
        self.move_sideways = 0.0   # -1~1，正=右转
        self.shoot = 0.0           # 0~1，>0.3 触发射击
        self.action = False        # 瞬时动作

        # 手柄初始化
        self._init_gamepad()

    def _init_gamepad(self):
        """初始化手柄（兼容 Ursina gamepad.py 的 bug）"""
        try:
            devices = base.devices.getDevices(InputDevice.DeviceClass.gamepad)
            if devices:
                self.gamepad_connected = True
                self.gamepad = devices[0]
                # 注册按键映射
                buttons = {
                    'face_a': 'a', 'face_b': 'b',
                    'face_x': 'x', 'face_y': 'y',
                    'start': 'start', 'back': 'back',
                }
                for original, new in buttons.items():
                    base.accept(f'gamepad-{original}', base.input,
                               extraArgs=[f'gamepad {new}'])
                print(f'Gamepad connected: {self.gamepad.name}')
            else:
                print('No gamepad detected, using keyboard/mouse')
        except Exception as e:
            print(f'Gamepad init failed: {e}')
            self.gamepad_connected = False

    def update(self):
        """每帧读取输入，输出归一化值"""
        move_fwd = 0.0
        move_side = 0.0
        shoot_val = 0.0
        self.action = False

        if self.gamepad_connected:
            move_fwd, move_side, shoot_val = self._read_gamepad()

        # 叠加键盘输入（手柄和键盘可同时使用）
        kb_fwd, kb_side, kb_shoot = self._read_keyboard()
        # 取绝对值更大的那个（或直接叠加，取决于设计）
        move_fwd = max(move_fwd, kb_fwd)
        move_side = max(move_side, kb_side)
        shoot_val = max(shoot_val, kb_shoot)

        self.move_forward = move_fwd
        self.move_sideways = move_side
        self.shoot = shoot_val

    def _read_keyboard(self):
        """读取键盘/鼠标输入"""
        fwd = 0.0
        side = 0.0
        shoot = 0.0

        if held_keys['w']:
            fwd = 1.0
        elif held_keys['s']:
            fwd = -1.0

        if held_keys['a']:
            side = -1.0
        elif held_keys['d']:
            side = 1.0

        if held_keys['left mouse']:
            shoot = 1.0

        return fwd, side, shoot

    def _read_gamepad(self):
        """读取手柄输入"""
        try:
            gamepad = self.gamepad
            fwd = 0.0
            side = 0.0
            shoot = 0.0

            # 左摇杆 Y 轴（前进/后退）
            y = gamepad.findAxis(InputDevice.Axis.left_y).value
            if abs(y) > self.gamepad_deadzone:
                fwd = -y  # Panda3D Y 轴反向
            else:
                fwd = 0.0

            # 左摇杆 X 轴（左转/右转）
            x = gamepad.findAxis(InputDevice.Axis.left_x).value
            if abs(x) > self.gamepad_deadzone:
                side = x
            else:
                side = 0.0

            # 右扳机（射击）
            rt = gamepad.findAxis(InputDevice.Axis.right_trigger).value
            if rt > 0.3:
                shoot = rt

            return fwd, side, shoot
        except Exception:
            self.gamepad_connected = False
            return 0.0, 0.0, 0.0

    def input(self, key):
        """处理瞬时按键输入"""
        if key == 'gamepad x':  # X 键 → 切换视角
            self.action = True
        elif key == 'v':        # V 键 → 切换视角
            self.action = True
```

### 4.2 HumanController 改造（arena/human_ctrl.py）

```python
class HumanController:
    """人类玩家控制器（支持键盘 + 手柄）"""

    def __init__(self, player, input_manager):
        self.player = player
        self.input_manager = input_manager
        self.move_speed = Config.HUMAN_MOVE_SPEED
        self.rotation_speed = Config.HUMAN_ROTATION_SPEED

    def update(self):
        if self.player.state.value not in ('alive', 'respawning'):
            return

        im = self.input_manager

        # 旋转（坦克式：左右 = 转向）
        if abs(im.move_sideways) > 0.1:
            rotation = im.move_sideways * self.rotation_speed * time.dt
            # 手柄摇杆值是连续的 [-1,1]，需要映射到旋转速度
            self.player.rotation_y += rotation

        # 前后移动
        if abs(im.move_forward) > 0.1:
            move_amount = im.move_forward * self.move_speed * time.dt
            direction = self.player.forward if move_amount > 0 else -self.player.forward
            ray = raycast(self.player.position, direction,
                          distance=abs(move_amount), ignore=(self.player,))
            if not ray.hit:
                self.player.position += direction * abs(move_amount)

        # 射击
        if im.shoot > 0.3:
            shoot_dir = self.player.forward.normalized()
            self.player.weapon.shoot(shoot_dir)
```

### 4.3 GameManager 改造（arena/game_manager.py）

```python
def start_match(self, selected_player_id):
    # ... 创建玩家 ...

    # 创建输入管理器
    from arena.input_manager import InputManager
    self.input_manager = InputManager()

    # 将 input_manager 传递给人类控制器
    for i, player in enumerate(self.players):
        if i == selected_player_id:
            player.controller = HumanController(player, self.input_manager)
            self.human_player = player
        else:
            player.controller = AIController(player)

def update(self):
    if self.state == GameState.PLAYING:
        # action 事件处理（视角切换等）
        if self.input_manager.action:
            self.camera_controller.toggle_distance()
            self.input_manager.action = False

        if self.human_player:
            hud.update_player_info(self.human_player)
```

### 4.4 Constants 新增（arena/constants.py）

```python
class Config:
    # ... 现有配置 ...

    # 手柄
    GAMEPAD_DEADZONE = 0.15         # 摇杆死区（0~1）
    GAMEPAD_ROTATION_SPEED = 120    # 摇杆旋转速度（度/秒）
    GAMEPAD_MOVE_SPEED = 8          # 摇杆移动速度
    GAMEPAD_SHOOT_THRESHOLD = 0.3   # 扳机射击阈值
```

### 4.5 HUD 更新（arena/hud.py）

```python
# 在操作提示中添加手柄按键说明
self.controls_text = Text(
    text='Keyboard: WASD-Move  LMB-Shoot  V-View\n'
         'Gamepad:  LS-Move   RT-Shoot   X-View',
    ...
)

# 手柄连接状态指示器
self.gamepad_indicator = Text(
    text='[GAMEPAD]',
    position=(0.5, -0.42),
    scale=0.8,
    color=color.green,
    parent=camera.ui,
    enabled=False  # 初始隐藏
)
```

---

## 5. 文件改动清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `arena/input_manager.py` | **新增** | 输入抽象层，统一键盘/手柄 |
| `arena/human_ctrl.py` | 修改 | 从 `held_keys` 改为从 `input_manager` 读取 |
| `arena/game_manager.py` | 修改 | 创建 `InputManager`，传递给控制器；处理 action 事件 |
| `arena/constants.py` | 修改 | 新增手柄配置参数 |
| `arena/hud.py` | 修改 | 更新操作提示，添加手柄状态指示器 |
| `arena/camera_ctrl.py` | 不变 | 视角切换通过 GameManager 间接调用 |
| `arena/ai_ctrl.py` | 不变 | AI 不受输入系统影响 |
| `arena/weapon.py` | 不变 | 射击接口不变 |

---

## 6. 实现步骤

### Phase 1：输入抽象层

- [ ] 创建 `arena/input_manager.py`
- [ ] 实现键盘输入读取（`_read_keyboard`）
- [ ] 实现手柄初始化（`_init_gamepad`），处理 Ursina gamepad bug
- [ ] 实现手柄输入读取（`_read_gamepad`），含死区处理
- [ ] 实现输入合并逻辑（`update`）
- [ ] 在 `constants.py` 添加手柄配置

### Phase 2：控制器适配

- [ ] 修改 `HumanController` 接收 `input_manager` 参数
- [ ] 替换 `held_keys` 读取为 `input_manager` 属性
- [ ] 适配摇杆连续值（非 0/1 开关）
- [ ] 修改 `GameManager` 创建和管理 `InputManager`
- [ ] 在 `input()` 中处理手柄瞬时按键

### Phase 3：UI 与反馈

- [ ] 更新 HUD 操作提示（键盘 + 手柄双显示）
- [ ] 添加手柄连接/断开状态指示器
- [ ] 射击使用扳机压力值控制射速（可选）

### Phase 4：测试

- [ ] 纯键盘测试（确保不退化）
- [ ] 键盘 + 手柄同时输入测试
- [ ] 无手柄启动测试（优雅降级）
- [ ] 手柄热插拔测试
- [ ] 摇杆死区测试（小幅度不应触发移动）
- [ ] AI 玩家不受影响测试

---

## 7. 已知风险与应对

| 风险 | 影响 | 应对方案 |
|------|------|----------|
| Ursina gamepad.py 有 `base` 未定义 bug | 直接 import 会崩溃 | 手动实现手柄初始化，不依赖 gamepad.py |
| 手柄未连接时调用 Panda3D API | 报错 | try/except 包裹，优雅降级为键盘模式 |
| 摇杆漂移（静止时值不为 0） | 角色自动移动 | 0.15 死区阈值 + 内置 0.1 死区 |
| Panda3D `findAxis` 在无手柄时崩溃 | 启动失败 | 初始化前检查 `devices` 是否非空 |
| 键盘和手柄输入同时生效 | 操作混乱 | 取较大值策略（或可切换输入源） |
| 不同手柄品牌按键映射差异 | 按键不响应 | Xbox 标准布局，覆盖绝大多数手柄 |

---

## 8. 扩展方向（未来版本）

- **输入源切换** — 在 HUD 中提供键盘/手柄模式切换
- **手柄振动反馈** — 射击时、被击中时触发振动
- **手柄菜单导航** — 角色选择界面支持手柄方向键 + A 键确认
- **手柄配置界面** — 死区、灵敏度可视化调节
- **触摸屏支持** — 移动端虚拟摇杆（Ursina 支持 mobile）
- **多手柄本地多人** — 4 个手柄控制 4 个角色（本地对战模式）
