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
        from ursina import Audio, invoke
        Audio(
            sound_file_name=cfg['file'],
            volume=vol,
            pitch=pitch,
            auto_destroy=True,
        )
        self.active_sounds += 1
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
