"""共享内存结构和 AI 进程管理单元测试（Layer 1 — 纯逻辑）"""
import ctypes
import math
import pytest
from arena.shared_state import (
    SharedGameState, PlayerInput, PlayerCommand,
    MAX_PLAYERS, shared_state_size,
)


class TestSharedStateStructure:
    """共享内存结构完整性测试"""

    def test_shared_state_size(self):
        """共享内存大小 > 0"""
        size = shared_state_size()
        assert size > 0

    def test_max_players(self):
        """最大玩家数为 4"""
        assert MAX_PLAYERS == 4

    def test_player_input_fields(self):
        """PlayerInput 字段完整"""
        p = PlayerInput()
        assert hasattr(p, 'player_id')
        assert hasattr(p, 'team_id')
        assert hasattr(p, 'state')
        assert hasattr(p, 'pos_x')
        assert hasattr(p, 'pos_y')
        assert hasattr(p, 'pos_z')
        assert hasattr(p, 'rotation_y')
        assert hasattr(p, 'hp')
        assert hasattr(p, 'spawn_x')
        assert hasattr(p, 'spawn_z')
        assert hasattr(p, 'ray_hit')
        assert hasattr(p, 'ray_distance')

    def test_player_command_fields(self):
        """PlayerCommand 字段完整"""
        c = PlayerCommand()
        assert hasattr(c, 'look_at_x')
        assert hasattr(c, 'look_at_z')
        assert hasattr(c, 'rotate_y')
        assert hasattr(c, 'move_fwd')
        assert hasattr(c, 'request_raycast')
        assert hasattr(c, 'shoot_dir_x')
        assert hasattr(c, 'shoot_dir_y')
        assert hasattr(c, 'shoot_dir_z')
        assert hasattr(c, 'avoiding')
        assert hasattr(c, 'avoid_direction')

    def test_shared_state_fields(self):
        """SharedGameState 字段完整"""
        s = SharedGameState()
        assert hasattr(s, 'running')
        assert hasattr(s, 'frame_number')
        assert hasattr(s, 'ai_frame_done')
        assert hasattr(s, 'players')
        assert hasattr(s, 'player_count')
        assert hasattr(s, 'commands')
        assert hasattr(s, 'dt')

    def test_players_array_size(self):
        """players 数组大小为 MAX_PLAYERS"""
        s = SharedGameState()
        assert len(s.players) == MAX_PLAYERS

    def test_commands_array_size(self):
        """commands 数组大小为 MAX_PLAYERS"""
        s = SharedGameState()
        assert len(s.commands) == MAX_PLAYERS


class TestPlayerInputReadWrite:
    """PlayerInput 读写测试"""

    def test_write_read_position(self):
        p = PlayerInput()
        p.pos_x = 10.5
        p.pos_y = 0.0
        p.pos_z = -24.0
        assert p.pos_x == pytest.approx(10.5)
        assert p.pos_z == pytest.approx(-24.0)

    def test_write_read_state(self):
        p = PlayerInput()
        p.state = 0  # alive
        assert p.state == 0
        p.state = 1  # dead
        assert p.state == 1

    def test_write_read_team(self):
        p = PlayerInput()
        p.team_id = 0  # RED
        assert p.team_id == 0
        p.team_id = 1  # BLUE
        assert p.team_id == 1

    def test_ray_hit(self):
        p = PlayerInput()
        p.ray_hit = 1
        p.ray_distance = 3.5
        assert p.ray_hit == 1
        assert p.ray_distance == pytest.approx(3.5)


