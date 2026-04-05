# CubicWheelLoader - Team Arena

基于 Ursina 引擎的 TPS 团队竞技对战游戏。

## 项目结构

```
CubicWheelLoader/
├── main.py                  # 游戏入口
├── fps_demo_v4.py           # 原始基线代码（参考）
├── team_arena_design.md     # 游戏设计文档
│
├── arena/                   # 游戏核心包
│   ├── __init__.py
│   ├── constants.py         # 枚举、常量、配置
│   ├── bullet.py            # 子弹实体
│   ├── weapon.py            # 武器系统
│   ├── player.py            # 玩家角色实体
│   ├── base.py              # 队伍基地
│   ├── game_map.py          # 对称竞技地图
│   ├── camera_ctrl.py       # 相机控制器
│   ├── human_ctrl.py        # 人类玩家控制器
│   ├── ai_ctrl.py           # AI 玩家控制器
│   ├── score_system.py      # 计分系统
│   ├── match_timer.py       # 比赛计时器
│   ├── kill_feed.py         # 击杀播报
│   ├── hud.py               # 抬头显示
│   ├── character_select.py  # 角色选择界面
│   └── game_manager.py      # 游戏主控
│
└── docs/                    # 历史设计文档
    ├── fps_demo_upgrade_design.md
    ├── third_person_mode_design.md
    └── tps_shoot_design_body_facing.md
```

## 运行

```bash
pip install ursina
python main.py
```

## 操作

| 按键 | 功能 |
|------|------|
| W/S | 前进/后退 |
| A/D | 左转/右转 |
| 鼠标左键 | 射击 |
| V | 切换视角距离 |
| Tab | 编辑器模式 |
