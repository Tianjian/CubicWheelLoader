"""AI 进程管理器 — 启动/停止 AI 子进程，同步共享内存

主进程通过 AIProcessManager 每帧：
1. 将玩家状态写入共享内存
2. 等待 AI 子进程完成计算
3. 读取 AI 决策并返回
"""
import math
import time
import ctypes
from multiprocessing import Process, shared_memory

from arena.shared_state import SharedGameState, MAX_PLAYERS, PlayerCommand
from arena.constants import Config


class AIProcessManager:
    """管理 AI 子进程的生命周期和共享内存通信"""

    def __init__(self):
        self.shm = None
        self.state = None
        self.process = None
        self._started = False

    def start(self, players_info):
        """启动 AI 子进程

        Args:
            players_info: list of dict with keys:
                player_id, team_id, spawn_x, spawn_z
                只包含 AI 玩家
        """
        if self._started:
            self.stop()

        # 创建共享内存
        size = ctypes.sizeof(SharedGameState)
        self.shm = shared_memory.SharedMemory(create=True, size=size)
        self.state = SharedGameState.from_buffer(self.shm.buf)

        # 初始化共享状态
        self.state.running = 0
        self.state.frame_number = 0
        self.state.ai_frame_done = 0
        self.state.player_count = len(players_info)
        self.state.dt = 1/60

        for i, info in enumerate(players_info):
            p = self.state.players[i]
            p.player_id = info['player_id']
            p.team_id = info['team_id']
            p.state = 0  # alive
            p.pos_x = info.get('spawn_x', 0)
            p.pos_y = 0
            p.pos_z = info.get('spawn_z', 0)
            p.rotation_y = 0
            p.hp = Config.PLAYER_MAX_HP
            p.spawn_x = info.get('spawn_x', 0)
            p.spawn_z = info.get('spawn_z', 0)
            p.ray_hit = 0
            p.ray_distance = 0

            # 初始化命令
            cmd = self.state.commands[i]
            cmd.move_fwd = 0
            cmd.request_raycast = 0
            cmd.shoot_dir_x = float('nan')
            cmd.shoot_dir_y = float('nan')
            cmd.shoot_dir_z = float('nan')
            cmd.avoiding = 0
            cmd.avoid_direction = 0

        # 启动子进程
        from arena.ai_worker import ai_process_main
        self.process = Process(
            target=ai_process_main,
            args=(self.shm.name,),
            daemon=True
        )
        self.process.start()

        # 标记运行
        self.state.running = 1
        self._started = True
        print(f'[AIProcessManager] Started AI subprocess (shm={self.shm.name})')

    def write_player_states(self, all_players, dt):
        """每帧将所有玩家状态写入共享内存

        Args:
            all_players: list of Player Entity objects
            dt: float — time.dt
        """
        if not self._started or not self.state:
            return

        self.state.dt = dt
        self.state.ai_frame_done = 0
        self.state.frame_number += 1

        for i, player in enumerate(all_players):
            if i >= MAX_PLAYERS:
                break
            p = self.state.players[i]
            p.pos_x = player.x
            p.pos_y = player.y
            p.pos_z = player.z
            p.rotation_y = player.rotation_y
            p.hp = player.hp
            # state mapping: alive=0, dead=1, respawning=2
            state_map = {'alive': 0, 'dead': 1, 'respawning': 2}
            p.state = state_map.get(player.state.value, 1)

    def read_commands(self, timeout=0.005):
        """等待 AI 完成并读取决策

        Args:
            timeout: 最大等待时间（秒）

        Returns:
            dict: {player_id: command_dict} 或空 dict
        """
        if not self._started or not self.state:
            return {}

        # 等待 AI 完成
        deadline = time.time() + timeout
        while self.state.ai_frame_done == 0:
            if time.time() > deadline:
                return {}  # 超时，返回空（使用上帧结果）
            time.sleep(0.001)

        result = {}
        nan = float('nan')
        for i in range(self.state.player_count):
            p = self.state.players[i]
            cmd = self.state.commands[i]

            command_dict = {
                'look_at': None,
                'rotate_y': None,
                'move_fwd': cmd.move_fwd,
                'request_raycast': bool(cmd.request_raycast),
                'shoot_dir': None,
            }

            if not math.isnan(cmd.look_at_x):
                command_dict['look_at'] = (cmd.look_at_x, cmd.look_at_z)

            if cmd.rotate_y != 0:
                command_dict['rotate_y'] = cmd.rotate_y

            if not math.isnan(cmd.shoot_dir_x):
                command_dict['shoot_dir'] = (cmd.shoot_dir_x, cmd.shoot_dir_y, cmd.shoot_dir_z)

            # 回避状态回传
            if cmd.avoiding:
                command_dict['_avoiding'] = True
                command_dict['_avoid_direction'] = cmd.avoid_direction

            result[p.player_id] = command_dict

        return result

    def stop(self):
        """停止 AI 子进程"""
        if not self._started:
            return

        if self.state:
            self.state.running = 0

        if self.process and self.process.is_alive():
            self.process.join(timeout=2.0)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=1.0)

        if self.shm:
            try:
                self.shm.close()
                self.shm.unlink()
            except Exception:
                pass

        self._started = False
        self.process = None
        self.shm = None
        self.state = None
        print('[AIProcessManager] Stopped AI subprocess')

    @property
    def is_running(self):
        return self._started and self.process and self.process.is_alive()
