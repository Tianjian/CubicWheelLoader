from ursina import *
from arena.constants import Config


class HUD:
    """抬头显示（比分、时间、血条、战绩）"""

    def __init__(self):
        self.score_text = None
        self.timer_text = None
        self.hp_bg = None
        self.hp_bar = None
        self.stats_text = None
        self.identity_text = None
        self.controls_text = None
        self.ground_crosshair = None
        self.ammo_text = None
        self.goal_status_text = None

    def create(self):
        """创建所有 HUD 元素"""
        # 比分板（顶部中央）
        self.score_text = Text(
            text='RED: 0    BLUE: 0',
            position=(0, 0.47),
            origin=(0, 0),
            scale=1.5,
            parent=camera.ui
        )

        # 倒计时
        self.timer_text = Text(
            text='05:00',
            position=(0, 0.43),
            origin=(0, 0),
            scale=1.2,
            color=color.yellow,
            parent=camera.ui
        )

        # 玩家血条背景
        self.hp_bg = Entity(
            parent=camera.ui, model='quad',
            position=(0, -0.35), scale=(0.4, 0.025),
            color=color.dark_gray
        )
        # 玩家血条前景
        self.hp_bar = Entity(
            parent=camera.ui, model='quad',
            position=(0, -0.35), scale=(0.4, 0.02),
            color=color.green
        )

        # 击杀/死亡统计
        self.stats_text = Text(
            text='K: 0  D: 0',
            position=(0, -0.42),
            origin=(0, 0),
            scale=1,
            parent=camera.ui
        )

        # 弹药显示
        self.ammo_text = Text(
            text='AMMO: 10/10',
            position=(0, -0.46),
            origin=(0, 0),
            scale=1,
            color=color.yellow,
            parent=camera.ui
        )

        # Goal 占领状态
        self.goal_status_text = Text(
            text='● ○ ● ○',
            position=(0, 0.39),
            origin=(0, 0),
            scale=1,
            parent=camera.ui
        )

        # 当前操控角色
        self.identity_text = Text(
            text='P1 - RED TEAM',
            position=(-0.8, -0.42),
            scale=1,
            color=color.white,
            parent=camera.ui
        )

        # 地面准星
        self.ground_crosshair = Entity(
            model='circle', color=color.yellow,
            scale=1, y=0.1
        )

        # 操作提示（左下角）
        self.controls_text = Text(
            text='Keyboard: WASD-Move  LMB-Shoot  V-View\n'
                 'Gamepad:  LS-Move  RS-Rotate  LT-Shoot  X-View',
            position=(-0.85, -0.35),
            scale=0.8,
            parent=camera.ui,
            color=color.white,
            background=True
        )

    def update_player_info(self, player):
        """更新人类玩家的 HUD 信息"""
        if not player:
            return

        # 身份
        team_label = 'RED' if player.team.value == 'red' else 'BLUE'
        self.identity_text.text = f'P{player.player_id} - {team_label} TEAM'
        self.identity_text.color = color.red if player.team.value == 'red' else color.azure

        # 血条
        ratio = max(0, player.hp / player.max_hp)
        self.hp_bar.scale_x = 0.4 * ratio
        if ratio > 0.5:
            self.hp_bar.color = color.green
        elif ratio > 0.25:
            self.hp_bar.color = color.yellow
        else:
            self.hp_bar.color = color.red

        # 战绩
        self.stats_text.text = f'K: {player.kills}  D: {player.deaths}'

        # 弹药
        if hasattr(player, 'weapon') and hasattr(player.weapon, 'current_ammo'):
            ammo = player.weapon.current_ammo
            max_ammo = player.weapon.max_ammo
            self.ammo_text.text = f'AMMO: {ammo}/{max_ammo}'
            self.ammo_text.color = color.yellow if ammo > 3 else color.red

        # 地面准星
        if player.state.value == 'alive':
            self.ground_crosshair.position = player.position + player.forward * 10
            self.ground_crosshair.y = 0.1
            self.ground_crosshair.enabled = True
        else:
            self.ground_crosshair.enabled = False

    def show_respawn_hint(self, remaining):
        """显示重生倒计时"""
        self.stats_text.text = f'RESPAWNING {int(remaining)}s...'
        self.stats_text.color = color.red

    def show_match_result(self, red_score, blue_score, winner_text, winner_color):
        """显示比赛结果"""
        self.score_text.text = ''
        self.timer_text.text = 'MATCH OVER'
        self.timer_text.color = winner_color

    def destroy(self):
        """销毁所有 HUD 元素"""
        for attr in ('score_text', 'timer_text', 'hp_bg', 'hp_bar',
                     'stats_text', 'identity_text', 'controls_text',
                     'ground_crosshair', 'ammo_text', 'goal_status_text'):
            obj = getattr(self, attr, None)
            if obj:
                destroy(obj)
                setattr(self, attr, None)


# 全局 HUD 实例
hud = HUD()
