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


def _load_settings():
    """从 game_settings.json 加载配置"""
    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'game_settings.json')
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError) as e:
        raise RuntimeError(f'[Config] Failed to load game_settings.json: {e}') from e


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
    WEAPON_MAX_AMMO = _settings['weapon']['max_ammo']

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
    AI_LOW_AMMO_THRESHOLD = _settings['ai']['low_ammo_threshold']
    AI_STRAFE_ENABLED = _settings['ai']['strafe_enabled']
    AI_LOS_CHECK_ENABLED = _settings['ai']['los_check_enabled']
    AI_GOAL_SHOOT_SPREAD_MULT = _settings['ai']['goal_shoot_spread_multiplier']
    AI_AVOID_NAVIGATE_TIMEOUT = _settings['ai']['avoid_navigate_timeout']

    # AI 策略评分
    AI_PROXIMITY_BOOST_K = _settings['ai']['proximity_boost_k']
    AI_GOAL_PRIORITY_WEIGHT = _settings['ai']['goal_priority_weight']
    AI_HIGH_AMMO_THRESHOLD = _settings['ai']['high_ammo_threshold']
    AI_DEFENDER_URGENCY_MULT = _settings['ai']['defender_urgency_multiplier']
    AI_SHOOTABLE_GOAL_MULT = _settings['ai']['shootable_goal_multiplier']
    AI_TEAMMATE_TARGET_PENALTY = _settings['ai']['teammate_target_penalty']

    # 比赛规则
    MATCH_DURATION = _settings['match']['duration']
    KILL_SCORE = _settings['match']['kill_score']
    GOAL_SCORE = _settings['match']['goal_score']
    GOAL_HIT_WINDOW = _settings['match']['goal_hit_window']
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
