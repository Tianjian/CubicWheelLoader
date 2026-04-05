"""
Windows XInput API 封装
========================
仅支持 Xbox 标准手柄（360/One/Series），Windows 原生支持。
已验证：Xbox One For Windows 手柄全部功能正常。

接口:
  is_available() -> bool
  get_state(controller=0) -> dict | None
  vibrate(controller=0, left=0.0, right=0.0)
"""
import ctypes
import sys

# ==================== 结构体 ====================

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
    _fields_ = [
        ('dwPacketNumber', ctypes.c_uint),
        ('Gamepad', XINPUT_GAMEPAD),
    ]

class XINPUT_VIBRATION(ctypes.Structure):
    _fields_ = [
        ('wLeftMotorSpeed', ctypes.c_ushort),
        ('wRightMotorSpeed', ctypes.c_ushort),
    ]

# ==================== 按键位掩码 ====================

BUTTONS = {
    'UP': 0x0001, 'DOWN': 0x0002, 'LEFT': 0x0004, 'RIGHT': 0x0008,
    'START': 0x0010, 'BACK': 0x0020, 'LS': 0x0040, 'RS': 0x0080,
    'LB': 0x0100, 'RB': 0x0200,
    'A': 0x1000, 'B': 0x2000, 'X': 0x4000, 'Y': 0x8000,
}

# ==================== 常量 ====================

MAX_AXIS = 32767
STICK_DEADZONE = 7849      # XInput 推荐死区
TRIGGER_THRESHOLD = 30     # 0..255

# ==================== DLL 加载 ====================

_dll = None
if sys.platform == 'win32':
    for name in ('xinput1_4', 'xinput1_3', 'xinput9_1_0'):
        try:
            _dll = ctypes.windll[name]
            break
        except OSError:
            continue


def is_available():
    """检查 XInput 是否可用"""
    return _dll is not None


def get_state(controller=0):
    """
    读取手柄状态。返回 None 表示未连接或平台不支持。

    Returns:
        dict | None: {
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

    # 归一化摇杆，应用死区
    lx = g.thumbLX / MAX_AXIS if abs(g.thumbLX) > STICK_DEADZONE else 0.0
    ly = g.thumbLY / MAX_AXIS if abs(g.thumbLY) > STICK_DEADZONE else 0.0
    rx = g.thumbRX / MAX_AXIS if abs(g.thumbRX) > STICK_DEADZONE else 0.0
    ry = -g.thumbRY / MAX_AXIS if abs(g.thumbRY) > STICK_DEADZONE else 0.0

    # 扳机 (0..255 -> 0..1)
    lt = g.bLeftTrigger / 255.0 if g.bLeftTrigger > TRIGGER_THRESHOLD else 0.0
    rt = g.bRightTrigger / 255.0 if g.bRightTrigger > TRIGGER_THRESHOLD else 0.0

    # 按键
    buttons = {name for name, mask in BUTTONS.items() if g.wButtons & mask}

    return {
        'lx': lx, 'ly': ly, 'rx': rx, 'ry': ry,
        'lt': lt, 'rt': rt, 'buttons': buttons,
    }


def vibrate(controller=0, left=0.0, right=0.0):
    """震动 (0.0..1.0)"""
    if not _dll:
        return
    vib = XINPUT_VIBRATION(int(left * 65535), int(right * 65535))
    try:
        _dll.XInputSetState(controller, ctypes.byref(vib))
    except OSError:
        pass
