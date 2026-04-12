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
├── fps_demo_v4.py           # 原始基线代码（参考）
├── test_gamepad.py          # 手柄测试脚本
│
├── arena/                   # 游戏核心包
│   ├── constants.py         # 枚举、常量、配置
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
├── maps/                    # 地图数据
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

## 技术栈

- **引擎**: [Ursina](https://www.ursinaengine.org/) (Python 3D 游戏引擎，底层 Panda3D)
- **手柄**: Windows XInput API (ctypes 直调)
- **AI 进程**: multiprocessing.shared_memory + ctypes Structures
- **测试**: pytest

## 详细设计

参见 [DESIGN.md](DESIGN.md)。
