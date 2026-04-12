# 声音系统升级设计文档（MP3 音效素材方案）

## 1. 现状分析

### 1.1 当前音效调用点

| # | 位置 | 触发条件 | 当前实现 |
|---|------|----------|----------|
| 1 | `weapon.py:66-75` | 每次射击 | `ursfx([(0,0),(0.05,0.8),(0.1,0.4),(0.15,0.2),(0.2,0)], volume=0.5, wave='noise', pitch=random(-2,-1), speed=1.5)` |
| 2 | `bullet.py:100-108` | 子弹命中任何目标 | `ursfx([(0,0),(0.05,0.5),(0.1,0.2),(0.15,0.1),(0.2,0)], volume=0.3, wave='noise', pitch=random(-8,-6), speed=2.0)` |

仅 2 个音效触发点，缺少：玩家受伤反馈、玩家死亡、击杀播报、比赛开始/结束、倒计时等。

### 1.2 当前 `sound/` 目录

```
sound/
├── countdown.mp3    (35.92 KB)
├── damage.mp3       (45.71 KB)
├── death.mp3        (21.94 KB)
├── hit_goal.mp3     (53.06 KB)
├── hit_player.mp3   (49.8 KB)
├── hit_wall.mp3     (50.61 KB)
├── kill.mp3         (31.84 KB)
├── match_end.mp3    (34.69 KB)
├── match_start.mp3  (83.26 KB)
└── shoot.mp3        (35.92 KB)
```

已有 10 个 MP3 音效素材，命名规范，全部就绪，但代码中仍用 `ursfx` 合成音，未使用这些文件。

### 1.3 方案选择：MP3 音效素材 vs ursfx 合成音

| | `ursfx` 合成音（原方案） | MP3 音效素材（新方案） |
|---|---|---|
| 音质 | 低，3种波形，8-bit 风格 | 高，真实枪声/爆炸/提示音 |
| 调试难度 | 高，需调5点包络+波形+pitch | 低，换文件即可 |
| 音色丰富度 | 极有限，sawtooth 会崩溃 | 无限，任意素材 |
| API 限制 | volume_curve必须5点，wave仅3种 | 几乎无限制 |
| 代码量 | 每个音效需配 envelope+wave+pitch | 只需文件名+音量 |
| 并发管理 | 需手动计数（invoke 延迟恢复） | `auto_destroy=True` 自动销毁 |
| 文件依赖 | 无 | 需要音频文件（每个几十KB） |

**决定：采用 MP3 音效素材方案。** 核心原因：当前声音"烦人"的根本原因是 ursfx 合成音听起来像噪声，换成真实音效素材后辨识度天然高，且代码大幅简化。

### 1.4 Ursina `Audio` API

```python
Audio(sound_file_name, volume=1, pitch=1, balance=0,
      loop=False, loops=1, autoplay=True, auto_destroy=False, group='sfx')
```

| 参数 | 说明 |
|------|------|
| `sound_file_name` | 文件名（不含扩展名），Ursina 自动搜索 `.ogg`/`.wav`/`.mp3` |
| `volume` | 音量 0~1（会被 `Audio.volume_multiplier` 全局缩放） |
| `pitch` | 播放速率（1.0=原速，0.5=半速低音，2.0=倍速高音） |
| `auto_destroy` | `True` = 播完自动销毁 Entity，无需手动清理 |
| `fade()`/`fade_out()` | 内置淡出动画 |

**搜索路径**：Ursina 在 `application.asset_folder` 和 `application.internal_audio_folder` 中递归搜索。需在启动时设置 `application.asset_folder` 指向项目根目录（`main.py` 中已设置）。

### 1.5 问题清单

