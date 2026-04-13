from enum import Enum
import json
import os


class Team(Enum):
    RED = "red"
    BLUE = "blue"

class PlayerState(Enum):
    ALIVE = "alive"
    DEAD = "dead"
    RESPawning = "respawning"

class GameState(Enum):
    MENU = "menu"
    CHARACTER_SELECT = "character_select"
    COUNTDOWN = "countdown"
    PLAYING = "playing"
    MATCH_END = "match_end"

class CameraMode(Enum):
    FIRST_PERSON = "first_person"
    THIRD_PERSON = "third_person"


# ==================== 默认配置（JSON 文件不存在时使用） ====================
_DEFAULTS = {
    'player': {'max_hp': 100, 'scale': 1, 'respawn_delay': 3.0, 'invincible_duration': 2.0},
    'weapon': {'bullet_damage': 30, 'bullet_speed': 35, 'fire_rate': 0.15, 'muzzle_flash_duration': 0.05, 'max_ammo': 10},
    'bullet': {'max_distance': 5, 'scale': 0.3, 'speed_multiplier': 1.5},
    'human': {'move_speed': 8, 'rotation_speed': 120, 'input_deadzone': 0.05},
    'ai': {'move_speed': 6, 'rotation_speed': 90, 'detection_range': 40, 'attack_range': 25,
           'shoot_spread': 0.05, 'shoot_interval': 0.4, 'patrol_arrive_distance': 2,
           'avoid_duration': 1.0, 'use_subprocess': False, 'subprocess_timeout': 0.005,
           'low_ammo_threshold': 3, 'strafe_enabled': True, 'los_check_enabled': True,
           'goal_shoot_spread_multiplier': 0.5, 'avoid_navigate_timeout': 3.0},
    'match': {'duration': 300, 'kill_score': 0, 'goal_score': 10, 'goal_hit_window': 7, 'timer_warning_seconds': 30},
    'camera': {'distance': 40, 'height': 15, 'fov_tps': 60, 'fov_far': 45,
               'transition_speed': 10, 'fov_spectator': 45, 'follow_enable_delay': 0.3},
    'gamepad': {'shoot_threshold': 0.3},
    'map': {'default_name': 'arena_classic'},
    'sound': {
        'master_volume': 0.8, 'max_concurrent': 6, 'ai_sound_throttle': 0.3,
        'shoot_full_distance': 15, 'shoot_mute_distance': 40,
        'shoot': {'file': 'shoot', 'volume': 0.35, 'pitch_range': [0.9, 1.1], 'duration': 0.3},
        'hit_player': {'file': 'hit_player', 'volume': 0.25, 'pitch_range': [1.0, 1.2], 'duration': 0.2},
        'hit_wall': {'file': 'hit_wall', 'volume': 0.15, 'pitch_range': [0.8, 1.0], 'duration': 0.15},
        'hit_goal': {'file': 'hit_goal', 'volume': 0.25, 'pitch_range': [1.0, 1.1], 'duration': 0.4},
        'damage': {'file': 'damage', 'volume': 0.3, 'pitch_range': [0.9, 1.0], 'duration': 0.4},
        'death': {'file': 'death', 'volume': 0.3, 'pitch_range': [0.8, 0.9], 'duration': 0.8},
        'kill': {'file': 'kill', 'volume': 0.2, 'pitch_range': [1.0, 1.0], 'duration': 0.4},
        'countdown': {'file': 'countdown', 'volume': 0.3, 'pitch_range': [1.0, 1.0], 'duration': 0.2},
        'match_start': {'file': 'match_start', 'volume': 0.35, 'pitch_range': [1.0, 1.0], 'duration': 0.6},
        'match_end': {'file': 'match_end', 'volume': 0.35, 'pitch_range': [1.0, 1.0], 'duration': 0.8},
    },
}


def _deep_merge(base, override):
    """深层合并字典：override 中的值覆盖 base，dict 类型递归合并"""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_settings():
    """从 game_settings.json 加载配置，缺失字段用默认值（支持嵌套 dict 深层合并）"""
    settings = {}
    for section, defaults in _DEFAULTS.items():
        settings[section] = dict(defaults)

    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'game_settings.json')
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                user_settings = json.load(f)
            for section, values in user_settings.items():
                if section in settings and isinstance(values, dict):
                    settings[section] = _deep_merge(settings[section], values)
                else:
                    settings[section] = values
        except (json.JSONDecodeError, IOError) as e:
            print(f'[Config] Warning: Failed to load game_settings.json: {e}, using defaults')

    return settings


_settings = _load_settings()


