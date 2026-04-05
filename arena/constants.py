from enum import Enum

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

# ==================== 游戏配置 ====================
class Config:
    # 玩家
    PLAYER_MAX_HP = 100
    PLAYER_SCALE = 1
    BULLET_DAMAGE = 10
    BULLET_SPEED = 35
    FIRE_RATE = 0.15

    # 重生
    RESPAWN_DELAY = 3.0
    INVINCIBLE_DURATION = 2.0

    # 计分
    KILL_SCORE = 3

    # 比赛时间（秒）
    MATCH_DURATION = 300  # 5 分钟

    # 地图
    MAP_SIZE = 64
    RED_BASE_POS = (0, 0, -28)
    BLUE_BASE_POS = (0, 0, 28)

    # 人类玩家
    HUMAN_MOVE_SPEED = 8
    HUMAN_ROTATION_SPEED = 120

    # AI 玩家
    AI_MOVE_SPEED = 6
    AI_ROTATION_SPEED = 90
    AI_DETECTION_RANGE = 40
    AI_ATTACK_RANGE = 25
    AI_SHOOT_SPREAD = 0.05

    # 相机（TPS）
    CAMERA_DISTANCE = 15
    CAMERA_HEIGHT = 8
    CAMERA_FOV_TPS = 55
    CAMERA_FOV_FAR = 30
    CAMERA_TRANSITION_SPEED = 15

    TEAM_COLORS = None  # 延迟初始化（需要 ursina.color）