| # | 问题 | 原因 | 影响 |
|---|------|------|------|
| 1 | **声音嘈杂刺耳** | 3 个 AI × 5 发/秒 = 15 次合成噪声叠加 | 连续嗡嗡声，听觉疲劳 |
| 2 | **音色单一** | 两个音效都是 `wave='noise'` | 无法区分射击和命中事件 |
| 3 | **无距离衰减** | 所有音效 volume 恒定 | 远处 AI 枪声和身边一样响 |
| 4 | **AI 枪声占比过大** | AI 射击频率 0.2s/次 | AI 声音覆盖人类声音 |
| 5 | **缺少关键音效** | 无受伤/死亡/击杀/倒计时/得分等 | 游戏事件缺乏听觉反馈 |
| 6 | **音效参数不可配** | 硬编码在 Python 代码中 | 无法快速调整 |
| 7 | **已有音效未使用** | `sound/` 目录有 mp3 但代码用 ursfx | 资源浪费 |

### 1.6 声音密度估算

```
3 个 AI，每个 AI shoot_interval=0.2s → 每秒 15 次射击
每次射击产生 1 个射击音效 + ~0.5 个命中音效 ≈ 22 个音效调用/秒
无距离衰减、无限流 → 持续噪声层
```

---

## 2. 设计目标

1. **大幅降低噪声密度** — AI 射击音效距离衰减 + 限流
2. **音色区分** — 不同事件使用不同音效文件，一听即知发生了什么
3. **关键事件有声** — 受伤、死亡、击杀、倒计时、比赛开始/结束、得分
4. **距离衰减** — 远处 AI 枪声自然变弱
5. **音效可配置** — 所有音效参数放入 `game_settings.json`
6. **集中管理** — 新增 `SoundManager` 统一管理音效播放

---

## 3. 音效事件与素材清单

### 3.1 所需音效素材

| # | 事件名 | 文件名 | 素材描述 | 时长建议 | 优先级 | 文件状态 |
|---|--------|--------|----------|----------|--------|----------|
| 1 | 射击 | `shoot` | 短促枪声，清脆不拖尾 | 0.2~0.4s | 高 | ✓ 已有 (35.92 KB) |
| 2 | 命中玩家 | `hit_player` | 清脆"叮"声/肉体命中反馈 | 0.1~0.3s | 高 | ✓ 已有 (49.8 KB) |
| 3 | 命中掩体 | `hit_wall` | 低沉"嗒"声/金属弹跳 | 0.1~0.2s | 低 | ✓ 已有 (50.61 KB) |
| 4 | 玩家受伤 | `damage` | 闷响/低沉冲击 | 0.2~0.5s | 高 | ✓ 已有 (45.71 KB) |
| 5 | 玩家死亡 | `death` | 沉重坠落/低频轰鸣 | 0.5~1.0s | 高 | ✓ 已有 (21.94 KB) |
| 6 | 击杀敌人 | `kill` | 清脆上升提示音/硬币声 | 0.2~0.5s | 高 | ✓ 已有 (31.84 KB) |
| 7 | 倒计时 | `countdown` | 短促节拍/电子"嘀"声 | 0.1~0.3s | 中 | ✓ 已有 (35.92 KB) |
| 8 | 比赛开始 | `match_start` | 上升音/号角/GO提示 | 0.5~1.0s | 中 | ✓ 已有 (83.26 KB) |
| 9 | 比赛结束 | `match_end` | 下降音/结束号角 | 0.5~1.5s | 中 | ✓ 已有 (34.69 KB) |
| 10 | 得分/达阵 | `hit_goal` | 得分提示/目标达成 | 0.2~0.5s | 中 | ✓ 已有 (53.06 KB) |

**共需 10 种音效素材，全部已就绪。**

### 3.2 素材规格要求

- **格式**：MP3（兼容 .ogg/.wav，Ursina 均支持）
- **采样率**：44100 Hz
- **声道**：单声道（节省内存，游戏音效无需立体声）
- **时长**：尽量短（见上表），避免拖尾叠加
- **音量**：素材本身音量归一化（避免某个文件特别响/特别轻）
- **文件大小**：每个 20~100 KB

### 3.3 素材现状

`sound/` 目录已包含 10 个命名规范的 MP3 文件，全部就绪。

