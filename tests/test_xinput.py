"""XInput _parse_state 纯函数单元测试（Layer 1）"""
import pytest
from arena.xinput import (
    XINPUT_STATE, XINPUT_GAMEPAD, BUTTONS,
    MAX_AXIS, STICK_DEADZONE, TRIGGER_THRESHOLD,
    _parse_state,
)


def make_state(wButtons=0, bLeftTrigger=0, bRightTrigger=0,
               thumbLX=0, thumbLY=0, thumbRX=0, thumbRY=0):
    """构造测试用的 XINPUT_STATE"""
    gamepad = XINPUT_GAMEPAD(
        wButtons=wButtons,
        bLeftTrigger=bLeftTrigger,
        bRightTrigger=bRightTrigger,
        thumbLX=thumbLX, thumbLY=thumbLY,
        thumbRX=thumbRX, thumbRY=thumbRY,
    )
    return XINPUT_STATE(dwPacketNumber=1, Gamepad=gamepad)


class TestStickNormalization:
    """摇杆归一化到 -1..1"""

    def test_max_positive_lx(self):
        state = make_state(thumbLX=MAX_AXIS)
        result = _parse_state(state)
        assert result['lx'] == pytest.approx(1.0)

    def test_max_negative_lx(self):
        state = make_state(thumbLX=-MAX_AXIS)
        result = _parse_state(state)
        assert result['lx'] == pytest.approx(-1.0)

    def test_max_positive_ly(self):
        state = make_state(thumbLY=MAX_AXIS)
        result = _parse_state(state)
        assert result['ly'] == pytest.approx(1.0)

    def test_max_negative_ly(self):
        state = make_state(thumbLY=-MAX_AXIS)
        result = _parse_state(state)
        assert result['ly'] == pytest.approx(-1.0)

    def test_half_positive_rx(self):
        state = make_state(thumbRX=MAX_AXIS // 2)
        result = _parse_state(state)
        assert result['rx'] == pytest.approx(0.5, abs=0.01)

    def test_ry_inverted(self):
        """右摇杆 Y 轴取反"""
        state = make_state(thumbRY=MAX_AXIS)
        result = _parse_state(state)
        assert result['ry'] == pytest.approx(-1.0)

    def test_ry_negative_becomes_positive(self):
        state = make_state(thumbRY=-MAX_AXIS)
        result = _parse_state(state)
        assert result['ry'] == pytest.approx(1.0)


class TestStickDeadzone:
    """死区内摇杆值归零"""

    def test_within_deadzone_lx(self):
        state = make_state(thumbLX=STICK_DEADZONE)
        result = _parse_state(state)
        assert result['lx'] == 0.0

    def test_within_deadzone_ly(self):
        state = make_state(thumbLY=STICK_DEADZONE)
        result = _parse_state(state)
        assert result['ly'] == 0.0

    def test_just_above_deadzone(self):
        state = make_state(thumbLX=STICK_DEADZONE + 1)
        result = _parse_state(state)
        assert result['lx'] != 0.0
        assert abs(result['lx']) < 1.0

    def test_zero_is_in_deadzone(self):
        state = make_state(thumbLX=0, thumbLY=0, thumbRX=0, thumbRY=0)
        result = _parse_state(state)
        assert result['lx'] == 0.0
        assert result['ly'] == 0.0
        assert result['rx'] == 0.0
        assert result['ry'] == 0.0


class TestTriggerNormalization:
    """扳机归一化到 0..1"""

    def test_max_left_trigger(self):
        state = make_state(bLeftTrigger=255)
        result = _parse_state(state)
        assert result['lt'] == pytest.approx(1.0)

    def test_max_right_trigger(self):
        state = make_state(bRightTrigger=255)
        result = _parse_state(state)
        assert result['rt'] == pytest.approx(1.0)

    def test_trigger_below_threshold(self):
        state = make_state(bLeftTrigger=TRIGGER_THRESHOLD)
        result = _parse_state(state)
        assert result['lt'] == 0.0

    def test_trigger_just_above_threshold(self):
        state = make_state(bLeftTrigger=TRIGGER_THRESHOLD + 1)
        result = _parse_state(state)
        assert result['lt'] > 0.0

    def test_zero_trigger(self):
        state = make_state(bLeftTrigger=0, bRightTrigger=0)
        result = _parse_state(state)
        assert result['lt'] == 0.0
        assert result['rt'] == 0.0


class TestButtons:
    """按键位掩码解析"""

    def test_no_buttons(self):
        state = make_state(wButtons=0)
        result = _parse_state(state)
        assert result['buttons'] == set()

    def test_single_button_a(self):
        state = make_state(wButtons=BUTTONS['A'])
        result = _parse_state(state)
        assert result['buttons'] == {'A'}

    def test_multiple_buttons(self):
        state = make_state(wButtons=BUTTONS['A'] | BUTTONS['X'])
        result = _parse_state(state)
        assert result['buttons'] == {'A', 'X'}

    def test_all_dpad(self):
        state = make_state(wButtons=BUTTONS['UP'] | BUTTONS['DOWN'] | BUTTONS['LEFT'] | BUTTONS['RIGHT'])
        result = _parse_state(state)
        assert result['buttons'] == {'UP', 'DOWN', 'LEFT', 'RIGHT'}


class TestReturnStructure:
    """返回字典结构完整性"""

    def test_all_keys_present(self):
        state = make_state()
        result = _parse_state(state)
        assert set(result.keys()) == {'lx', 'ly', 'rx', 'ry', 'lt', 'rt', 'buttons'}

    def test_types(self):
        state = make_state()
        result = _parse_state(state)
        assert isinstance(result['lx'], float)
        assert isinstance(result['ly'], float)
        assert isinstance(result['rx'], float)
        assert isinstance(result['ry'], float)
        assert isinstance(result['lt'], float)
        assert isinstance(result['rt'], float)
        assert isinstance(result['buttons'], set)
