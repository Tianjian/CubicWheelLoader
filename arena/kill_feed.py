from ursina import *


class KillFeed:
    """击杀播报（右上角滚动消息）"""

    def __init__(self):
        self.messages = []
        self.max_messages = 5
        self.base_y = 0.2
        self.line_offset = -0.04

    def add_kill(self, killer_name, killer_team, victim_name, _victim_team=''):
        team_color = color.red if killer_team == 'red' else color.azure

        msg = Text(
            text=f'{killer_name} >>> {victim_name}',
            position=(0.25, self.base_y - len(self.messages) * self.line_offset),
            scale=0.8,
            color=team_color,
            background=True
        )
        self.messages.append(msg)
        invoke(self._remove_message, msg, delay=5.0)

    def _remove_message(self, msg):
        if msg in self.messages:
            self.messages.remove(msg)
            destroy(msg)
            self._rearrange()

    def _rearrange(self):
        """重新排列剩余消息"""
        for i, msg in enumerate(self.messages):
            msg.y = self.base_y - i * self.line_offset

    def clear(self):
        for msg in self.messages[:]:
            destroy(msg)
        self.messages.clear()


# 全局实例
kill_feed = KillFeed()