| 文件 | 事件 | 状态 |
|------|------|------|
| `shoot.mp3` | 射击 | ✓ 已有 |
| `hit_player.mp3` | 命中玩家 | ✓ 已有 |
| `hit_wall.mp3` | 命中掩体 | ✓ 已有 |
| `damage.mp3` | 受伤 | ✓ 已有 |
| `death.mp3` | 死亡 | ✓ 已有 |
| `kill.mp3` | 击杀提示 | ✓ 已有 |
| `countdown.mp3` | 倒计时 | ✓ 已有 |
| `match_start.mp3` | 比赛开始 | ✓ 已有 |
| `match_end.mp3` | 比赛结束 | ✓ 已有 |
| `hit_goal.mp3` | 得分/达阵 | ✓ 已有 |

### 3.4 目标 `sound/` 目录结构

```
sound/
├── shoot.mp3           # 射击（已有 ✓）
├── hit_player.mp3      # 命中玩家（已有 ✓）
├── hit_wall.mp3        # 命中掩体（已有 ✓）
├── damage.mp3          # 受伤（已有 ✓）
├── death.mp3           # 死亡（已有 ✓）
├── kill.mp3            # 击杀提示（已有 ✓）
├── countdown.mp3       # 倒计时（已有 ✓）
├── match_start.mp3     # 比赛开始（已有 ✓）
├── match_end.mp3       # 比赛结束（已有 ✓）
└── hit_goal.mp3        # 得分/达阵（已有 ✓）
```

> 文件名需与 `game_settings.json` 中的 `file` 字段匹配。Ursina `Audio` 按文件名（不含扩展名）搜索。

### 3.5 AI 射击音效按距离分 3 档

| 距离 | 行为 | 音量比例 |
|------|------|----------|
| < 15 单位 | 正常播放 | 100% |
| 15-40 单位 | 线性衰减 | 30% → 0% |
| > 40 单位 | 不播放 | 0% |

### 3.6 最大同时音效数

- 同时活跃的 Audio 不超过 **6 个**
- 优先级：人类射击 > 受伤/死亡 > 击杀 > AI 射击 > 命中掩体

---

## 4. 技术方案

### 4.1 新增 `arena/sound_manager.py`

