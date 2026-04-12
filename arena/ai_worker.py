"""AI 子进程主循环

在独立进程中运行，从共享内存读取玩家状态，运行 AI 计算，写回决策。
不导入任何 Ursina 模块，纯 Python + ctypes。
"""
import math
import time
import random
import ctypes
from multiprocessing.shared_memory import SharedMemory

from arena.shared_state import SharedGameState, MAX_PLAYERS, PlayerCommand
from arena.ai_ctrl import AIController, forward_from_rotation, dist_3d

# ==================== 纯数据 AI 控制器 ====================

class AIDecider:
    """纯数据 AI 决策器（不持有 Entity 引用）

    从共享内存的 PlayerInput 读取状态，输出 PlayerCommand。
    """

    def __init__(self, player_id, team_id, spawn_x, spawn_z,
                 detection_range=40, attack_range=25, shoot_spread=0.05):
        self.player_id = player_id
        self.team_id = team_id
        self.spawn_x = spawn_x
        self.spawn_z = spawn_z

        self.detection_range = detection_range
        self.attack_range = attack_range
        self.shoot_spread = shoot_spread

        self.patrol_points = []
        self.current_patrol_idx = 0
        self.state = 'patrol'

        # 碰撞回避
        self.avoiding = False
        self.avoid_end_time = 0
        self.avoid_direction = 0

        # 射击节流
        self.last_shoot_time = 0
        self.shoot_interval = 0.2

    def update(self, my_input, all_inputs, dt):
        """计算决策，返回 dict

        Args:
            my_input: PlayerInput — 自己的状态
            all_inputs: list[PlayerInput] — 所有玩家状态
            dt: float — 上一帧时间

        Returns:
            dict: 决策字典
        """
        if my_input.state != 0:  # 0=alive
            return {}

        # 碰撞回避优先
        if self.avoiding:
            if time.time() < self.avoid_end_time:
                return {
                    'rotate_y': self.avoid_direction * 90 * dt,
                    'move_fwd': 1.0,
                    'request_raycast': True,
                    'shoot_dir': None,
                    'avoiding': True,
                    'avoid_direction': self.avoid_direction,
                }
            else:
                self.avoiding = False

        # 寻找最近敌人
        my_pos = (my_input.pos_x, my_input.pos_y, my_input.pos_z)
        enemy = None
        enemy_pos = None
        min_dist = float('inf')
        for p in all_inputs:
            if p.team_id != self.team_id and p.state == 0:
                p_pos = (p.pos_x, p.pos_y, p.pos_z)
                d = dist_3d(my_pos, p_pos)
                if d < min_dist:
                    min_dist = d
                    enemy = p
                    enemy_pos = p_pos

        if enemy and min_dist < self.attack_range:
            return self._attack(my_input, enemy)
        elif enemy and min_dist < self.detection_range:
            return self._chase(enemy)
        else:
            return self._patrol(my_input, dt)

    def _attack(self, my_input, target):
        self.state = 'attack'
        result = {
            'look_at': (target.pos_x, target.pos_z),
            'move_fwd': 0.0,
            'request_raycast': False,
            'shoot_dir': None,
            'avoiding': False,
            'avoid_direction': 0,
        }

        if time.time() - self.last_shoot_time > self.shoot_interval:
            fwd = forward_from_rotation(my_input.rotation_y)
            spread = (
                random.uniform(-self.shoot_spread, self.shoot_spread),
                random.uniform(-self.shoot_spread, self.shoot_spread),
                random.uniform(-self.shoot_spread, self.shoot_spread),
            )
            result['shoot_dir'] = (fwd[0] + spread[0], fwd[1] + spread[1], fwd[2] + spread[2])
            self.last_shoot_time = time.time()

        return result

    def _chase(self, target):
        self.state = 'chase'
        return {
            'look_at': (target.pos_x, target.pos_z),
            'move_fwd': 1.0,
            'request_raycast': True,
            'shoot_dir': None,
            'avoiding': False,
            'avoid_direction': 0,
        }

    def _patrol(self, my_input, dt):
        self.state = 'patrol'
        if not self.patrol_points:
            self._generate_patrol_points()

        target = self.patrol_points[self.current_patrol_idx]
        my_pos = (my_input.pos_x, my_input.pos_y, my_input.pos_z)
        if dist_3d(my_pos, target) < 2:
            self.current_patrol_idx = (self.current_patrol_idx + 1) % len(self.patrol_points)

        return {
            'look_at': (target[0], target[2]),
            'move_fwd': 1.0,
            'request_raycast': True,
            'shoot_dir': None,
            'avoiding': False,
            'avoid_direction': 0,
        }

    def _generate_patrol_points(self):
        z_sign = 1 if self.team_id == 0 else -1
        base_z = self.spawn_z
        self.patrol_points = [
            (-10, 0, base_z + z_sign * 5),
            (10, 0, base_z + z_sign * 5),
            (-10, 0, base_z + z_sign * 15),
            (10, 0, base_z + z_sign * 15),
            (0, 0, base_z + z_sign * 10),
        ]

    def set_avoiding(self, direction):
        """由主进程 raycast 结果触发"""
        self.avoiding = True
        self.avoid_end_time = time.time() + 1.0
        self.avoid_direction = direction


