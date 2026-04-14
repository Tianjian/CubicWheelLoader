# CubicWheelLoader — TPS 团队竞技对战

基于 Ursina 引擎的第三人称视角团队竞技对战游戏。4 名玩家分为红蓝两队，占领 Goal 圆柱得分，击杀对手加分，2 分钟比赛结束后总分高的队伍获胜。

## 快速开始

```bash
pip install ursina
python main.py
```

## 操作

| 按键 | 功能 |
|------|------|
| W / S | 前进 / 后退 |
| A / D | 左转 / 右转 |
| 鼠标左键 | 射击（按住连射） |
| V | 切换 TPS 远 / 近视角 |
| Tab | 编辑器模式 |

### 手柄（Xbox 标准手柄）

| 操作 | 手柄 |
|------|------|
| 移动 | 左摇杆 |
| 旋转 | 右摇杆 X |
| 射击 | 左扳机 LT |
| 切换视角 | X 键 |

## 项目结构

```
CubicWheelLoader/
├── main.py                  # 游戏入口
├── game_settings.json       # 游戏参数配置（唯一配置源）
│
├── arena/                   # 游戏核心包
│   ├── constants.py         # 枚举、常量、配置（从 JSON 加载）
│   ├── xinput.py            # Windows XInput ctypes 封装
│   ├── input_manager.py     # 输入抽象层（键盘 + 手柄）
│   ├── player.py            # 玩家角色实体
│   ├── weapon.py            # 武器系统（含弹药）
│   ├── bullet.py            # 子弹实体
│   ├── goal.py              # Goal 圆柱目标
│   ├── base.py              # 队伍基地
│   ├── game_map.py          # 竞技地图
│   ├── map_loader.py        # 地图 JSON 加载器
│   ├── camera_ctrl.py       # 相机控制器（队伍对称）
│   ├── human_ctrl.py        # 人类玩家控制器
│   ├── ai_ctrl.py           # AI 控制器（6 状态机 + 绕行导航）
│   ├── ai_worker.py         # AI 子进程入口（纯 Python，无 Ursina 依赖）
│   ├── ai_process.py        # AI 进程管理器
│   ├── shared_state.py      # 共享内存 ctypes 结构定义
│   ├── score_system.py      # 计分系统（击杀分 + Goal 分独立追踪）
│   ├── match_timer.py       # 比赛计时器
│   ├── kill_feed.py         # 击杀播报
│   ├── hud.py               # 抬头显示
│   ├── sound_manager.py     # 音效管理器（MP3 + 距离衰减 + 限流）
│   ├── character_select.py  # 角色选择界面
│   └── game_manager.py      # 游戏主控
│
├── maps/                    # 地图数据（JSON）
│   └── arena_classic.json   # 默认地图
│
├── sound/                   # 音效素材（MP3）
│   ├── shoot.mp3
│   ├── hit_player.mp3
│   ├── hit_wall.mp3
│   ├── hit_goal.mp3
│   ├── damage.mp3
│   ├── death.mp3
│   ├── kill.mp3
│   ├── countdown.mp3
│   ├── match_start.mp3
│   └── match_end.mp3
│
└── tests/                   # 单元测试
    ├── conftest.py
    ├── test_xinput.py
    ├── test_input_manager.py
    ├── test_map_loader.py
    ├── test_score_system.py
    ├── test_match_timer.py
    ├── test_ai_ctrl.py
    └── test_shared_state.py
```

## 游戏规则

- **4 名 Player**：红队 x2 + 蓝队 x2，人类选择 1 个，其余 AI 控制
- **Goal 占领**：4 个圆柱目标，子弹命中 7 次内多数方占领，每个 10 分
- **击杀得分**：击杀敌方 +3 分（可配置，`kill_score > 0` 时生效）
- **弹药系统**：每人 10 发子弹，仅本方基地自动装填
- **比赛时长**：120 秒（2 分钟）
- **胜负判定**：总分 = 击杀分 + Goal 分，高分者胜

## 测试

```bash
# 运行全部测试
pytest tests/ -v

# 仅运行纯逻辑测试（无需 Ursina 运行时）
pytest tests/test_xinput.py tests/test_map_loader.py tests/test_input_manager.py tests/test_shared_state.py -v
```

## 配置

### 游戏参数配置（game_settings.json）

项目根目录下的 `game_settings.json` 是唯一的配置源，集中管理所有游戏规则和参数，修改后重启游戏即生效。

