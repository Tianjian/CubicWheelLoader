"""input_manager 纯函数单元测试（Layer 1）"""
import pytest
from arena.input_manager import merge_inputs, parse_gamepad_state


class TestMergeInputs:
    """测试 merge_inputs 输入合并逻辑"""

    def test_keyboard_overrides_small_gamepad(self):
        assert merge_inputs(1.0, 0.3) == 1.0
        assert merge_inputs(-1.0, -0.3) == -1.0

    def test_gamepad_negative_not_swallowed(self):
        assert merge_inputs(0.0, -0.5) == -0.5
        assert merge_inputs(0.0, -1.0) == -1.0

    def test_keyboard_negative_overrides_gamepad(self):
        assert merge_inputs(-1.0, 0.5) == -1.0

    def test_both_zero(self):
        assert merge_inputs(0.0, 0.0) == 0.0

    def test_gamepad_larger_absolute(self):
        assert merge_inputs(0.0, 0.8) == 0.8
        assert merge_inputs(0.0, -0.8) == -0.8

    def test_equal_absolute_takes_gamepad(self):
        """绝对值相等时取手柄值（gp_val 在 else 分支）"""
        assert merge_inputs(0.5, 0.5) == 0.5
        assert merge_inputs(-0.5, 0.5) == 0.5  # abs equal, takes gp

    def test_gamepad_positive_over_keyboard_small(self):
        assert merge_inputs(0.1, 0.9) == 0.9


class TestParseGamepadState:
    """测试 parse_gamepad_state 解析逻辑"""

    def test_none_returns_zeros(self):
        fwd, side, shoot, action = parse_gamepad_state(None)
        assert fwd == 0.0
        assert side == 0.0
        assert shoot == 0.0
        assert action is False

    def test_stick_maps_to_forward(self):
        state = {'ly': 0.5, 'rx': 0, 'lt': 0, 'rt': 0, 'buttons': set()}
        fwd, side, shoot, action = parse_gamepad_state(state)
        assert fwd == 0.5

    def test_stick_negative_forward(self):
        state = {'ly': -0.7, 'rx': 0, 'lt': 0, 'rt': 0, 'buttons': set()}
        fwd, side, shoot, action = parse_gamepad_state(state)
        assert fwd == -0.7

    def test_stick_maps_to_sideways(self):
        state = {'ly': 0, 'rx': -0.7, 'lt': 0, 'rt': 0, 'buttons': set()}
        fwd, side, shoot, action = parse_gamepad_state(state)
        assert side == -0.7

    def test_trigger_maps_to_shoot(self):
        state = {'ly': 0, 'rx': 0, 'lt': 0.8, 'rt': 0, 'buttons': set()}
        fwd, side, shoot, action = parse_gamepad_state(state)
        assert shoot == 0.8

    def test_x_button_sets_action(self):
        state = {'ly': 0, 'rx': 0, 'lt': 0, 'rt': 0, 'buttons': {'X'}}
        fwd, side, shoot, action = parse_gamepad_state(state)
        assert action is True

    def test_no_x_button_no_action(self):
        state = {'ly': 0, 'rx': 0, 'lt': 0, 'rt': 0, 'buttons': {'A'}}
        fwd, side, shoot, action = parse_gamepad_state(state)
        assert action is False

    def test_empty_buttons_no_action(self):
        state = {'ly': 0, 'rx': 0, 'lt': 0, 'rt': 0, 'buttons': set()}
        fwd, side, shoot, action = parse_gamepad_state(state)
        assert action is False

    def test_missing_buttons_key_no_action(self):
        state = {'ly': 0, 'rx': 0, 'lt': 0, 'rt': 0}
        fwd, side, shoot, action = parse_gamepad_state(state)
        assert action is False

    def test_combined_input(self):
        state = {'ly': 0.8, 'rx': -0.3, 'lt': 0.6, 'rt': 0, 'buttons': {'X', 'A'}}
        fwd, side, shoot, action = parse_gamepad_state(state)
        assert fwd == 0.8
        assert side == -0.3
        assert shoot == 0.6
        assert action is True
