from ursina import *
from arena.constants import Team, GameState, Config
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
from arena.sound_manager import sound_manager


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
        self.ai_process_manager = None  # P3: AI 子进程管理器

    def start_match(self, selected_player_id, map_name=None):
        """开始比赛"""
        print(f'Starting match, human controls P{selected_player_id + 1}')

        # 创建输入管理器（统一键盘/手柄）
        self.input_manager = InputManager()

        # 加载地图数据
        from arena.map_loader import load_map, load_default_map
        if map_name:
            self.map_data = load_map(map_name)
        else:
            self.map_data = load_default_map()

        # 创建地图
        self.game_map = GameMap(self.map_data)

        # 创建 4 个玩家（出生点从地图数据读取）
        red_pos = self.map_data['red_base']['position']
        blue_pos = self.map_data['blue_base']['position']
        red_spawn = Vec3(*red_pos)
        blue_spawn = Vec3(*blue_pos)

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

        # 启动 AI 子进程（如果配置开启）
        if Config.AI_USE_SUBPROCESS:
            self._start_ai_subprocess()
        else:
            self.ai_process_manager = None

        # 创建 HUD
        hud.create()

        # 重置计分和计时
        self.score_system.reset()
        self.timer.reset()

        # 开始倒计时
        self.state = GameState.COUNTDOWN
        self._countdown(3)

    def _start_ai_subprocess(self):
        """启动 AI 子进程"""
        from arena.ai_process import AIProcessManager
        self.ai_process_manager = AIProcessManager()

        # 收集所有玩家信息（子进程需要知道所有玩家的位置来寻敌）
        players_info = []
        for player in self.players:
            players_info.append({
                'player_id': player.player_id,
                'team_id': 0 if player.team == Team.RED else 1,
                'spawn_x': player.spawn_position.x,
                'spawn_z': player.spawn_position.z,
            })
        self.ai_process_manager.start(players_info)

    def _countdown(self, seconds):
        """倒计时"""
        if seconds > 0:
            countdown_text = Text(
                text=str(seconds),
                origin=(0, 0),
                scale=5,
                color=color.yellow
            )
            sound_manager.play_countdown()
            invoke(destroy, countdown_text, delay=0.9)
            invoke(self._countdown, seconds - 1, delay=1.0)
        else:
            go_text = Text(
                text='GO!',
                origin=(0, 0),
                scale=5,
                color=color.green
            )
            sound_manager.play_match_start()
            invoke(destroy, go_text, delay=0.5)
            self.state = GameState.PLAYING
            self.timer.start()

    def on_player_killed(self, killer, victim):
        """击杀事件"""
        # 击杀不再加分

        # 击杀音效（人类玩家击杀时播放）
        if killer == self.human_player:
            sound_manager.play_kill()

        # 击杀播报
        kill_feed.add_kill(
            f'P{killer.player_id}', killer.team.value,
            f'P{victim.player_id}', victim.team.value
        )

        # 人类玩家死亡处理
        if victim == self.human_player:
            self._on_human_dead()

    def on_goal_owner_changed(self):
        """Goal 占领方变化时更新实时比分"""
        self.score_system.update_from_goals(self.game_map.goals)
        # 更新 HUD Goal 状态
        self._update_goal_status()

    def _update_goal_status(self):
        """更新 HUD 的 Goal 占领状态显示"""
        from arena.hud import hud
        if not hud.goal_status_text:
            return
        status_parts = []
        for goal in self.game_map.goals:
            if goal.owner == Team.RED:
                status_parts.append('●')
            elif goal.owner == Team.BLUE:
                status_parts.append('◆')
            else:
                status_parts.append('○')
        hud.goal_status_text.text = '  '.join(status_parts)

    def _on_human_dead(self):
        """人类玩家死亡"""
        self.camera_controller.set_spectator()
        hud.ground_crosshair.enabled = False
        # 相机恢复移入 Player.respawn()，避免 invoke 竞态

    def end_match(self):
        """比赛结束"""
        self.state = GameState.MATCH_END
        self.timer.stop()

        # 比赛结束音效
        sound_manager.play_match_end()

        # 从 Goal 计算结算分数
        red_score = 0
        blue_score = 0
        for goal in self.game_map.goals:
            if goal.owner == Team.RED:
                red_score += Config.GOAL_SCORE
            elif goal.owner == Team.BLUE:
                blue_score += Config.GOAL_SCORE

        if red_score > blue_score:
            winner = "RED TEAM WINS!"
            winner_color = color.red
        elif blue_score > red_score:
            winner = "BLUE TEAM WINS!"
            winner_color = color.azure
        else:
            winner = "DRAW!"
            winner_color = color.yellow

        # 结果画面（保存引用以便 _restart 清理）
        self._result_ui = []

        self.result_bg = Entity(
            parent=camera.ui,
            model='quad',
            scale=(0.6, 0.5),
            color=color.black66,
            z=0.1
        )
        self._result_ui.append(self.result_bg)

        t = Text(
            text='MATCH OVER',
            position=(0, 0.15),
            origin=(0, 0),
            scale=2.5,
            color=color.white,
            parent=camera.ui
        )
        self._result_ui.append(t)

        t = Text(
            text=f'RED: {red_score}    BLUE: {blue_score}',
            position=(0, 0),
            origin=(0, 0),
            scale=2,
            color=color.white,
            parent=camera.ui
        )
        self._result_ui.append(t)

        t = Text(
            text=winner,
            position=(0, -0.12),
            origin=(0, 0),
            scale=2.5,
            color=winner_color,
            parent=camera.ui
        )
        self._result_ui.append(t)

        btn = Button(
            text='RESTART',
            position=(0, -0.25),
            scale=(0.15, 0.05),
            color=color.green,
            on_click=self._restart
        )
        self._result_ui.append(btn)

    def _restart(self):
        """重新开始"""
        # 1. 清理 end_match UI
        for ui in getattr(self, '_result_ui', []):
            destroy(ui)
        self._result_ui = []

        # 2. 停止 AI 子进程
        if self.ai_process_manager:
            self.ai_process_manager.stop()
            self.ai_process_manager = None

        # 3. 销毁输入管理器
        if self.input_manager:
            destroy(self.input_manager)
            self.input_manager = None

        # 4. 销毁相机控制器
        if self.camera_controller:
            destroy(self.camera_controller)
            self.camera_controller = None

        # 5. 销毁地图（包含基地、掩体、边界墙）
        if self.game_map:
            self.game_map.destroy()
            self.game_map = None

        # 6. 标记+销毁玩家（防止延迟回调）
        for p in self.players:
            p.destroyed = True
            if hasattr(p, 'weapon'):
                p.weapon.destroyed = True
            destroy(p)

        # 7. 清理飞行中的子弹
        from arena.bullet import clear_all_bullets
        clear_all_bullets()

        # 8. 销毁 HUD
        hud.destroy()

        # 9. 清理击杀播报
        kill_feed.clear()

        # 10. 重置状态
        self.players = []
        self.human_player = None
        self.state = GameState.MENU

        # 11. 重新显示角色选择
        from arena.character_select import CharacterSelect
        CharacterSelect()

    def update(self):
        """每帧更新"""
        if self.state == GameState.PLAYING:
            # 处理瞬时动作（视角切换）
            if self.input_manager and self.input_manager.action:
                if self.camera_controller:
                    self.camera_controller.toggle_distance()

            # 应用 AI 决策
            if self.ai_process_manager and self.ai_process_manager.is_running:
                # 子进程模式：写入状态 → 读取决策 → 应用
                self.ai_process_manager.write_player_states(self.players, time.dt)
                commands = self.ai_process_manager.read_commands(Config.AI_SUBPROCESS_TIMEOUT)
                for player in self.players:
                    if player == self.human_player:
                        continue
                    cmd = commands.get(player.player_id)
                    if cmd:
                        self._apply_ai_command(player, cmd)
            else:
                # 主线程模式：从 Player._pending_ai_cmd 读取
                for player in self.players:
                    if player == self.human_player:
                        continue
                    cmd = getattr(player, '_pending_ai_cmd', None)
                    if cmd:
                        self._apply_ai_command(player, cmd)
                        player._pending_ai_cmd = None

            # 更新 HUD
            if self.human_player:
                hud.update_player_info(self.human_player)

    @staticmethod
    def _apply_ai_command(player, cmd):
        """将 AI 决策字典应用到玩家实体"""
        if not cmd:
            return

        if 'look_at' in cmd and cmd['look_at'] is not None:
            tx, tz = cmd['look_at']
            player.look_at_2d(Vec3(tx, player.y, tz), 'y')

        if 'rotate_y' in cmd and cmd['rotate_y'] is not None:
            player.rotation_y += cmd['rotate_y']

        if cmd.get('move_fwd') and abs(cmd['move_fwd']) > 0.05:
            move_distance = cmd['move_fwd'] * Config.AI_MOVE_SPEED * time.dt
            if cmd.get('request_raycast'):
                move_ignore = [player]
                if game_manager.game_map:
                    move_ignore.extend(game_manager.game_map.goals)
                ray = raycast(player.position, player.forward,
                              distance=move_distance, ignore=move_ignore, debug=False)
                if ray.hit:
                    # 通知 AIController 进入回避模式
                    if hasattr(player.controller, 'avoiding'):
                        import random as _rand
                        player.controller.avoiding = True
                        player.controller.avoid_end_time = time.time() + Config.AI_AVOID_DURATION
                        player.controller.avoid_direction = 1 if _rand.random() > 0.5 else -1
                    return  # 不移动
            player.position += player.forward * move_distance

        if cmd.get('shoot_dir'):
            dx, dy, dz = cmd['shoot_dir']
            player.weapon.shoot(Vec3(dx, dy, dz))


# 全局 GameManager 实例
game_manager = GameManager()