```json
{
    "player": {
        "max_hp": 100,
        "scale": 1,
        "respawn_delay": 3.0,
        "invincible_duration": 2.0
    },
    "weapon": {
        "bullet_damage": 30,
        "bullet_speed": 35,
        "fire_rate": 0.15,
        "muzzle_flash_duration": 0.05,
        "max_ammo": 10
    },
    "bullet": {
        "max_distance": 5,
        "scale": 0.3,
        "speed_multiplier": 1.5
    },
    "human": {
        "move_speed": 8,
        "rotation_speed": 120,
        "input_deadzone": 0.05
    },
    "ai": {
        "move_speed": 6,
        "rotation_speed": 90,
        "detection_range": 40,
        "attack_range": 25,
        "shoot_spread": 0.05,
        "shoot_interval": 0.4,
        "patrol_arrive_distance": 2,
        "avoid_duration": 1.0,
        "use_subprocess": false,
        "subprocess_timeout": 0.005,
        "low_ammo_threshold": 3,
        "strafe_enabled": true,
        "los_check_enabled": true,
        "goal_shoot_spread_multiplier": 0.5,
        "avoid_navigate_timeout": 3.0
    },
    "match": {
        "duration": 120,
        "kill_score": 3,
        "goal_score": 10,
        "goal_hit_window": 7,
        "timer_warning_seconds": 30
    },
    "camera": {
        "distance": 40,
        "height": 15,
        "fov_tps": 60,
        "fov_far": 45,
        "transition_speed": 10,
        "fov_spectator": 45,
        "follow_enable_delay": 0.3
    },
    "gamepad": {
        "shoot_threshold": 0.3
    },
    "map": {
        "default_name": "arena_classic"
    },
    "sound": {
        "master_volume": 0.8,
        "max_concurrent": 6,
        "ai_sound_throttle": 0.3,
        "shoot_full_distance": 15,
        "shoot_mute_distance": 40
    }
}
```

| 分区 | 关键参数 | 说明 |
|------|----------|------|
| player | max_hp, respawn_delay, invincible_duration | 玩家生命、重生延迟、无敌时长 |
| weapon | bullet_damage, max_ammo, fire_rate | 子弹伤害、弹药上限、射击间隔 |
| bullet | max_distance, scale, speed_multiplier | 子弹射程、大小、飞行速度倍率 |
| human | move_speed, rotation_speed, input_deadzone | 人类移动/旋转速度、输入死区 |
| ai | detection_range, attack_range, shoot_interval | AI 检测/攻击距离、射击节流 |
| ai | low_ammo_threshold, strafe_enabled, los_check_enabled | AI 弹药管理、侧步走位、视线检测 |
| ai | goal_shoot_spread_multiplier, avoid_navigate_timeout | AI Goal 射击精度、绕行超时 |
| ai | use_subprocess, subprocess_timeout | AI 子进程开关和超时 |
| match | duration, kill_score, goal_score, goal_hit_window | 比赛时长、击杀得分、Goal 得分、占领窗口 |
| camera | distance, height, fov_tps, fov_far | 相机距离/高度/FOV |
| gamepad | shoot_threshold | 手柄扳机射击阈值 |
| map | default_name | 默认地图名 |
| sound | master_volume, max_concurrent, ai_sound_throttle | 音量、并发数、AI 限流 |

### 地图配置（maps/*.json）

地图数据存放在 `maps/` 目录下，每个 JSON 文件代表一张地图。

```json
{
    "name": "Arena Classic",
    "version": 3,
    "ground": {
        "size": 45,
        "texture": "grass",
        "texture_scale": [6, 6]
    },
    "red_base": {
        "position": [0, 0, -17],
        "radius": 4,
        "reload_radius": 4,
        "pillars": [[-1.4, -1.4], [1.4, -1.4], [-1.4, 1.4], [1.4, 1.4]],
        "pillar_height": 5
    },
    "blue_base": {
        "position": [0, 0, 17],
        "radius": 4,
        "reload_radius": 4,
        "pillars": [[-1.4, -1.4], [1.4, -1.4], [-1.4, 1.4], [1.4, 1.4]],
        "pillar_height": 5
    },
    "goals": [
        {"id": 1, "position": [-6, 0, -6]},
        {"id": 2, "position": [6, 0, -6]},
        {"id": 3, "position": [-6, 0, 6]},
        {"id": 4, "position": [6, 0, 6]}
    ],
    "cover": [
        {"position": [-6, 0, 0], "scale": [2, 2.5, 1]},
        {"position": [6, 0, 0], "scale": [2, 2.5, 1]},
        {"position": [0, 0, -6], "scale": [2, 2.5, 1]},
        {"position": [0, 0, 6], "scale": [2, 2.5, 1]}
    ],
    "boundary": {
        "thickness": 1,
        "height": 5
    }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 地图名称（显示用） |
| version | int | 地图版本号 |
| ground.size | int | 地面尺寸（正方形边长） |
| ground.texture | string | 地面纹理名 |
| ground.texture_scale | [int, int] | 纹理重复次数 |
| red_base / blue_base.position | [x, y, z] | 基地位置（也是玩家出生点） |
| red_base / blue_base.radius | float | 基地地面标记半径 |
| red_base / blue_base.reload_radius | float | 基地装填范围半径 |
| red_base / blue_base.pillars | [[dx, dz], ...] | 基地柱子相对位置 |
| red_base / blue_base.pillar_height | float | 柱子高度 |
| goals[].id | int | Goal 编号 |
| goals[].position | [x, y, z] | Goal 位置 |
| cover[].position | [x, y, z] | 掩体位置 |
| cover[].scale | [x, y, z] | 掩体尺寸 |
| boundary.thickness | int | 边界墙厚度 |
| boundary.height | int | 边界墙高度 |

## 技术栈

- **引擎**: [Ursina](https://www.ursinaengine.org/) (Python 3D 游戏引擎，底层 Panda3D)
- **手柄**: Windows XInput API (ctypes 直调)
- **AI 进程**: multiprocessing.shared_memory + ctypes Structures
- **测试**: pytest

## 详细设计

参见 [DESIGN.md](DESIGN.md)。
