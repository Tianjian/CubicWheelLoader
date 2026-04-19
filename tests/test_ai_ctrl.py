"""AI 控制器纯函数 + 决策逻辑单元测试"""
import math
import time
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


class TestComputeDetourWaypoint:
    """_compute_detour_waypoint 绕行路径点计算测试"""

    @pytest.fixture
    def ai_ctrl(self, ursina_app):
        from arena.player import Player
        from arena.ai_ctrl import AIController
        from arena.constants import Team
        player = Player(player_id=2, team=Team.RED,
                        spawn_position=Vec3(0, 0, 0))
        ctrl = AIController(player)
        yield ctrl
        from ursina import destroy
        destroy(player)

    def test_obstacle_directly_ahead_target_right(self, ai_ctrl):
        """障碍物在前方，目标在右侧 → 选择右侧绕行点"""
        # AI 在 (0,0,0)，障碍物在 (5,0,0)，目标在 (10,0,0) 正后方
        obstacle_pos = Vec3(5, 0, 0)
        target_pos = (10, 0, 0)
        waypoint = ai_ctrl._compute_detour_waypoint(obstacle_pos, target_pos)

        # 应该选择离目标更近的一侧
        # 左侧: (5, 0, -3.5), 右侧: (5, 0, 3.5)
        # 目标在 x=10，两侧离目标等距（都是 sqrt(25 + 12.25)）
        # 但由于浮点精度，选择哪个都可以，只需验证是其中一个
        assert waypoint.y == 0
        assert abs(waypoint.x - 5) < 0.1  # x 接近障碍物 x
        assert abs(abs(waypoint.z) - 3.5) < 0.1  # z 在 ±3.5

    def test_obstacle_ahead_target_offset_left(self, ai_ctrl):
        """障碍物在前方，目标偏左 → 选择左侧绕行点"""
        obstacle_pos = Vec3(5, 0, 0)
        target_pos = (10, 0, -5)  # 目标偏左（-z 方向）

        waypoint = ai_ctrl._compute_detour_waypoint(obstacle_pos, target_pos)

        # 左侧绕行点 (5, 0, -2.5) 离目标更近
        assert waypoint.z < 0  # 应该在左侧（-z）

    def test_obstacle_ahead_target_offset_right(self, ai_ctrl):
        """障碍物在前方，目标偏右 → 选择右侧绕行点"""
        obstacle_pos = Vec3(5, 0, 0)
        target_pos = (10, 0, 5)  # 目标偏右（+z 方向）

        waypoint = ai_ctrl._compute_detour_waypoint(obstacle_pos, target_pos)

        # 右侧绕行点 (5, 0, 2.5) 离目标更近
        assert waypoint.z > 0  # 应该在右侧（+z）

    def test_obstacle_on_right_target_ahead(self, ai_ctrl):
        """AI 在原点，障碍物在右前方，目标正前方"""
        # 将 AI 移到 (-5, 0, 0)
        ai_ctrl.player.position = Vec3(-5, 0, 0)
        obstacle_pos = Vec3(0, 0, 3)
        target_pos = (5, 0, 0)

        waypoint = ai_ctrl._compute_detour_waypoint(obstacle_pos, target_pos)

        # 应该是障碍物两侧的某个点
        assert waypoint.y == 0

    def test_ai_on_top_of_obstacle(self, ai_ctrl):
        """AI 在障碍物正上方（极端情况）"""
        # AI 和障碍物在同一位置
        ai_ctrl.player.position = Vec3(5, 0, 5)
        obstacle_pos = Vec3(5, 0, 5)
        target_pos = (10, 0, 10)

        # 不应崩溃，应基于 player.forward 计算方向
        waypoint = ai_ctrl._compute_detour_waypoint(obstacle_pos, target_pos)
        assert isinstance(waypoint, Vec3)

    def test_detour_dist_is_3_5(self, ai_ctrl):
        """绕行距离为 3.5（障碍物半宽1+边距2.5）"""
        ai_ctrl.player.position = Vec3(0, 0, 0)
        obstacle_pos = Vec3(10, 0, 0)
        target_pos = (20, 0, 0)

        waypoint = ai_ctrl._compute_detour_waypoint(obstacle_pos, target_pos)

        # waypoint 应该在障碍物侧面 3.5 距离处
        offset = abs(waypoint.z)  # 左右偏移在 z 轴
        assert abs(offset - 3.5) < 0.1