class Config:
    """游戏配置 — 从 game_settings.json 加载，缺失值用默认值"""

    # 玩家
    PLAYER_MAX_HP = _settings['player']['max_hp']
    PLAYER_SCALE = _settings['player']['scale']
    RESPAWN_DELAY = _settings['player']['respawn_delay']
    INVINCIBLE_DURATION = _settings['player']['invincible_duration']

    # 武器
    BULLET_DAMAGE = _settings['weapon']['bullet_damage']
    BULLET_SPEED = _settings['weapon']['bullet_speed']
    FIRE_RATE = _settings['weapon']['fire_rate']
    MUZZLE_FLASH_DURATION = _settings['weapon']['muzzle_flash_duration']
    WEAPON_MAX_AMMO = _settings['weapon'].get('max_ammo', 10)

    # 子弹
    BULLET_MAX_DISTANCE = _settings['bullet']['max_distance']
    BULLET_SCALE = _settings['bullet']['scale']
    BULLET_SPEED_MULTIPLIER = _settings['bullet']['speed_multiplier']

    # 人类玩家
    HUMAN_MOVE_SPEED = _settings['human']['move_speed']
    HUMAN_ROTATION_SPEED = _settings['human']['rotation_speed']
    INPUT_DEADZONE = _settings['human']['input_deadzone']

    # AI 玩家
    AI_MOVE_SPEED = _settings['ai']['move_speed']
    AI_ROTATION_SPEED = _settings['ai']['rotation_speed']
    AI_DETECTION_RANGE = _settings['ai']['detection_range']
    AI_ATTACK_RANGE = _settings['ai']['attack_range']
    AI_SHOOT_SPREAD = _settings['ai']['shoot_spread']
    AI_SHOOT_INTERVAL = _settings['ai']['shoot_interval']
    AI_PATROL_ARRIVE_DISTANCE = _settings['ai']['patrol_arrive_distance']
    AI_AVOID_DURATION = _settings['ai']['avoid_duration']
    AI_LOW_AMMO_THRESHOLD = _settings['ai'].get('low_ammo_threshold', 3)
    AI_STRAFE_ENABLED = _settings['ai'].get('strafe_enabled', True)
    AI_LOS_CHECK_ENABLED = _settings['ai'].get('los_check_enabled', True)
    AI_GOAL_SHOOT_SPREAD_MULT = _settings['ai'].get('goal_shoot_spread_multiplier', 0.5)
    AI_AVOID_NAVIGATE_TIMEOUT = _settings['ai'].get('avoid_navigate_timeout', 3.0)

    # AI 子进程
    AI_USE_SUBPROCESS = _settings['ai']['use_subprocess']
    AI_SUBPROCESS_TIMEOUT = _settings['ai']['subprocess_timeout']

    # 比赛规则
    MATCH_DURATION = _settings['match']['duration']
    KILL_SCORE = _settings['match']['kill_score']
    GOAL_SCORE = _settings['match'].get('goal_score', 10)
    GOAL_HIT_WINDOW = _settings['match'].get('goal_hit_window', 7)
    TIMER_WARNING_SECONDS = _settings['match']['timer_warning_seconds']

    # 相机
    CAMERA_DISTANCE = _settings['camera']['distance']
    CAMERA_HEIGHT = _settings['camera']['height']
    CAMERA_FOV_TPS = _settings['camera']['fov_tps']
    CAMERA_FOV_FAR = _settings['camera']['fov_far']
    CAMERA_TRANSITION_SPEED = _settings['camera']['transition_speed']
    CAMERA_FOV_SPECTATOR = _settings['camera']['fov_spectator']
    CAMERA_FOLLOW_ENABLE_DELAY = _settings['camera']['follow_enable_delay']

    # 手柄
    GAMEPAD_SHOOT_THRESHOLD = _settings['gamepad']['shoot_threshold']

    # 地图
    DEFAULT_MAP_NAME = _settings['map']['default_name']

    # 音效
    SOUND_MASTER_VOLUME = _settings['sound']['master_volume']
    SOUND_MAX_CONCURRENT = _settings['sound']['max_concurrent']
    SOUND_AI_THROTTLE = _settings['sound']['ai_sound_throttle']
    SOUND_SHOOT_FULL_DIST = _settings['sound']['shoot_full_distance']
    SOUND_SHOOT_MUTE_DIST = _settings['sound']['shoot_mute_distance']
    SOUND_SHOOT = _settings['sound']['shoot']
    SOUND_HIT_PLAYER = _settings['sound']['hit_player']
    SOUND_HIT_WALL = _settings['sound']['hit_wall']
    SOUND_HIT_GOAL = _settings['sound']['hit_goal']
    SOUND_DAMAGE = _settings['sound']['damage']
    SOUND_DEATH = _settings['sound']['death']
    SOUND_KILL = _settings['sound']['kill']
    SOUND_COUNTDOWN = _settings['sound']['countdown']
    SOUND_MATCH_START = _settings['sound']['match_start']
    SOUND_MATCH_END = _settings['sound']['match_end']

    TEAM_COLORS = None  # 延迟初始化（需要 ursina.color）
