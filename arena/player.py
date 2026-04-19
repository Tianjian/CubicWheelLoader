from ursina import *
from arena.constants import Team, PlayerState, Config


# 延迟初始化队伍颜色（需要 ursina.color 已就绪）
def get_team_color(team):
    return color.red if team == Team.RED else color.azure


class Player(Entity):
    """游戏角色实体"""

    def __init__(self, player_id, team, spawn_position, **kwargs):
        team_color = get_team_color(team)

        super().__init__(
            model='cube',
            origin_y=-.5,
            scale=Config.PLAYER_SCALE,
            collider='box',
            position=spawn_position,
            color=team_color,
            **kwargs
        )

        self.player_id = player_id      # 1-4
        self.team = team                # RED / BLUE
        self.state = PlayerState.ALIVE
        self.invincible = False
        self.spawn_position = spawn_position

        # 生命值
        self.max_hp = Config.PLAYER_MAX_HP
        self.hp = Config.PLAYER_MAX_HP
        self.original_color = team_color

        # 击杀计分
        self.kills = 0
        self.deaths = 0

        # 控制器（由 GameManager 赋值）
        self.controller = None
        self.destroyed = False
        self._pending_ai_cmd = None

        # 基地装填检测节流
        self._base_reload_counter = 0

        # 武器
        from arena.weapon import Weapon
        self.weapon = Weapon(
            owner=self,
            parent=self,
            model='cube',
            position=(0.5, 0.5, 0.25),
            scale=(.3, .2, 1),
            origin_z=-0.5,
            color=team_color,
            bullet_damage=Config.BULLET_DAMAGE,
            bullet_speed=Config.BULLET_SPEED,
            fire_rate=Config.FIRE_RATE
        )

        # 血条（无背景，避免 Z-fighting）
        self.health_bar_bg = None
        self.health_bar = Entity(
            parent=self, y=2, model='quad',
            color=color.green, scale=(1.5, 0.1),
            billboard=True, unlit=True, double_sided=True
        )
        self.health_bar.cull = False

        # 名字标签
        team_label = 'RED' if team == Team.RED else 'BLUE'
        self.name_tag = Text(
            text=f'P{player_id} [{team_label}]',
            parent=self,
            y=2.5,
            scale=12,
            origin=(0, 0),
            billboard=True,
            color=team_color,
            z=-0.01
        )

        # 弹药显示（血条下方，数字形式）
        self.ammo_text = Text(
            text=f'{self.weapon.max_ammo}/{self.weapon.max_ammo}',
            parent=self,
            y=1.7,
            scale=10,
            origin=(0, 0),
            billboard=True,
            color=color.yellow,
            z=-0.01
        )

    def take_damage(self, damage, attacker):
        """受到伤害"""
        if self.state != PlayerState.ALIVE:
            return
        if self.invincible:
            return

        self.hp -= damage
        # 受伤音效（仅人类玩家听到）
        from arena.game_manager import game_manager
        if self == game_manager.human_player:
            from arena.sound_manager import sound_manager
            sound_manager.play_damage()
        # 更新血条
        ratio = max(0, self.hp / self.max_hp)
        self.health_bar.scale_x = ratio * 1.5
        # 血条变色
        if ratio > 0.5:
            self.health_bar.color = color.green
        elif ratio > 0.25:
            self.health_bar.color = color.yellow
        else:
            self.health_bar.color = color.red

        if self.hp <= 0:
            self.die(attacker)

    def suicide(self):
        """自杀（连续3下X键触发），不计入击杀/死亡统计"""
        if self.state != PlayerState.ALIVE:
            return
        self.state = PlayerState.DEAD
        # 自杀不计入 deaths/kills，不触发 on_player_killed
        from arena.sound_manager import sound_manager
        sound_manager.play_death()
        from arena.game_manager import game_manager
        if self == game_manager.human_player and game_manager.camera_controller:
            game_manager.camera_controller.set_spectator()
            from arena.hud import hud
            hud.ground_crosshair.enabled = False
        invoke(self.respawn, delay=Config.RESPAWN_DELAY)

    def die(self, killer):
        """死亡处理"""
        self.state = PlayerState.DEAD
        self.deaths += 1
        killer.kills += 1

        # 通知 GameManager
        from arena.game_manager import game_manager

        # 死亡音效（仅人类玩家听到自己的）
        if self == game_manager.human_player:
            from arena.sound_manager import sound_manager
            sound_manager.play_death()

        game_manager.on_player_killed(killer, self)

        # 延迟重生
        invoke(self.respawn, delay=Config.RESPAWN_DELAY)

    def respawn(self):
        """在基地重生"""
        if self.destroyed:
            return
        self.hp = self.max_hp
        self.health_bar.scale_x = 1.5
        self.health_bar.color = color.green
        self.weapon.reload()
        self._update_ammo_display()
        self.position = Vec3(self.spawn_position)
        self.rotation_y = 180 if self.team == Team.BLUE else 0
        self.visible = True

        # 进入重生无敌状态
        self.state = PlayerState.RESPawning
        self.invincible = True
        self._blink_time = 0
        self._blink_count = 0
        invoke(self._end_invincibility, delay=Config.INVINCIBLE_DURATION)

        # 如果是人类玩家，恢复相机和准星（在 respawn 内部执行，避免竞态）
        from arena.game_manager import game_manager
        if self == game_manager.human_player and game_manager.camera_controller:
            game_manager.camera_controller.set_third_person()
            from arena.hud import hud
            hud.ground_crosshair.enabled = True

    def _end_invincibility(self):
        """结束无敌状态"""
        if self.destroyed:
            return
        self.invincible = False
        self.state = PlayerState.ALIVE
        self.visible = True
        self.color = self.original_color
        self.weapon.color = self.original_color

    def update(self):
        """每帧更新"""
        if self.state == PlayerState.RESPawning:
            # 无敌闪烁效果
            self._blink_time += time.dt
            if self._blink_time > 0.1:
                self._blink_time = 0
                self.visible = not self.visible
                self._blink_count += 1
                if self._blink_count > 20:
                    self.visible = True
            return

        if self.state == PlayerState.ALIVE and self.controller:
            # 基地装填检测（每10帧检测一次，减少distance调用）
            self._base_reload_counter += 1
            if self._base_reload_counter % 10 == 0:
                self._check_base_reload()
            # 更新弹药显示
            self._update_ammo_display()
            # AI 控制器返回决策字典（由 GameManager 统一应用）
            # 人类控制器直接操作玩家
            result = self.controller.update()
            if isinstance(result, dict) and result:
                self._pending_ai_cmd = result
            else:
                self._pending_ai_cmd = None

    def _check_base_reload(self):
        """在本方基地内自动装填弹药"""
        if self.weapon.current_ammo >= self.weapon.max_ammo:
            return
        from arena.game_manager import game_manager
        base_cfg = game_manager.map_data.get('red_base', {}) \
            if self.team == Team.RED \
            else game_manager.map_data.get('blue_base', {})
        base_pos = Vec3(*base_cfg.get('position', [0, 0, 0]))
        reload_radius = base_cfg.get('reload_radius', base_cfg.get('radius', 6))
        if distance(self.position, base_pos) < reload_radius:
            self.weapon.reload()
            self._update_ammo_display()
            from arena.sound_manager import sound_manager
            sound_manager.play_reload()

    def _update_ammo_display(self):
        """更新弹药显示（仅在实际变化时更新）"""
        ammo = self.weapon.current_ammo
        max_ammo = self.weapon.max_ammo
        new_text = f'{ammo}/{max_ammo}'
        if self.ammo_text.text != new_text:
            self.ammo_text.text = new_text
            self.ammo_text.color = color.yellow if ammo > 3 else color.red