```python
import time
import random
from arena.constants import Config


class SoundManager:
    """集中音效管理器 — MP3音效、距离衰减、限流、优先级"""

    def __init__(self):
        self.active_sounds = 0
        self.max_concurrent = Config.SOUND_MAX_CONCURRENT
        self._last_ai_shoot_time = {}  # player_id -> timestamp

    def play_shoot(self, shooter_pos=None, listener_pos=None,
                   is_ai=False, player_id=None):
        """播放射击音效（带距离衰减 + AI 限流）"""
        # AI 限流
        if is_ai:
            now = time.time()
            last = self._last_ai_shoot_time.get(player_id, 0)
            if now - last < Config.SOUND_AI_THROTTLE:
                return
            self._last_ai_shoot_time[player_id] = now

        # 距离衰减（仅 AI）
        volume_scale = 1.0
        if is_ai and shooter_pos and listener_pos:
            volume_scale = self._distance_volume(
                shooter_pos, listener_pos,
                Config.SOUND_SHOOT_FULL_DIST,
                Config.SOUND_SHOOT_MUTE_DIST
            )
            if volume_scale <= 0:
                return

        cfg = Config.SOUND_SHOOT
        pitch = random.uniform(cfg['pitch_range'][0], cfg['pitch_range'][1])
        self._play(cfg, volume_scale, pitch)

    def play_hit_player(self):
        """播放命中玩家音效"""
        cfg = Config.SOUND_HIT_PLAYER
        pitch = random.uniform(cfg['pitch_range'][0], cfg['pitch_range'][1])
        self._play(cfg, 1.0, pitch)

    def play_hit_wall(self):
        """播放命中掩体音效"""
        cfg = Config.SOUND_HIT_WALL
        pitch = random.uniform(cfg['pitch_range'][0], cfg['pitch_range'][1])
        self._play(cfg, 1.0, pitch)

    def play_hit_goal(self):
        """播放得分/达阵音效"""
        cfg = Config.SOUND_HIT_GOAL
        pitch = random.uniform(cfg['pitch_range'][0], cfg['pitch_range'][1])
        self._play(cfg, 1.0, pitch)

    def play_damage(self):
        """播放受伤音效"""
        cfg = Config.SOUND_DAMAGE
        pitch = random.uniform(cfg['pitch_range'][0], cfg['pitch_range'][1])
        self._play(cfg, 1.0, pitch)

    def play_death(self):
        """播放死亡音效"""
        cfg = Config.SOUND_DEATH
        pitch = random.uniform(cfg['pitch_range'][0], cfg['pitch_range'][1])
        self._play(cfg, 1.0, pitch)

    def play_kill(self):
        """播放击杀提示音"""
        cfg = Config.SOUND_KILL
        pitch = random.uniform(cfg['pitch_range'][0], cfg['pitch_range'][1])
        self._play(cfg, 1.0, pitch)

    def play_countdown(self):
        """播放倒计时音效"""
        cfg = Config.SOUND_COUNTDOWN
        self._play(cfg, 1.0, cfg['pitch_range'][0])

    def play_match_start(self):
        """播放比赛开始音效"""
        cfg = Config.SOUND_MATCH_START
        self._play(cfg, 1.0, cfg['pitch_range'][0])

    def play_match_end(self):
        """播放比赛结束音效"""
        cfg = Config.SOUND_MATCH_END
        self._play(cfg, 1.0, cfg['pitch_range'][0])

    def _play(self, cfg, volume_scale=1.0, pitch=1.0):
        """底层播放：并发限制 + 主音量缩放"""
        if self.active_sounds >= self.max_concurrent:
            return
        vol = cfg['volume'] * volume_scale * Config.SOUND_MASTER_VOLUME
        if vol <= 0.01:
            return
        from ursina import Audio
        Audio(
            sound_file_name=cfg['file'],
            volume=vol,
            pitch=pitch,
            auto_destroy=True,
        )
        self.active_sounds += 1
        # 利用 invoke 延迟恢复计数（估算音效时长）
        duration = cfg.get('duration', 0.3)
        invoke(self._on_sound_end, delay=duration)

    def _on_sound_end(self):
        self.active_sounds = max(0, self.active_sounds - 1)

    @staticmethod
    def _distance_volume(shooter_pos, listener_pos,
                         full_dist, mute_dist):
        """计算距离衰减音量（0.0~1.0）"""
        d = (shooter_pos - listener_pos).length()
        if d > mute_dist:
            return 0.0
        if d < full_dist:
            return 1.0
        return 1.0 - (d - full_dist) / (mute_dist - full_dist)


# 全局实例
sound_manager = SoundManager()
```

### 4.2 音效参数结构

每个音效由以下字段定义（全部可配置）：

```python
# 每个音效配置格式
{
    'file': 'shoot',         # 音效文件名（不含扩展名，Ursina 自动搜索 .mp3/.ogg/.wav）
    'volume': 0.35,          # 基础音量（会被 master_volume * distance_scale 缩放）
    'pitch_range': [0.9, 1.1],  # [min, max] 播放速率范围，调用前 random.uniform
    'duration': 0.3,         # 音效估算时长（秒），用于并发计数恢复
}
```

**与 ursfx 方案的关键差异：**
- 无 `envelope`（包络由音效文件本身定义）
- 无 `wave`（波形由音效文件本身定义）
- `pitch_range` 含义变化：ursfx 是半音偏移，Audio 是播放速率倍数
- 新增 `duration`：因 `auto_destroy` 无法回调，需手动估算时长来恢复并发计数
- 新增 `file`：音效文件名

**各音效参数设计：**

#### 射击 (`shoot`)
- 文件：`shoot.mp3`（已有 ✓）
- 音量 0.35（原 ursfx 0.5 降低 30%）
- pitch [0.9, 1.1]：微小随机变化，避免连续射击听起来完全一样
- duration 0.3s

#### 命中玩家 (`hit_player`)
- 文件：`hit_player.mp3`（已有 ✓）
- 音量 0.25
- pitch [1.0, 1.2]：略高，清脆反馈
- duration 0.2s