class TestOnCollision:
    """on_collision 碰撞回调测试"""

    @pytest.fixture
    def ai_ctrl(self, ursina_app):
        from arena.player import Player
        from arena.ai_ctrl import AIController
        from arena.constants import Team
        player = Player(player_id=2, team=Team.RED,
                        spawn_position=Vec3(0, 0, 0))
        ctrl = AIController(player)
        yield ctrl
        from ursina import destroy
        destroy(player)

    def test_first_collision_enters_navigating(self, ai_ctrl):
        """首次碰撞进入绕行状态"""
        assert ai_ctrl.navigating is False

        obstacle_pos = Vec3(5, 0, 0)
        target_pos = (10, 0, 0)
        ai_ctrl.on_collision(obstacle_pos, target_pos)

        assert ai_ctrl.navigating is True
        assert ai_ctrl.nav_waypoint is not None
        assert ai_ctrl.nav_target_pos == target_pos
        assert ai_ctrl.nav_stuck_count == 0

    def test_navigate_returns_look_at_waypoint(self, ai_ctrl):
        """绕行状态返回朝向 waypoint 的决策"""
        obstacle_pos = Vec3(5, 0, 0)
        target_pos = (10, 0, 0)
        ai_ctrl.on_collision(obstacle_pos, target_pos)

        # Mock LOS 为 False（模拟仍有障碍物遮挡）
        ai_ctrl._has_line_of_sight = lambda pos: False

        result = ai_ctrl._navigate()
        assert result['look_at'] == (ai_ctrl.nav_waypoint.x, ai_ctrl.nav_waypoint.z)
        assert result['move_fwd'] == 1.0
        assert result['request_raycast'] is False

    def test_same_obstacle_twice_increments_stuck(self, ai_ctrl):
        """连续碰到同一障碍物增加卡住计数"""
        obstacle_pos = Vec3(5, 0, 0)
        target_pos = (10, 0, 0)

        ai_ctrl.on_collision(obstacle_pos, target_pos)
        assert ai_ctrl.nav_stuck_count == 0

        # 再次碰到同一障碍物
        ai_ctrl.on_collision(obstacle_pos, target_pos)
        assert ai_ctrl.nav_stuck_count == 1

    def test_stuck_count_flips_direction_at_2(self, ai_ctrl):
        """卡住超过2次后翻转方向"""
        obstacle_pos = Vec3(5, 0, 0)
        target_pos = (10, 0, 0)

        # 碰撞3次
        for _ in range(3):
            ai_ctrl.on_collision(obstacle_pos, target_pos)

        assert ai_ctrl.nav_stuck_count >= 2

    def test_different_obstacle_resets_stuck(self, ai_ctrl):
        """碰到不同障碍物重置卡住计数"""
        target_pos = (10, 0, 0)

        ai_ctrl.on_collision(Vec3(5, 0, 0), target_pos)
        ai_ctrl.on_collision(Vec3(5, 0, 0), target_pos)
        assert ai_ctrl.nav_stuck_count == 1

        # 碰到远处的新障碍物
        ai_ctrl.on_collision(Vec3(20, 0, 0), target_pos)
        assert ai_ctrl.nav_stuck_count == 0

    def test_navigating_collision_preserves_original_target(self, ai_ctrl):
        """绕行中再次碰撞保留原始目标位置"""
        original_target = (20, 0, 0)
        ai_ctrl.on_collision(Vec3(5, 0, 0), original_target)
        assert ai_ctrl.nav_target_pos == original_target

        # 绕行中碰到新障碍物，传入了不同的 target_pos
        ai_ctrl.on_collision(Vec3(5, 0, 1), (5, 0, 2))
        # 原始目标应保留
        assert ai_ctrl.nav_target_pos == original_target