class TestPlayerCommandReadWrite:
    """PlayerCommand 读写测试"""

    def test_write_read_look_at(self):
        c = PlayerCommand()
        c.look_at_x = 5.0
        c.look_at_z = -10.0
        assert c.look_at_x == pytest.approx(5.0)
        assert c.look_at_z == pytest.approx(-10.0)

    def test_nan_shoot_dir(self):
        c = PlayerCommand()
        c.shoot_dir_x = float('nan')
        assert math.isnan(c.shoot_dir_x)

    def test_move_fwd(self):
        c = PlayerCommand()
        c.move_fwd = 1.0
        assert c.move_fwd == pytest.approx(1.0)

    def test_request_raycast(self):
        c = PlayerCommand()
        c.request_raycast = 1
        assert c.request_raycast == 1


class TestSharedStateBufferMapping:
    """共享内存缓冲区映射测试"""

    def test_from_buffer_roundtrip(self):
        """写入后重新映射，数据一致"""
        buf = bytearray(shared_state_size())
        s1 = SharedGameState.from_buffer(buf)
        s1.running = 1
        s1.frame_number = 42
        s1.dt = 0.016
        s1.player_count = 2
        s1.players[0].player_id = 1
        s1.players[0].pos_x = 10.0
        s1.players[1].player_id = 2
        s1.players[1].pos_z = -20.0
        s1.commands[0].move_fwd = 1.0

        # 重新映射同一缓冲区
        s2 = SharedGameState.from_buffer(buf)
        assert s2.running == 1
        assert s2.frame_number == 42
        assert s2.dt == pytest.approx(0.016)
        assert s2.player_count == 2
        assert s2.players[0].player_id == 1
        assert s2.players[0].pos_x == pytest.approx(10.0)
        assert s2.players[1].pos_z == pytest.approx(-20.0)
        assert s2.commands[0].move_fwd == pytest.approx(1.0)


class TestAIDecider:
    """AI 子进程中的 AIDecider 纯逻辑测试"""

    def test_alive_player_returns_command(self):
        from arena.ai_worker import AIDecider
        d = AIDecider(player_id=2, team_id=0, spawn_x=0, spawn_z=-24)
        # 创建 mock input
        inp = PlayerInput()
        inp.player_id = 2
        inp.team_id = 0
        inp.state = 0  # alive
        inp.pos_x = 0
        inp.pos_y = 0
        inp.pos_z = -24
        inp.rotation_y = 0

        result = d.update(inp, [inp], 1/60)
        assert isinstance(result, dict)
        assert 'move_fwd' in result

    def test_dead_player_returns_empty(self):
        from arena.ai_worker import AIDecider
        d = AIDecider(player_id=2, team_id=0, spawn_x=0, spawn_z=-24)
        inp = PlayerInput()
        inp.state = 1  # dead

        result = d.update(inp, [inp], 1/60)
        assert result == {}

    def test_patrol_points_generated(self):
        from arena.ai_worker import AIDecider
        d = AIDecider(player_id=2, team_id=0, spawn_x=0, spawn_z=-24)
        d._generate_patrol_points()
        assert len(d.patrol_points) == 5

    def test_dict_to_command(self):
        from arena.ai_worker import dict_to_command
        cmd = PlayerCommand()
        d = {
            'look_at': (5.0, -10.0),
            'move_fwd': 1.0,
            'request_raycast': True,
            'shoot_dir': (0.1, 0.0, 0.9),
            'avoiding': False,
            'avoid_direction': 0,
        }
        dict_to_command(d, cmd)
        assert cmd.look_at_x == pytest.approx(5.0)
        assert cmd.look_at_z == pytest.approx(-10.0)
        assert cmd.move_fwd == pytest.approx(1.0)
        assert cmd.request_raycast == 1
        assert cmd.shoot_dir_x == pytest.approx(0.1)

    def test_dict_to_command_no_shoot(self):
        from arena.ai_worker import dict_to_command
        cmd = PlayerCommand()
        d = {
            'look_at': None,
            'move_fwd': 0.0,
            'request_raycast': False,
            'shoot_dir': None,
            'avoiding': False,
            'avoid_direction': 0,
        }
        dict_to_command(d, cmd)
        assert math.isnan(cmd.shoot_dir_x)
        assert math.isnan(cmd.look_at_x)
