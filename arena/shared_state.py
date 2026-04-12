"""共享内存结构定义 — 主进程与 AI 子进程的通信协议

主进程每帧写入所有玩家状态 → AI 子进程读取后计算决策 → 写回命令 → 主进程读取并应用。

所有结构使用 ctypes，布局固定，可直接映射到 SharedMemory。
"""
import ctypes
from arena.constants import Config

# ==================== 常量 ====================

MAX_PLAYERS = 4
MAX_PATROL_POINTS = 8
MAX_NAME_LEN = 16

# ==================== 单个玩家状态（主进程 → AI）====================

class PlayerInput(ctypes.Structure):
    """主进程写入的玩家状态"""
    _fields_ = [
        ('player_id', ctypes.c_int32),       # 1-4
        ('team_id', ctypes.c_int32),         # 0=RED, 1=BLUE
        ('state', ctypes.c_int32),           # 0=alive, 1=dead, 2=respawning
        ('pos_x', ctypes.c_float),
        ('pos_y', ctypes.c_float),
        ('pos_z', ctypes.c_float),
        ('rotation_y', ctypes.c_float),
        ('hp', ctypes.c_float),
        ('spawn_x', ctypes.c_float),
        ('spawn_z', ctypes.c_float),
        # raycast 结果（主进程代为执行）
        ('ray_hit', ctypes.c_int32),         # 0=无障碍, 1=有障碍
        ('ray_distance', ctypes.c_float),
    ]


# ==================== 单个玩家 AI 决策（AI → 主进程）====================

class PlayerCommand(ctypes.Structure):
    """AI 子进程写回的决策"""
    _fields_ = [
        ('look_at_x', ctypes.c_float),       # 朝向目标 X（NaN = 不设置）
        ('look_at_z', ctypes.c_float),       # 朝向目标 Z
        ('rotate_y', ctypes.c_float),        # 旋转增量（0 = 不设置）
        ('move_fwd', ctypes.c_float),        # -1..1 前进量
        ('request_raycast', ctypes.c_int32), # 是否需要碰撞检测
        ('shoot_dir_x', ctypes.c_float),     # 射击方向（NaN = 不射击）
        ('shoot_dir_y', ctypes.c_float),
        ('shoot_dir_z', ctypes.c_float),
        ('avoiding', ctypes.c_int32),        # AI 内部状态回传
        ('avoid_direction', ctypes.c_int32), # 回避方向
    ]


# ==================== 完整共享状态 ====================

class SharedGameState(ctypes.Structure):
    """主进程与 AI 子进程的完整共享内存布局"""
    _fields_ = [
        # 控制
        ('running', ctypes.c_int32),          # 1=运行中, 0=停止
        ('frame_number', ctypes.c_int32),     # 帧计数，主进程递增
        ('ai_frame_done', ctypes.c_int32),    # AI 完成标志
        # 玩家输入
        ('players', PlayerInput * MAX_PLAYERS),
        ('player_count', ctypes.c_int32),
        # AI 决策输出
        ('commands', PlayerCommand * MAX_PLAYERS),
        # dt
        ('dt', ctypes.c_float),              # 上一帧的 time.dt
    ]


def shared_state_size():
    """返回共享内存大小"""
    return ctypes.sizeof(SharedGameState)
