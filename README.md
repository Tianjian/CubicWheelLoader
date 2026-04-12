# CubicWheelLoader — TPS 团队竞技对战

基于 Ursina 引擎的第三人称视角团队竞技对战游戏。4 名玩家分为红蓝两队，击杀对手得分，5 分钟比赛结束后总分高的队伍获胜。

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
├── game_settings.json       # 游戏参数配置
│
├── arena/                   # 游戏核心包
│   ├── constants.py         # 枚举、常量、配置（从 JSON 加载）
│   ├── xinput.py            # Windows XInput ctypes 封装
│   ├── input_manager.py     # 输入抽象层（键盘 + 手柄）
│   ├── player.py            # 玩家角色实体
│   ├── weapon.py            # 武器系统
│   ├── bullet.py            # 子弹实体
│   ├── base.py              # 队伍基地
│   ├── game_map.py          # 竞技地图
│   ├── map_loader.py        # 地图 JSON 加载器
│   ├── camera_ctrl.py       # 相机控制器
│   ├── human_ctrl.py        # 人类玩家控制器
│   ├── ai_ctrl.py           # AI 控制器（纯计算，返回决策字典）
│   ├── ai_worker.py         # AI 子进程入口（纯 Python，无 Ursina 依赖）
│   ├── ai_process.py        # AI 进程管理器
│   ├── shared_state.py      # 共享内存 ctypes 结构定义
│   ├── score_system.py      # 计分系统
│   ├── match_timer.py       # 比赛计时器
│   ├── kill_feed.py         # 击杀播报
│   ├── hud.py               # 抬头显示
│   ├── character_select.py  # 角色选择界面
│   └── game_manager.py      # 游戏主控
│
├── maps/                    # 地图数据（JSON）
│   └── arena_classic.json   # 默认地图
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

## 测试

```bash
# 运行全部测试
pytest tests/ -v

# 仅运行纯逻辑测试（无需 Ursina 运行时）
pytest tests/test_xinput.py tests/test_map_loader.py tests/test_input_manager.py tests/test_shared_state.py -v
```

## 配置

### 游戏参数配置（game_settings.json）

项目根目录下的 `game_settings.json` 集中管理所有游戏规则和参数，修改后重启游戏即生效。如果该文件不存在或字段缺失，自动使用内置默认值。

```json
{
    "player": {
        "max_hp": 100,
        "scale": 1,
        "respawn_delay": 3.0,
        "invincible_duration": 2.0
    },
    "weapon": {
        "bullet_damage": 10,
        "bullet_speed": 35,
        "fire_rate": 0.15,
        "muzzle_flash_duration": 0.05
    },
    "bullet": {
        "max_distance": 100,
        "scale": 0.1,
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
        "shoot_interval": 0.2,
        "patrol_arrive_distance": 2,
        "avoid_duration": 1.0,
        "use_subprocess": false,
        "subprocess_timeout": 0.005
    },
    "match": {
        "duration": 300,
        "kill_score": 3,
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
    }
}
```

| 分区 | 关键参数 | 说明 |
|------|----------|------|
| player | max_hp, respawn_delay, invincible_duration | 玩家生命、重生延迟、无敌时长 |
| weapon | bullet_damage, bullet_speed, fire_rate | 子弹伤害、速度、射击间隔 |
| bullet | max_distance, scale, speed_multiplier | 子弹射程、大小、飞行速度倍率 |
| human | move_speed, rotation_speed, input_deadzone | 人类移动/旋转速度、输入死区 |
| ai | detection_range, attack_range, shoot_spread, shoot_interval | AI 检测/攻击距离、射击散布/节流 |
| ai | use_subprocess, subprocess_timeout | AI 子进程开关和超时 |
| match | duration, kill_score, timer_warning_seconds | 比赛时长、击杀得分、计时器闪烁秒数 |
| camera | distance, height, fov_tps, fov_far | 相机距离/高度/FOV |
| gamepad | shoot_threshold | 手柄扳机射击阈值 |
| map | default_name | 默认地图名（对应 maps/ 下的 JSON 文件名） |

### 地图配置（maps/*.json）

地图数据存放在 `maps/` 目录下，每个 JSON 文件代表一张地图。`game_settings.json` 中的 `map.default_name` 指定启动时加载的默认地图。添加新地图只需在 `maps/` 下新建 JSON 文件。

```json
{
    "name": "Arena Classic",
    "version": 1,
    "ground": {
        "size": 64,
        "texture": "grass",
        "texture_scale": [8, 8]
    },
    "red_base": {
        "position": [0, 0, -24],
        "radius": 6,
        "pillars": [[-2, -2], [2, -2], [-2, 2], [2, 2]],
        "pillar_height": 5
    },
    "blue_base": {
        "position": [0, 0, 24],
        "radius": 6,
        "pillars": [[-2, -2], [2, -2], [-2, 2], [2, 2]],
        "pillar_height": 5
    },
    "cover": [
        {"position": [-12, 0, -10], "scale": [2, 2.5, 1]},
        {"position": [12, 0, 10], "scale": [2, 2.5, 1]}
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
| red_base / blue_base.pillars | [[dx, dz], ...] | 基地柱子相对位置 |
| red_base / blue_base.pillar_height | float | 柱子高度 |
| cover[].position | [x, y, z] | 掩体位置 |
| cover[].scale | [x, y, z] | 掩体尺寸 |
| cover[].color | float | 可选，掩体灰度 (0-1)，默认 0.95 |
| boundary.thickness | int | 边界墙厚度 |
| boundary.height | int | 边界墙高度 |

## 技术栈

- **引擎**: [Ursina](https://www.ursinaengine.org/) (Python 3D 游戏引擎，底层 Panda3D)
- **手柄**: Windows XInput API (ctypes 直调)
- **AI 进程**: multiprocessing.shared_memory + ctypes Structures
- **测试**: pytest

## 详细设计

参见 [DESIGN.md](DESIGN.md)。
