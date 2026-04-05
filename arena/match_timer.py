from ursina import *
from arena.constants import Config


class MatchTimer(Entity):
    """比赛计时器"""

    def __init__(self):
        super().__init__()
        self.duration = Config.MATCH_DURATION
        self.remaining = Config.MATCH_DURATION
        self.is_running = False

    def start(self):
        self.is_running = True

    def stop(self):
        self.is_running = False

    def reset(self):
        self.remaining = self.duration
        self.is_running = False

    def update(self):
        if not self.is_running or self.remaining <= 0:
            return

        self.remaining -= time.dt
        self._update_display()

        if self.remaining <= 0:
            self.remaining = 0
            self._update_display()
            self.is_running = False
            from arena.game_manager import game_manager
            game_manager.end_match()

    def _update_display(self):
        from arena.hud import hud
        minutes = int(self.remaining) // 60
        seconds = int(self.remaining) % 60

        if hud.timer_text:
            hud.timer_text.text = f'{minutes:02d}:{seconds:02d}'

        # 最后 30 秒闪烁
        if self.remaining <= 30 and hud.timer_text:
            if int(self.remaining * 2) % 2 == 0:
                hud.timer_text.color = color.red
            else:
                hud.timer_text.color = color.yellow