def dict_to_command(d, cmd):
    """将决策字典写入 PlayerCommand 结构"""
    import math
    nan = float('nan')

    cmd.look_at_x = d.get('look_at', (nan, nan))[0] if d.get('look_at') else nan
    cmd.look_at_z = d.get('look_at', (nan, nan))[1] if d.get('look_at') else nan
    cmd.rotate_y = d.get('rotate_y', 0.0)
    cmd.move_fwd = d.get('move_fwd', 0.0)
    cmd.request_raycast = 1 if d.get('request_raycast') else 0
    sd = d.get('shoot_dir')
    if sd:
        cmd.shoot_dir_x, cmd.shoot_dir_y, cmd.shoot_dir_z = sd
    else:
        cmd.shoot_dir_x = nan
        cmd.shoot_dir_y = nan
        cmd.shoot_dir_z = nan
    cmd.avoiding = 1 if d.get('avoiding') else 0
    cmd.avoid_direction = d.get('avoid_direction', 0)


def ai_process_main(shm_name):
    """AI 子进程入口

    Args:
        shm_name: 共享内存名称
    """
    # 连接共享内存
    shm = SharedMemory(name=shm_name)
    state = SharedGameState.from_buffer(shm.buf)

    # 初始化 AI 决策器（从共享内存的初始玩家数据读取）
    deciders = {}
    # 等待主进程写入初始数据
    while state.running == 0:
        time.sleep(0.01)

    for i in range(state.player_count):
        p = state.players[i]
        deciders[p.player_id] = AIDecider(
            player_id=p.player_id,
            team_id=p.team_id,
            spawn_x=p.spawn_x,
            spawn_z=p.spawn_z,
        )

    last_frame = 0
    print(f'[AI Worker] Started, managing {len(deciders)} AI players')

    while state.running:
        # 等待新帧
        if state.frame_number == last_frame:
            time.sleep(0.001)
            continue
        last_frame = state.frame_number
        dt = state.dt if state.dt > 0 else 1/60

        # 收集所有玩家输入
        all_inputs = [state.players[i] for i in range(state.player_count)]

        # 为每个 AI 玩家计算决策
        for pid, decider in deciders.items():
            # 找到自己的输入
            my_input = None
            for p in all_inputs:
                if p.player_id == pid:
                    my_input = p
                    break
            if my_input is None:
                continue

            # raycast 回避反馈
            if my_input.ray_hit and decider.state != 'patrol':
                decider.set_avoiding(1 if random.random() > 0.5 else -1)

            # 计算
            decision = decider.update(my_input, all_inputs, dt)

            # 写回
            for i in range(state.player_count):
                if state.players[i].player_id == pid:
                    dict_to_command(decision, state.commands[i])
                    break

        state.ai_frame_done = 1

    # 清理
    shm.close()
    print('[AI Worker] Stopped')


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        ai_process_main(sys.argv[1])