#### 命中掩体 (`hit_wall`)
- 文件：`hit_wall.mp3`（已有 ✓）
- 音量 0.15：次要事件，低音量
- pitch [0.8, 1.0]：略低沉
- duration 0.15s

#### 得分/达阵 (`hit_goal`)
- 文件：`hit_goal.mp3`（已有 ✓）
- 音量 0.25：正面反馈事件
- pitch [1.0, 1.1]：略高，愉悦感
- duration 0.4s

#### 受伤 (`damage`)
- 文件：`damage.mp3`（已有 ✓）
- 音量 0.3
- pitch [0.9, 1.0]：接近原速
- duration 0.4s

#### 死亡 (`death`)
- 文件：`death.mp3`（已有 ✓）
- 音量 0.3
- pitch [0.8, 0.9]：略慢，沉重感
- duration 0.8s

#### 击杀提示 (`kill`)
- 文件：`kill.mp3`（已有 ✓）
- 音量 0.2
- pitch [1.0, 1.0]：固定音高
- duration 0.4s

#### 倒计时 (`countdown`)
- 文件：`countdown.mp3`（已有 ✓）
- 音量 0.3
- pitch [1.0, 1.0]：固定音高
- duration 0.2s

#### 比赛开始 (`match_start`)
- 文件：`match_start.mp3`（已有 ✓）
- 音量 0.35
- pitch [1.0, 1.0]：固定
- duration 0.6s

#### 比赛结束 (`match_end`)
- 文件：`match_end.mp3`（已有 ✓）
- 音量 0.35
- pitch [1.0, 1.0]：固定
- duration 0.8s

### 4.3 距离衰减参数

```python
'shoot_full_distance': 15,   # 此距离内满音量
'shoot_mute_distance': 40,   # 此距离外静音
```

线性插值：`volume_scale = 1 - (d - full) / (mute - full)`

仅对 AI 射击音效应用衰减。人类玩家射击始终满音量。

### 4.4 AI 射击音效限流

```python
'ai_sound_throttle': 0.3  # AI 射击音效最小间隔（秒）
```

AI 的 `shoot_interval` 是 0.2s，音效播放间隔限制为 0.3s，每个 AI 每秒最多 3.3 次枪声。

### 4.5 `application.asset_folder` 配置

Ursina `Audio` 搜索音效文件的路径由 `application.asset_folder` 决定。需确认 `main.py` 中已正确设置，使 `sound/` 目录在搜索路径内：

```python
# main.py 中（已有或需添加）
application.asset_folder = Path(__file__).parent
```

Ursina 会在 `application.asset_folder` 下递归搜索 `**/{filename}.mp3`，因此 `sound/shoot.mp3` 可直接用 `Audio('shoot')` 播放。

---

## 5. `game_settings.json` 新增配置

```json
{
    "sound": {
        "master_volume": 0.8,
        "max_concurrent": 6,
        "ai_sound_throttle": 0.3,
        "shoot_full_distance": 15,
        "shoot_mute_distance": 40,
        "shoot": {
            "file": "shoot",
            "volume": 0.35,
            "pitch_range": [0.9, 1.1],
            "duration": 0.3
        },
        "hit_player": {
            "file": "hit_player",
            "volume": 0.25,
            "pitch_range": [1.0, 1.2],
            "duration": 0.2
        },
        "hit_wall": {
            "file": "hit_wall",
            "volume": 0.15,
            "pitch_range": [0.8, 1.0],
            "duration": 0.15
        },
        "hit_goal": {
            "file": "hit_goal",
            "volume": 0.25,
            "pitch_range": [1.0, 1.1],
            "duration": 0.4
        },
        "damage": {
            "file": "damage",
            "volume": 0.3,
            "pitch_range": [0.9, 1.0],
            "duration": 0.4
        },
        "death": {
            "file": "death",
            "volume": 0.3,
            "pitch_range": [0.8, 0.9],
            "duration": 0.8
        },
        "kill": {
            "file": "kill",
            "volume": 0.2,
            "pitch_range": [1.0, 1.0],
            "duration": 0.4
        },
        "countdown": {
            "file": "countdown",
            "volume": 0.3,
            "pitch_range": [1.0, 1.0],
            "duration": 0.2
        },
        "match_start": {
            "file": "match_start",
            "volume": 0.35,
            "pitch_range": [1.0, 1.0],
            "duration": 0.6
        },
        "match_end": {
            "file": "match_end",
            "volume": 0.35,
            "pitch_range": [1.0, 1.0],
            "duration": 0.8
        }
    }
}
```

