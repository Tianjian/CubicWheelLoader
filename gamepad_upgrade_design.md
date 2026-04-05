# 手柄操控升级设计文档

## 1. 项目现状分析

### 1.1 当前输入架构

当前游戏采用**硬编码键盘+鼠标**的输入方式，输入逻辑分散在多个模块中：

```
输入源                读取位置                    功能
────────────────────────────────────────────────────────
held_keys['w/s']     human_ctrl.py:24-34          前后移动（固定速度 8）
held_keys['a/d']     human_ctrl.py:18-21          左右旋转（固定速度 120）
held_keys['left mouse'] human_ctrl.py:37-39       射击（开关式）
```

### 1.2 问题

| 问题 | 说明 |
|------|------|
| 输入分散 | 移动/旋转/射击的输入读取硬编码在 HumanController 内部 |
| 不可扩展 | 添加手柄需要修改 HumanController |
| 无输入抽象 | 没有统一的输入接口（键盘/鼠标/手柄共享） |
| 无模拟量 | 键盘只有 0/1，手柄摇杆需要连续值支持 |
| 无手柄支持 | Panda3D 的 InputDevice API 在 Windows 上无法读取 Xbox 手柄数据 |

### 1.3 手柄输入方案（已验证）

**实测结论：Panda3D 的 `InputDevice` API 在 Windows 上无法正常读取 Xbox 手柄的摇杆/按键数据**（设备能检测到，但 `getAxis`/`findAxis`/`getButtonEvents` 均不返回有效数据。pygame 的 SDL 后端也被 Panda3D 锁定干扰。）

**最终方案：直接调用 Windows XInput API（ctypes）**
- 绕过 Panda3D 和 SDL，完全不冲突
- 仅支持 Xbox 标准手柄（360/One/Series），Windows 原生支持无需驱动
- 通过 `xinput1_4.dll` 读取完整状态（摇杆/扳机/按键/震动）
- 已在 `test_gamepad.py` 中验证，Xbox One For Windows 手柄全部功能正常

```python
import ctypes

class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ('wButtons', ctypes.c_ushort),       # 按键 bitmask (16 bits)
        ('bLeftTrigger', ctypes.c_ubyte),     # 0..255
        ('bRightTrigger', ctypes.c_ubyte),
        ('thumbLX', ctypes.c_short),          # -32768..32767
        ('thumbLY', ctypes.c_short),
        ('thumbRX', ctypes.c_short),
        ('thumbRY', ctypes.c_short),
    ]

class XINPUT_STATE(ctypes.Structure):
    _fields_ = [('dwPacketNumber', ctypes.c_uint), ('Gamepad', XINPUT_GAMEPAD)]

xinput = ctypes.windll.xinput1_4  # Win10+ fallback: xinput1_3, xinput9_1_0
state = XINPUT_STATE()
xinput.XInputGetState(0, ctypes.byref(state))  # 0=成功, 1167=未连接
```

**Xbox One For Windows 实测数据：**
- 设备名: `Controller (Xbox One For Windows)`
- 6 轴: LX, LY, RX, RY, LT, RT
- 16 按钮: A B X Y LB RB Back Start LS RS DPad(4) Home
- 1 Hat (D-Pad)
- 轴 4/5 (LT/RT) 零位 = -1.0，需转换为 0..1
- 左摇杆 Y 轴有约 0.05 的静止漂移，需死区处理 (>7849 / 32767 ≈ 0.24)

---

## 2. 设计目标

### 2.1 核心原则

1. **输入抽象层** — 统一键盘/鼠标/手柄的输入读取，控制器只读抽象接口
2. **最小侵入** — 不改变 AI 逻辑，不改变游戏流程，只重构输入部分
3. **模拟量支持** — 摇杆/扳机值直接映射到速度，杆量越大速度越快
4. **热插拔** — 手柄连接/断开时自动切换，无需重启
5. **无手柄时零影响** — 无手柄时完全退化为键盘模式

### 2.2 手柄按键映射（Xbox 标准布局）

| 操作 | 键盘/鼠标 | 手柄 |
|------|-----------|------|
| 前进 | W | **左摇杆 ↑** (thumbLY > 0) |
| 后退 | S | **左摇杆 ↓** (thumbLY < 0) |
| 左转 | A | **右摇杆 ←** (thumbRX < 0) |
| 右转 | D | **右摇杆 →** (thumbRX > 0) |
| 射击 | 鼠标左键 | **左扳机 LT** (bLeftTrigger > 阈值) |
| 切换视角 | V | X 键 (face_x) |

**设计说明：**
- 左摇杆控制移动（与主流 TPS 游戏一致）
- 右摇杆控制视角旋转（双摇杆操作更精确）
- 左扳机射击（符合 FPS/TPS 习惯，LT 更自然）
- 速度与杆量线性相关（摇杆推一半 = 一半速度）

