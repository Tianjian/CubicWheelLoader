from ursina import *
from arena.constants import Team


class CharacterSelect:
    """角色选择界面"""

    def __init__(self):
        self.selected_id = None
        self.cards = []
        self._elements = []

        # 标题
        title = Text(
            text='TEAM ARENA',
            position=(0, 0.35),
            origin=(0, 0),
            scale=3,
            color=color.yellow,
            parent=camera.ui
        )
        self._elements.append(title)

        subtitle = Text(
            text='Select your character to begin',
            position=(0, 0.25),
            origin=(0, 0),
            scale=1.2,
            color=color.white,
            parent=camera.ui
        )
        self._elements.append(subtitle)

        # 4 个角色卡片
        for i in range(4):
            team = Team.RED if i < 2 else Team.BLUE
            team_color = color.red if team == Team.RED else color.azure

            card = Button(
                text=f'P{i+1}\n{team.value.upper()} TEAM',
                position=(-0.3 + i * 0.2, 0.05),
                scale=(0.18, 0.3),
                color=team_color,
                on_click=Func(self._select_character, i)
            )
            self.cards.append(card)

        # 开始按钮
        self.start_btn = Button(
            text='START',
            position=(0, -0.3),
            scale=(0.2, 0.06),
            color=color.green,
            enabled=False,
            on_click=self._start_match
        )

        # 操作说明
        controls = Text(
            text='Choose P1-P4 to join either team\n'
                 'AI will control the remaining players',
            position=(0, -0.45),
            origin=(0, 0),
            scale=0.9,
            color=color.gray,
            parent=camera.ui
        )
        self._elements.append(controls)

    def _select_character(self, idx):
        """选择角色"""
        self.selected_id = idx
        for i, card in enumerate(self.cards):
            card.highlight = Color(255, 255, 0, 100) if i == idx else Color.clear
        self.start_btn.enabled = True

    def _start_match(self):
        """开始比赛"""
        from arena.game_manager import game_manager
        game_manager.start_match(self.selected_id)
        # 销毁选择界面
        self._destroy()

    def _destroy(self):
        """清理选择界面"""
        for card in self.cards:
            destroy(card)
        destroy(self.start_btn)
        for elem in self._elements:
            destroy(elem)