**与 ursfx 方案的配置差异：**
- 删除了 `envelope`（5点包络）和 `wave`（波形）字段
- `pitch_range` 从半音偏移改为播放速率倍数
- 新增 `file`（音效文件名）和 `duration`（时长估算）字段
- 配置大幅简化，每个音效仅 4 个字段

---

## 6. 文件改动清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `arena/sound_manager.py` | **新增** | 集中音效管理器（MP3播放、距离衰减、限流、并发限制） |
| `game_settings.json` | 修改 | 新增 `sound` 配置段 |
| `arena/constants.py` | 修改 | Config 类新增 sound 相关属性 |
| `arena/weapon.py` | 修改 | 删除 `play_shoot_sound()`，改为调用 `sound_manager.play_shoot()` |
| `arena/bullet.py` | 修改 | 删除 `play_impact_sound()`，`on_hit` 区分命中玩家/掩体，调用 sound_manager |
| `arena/player.py` | 修改 | `take_damage()` 新增受伤音效，`die()` 新增死亡音效 |
| `arena/game_manager.py` | 修改 | 击杀音效、倒计时音效、比赛开始/结束音效、得分音效 |
| `sound/` 目录 | ✓ 已就绪 | 10 个 MP3 文件，无需新增 |

---

## 7. 实施步骤

### Phase 1：音效素材准备

1. ~~重命名已有素材~~ — 已完成（`sound/` 目录已整理为规范命名）
2. ~~确认已有素材音质~~ — 已有 10 个 MP3 文件，命名规范
3. ~~新增缺失素材~~ — 已完成（`damage.mp3` 已补齐）
4. 确认 `main.py` 中 `application.asset_folder` 已设置

**Phase 1 验证点**：`sound/` 目录包含 10 个命名规范的 mp3 文件，`Audio('shoot')` 可正常播放。

### Phase 2：音效管理器 + 基础改造

5. 新增 `arena/sound_manager.py`
6. `game_settings.json` 新增 `sound` 配置段
7. `constants.py` Config 加载 sound 配置
8. 改造 `weapon.py` — 射击音效走 `sound_manager.play_shoot()`
9. 改造 `bullet.py` — 命中音效走 `sound_manager.play_hit_player/wall()`，需在 `on_hit` 中区分目标类型

**Phase 2 验证点**：游戏中使用真实枪声音效，命中玩家/掩体音效不同，整体噪声明显降低。

### Phase 3：距离衰减 + AI 限流

10. `weapon.shoot()` 传入 shooter 位置和人类玩家位置
11. AI 射击音效限流（throttle）
12. 最大并发音效数限制

**Phase 3 验证点**：远处 AI 几乎听不到，每秒枪声从 15 次降至 ~5 次。

### Phase 4：新增事件音效

13. 受伤音效 — `player.take_damage()` 中调用 `sound_manager.play_damage()`
14. 死亡音效 — `player.die()` 中调用 `sound_manager.play_death()`
15. 击杀提示 — `game_manager.on_player_killed()` 中调用 `sound_manager.play_kill()`
16. 得分音效 — `game_manager.on_player_killed()` 中 `add_score()` 后调用 `sound_manager.play_hit_goal()`
17. 倒计时 — `game_manager._countdown()` 中调用 `sound_manager.play_countdown()`
18. 比赛开始 — `_countdown(0)` GO! 时调用 `sound_manager.play_match_start()`
19. 比赛结束 — `game_manager.end_match()` 中调用 `sound_manager.play_match_end()`

### Phase 5：测试调优