---

## 3. 架构设计

### 3.1 新增/修改模块

```
arena/
├── xinput.py             # [新] XInput ctypes 封装（平台相关层）
├── input_manager.py      # [新] 输入抽象层，统一键盘/手柄
├── human_ctrl.py          # [改] 改为从 input_manager 读取
├── game_manager.py        # [改] 创建 InputManager，传递给控制器
├── constants.py           # [改] 新增手柄配置
└── hud.py                # [改] 更新操作提示
```

### 3.2 InputManager 架构

```python
class InputManager(Entity):
    """输入管理器 — 统一键盘/鼠标/手柄输入"""

    # ========== 输出接口（控制器只需读这些） ==========
    move_forward: float      # -1 ~ 1，正值前进（杆量 = 速度比例）
    move_sideways: float     # -1 ~ 1，正值右转（杆量 = 转速比例）
    shoot: float             # 0 ~ 1，> 0 表示射击（扳机压力）
    action: bool             # 瞬时动作（切换视角等，消费型）

    # ========== 内部状态 ==========
    gamepad_connected: bool
```

控制器不再直接读取 `held_keys`，而是通过 `input_manager.move_forward` 等属性获取统一输入。

### 3.3 数据流

```
键盘 held_keys ──┐
                   ├──→ InputManager.update() ──→ move_forward / move_sideways / shoot
XInput 状态  ────┘         (归一化、死区处理、杆量映射)

input(key) ────────→ InputManager.input() ──→ action (切换视角)
```

### 3.4 杆量到速度的映射

```python
# 键盘模式（离散）：W 按下 = move_forward = 1.0 → 固定速度 8
# 手柄模式（连续）：左摇杆推到 50% = move_forward = 0.5 → 速度 4

actual_speed = move_forward * HUMAN_MOVE_SPEED    # 键盘: 8, 手柄: 0~8
actual_rotation = move_sideways * HUMAN_ROTATION_SPEED  # 键盘: 120, 手柄: 0~120
```

---

## 4. 模块详细设计

### 4.1 XInput 封装（arena/xinput.py）

独立模块，封装 Windows XInput API，提供平台无关的读取接口。

```python
"""
Windows XInput API 封装
仅支持 Xbox 标准手柄（360/One/Series），Windows 原生支持。
"""
import ctypes
import sys

# XInput 结构体
class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ('wButtons', ctypes.c_ushort),
        ('bLeftTrigger', ctypes.c_ubyte),
        ('bRightTrigger', ctypes.c_ubyte),
        ('thumbLX', ctypes.c_short),
        ('thumbLY', ctypes.c_short),
        ('thumbRX', ctypes.c_short),
        ('thumbRY', ctypes.c_short),
    ]

class XINPUT_STATE(ctypes.Structure):
    _fields_ = [('dwPacketNumber', ctypes.c_uint), ('Gamepad', XINPUT_GAMEPAD)]

class XINPUT_VIBRATION(ctypes.Structure):
    _fields_ = [('wLeftMotorSpeed', ctypes.c_ushort), ('wRightMotorSpeed', ctypes.c_ushort)]

# 按键位掩码
BUTTONS = {
    'UP': 0x0001, 'DOWN': 0x0002, 'LEFT': 0x0004, 'RIGHT': 0x0008,
    'START': 0x0010, 'BACK': 0x0020, 'LS': 0x0040, 'RS': 0x0080,
    'LB': 0x0100, 'RB': 0x0200,
    'A': 0x1000, 'B': 0x2000, 'X': 0x4000, 'Y': 0x8000,
}

# 常量
MAX_AXIS = 32767
STICK_DEADZONE = 7849      # XInput 推荐死区
TRIGGER_THRESHOLD = 30     # 0..255

# DLL 加载
if sys.platform == 'win32':
    _dll = None
    for name in ('xinput1_4', 'xinput1_3', 'xinput9_1_0'):
        try:
            _dll = ctypes.windll[name]
            break
        except OSError:
            continue


def is_available() -> bool:
    """检查 XInput 是否可用"""
    return _dll is not None


def get_state(controller=0) -> dict | None:
    """
    读取手柄状态。返回 None 表示未连接或平台不支持。
    返回值:
        {
            'lx': float, 'ly': float,   # 左摇杆 (-1..1)
            'rx': float, 'ry': float,   # 右摇杆 (-1..1)
            'lt': float, 'rt': float,   # 扳机 (0..1)
            'buttons': set[str],        # 当前按下的按键名
        }
    """
    if not _dll:
        return None
    state = XINPUT_STATE()
    result = _dll.XInputGetState(controller, ctypes.byref(state))
    if result != 0:
        return None
    g = state.Gamepad
    lx = g.thumbLX / MAX_AXIS if abs(g.thumbLX) > STICK_DEADZONE else 0.0
    ly = -g.thumbLY / MAX_AXIS if abs(g.thumbLY) > STICK_DEADZONE else 0.0
    rx = g.thumbRX / MAX_AXIS if abs(g.thumbRX) > STICK_DEADZONE else 0.0
    ry = -g.thumbRY / MAX_AXIS if abs(g.thumbRY) > STICK_DEADZONE else 0.0
    lt = g.bLeftTrigger / 255.0 if g.bLeftTrigger > TRIGGER_THRESHOLD else 0.0
    rt = g.bRightTrigger / 255.0 if g.bRightTrigger > TRIGGER_THRESHOLD else 0.0
    buttons = {name for mask, name in BUTTONS.items() if g.wButtons & mask}
    return {'lx': lx, 'ly': ly, 'rx': rx, 'ry': ry, 'lt': lt, 'rt': rt, 'buttons': buttons}


def vibrate(controller=0, left=0.0, right=0.0):
    """震动 (0.0..1.0)"""
    if not _dll:
        return
    vib = XINPUT_VIBRATION(int(left * 65535), int(right * 65535))
    try:
        _dll.XInputSetState(controller, ctypes.byref(vib))
    except OSError:
        pass
```

