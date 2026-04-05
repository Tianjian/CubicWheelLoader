"""
手柄测试脚本 (XInput via ctypes)
===================================
直接调用 Windows XInput API，不依赖 pygame，不与 Panda3D 冲突。
Xbox One/360/Series 手柄专用。

操作：移动摇杆/按键/扳机 | ESC 退出
"""
import sys, math, ctypes
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from ursina import *

# ==================== XInput API ====================

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

xinput = ctypes.windll.xinput1_4
try:
    xinput.XInputGetState
except AttributeError:
    xinput = ctypes.windll.xinput1_3
try:
    xinput.XInputGetState
except AttributeError:
    xinput = ctypes.windll.xinput9_1_0

XINPUT_BUTTONS = {
    0x0001: 'UP',     0x0002: 'DOWN',   0x0004: 'LEFT',    0x0008: 'RIGHT',
    0x0010: 'START',  0x0020: 'BACK',   0x0040: 'LS',      0x0080: 'RS',
    0x1000: 'A',      0x2000: 'B',      0x4000: 'X',       0x8000: 'Y',
    0x0100: 'LB',     0x0200: 'RB',
}

MAX_VAL = 32767
STICK_DZ = 7849
TRIG_TH = 30


def xinput_get_state(controller=0):
    state = XINPUT_STATE()
    result = xinput.XInputGetState(controller, ctypes.byref(state))
    if result != 0:
        return False, None
    g = state.Gamepad
    lx = g.thumbLX / MAX_VAL if abs(g.thumbLX) > STICK_DZ else 0.0
    ly = -g.thumbLY / MAX_VAL if abs(g.thumbLY) > STICK_DZ else 0.0
    rx = g.thumbRX / MAX_VAL if abs(g.thumbRX) > STICK_DZ else 0.0
    ry = -g.thumbRY / MAX_VAL if abs(g.thumbRY) > STICK_DZ else 0.0
    lt = g.bLeftTrigger / 255.0 if g.bLeftTrigger > TRIG_TH else 0.0
    rt = g.bRightTrigger / 255.0 if g.bRightTrigger > TRIG_TH else 0.0
    buttons = {name for mask, name in XINPUT_BUTTONS.items() if g.wButtons & mask}
    return True, {'lx': lx, 'ly': ly, 'rx': rx, 'ry': ry,
                  'lt': lt, 'rt': rt, 'buttons': buttons}


def xinput_vibrate(controller=0, left=0.0, right=0.0):
    class VIB(ctypes.Structure):
        _fields_ = [('wLeftMotorSpeed', ctypes.c_ushort), ('wRightMotorSpeed', ctypes.c_ushort)]
    try:
        xinput.XInputSetState(controller, ctypes.byref(VIB(int(left * 65535), int(right * 65535))))
    except:
        pass


def make_bar(pct, width=20):
    """生成文本进度条 [##########----------]"""
    filled = int(pct / 100 * width)
    return f'[{("#" * filled + "." * (width - filled))}]'


# ==================== App ====================

app = Ursina(title='Gamepad Test (XInput)', borderless=False)
window.color = color.dark_gray

# 全部用 Text，零 Entity 渲染冲突
Text(text='GAMEPAD TEST (XInput)', position=(0, 0.48), origin=(0, 0),
     scale=2, color=color.yellow)
status_text = Text(text='...', position=(0, 0.42), origin=(0, 0),
                   scale=1, color=color.green)

# 左摇杆
ls_text = Text(text='LEFT STICK\nX: +0.000  Y: +0.000', position=(-0.28, 0.28),
               origin=(-0.5, 0.5), scale=0.9, color=color.white)

# 右摇杆
rs_text = Text(text='RIGHT STICK\nX: +0.000  Y: +0.000', position=(0.05, 0.28),
               origin=(-0.5, 0.5), scale=0.9, color=color.white)

# 扳机
trig_text = Text(text='LT: 0% [░░░░░░░░░░░░░░░░░░░░]\nRT: 0% [░░░░░░░░░░░░░░░░░░░░]',
                position=(0, 0.08), origin=(0, 0.5), scale=0.9, color=color.white)

# 按键
Text(text='BUTTONS:', position=(-0.45, -0.05), origin=(0, 0),
     scale=1, color=color.white)
btn_text = Text(text='(none)', position=(-0.45, -0.10), origin=(0, 0),
                scale=1, color=color.gray)

# 提示
Text(text='Move sticks / press buttons / pull triggers | ESC = quit',
     position=(0, -0.47), origin=(0, 0), scale=0.7, color=color.gray)


def update():
    connected, state = xinput_get_state(0)
    if not connected:
        status_text.text = 'NOT CONNECTED'
        status_text.color = color.red
        return

    status_text.text = 'Connected'
    status_text.color = color.green

    # 摇杆文字
    lx, ly = state['lx'], state['ly']
    rx, ry = state['rx'], state['ry']
    ls_text.text = f'LEFT STICK\nX: {lx:+.3f}  Y: {ly:+.3f}'
    ls_text.color = color.lime if abs(lx) > 0.01 or abs(ly) > 0.01 else color.white
    rs_text.text = f'RIGHT STICK\nX: {rx:+.3f}  Y: {ry:+.3f}'
    rs_text.color = color.lime if abs(rx) > 0.01 or abs(ry) > 0.01 else color.white

    # 扳机条
    lt_pct = state['lt'] * 100
    rt_pct = state['rt'] * 100
    trig_text.text = f'LT: {lt_pct:3.0f}% {make_bar(lt_pct)}\nRT: {rt_pct:3.0f}% {make_bar(rt_pct)}'

    # 按键
    btns = state['buttons']
    if btns:
        btn_text.text = ' '.join(sorted(btns))
        btn_text.color = color.yellow
        xinput_vibrate(0, 0.3, 0.3)
        invoke(lambda: xinput_vibrate(0, 0, 0), delay=0.08)
    else:
        btn_text.text = '(none)'
        btn_text.color = color.gray


def input(key):
    if key == 'escape':
        application.quit()


if __name__ == '__main__':
    app.run()