class TestNavigate:
    """_navigate 绕行状态测试"""

    @pytest.fixture
    def ai_ctrl(self, ursina_app):
        from arena.player import Player
        from arena.ai_ctrl import AIController
        from arena.constants import Team
        player = Player(player_id=2, team=Team.RED,
                        spawn_position=Vec3(0, 0, 0))
        ctrl = AIController(player)
        yield ctrl
        from ursina import destroy
        destroy(player)

    def test_timeout_exits_to_patrol(self, ai_ctrl):
        """超时退出绕行切换巡逻"""
        obstacle_pos = Vec3(5, 0, 0)
        target_pos = (10, 0, 0)
        ai_ctrl.on_collision(obstacle_pos, target_pos)

        # 模拟超时
        ai_ctrl.nav_start_time = time.time() - 10.0
        result = ai_ctrl._navigate()

        assert ai_ctrl.navigating is False
        # 应该返回巡逻决策
        assert result['move_fwd'] == 1.0

    def test_end_navigate_resets_state(self, ai_ctrl):
        """_end_navigate 重置所有绕行状态"""
        obstacle_pos = Vec3(5, 0, 0)
        target_pos = (10, 0, 0)
        ai_ctrl.on_collision(obstacle_pos, target_pos)

        ai_ctrl._end_navigate()
        assert ai_ctrl.navigating is False
        assert ai_ctrl.nav_waypoint is None
        assert ai_ctrl.nav_target_pos is None
        assert ai_ctrl.nav_stuck_count == 0

    def test_navigate_priority_over_state_machine(self, ai_ctrl):
        """绕行状态优先于状态机"""
        obstacle_pos = Vec3(5, 0, 0)
        target_pos = (10, 0, 0)
        ai_ctrl.on_collision(obstacle_pos, target_pos)

        # Mock LOS 为 False（模拟仍有障碍物遮挡）
        ai_ctrl._has_line_of_sight = lambda pos: False

        # update() 应该调用 _navigate() 而不是 _state_machine()
        result = ai_ctrl.update()
        assert ai_ctrl.navigating is True
        assert result['look_at'] == (ai_ctrl.nav_waypoint.x, ai_ctrl.nav_waypoint.z)

    def test_dead_player_skips_navigate(self, ai_ctrl):
        """死亡玩家不执行绕行"""
        from arena.constants import PlayerState
        obstacle_pos = Vec3(5, 0, 0)
        target_pos = (10, 0, 0)
        ai_ctrl.on_collision(obstacle_pos, target_pos)

        ai_ctrl.player.state = PlayerState.DEAD
        result = ai_ctrl.update()
        assert result == {}


class TestAIControllerDecision:
    """AIController 决策字典结构测试"""

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
        ai_ctrl.patrol_points = [
            Vec3(-10, 0, -20), Vec3(10, 0, -20),
            Vec3(-10, 0, -10), Vec3(10, 0, -10),
            Vec3(0, 0, -15),
        ]
        # Mock 掉需要 game_manager 的方法
        ai_ctrl._evaluate_targets = lambda: []

        result = ai_ctrl.update()
        assert isinstance(result, dict)
        assert 'look_at' in result
        assert 'move_fwd' in result
        assert 'request_raycast' in result
        assert 'shoot_dir' in result
        assert result['move_fwd'] == 1.0
        assert result['request_raycast'] is True
        assert result['shoot_dir'] is None

    def test_navigating_state_returns_waypoint_direction(self, ai_ctrl):
        """绕行状态返回朝向 waypoint 的决策"""
        obstacle_pos = Vec3(5, 0, -24)
        target_pos = (10, 0, -24)
        ai_ctrl.on_collision(obstacle_pos, target_pos)

        result = ai_ctrl.update()
        assert isinstance(result, dict)
        assert result['look_at'] is not None
        assert result['move_fwd'] == 1.0
        assert result['request_raycast'] is True

    def test_current_target_goal_id_set_when_shooting_goal(self, ai_ctrl):
        """射击 Goal 时声明 current_target_goal_id"""
        assert ai_ctrl.current_target_goal_id is None

        # 模拟一个 Goal 对象
        class MockGoal:
            goal_id = 3
            position = Vec3(3, 0, -24)
            owner = None  # 不属于己方

        ai_ctrl._shoot_goal(MockGoal())
        assert ai_ctrl.current_target_goal_id == 3

    def test_current_target_goal_id_cleared_in_other_states(self, ai_ctrl):
        """非射击 Goal 状态时清除 current_target_goal_id"""
        ai_ctrl.current_target_goal_id = 3
        ai_ctrl.patrol_points = [Vec3(-10, 0, -20), Vec3(10, 0, -20)]
        ai_ctrl._evaluate_targets = lambda: []

        ai_ctrl.update()
        assert ai_ctrl.current_target_goal_id is None


