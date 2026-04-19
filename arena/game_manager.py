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
        # HUD 更新节流计数器
        self._hud_counter = 0


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
            Player(player_id=3, team=Team.BLUE, spawn_position=blue_spawn + Vec3(-2, 0, 0), rotation_y=180),
            Player(player_id=4, team=Team.BLUE, spawn_position=blue_spawn + Vec3(2, 0, 0), rotation_y=180),
        ]

        # 分配控制器
        ai_index = 0
        team_ai_count = {}  # 每个队伍的AI计数，用于分配相反巡逻方向
        for i, player in enumerate(self.players):
            if i == selected_player_id:
                player.controller = HumanController(player, self.input_manager)
                self.human_player = player
            else:
                player.controller = AIController(player)
                # 为每个AI分配不同的节流偏移（0/1/2），确保决策帧错开
                offset = ai_index % 3
                player.controller._throttle_offset = offset
                # counter初始值=2-offset，使首次update(counter+1+offset)%3==0
                player.controller._frame_counter = 2 - offset
                ai_index += 1

                # 同队第二个AI巡逻方向取反，避免同队AI路线完全相同
                team_key = player.team
                team_ai_count[team_key] = team_ai_count.get(team_key, 0) + 1
                if team_ai_count[team_key] % 2 == 0:
                    player.controller._patrol_direction = -1
                    player.controller.current_patrol_idx = -1  # 从末尾开始

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
        # 击杀加分
        if Config.KILL_SCORE > 0:
            self.score_system.add_score(killer.team, Config.KILL_SCORE)

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

        # 结算总分（含击杀分 + 目标分）
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

        # 2. 销毁输入管理器
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

            # 应用 AI 决策（主线程模式）
            for player in self.players:
                if player == self.human_player:
                    continue
                cmd = getattr(player, '_pending_ai_cmd', None)
                if cmd:
                    self._apply_ai_command(player, cmd)
                    player._pending_ai_cmd = None

            # 更新 HUD
            if self.human_player:
                # 准星每帧更新（保证流畅）
                hud.update_crosshair(self.human_player)
                # 文本信息每3帧更新（减少开销）
                self._hud_counter += 1
                if self._hud_counter % 3 == 0:
                    hud.update_player_info(self.human_player)

    # 同队AI最小间距（小于此值时推开，防止 collider 重叠导致物理抖动/卡住）
    _TEAMMATE_MIN_DIST = 2.0

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
                # 排除队友，避免同队AI互相阻挡卡住
                for p in game_manager.players:
                    if p != player and p.team == player.team:
                        move_ignore.append(p)
                ray = raycast(player.position, player.forward,
                              distance=move_distance, ignore=move_ignore, debug=False)
                if ray.hit:
                    # 通知 AIController 计算绕行路径
                    if hasattr(player.controller, 'on_collision'):
                        obstacle_pos = ray.entity.position if hasattr(ray.entity, 'position') else ray.world_point
                        look_at = cmd.get('look_at', (0, 0))
                        target_pos = (look_at[0], 0, look_at[1])
                        player.controller.on_collision(obstacle_pos, target_pos)
                    return  # 不移动
            player.position += player.forward * move_distance

        # 同队AI分离：防止 collider 重叠导致物理引擎推挤抖动
        GameManager._separate_teammates(player)

        if cmd.get('shoot_dir'):
            dx, dy, dz = cmd['shoot_dir']
            player.weapon.shoot(Vec3(dx, dy, dz))

    @staticmethod
    def _separate_teammates(player):
        """如果与同队队友距离过近，主动推开，避免 box collider 重叠引发物理抖动"""
        min_dist = GameManager._TEAMMATE_MIN_DIST
        my_xz = Vec3(player.x, 0, player.z)
        for p in game_manager.players:
            if p == player or p.team != player.team:
                continue
            other_xz = Vec3(p.x, 0, p.z)
            diff = my_xz - other_xz
            d = diff.length()
            if 0.01 < d < min_dist:
                # 沿分离方向推开到 min_dist
                push = diff.normalized() * (min_dist - d) * 0.5
                player.x += push.x
                player.z += push.z


# 全局 GameManager 实例
game_manager = GameManager()