19. 纯键盘测试 — 所有音效是否正常触发
20. AI 密集战斗 — 是否仍然嘈杂
21. 距离衰减测试 — 远处 AI 是否安静
22. 参数调优 — 微调音量/pitch 直到舒适
23. 清理 `sound/` 目录中未使用的原始文件

---

## 8. bullet.py 命中区分改造详情

当前 `bullet.py:on_hit()` 不区分命中目标类型，需要修改：

```python
# 改造前
def on_hit(self, hit_info):
    self.create_impact_effect(hit_info.world_point, hit_info.world_normal)
    self.play_impact_sound()

# 改造后
def on_hit(self, hit_info, hit_player=False):
    self.create_impact_effect(hit_info.world_point, hit_info.world_normal)
    from arena.sound_manager import sound_manager
    if hit_player:
        sound_manager.play_hit_player()
    else:
        sound_manager.play_hit_wall()
```

调用处（`bullet.py:update()` 内）改为：

```python
if hasattr(target, 'team'):
    if target == self.owner:
        self.on_hit(hit_info)                    # 自身子弹命中掩体
    elif target.team == self.owner.team:
        self.on_hit(hit_info)                    # 友军子弹命中掩体
    elif hasattr(target, 'invincible') and target.invincible:
        self.on_hit(hit_info)                    # 无敌命中掩体
    else:
        target.take_damage(self.damage, self.owner)
        self.on_hit(hit_info, hit_player=True)   # 命中敌方玩家
else:
    self.on_hit(hit_info)                        # 命中非玩家实体
```

---

## 9. 效果对比

### 改造前

```
3 AI 每秒 15 次合成噪声射击声 + 7.5 次合成噪声命中声 = 22 个 ursfx/秒
全部满音量，无衰减，全部 wave='noise'
→ 持续白噪声嗡嗡声，无法区分事件
```

### 改造后

```
3 AI 音效 throttle 0.3s → 每个 AI 每秒最多 3.3 次枪声
其中 ~50% 因距离远被衰减/静音
剩余 ~5 次射击声，volume 0.35 × master 0.8 × 平均衰减 0.3 ≈ 0.08
1 次人类射击，volume 0.35 × 0.8 = 0.28（真实枪声，清脆）
命中玩家：sine 风格真实音效，volume 0.25 × 0.8 = 0.20
命中掩体：低沉音效，volume 0.15 × 0.8 = 0.12
受伤/死亡/击杀/得分/倒计时：各自独立音效，一听即知
最大并发 6 个，超出直接跳过
→ 听感：真实枪声 + 偶尔命中提示 + 关键事件反馈
```

预计噪声密度降低 **70-80%**，音色辨识度从"全是噪声"提升为"每种事件清晰可辨"。

---

## 10. 素材获取指南

| 素材 | 推荐搜索关键词 | 推荐站点 | 状态 |
|------|---------------|----------|------|
| 枪声 | "pistol shot short", "gunshot clean" | freesound.org, opengameart.org | ✓ 已有 |
| 命中玩家 | "hit marker", "body impact" | freesound.org | ✓ 已有 |
| 命中掩体 | "bullet concrete", "ricochet short" | freesound.org | ✓ 已有 |
| 受伤 | "pain grunt short", "impact low" | freesound.org | ✓ 已有 |
| 死亡 | "low boom", "game over boom" | freesound.org, opengameart.org | ✓ 已有 |
| 倒计时 | "beep short", "electronic beep" | freesound.org | ✓ 已有 |
| 比赛结束 | "game over descending", "horn end" | freesound.org, opengameart.org | ✓ 已有 |
| 得分 | "coin", "score chime", "achievement" | freesound.org | ✓ 已有 |

**推荐站点：**
- **freesound.org** — 最大免费音效库，CC0 许可素材丰富，需注册
- **opengameart.org** — 游戏专用素材，CC0/CC-BY 许可
- **mixkit.co** — 免费音效，无需注册

**素材处理建议：**
- 下载后用 Audacity 裁剪到推荐时长，去除静音头尾
- 归一化音量（Audacity: 效果 → 音量归一化）
- 导出为 MP3 44100Hz 单声道