class TestIsInOurHalf:
    """_is_in_our_half 半场判断测试"""

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

    def test_red_team_negative_z_is_our_half(self, ai_ctrl):
        """RED 队：z < 0 是本方半场"""
        assert ai_ctrl._is_in_our_half(Vec3(0, 0, -5)) is True
        assert ai_ctrl._is_in_our_half(Vec3(0, 0, 5)) is False
        assert ai_ctrl._is_in_our_half(Vec3(0, 0, 0)) is False

    def test_blue_team_positive_z_is_our_half(self, ai_ctrl):
        """BLUE 队：z > 0 是本方半场"""
        from arena.constants import Team
        ai_ctrl.player.team = Team.BLUE
        assert ai_ctrl._is_in_our_half(Vec3(0, 0, 5)) is True
        assert ai_ctrl._is_in_our_half(Vec3(0, 0, -5)) is False
        assert ai_ctrl._is_in_our_half(Vec3(0, 0, 0)) is False


class TestEvaluateTargets:
    """_evaluate_targets 统一目标评分测试"""

    @pytest.fixture
    def ai_ctrl(self, ursina_app):
        from arena.player import Player
        from arena.ai_ctrl import AIController
        from arena.constants import Team
        player = Player(player_id=2, team=Team.RED,
                        spawn_position=Vec3(0, 0, -5))
        ctrl = AIController(player)
        yield ctrl
        from ursina import destroy
        destroy(player)

    def test_empty_when_no_targets(self, ai_ctrl):
        """无目标时返回空列表"""
        ai_ctrl._get_teammate_target_ids = lambda: set()
        # Mock game_manager 返回空目标
        import arena.game_manager as gm_mod
        original_gm = gm_mod.game_manager

        class MockMap:
            goals = []

        class MockGM:
            game_map = MockMap()
            players = []

        gm_mod.game_manager = MockGM()
        try:
            result = ai_ctrl._evaluate_targets()
            assert result == []
        finally:
            gm_mod.game_manager = original_gm

    def test_goal_scores_higher_than_distant_player(self, ai_ctrl):
        """近处 Goal 评分高于远处普通敌人"""
        from arena.constants import Team, PlayerState
        import arena.game_manager as gm_mod
        original_gm = gm_mod.game_manager

        class MockGoal:
            goal_id = 1
            position = Vec3(3, 0, -5)
            owner = Team.BLUE

        class MockMap:
            goals = [MockGoal()]

        class MockWeapon:
            current_ammo = 3

        class MockPlayer:
            team = Team.BLUE
            state = PlayerState.ALIVE
            position = Vec3(10, 0, 10)
            weapon = MockWeapon()

        class MockGM:
            game_map = MockMap()
            players = [MockPlayer()]

        ai_ctrl._get_teammate_target_ids = lambda: set()
        ai_ctrl._has_line_of_sight = lambda pos: True
        gm_mod.game_manager = MockGM()
        try:
            result = ai_ctrl._evaluate_targets()
            assert len(result) >= 2
            # Goal should score higher
            assert result[0][1] == 'goal'
        finally:
            gm_mod.game_manager = original_gm

    def test_defender_urgency_on_high_ammo_enemy_in_our_half(self, ai_ctrl):
        """本方半场高弹药敌人获得防守加成，评分超过 Goal"""
        from arena.constants import Team, PlayerState, Config
        import arena.game_manager as gm_mod
        original_gm = gm_mod.game_manager

        class MockGoal:
            goal_id = 1
            position = Vec3(6, 0, -6)
            owner = Team.BLUE

        class MockMap:
            goals = [MockGoal()]

        class MockWeapon:
            current_ammo = Config.AI_HIGH_AMMO_THRESHOLD  # 高弹药

        class MockEnemy:
            team = Team.BLUE
            state = PlayerState.ALIVE
            position = Vec3(1, 0, -3)  # RED 本方半场 (z<0)
            weapon = MockWeapon()

        class MockGM:
            game_map = MockMap()
            players = [MockEnemy()]

        ai_ctrl._get_teammate_target_ids = lambda: set()
        ai_ctrl._has_line_of_sight = lambda pos: True
        gm_mod.game_manager = MockGM()
        try:
            result = ai_ctrl._evaluate_targets()
            assert len(result) >= 2
            # 防守加成的敌人应排第一
            assert result[0][1] == 'player'
        finally:
            gm_mod.game_manager = original_gm
