"""
输入管理器 — 统一键盘/鼠标/手柄输入
==========================================
控制器通过统一的归一化接口读取输入，不关心输入来源。

输出接口:
  move_forward: float   # -1~1，正=前进（杆量 = 速度比例）
  move_sideways: float  # -1~1，正=右转（杆量 = 转速比例）
  shoot: float          # 0~1，>0 表示射击
  action: bool          # 瞬时动作（切换视角等，消费型）
  gamepad_connected: bool
  input_source: str     # 'gamepad' | 'keyboard'
"""
from ursina import *
from arena.xinput import get_state, is_available, vibrate
from arena.constants import Config


class InputManager(Entity):
    """输入管理器 — 统一键盘/鼠标/手柄输入"""

    def __init__(self):
        super().__init__()
        self.gamepad_connected = is_available()

        # 输出接口
        self.move_forward = 0.0
        self.move_sideways = 0.0
        self.shoot = 0.0
        self.action = False

        if self.gamepad_connected:
            print('[InputManager] Gamepad detected (XInput)')
        else:
            print('[InputManager] No gamepad, keyboard only')

    def update(self):
        """每帧读取输入，自动合并键盘和手柄"""
        self.action = False

        kb = self._read_keyboard()
        gp = self._read_gamepad()

        # 合并：取绝对值较大的输入（保留符号）
        # 键盘 0/1 覆盖手柄小量，手柄负值不会被键盘的 0.0 吞掉
        def _merge(kb_val, gp_val):
            return kb_val if abs(kb_val) > abs(gp_val) else gp_val

        self.move_forward = _merge(kb[0], gp[0])
        self.move_sideways = _merge(kb[1], gp[1])
        self.shoot = _merge(kb[2], gp[2])

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
        state = get_state(0)
        if state is None:
            self.gamepad_connected = False
            self.input_source = 'keyboard'
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
            self.action = True

        return fwd, side, shoot

    def input(self, key):
        """处理 Ursina 键盘瞬时按键"""
        if key == 'v':
            self.action = True  # V 键 → 切换视角
