from ursina import *
from arena.constants import Team, PlayerState, GameState, Config
from arena.player import Player
from arena.human_ctrl import HumanController
from arena.ai_ctrl import AIController
from arena.camera_ctrl import CameraController
from arena.game_map import GameMap
from arena.score_system import TeamScoreSystem
from arena.match_timer import MatchTimer
from arena.kill_feed import kill_feed
from arena.hud import hud
from arena.input_manager import InputManager


class GameManager(Entity):
    """游戏主控（状态机：菜单/选择/倒计时/进行/结束）"""

    def __init__(self):
        super().__init__()
        self.state = GameState.MENU
        self.players = []
        self.human_player = None
        self.score_system = TeamScoreSystem()
        self.timer = MatchTimer()
        self.camera_controller = None
        self.game_map = None
        self.input_manager = None

    def start_match(self, selected_player_id):
        """开始比赛"""
        print(f'Starting match, human controls P{selected_player_id + 1}')

        # 创建输入管理器（统一键盘/手柄）
        self.input_manager = InputManager()

        # 创建地图
        self.game_map = GameMap()

        # 创建 4 个玩家
        red_spawn = Vec3(Config.RED_BASE_POS)
        blue_spawn = Vec3(Config.BLUE_BASE_POS)

        self.players = [
            Player(player_id=1, team=Team.RED, spawn_position=red_spawn + Vec3(-2, 0, 0)),
            Player(player_id=2, team=Team.RED, spawn_position=red_spawn + Vec3(2, 0, 0)),
            Player(player_id=3, team=Team.BLUE, spawn_position=blue_spawn + Vec3(-2, 0, 0)),
            Player(player_id=4, team=Team.BLUE, spawn_position=blue_spawn + Vec3(2, 0, 0)),
        ]

        # 分配控制器
        for i, player in enumerate(self.players):
            if i == selected_player_id:
                player.controller = HumanController(player, self.input_manager)
                self.human_player = player
            else:
                player.controller = AIController(player)

        # 创建相机控制器
        self.camera_controller = CameraController(self.human_player)

        # 创建 HUD
        hud.create()

        # 重置计分和计时
        self.score_system.reset()
        self.timer.reset()

        # 开始倒计时
        self.state = GameState.COUNTDOWN
        self._countdown(3)

    def _countdown(self, seconds):
        """倒计时"""
        if seconds > 0:
            countdown_text = Text(
                text=str(seconds),
                origin=(0, 0),
                scale=5,
                color=color.yellow
            )
            invoke(destroy, countdown_text, delay=0.9)
            invoke(self._countdown, seconds - 1, delay=1.0)
        else:
            go_text = Text(
                text='GO!',
                origin=(0, 0),
                scale=5,
                color=color.green
            )
            invoke(destroy, go_text, delay=0.5)
            self.state = GameState.PLAYING
            self.timer.start()

    def on_player_killed(self, killer, victim):
        """击杀事件"""
        # 加分
        self.score_system.add_score(killer.team, Config.KILL_SCORE)

        # 击杀播报
        kill_feed.add_kill(
            f'P{killer.player_id}', killer.team.value,
            f'P{victim.player_id}', victim.team.value
        )

        # 人类玩家死亡处理
        if victim == self.human_player:
            self._on_human_dead()

    def _on_human_dead(self):
        """人类玩家死亡"""
        self.camera_controller.set_spectator()
        hud.ground_crosshair.enabled = False
        # 3 秒后重生时恢复相机
        invoke(self._on_human_respawn, delay=Config.RESPAWN_DELAY)

    def _on_human_respawn(self):
        """人类玩家重生"""
        if self.human_player and self.human_player.state.value == 'respawning':
            self.camera_controller.set_third_person()

    def end_match(self):
        """比赛结束"""
        self.state = GameState.MATCH_END
        self.timer.stop()

        red_score = self.score_system.get_score(Team.RED)
        blue_score = self.score_system.get_score(Team.BLUE)

        if red_score > blue_score:
            winner = "RED TEAM WINS!"
            winner_color = color.red
        elif blue_score > red_score:
            winner = "BLUE TEAM WINS!"
            winner_color = color.azure
        else:
            winner = "DRAW!"
            winner_color = color.yellow

        # 结果画面
        self.result_bg = Entity(
            parent=camera.ui,
            model='quad',
            scale=(0.6, 0.5),
            color=color.black66,
            z=0.1
        )
        Text(
            text='MATCH OVER',
            position=(0, 0.15),
            origin=(0, 0),
            scale=2.5,
            color=color.white,
            parent=camera.ui
        )
        Text(
            text=f'RED: {red_score}    BLUE: {blue_score}',
            position=(0, 0),
            origin=(0, 0),
            scale=2,
            color=color.white,
            parent=camera.ui
        )
        Text(
            text=winner,
            position=(0, -0.12),
            origin=(0, 0),
            scale=2.5,
            color=winner_color,
            parent=camera.ui
        )
        Button(
            text='RESTART',
            position=(0, -0.25),
            scale=(0.15, 0.05),
            color=color.green,
            on_click=self._restart
        )

    def _restart(self):
        """重新开始"""
        # 销毁输入管理器
        if self.input_manager:
            destroy(self.input_manager)
            self.input_manager = None

        # 清理场景中的玩家实体
        for p in self.players:
            destroy(p)

        # 清理 UI
        kill_feed.clear()

        # 重置状态
        self.players = []
        self.human_player = None
        self.camera_controller = None
        self.state = GameState.MENU

        # 重新显示角色选择
        from arena.character_select import CharacterSelect
        CharacterSelect()

    def update(self):
        """每帧更新"""
        if self.state == GameState.PLAYING:
            # 处理瞬时动作（视角切换）
            if self.input_manager and self.input_manager.action:
                if self.camera_controller:
                    self.camera_controller.toggle_distance()

            # 更新 HUD
            if self.human_player:
                hud.update_player_info(self.human_player)


# 全局 GameManager 实例
game_manager = GameManager()