### 4.2 InputManager（arena/input_manager.py）

输入抽象层，统一键盘和手柄输入。

```python
from ursina import *
from arena.xinput import get_state, is_available, vibrate
from arena.constants import Config


class InputManager(Entity):
    """输入管理器 — 统一键盘/鼠标/手柄输入"""

    def __init__(self):
        super().__init__()
        self.gamepad_connected = is_available()

        # 输出接口（归一化值）
        self.move_forward = 0.0    # -1~1，正=前进
        self.move_sideways = 0.0   # -1~1，正=右转
        self.shoot = 0.0           # 0~1
        self.action = False        # 瞬时动作（消费型，读取后重置）

        if self.gamepad_connected:
            print('[InputManager] Gamepad detected (XInput)')
        else:
            print('[InputManager] No gamepad, keyboard mode')

    def update(self):
        """每帧读取输入，输出归一化值"""
        # 重置瞬时动作
        self.action = False

        gp = self._read_gamepad()
        kb = self._read_keyboard()

        # 合并：取绝对值较大值（键盘 0/1 优先级高于手柄小量）
        self.move_forward = max(gp[0], kb[0])
        self.move_sideways = max(gp[1], kb[1])
        self.shoot = max(gp[2], kb[2])

    def _read_keyboard(self):
        """读取键盘/鼠标输入（与原 HumanController 相同逻辑）"""
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
        if not self.gamepad_connected:
            return 0.0, 0.0, 0.0

        state = get_state(0)
        if state is None:
            self.gamepad_connected = False
            return 0.0, 0.0, 0.0

        # 左摇杆 Y → 前后移动
        fwd = state['ly']

        # 右摇杆 X → 左右旋转
        side = state['rx']

        # 左扳机 → 射击
        shoot = state['lt']

        # 瞬时按键
        buttons = state['buttons']
        if 'X' in buttons:
            self.action = True  # X 键 → 切换视角

        return fwd, side, shoot

    def input(self, key):
        """处理 Ursina 键盘瞬时按键"""
        if key == 'v':
            self.action = True  # V 键 → 切换视角
```

### 4.3 HumanController 改造（arena/human_ctrl.py）

```python
class HumanController:
    """人类玩家控制器（支持键盘 + 手柄，杆量 = 速度）"""

    def __init__(self, player, input_manager):
        self.player = player
        self.im = input_manager
        self.move_speed = Config.HUMAN_MOVE_SPEED
        self.rotation_speed = Config.HUMAN_ROTATION_SPEED

    def update(self):
        if self.player.state.value not in ('alive', 'respawning'):
            return

        im = self.im

        # 旋转（右摇杆 X / 键盘 A/D，杆量 = 速度比例）
        if abs(im.move_sideways) > 0.05:
            rotation = im.move_sideways * self.rotation_speed * time.dt
            self.player.rotation_y += rotation

        # 前后移动（左摇杆 Y / 键盘 W/S，杆量 = 速度比例）
        if abs(im.move_forward) > 0.05:
            move_amount = im.move_forward * self.move_speed * time.dt
            direction = self.player.forward if move_amount > 0 else -self.player.forward
            ray = raycast(self.player.position, direction,
                          distance=abs(move_amount), ignore=(self.player,))
            if not ray.hit:
                self.player.position += direction * abs(move_amount)

        # 射击（左扳机 / 鼠标左键）
        if im.shoot > 0.3:
            shoot_dir = self.player.forward.normalized()
            self.player.weapon.shoot(shoot_dir)
```

