"""AI 控制器纯函数 + 决策逻辑单元测试"""
import math
import pytest
from arena.ai_ctrl import forward_from_rotation, dist_3d
from ursina import Vec3


class TestForwardFromRotation:
    """forward_from_rotation 纯函数测试"""

    def test_zero_rotation(self):
        """0度朝 +Z"""
        fx, fy, fz = forward_from_rotation(0)
        assert fy == 0
        assert fz == pytest.approx(1.0, abs=0.01)
        assert fx == pytest.approx(0.0, abs=0.01)

    def test_90_degrees(self):
        """90度朝 +X"""
        fx, fy, fz = forward_from_rotation(90)
        assert fx == pytest.approx(1.0, abs=0.01)
        assert fy == 0
        assert fz == pytest.approx(0.0, abs=0.01)

    def test_180_degrees(self):
        """180度朝 -Z"""
        fx, fy, fz = forward_from_rotation(180)
        assert fx == pytest.approx(0.0, abs=0.01)
        assert fz == pytest.approx(-1.0, abs=0.01)

    def test_negative_90(self):
        """-90度朝 -X"""
        fx, fy, fz = forward_from_rotation(-90)
        assert fx == pytest.approx(-1.0, abs=0.01)
        assert fz == pytest.approx(0.0, abs=0.01)

    def test_y_always_zero(self):
        """Y 分量始终为 0"""
        for angle in [0, 45, 90, 180, 270, -45]:
            _, fy, _ = forward_from_rotation(angle)
            assert fy == 0

    def test_unit_length(self):
        """返回单位向量"""
        for angle in [0, 30, 60, 90, 120, 180, 270]:
            fx, fy, fz = forward_from_rotation(angle)
            length = math.sqrt(fx**2 + fy**2 + fz**2)
            assert length == pytest.approx(1.0, abs=0.01)


class TestDist3d:
    """dist_3d 纯函数测试"""

    def test_same_point(self):
        assert dist_3d((0, 0, 0), (0, 0, 0)) == 0.0

    def test_unit_distance_x(self):
        assert dist_3d((0, 0, 0), (1, 0, 0)) == pytest.approx(1.0)

    def test_unit_distance_y(self):
        assert dist_3d((0, 0, 0), (0, 1, 0)) == pytest.approx(1.0)

    def test_unit_distance_z(self):
        assert dist_3d((0, 0, 0), (0, 0, 1)) == pytest.approx(1.0)

    def test_diagonal(self):
        d = dist_3d((0, 0, 0), (1, 1, 1))
        assert d == pytest.approx(math.sqrt(3), abs=0.001)

    def test_negative_coordinates(self):
        assert dist_3d((-1, 0, 0), (1, 0, 0)) == pytest.approx(2.0)

    def test_symmetric(self):
        a, b = (3, 4, 5), (10, 20, 30)
        assert dist_3d(a, b) == pytest.approx(dist_3d(b, a))

    def test_non_origin(self):
        d = dist_3d((1, 2, 3), (4, 6, 3))
        assert d == pytest.approx(5.0)  # 3-4-5 triangle in xy


class TestAIControllerDecision:
    """AIController 决策字典结构测试（需要 Ursina 运行时创建 Player）"""

    @pytest.fixture
    def ai_ctrl(self, ursina_app):
        from arena.player import Player
        from arena.ai_ctrl import AIController
        from arena.constants import Team
        player = Player(player_id=2, team=Team.RED,
                        spawn_position=Vec3(0, 0, -24))
        ctrl = AIController(player)
        yield ctrl
        from ursina import destroy
        destroy(player)

    def test_dead_player_returns_empty(self, ai_ctrl):
        """死亡玩家返回空字典"""
        from arena.constants import PlayerState
        ai_ctrl.player.state = PlayerState.DEAD
        result = ai_ctrl.update()
        assert result == {}

    def test_patrol_returns_decision_dict(self, ai_ctrl):
        """巡逻状态返回正确结构的决策字典"""
        # 无敌人在场时（game_manager 未初始化，_find_nearest_enemy 会报错）
        # 需要预先设置巡逻点避免调用 game_manager
        ai_ctrl.patrol_points = [
            Vec3(-10, 0, -20), Vec3(10, 0, -20),
            Vec3(-10, 0, -10), Vec3(10, 0, -10),
            Vec3(0, 0, -15),
        ]
        # 需要避免 _find_nearest_enemy 访问 game_manager
        ai_ctrl._find_nearest_enemy = lambda: None

        result = ai_ctrl.update()
        assert isinstance(result, dict)
        assert 'look_at' in result
        assert 'move_fwd' in result
        assert 'request_raycast' in result
        assert 'shoot_dir' in result
        assert result['move_fwd'] == 1.0
        assert result['request_raycast'] is True
        assert result['shoot_dir'] is None

    def test_attack_returns_shoot_dir(self, ai_ctrl):
        """攻击状态返回射击方向"""
        import time as _time
        # 创建 mock enemy
        class MockEnemy:
            position = Vec3(5, 0, -20)
        enemy = MockEnemy()

        # 强制进入攻击路径
        ai_ctrl.state = 'patrol'
        ai_ctrl._find_nearest_enemy = lambda: enemy
        ai_ctrl.last_shoot_time = 0  # 允许射击

        result = ai_ctrl.update()
        assert isinstance(result, dict)
        assert result.get('shoot_dir') is not None
        assert len(result['shoot_dir']) == 3

    def test_chase_returns_look_at(self, ai_ctrl):
        """追击状态返回朝向目标"""
        class MockEnemy:
            position = Vec3(30, 0, -20)  # dist ≈ 30.3, 在 detection_range(40) 内但不在 attack_range(25) 内
        enemy = MockEnemy()

        ai_ctrl._find_nearest_enemy = lambda: enemy
        # 确保 distance 在 chase 范围内
        # player pos = (0,0,-24), enemy pos = (20,0,-20) => dist ≈ 20.4
        result = ai_ctrl.update()
        assert isinstance(result, dict)
        assert result.get('look_at') is not None
        assert result['move_fwd'] == 1.0

    def test_avoiding_returns_rotate(self, ai_ctrl):
        """回避状态返回旋转指令"""
        import time as _time
        ai_ctrl.avoiding = True
        ai_ctrl.avoid_end_time = _time.time() + 5.0
        ai_ctrl.avoid_direction = 1

        result = ai_ctrl.update()
        assert 'rotate_y' in result
        assert result['rotate_y'] != 0
        assert result['move_fwd'] == 1.0

    def test_avoiding_expired_clears_flag(self, ai_ctrl):
        """回避超时后清除回避标志"""
        import time as _time
        ai_ctrl.avoiding = True
        ai_ctrl.avoid_end_time = _time.time() - 1.0  # 已过期
        ai_ctrl.patrol_points = [Vec3(-10, 0, -20), Vec3(10, 0, -20)]
        ai_ctrl._find_nearest_enemy = lambda: None

        result = ai_ctrl.update()
        assert ai_ctrl.avoiding is False