**关键变化：**
- `held_keys['a']` → `im.move_sideways`（值从 0/1 变为 -1~1 连续值）
- `held_keys['w']` → `im.move_forward`（值从 0/1 变为 -1~1 连续值）
- 速度 = `abs(输入值) * 基础速度`（键盘=满值=满速，手柄=杆量=对应速度）

### 4.4 GameManager 改造（arena/game_manager.py）

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
        # action 事件处理
        if self.input_manager and self.input_manager.action:
            if self.camera_controller:
                self.camera_controller.toggle_distance()

        if self.human_player:
            hud.update_player_info(self.human_player)
```

### 4.5 Constants 新增（arena/constants.py）

```python
class Config:
    # ... 现有配置（不变） ...

    # 手柄
    GAMEPAD_DEADZONE = 7849        # XInput 原始死区（已在 xinput.py 处理）
    GAMEPAD_SHOOT_THRESHOLD = 0.3  # 扳机射击阈值（归一化后 0~1）
```

### 4.6 HUD 更新（arena/hud.py）

```python
# 更新操作提示
self.controls_text.text = (
    'Keyboard: WASD-Move  LMB-Shoot  V-View\n'
    'Gamepad:  LS-Move  RS-Rotate  LT-Shoot  X-View'
)
```

---

## 5. 文件改动清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `arena/xinput.py` | **新增** | XInput ctypes 封装，平台相关层 |
| `arena/input_manager.py` | **新增** | 输入抽象层，统一键盘/手柄 |
| `arena/human_ctrl.py` | 修改 | 构造函数加 `input_manager` 参数；从 `held_keys` 改为读 `im` 属性 |
| `arena/game_manager.py` | 修改 | 创建 `InputManager`，传递给 HumanController；处理 action |
| `arena/constants.py` | 修改 | 新增 GAMEPAD_SHOOT_THRESHOLD |
| `arena/hud.py` | 修改 | 更新操作提示文字 |
| `arena/ai_ctrl.py` | **不变** | AI 不受输入系统影响 |
| `arena/weapon.py` | **不变** | 射击接口不变 |
| `arena/camera_ctrl.py` | **不变** | 视角切换通过 GameManager 间接调用 |

---

## 6. 实现步骤

### Phase 1：XInput 封装 + 输入抽象层

- [ ] 创建 `arena/xinput.py`（从 test_gamepad.py 提取已验证的代码）
- [ ] 创建 `arena/input_manager.py`
- [ ] 实现键盘输入读取（`_read_keyboard`）
- [ ] 实现手柄输入读取（`_read_gamepad`），左摇杆Y→前后，右摇杆X→旋转，LT→射击
- [ ] 实现输入合并逻辑（`update`），取较大值
- [ ] 在 `constants.py` 添加手柄配置

### Phase 2：控制器适配

- [ ] 修改 `HumanController.__init__` 接收 `input_manager` 参数
- [ ] 替换 `held_keys` 读取为 `im.move_forward` / `im.move_sideways` / `im.shoot`
- [ ] 速度计算改为 `abs(输入值) * 基础速度`（杆量比例）
- [ ] 修改 `GameManager.start_match` 创建 InputManager
- [ ] 在 `GameManager.update` 中处理 action（视角切换）

### Phase 3：UI 与反馈

- [ ] 更新 HUD 操作提示（键盘 + 手柄双显示）
- [ ] 射击使用扳机压力值控制射速（可选）

### Phase 4：测试

- [ ] 纯键盘测试（确保功能不退化）
- [ ] 纯手柄测试（移动/旋转/射击/视角切换）
- [ ] 键盘 + 手柄同时输入测试
- [ ] 无手柄启动测试（优雅降级）
- [ ] 杆量速度测试（半推摇杆 = 半速）
- [ ] 摇杆死区测试（小幅度不应触发移动）
- [ ] AI 玩家不受影响测试

---

## 7. 已知风险与应对

| 风险 | 影响 | 应对方案 |
|------|------|----------|
| 非 Windows 平台 | XInput 不可用 | `is_available()` 返回 False，自动退化为键盘模式 |
| 非 Xbox 手柄（PS5/Switch） | XInput 不支持 | 后续可扩展 SDL/pygame 后端（需解决 Panda3D 冲突） |
| 摇杆漂移 | 静止时角色微动 | XInput 内置 7849 死区阈值 + InputManager 0.05 阈值 |
| 手柄热插拔 | `get_state` 返回 None | 自动降级，下帧恢复 |
| 键盘和手柄同时输入 | 操作混乱 | 取较大值策略（键盘 0/1 覆盖手柄小量） |
| InputManager 未初始化时访问 | AttributeError | GameManager 在 start_match 中创建，生命周期与比赛一致 |
