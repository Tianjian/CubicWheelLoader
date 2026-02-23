from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from ursina.shaders import lit_with_shadows_shader
from enum import Enum
from math import radians

app = Ursina()

# 设置随机种子和默认着色器
random.seed(0)
Entity.default_shader = lit_with_shadows_shader

# 创建地面
ground = Entity(model='plane', collider='box', scale=64, texture='grass', texture_scale=(4,4))

# 编辑器相机（Tab 键切换）
editor_camera = EditorCamera(enabled=False, ignore_paused=True)

# 玩家控制器
player = FirstPersonController(model='cube', z=-10, color=color.orange, origin_y=-.5, speed=8, collider='box')
player.collider = BoxCollider(player, Vec3(0,1,0), Vec3(1,2,1))

# 可射击对象父节点
shootables_parent = Entity()
mouse.traverse_target = shootables_parent

# 创建随机墙壁
for i in range(16):
    Entity(model='cube', origin_y=-.5, scale=2, texture='brick', texture_scale=(1,2),
        x=random.uniform(-8,8),
        z=random.uniform(-8,8) + 8,
        collider='box',
        scale_y = random.uniform(2,3),
        color=color.hsv(0, 0, random.uniform(.9, 1))
        )


# ==================== Bullet 类（保持不变）====================

class Bullet(Entity):
    """实体子弹类"""
    def __init__(self, start_position, direction, damage=10, speed=35, **kwargs):
        super().__init__(
            model='sphere',
            scale=0.1,
            color=color.yellow,
            position=start_position,
            collider='sphere',
            **kwargs
        )

        self.direction = direction
        self.damage = damage
        self.speed = speed
        self.max_distance = 100
        self.start_position = start_position

    def update(self):
        if distance(self.position, self.start_position) > self.max_distance:
            destroy(self)
            return

        move_distance = self.speed * time.dt * 1.5
        hit_info = raycast(
            self.position,
            self.direction,
            distance=move_distance,
            ignore=(self,)
        )

        if hit_info.hit:
            if hasattr(hit_info.entity, 'hp'):
                hit_info.entity.hp -= self.damage
                original_color = hit_info.entity.color
                hit_info.entity.color = color.red
                hit_info.entity.animate_color(original_color, duration=0.1)

            self.on_hit(hit_info)
            destroy(self)
            return

        self.position += self.direction * self.speed * time.dt

    def on_hit(self, hit_info):
        self.create_impact_effect(hit_info.world_point, hit_info.world_normal)
        self.play_impact_sound()

    def create_impact_effect(self, position, normal):
        for _ in range(5):
            particle = Entity(
                model='cube',
                scale=0.05,
                color=color.orange,
                position=position
            )
            spread = Vec3(
                random.uniform(-1, 1),
                random.uniform(-1, 1),
                random.uniform(-1, 1)
            ).normalized()
            particle.animate_position(
                position + (normal + spread).normalized() * 0.5,
                duration=0.3
            )
            particle.animate_scale(0, duration=0.3)
            destroy(particle, delay=0.3)

    def play_impact_sound(self):
        from ursina.prefabs.ursfx import ursfx
        ursfx(
            [(0.0, 0.0), (0.05, 0.5), (0.1, 0.2), (0.15, 0.1), (0.2, 0.0)],
            volume=0.3,
            wave='noise',
            pitch=random.uniform(-8, -6),
            speed=2.0
        )


# ==================== 相机控制器（升级版）====================

class CameraMode(Enum):
    FIRST_PERSON = "first_person"
    THIRD_PERSON = "third_person"


class CameraController(Entity):
    """相机控制器（v4: 方向跟随本体）"""
    def __init__(self, target_entity):
        super().__init__()
        self.target = target_entity
        self.mode = CameraMode.FIRST_PERSON
        self.tps_offset = Vec3(0, 15, -40)  # TPS 相机偏移
        self.camera_distance = 40  # 相机距离
        self.camera_height = 15    # 相机高度
        self.fov = {
            CameraMode.FIRST_PERSON: 90,
            CameraMode.THIRD_PERSON: 60
        }
        self.transition_speed = 10
        # 保存 FPS 模式下的相机旋转
        self.fps_camera_rotation = Vec3(0, 0, 0)

    def toggle_mode(self):
        """切换视角模式"""
        if self.mode == CameraMode.FIRST_PERSON:
            self.set_third_person()
        else:
            self.set_first_person()

    def set_first_person(self):
        """设置为第一人称"""
        self.mode = CameraMode.FIRST_PERSON
        player.visible = False
        gun.enabled = True

        # 将枪从玩家移回相机
        gun.parent = camera
        gun.position = (.5, -.25, .25)
        gun.rotation = (0, 0, 0)

        # 设置相机为 camera_pivot 的子对象（这是 FirstPersonController 的正确做法）
        camera.parent = player.camera_pivot
        camera.position = (0, 0, 0)

        # 恢复保存的相机旋转（只恢复 x，y 由 player 控制旋转）
        camera.rotation_x = self.fps_camera_rotation.x

        camera.animate('fov', self.fov[CameraMode.FIRST_PERSON], duration=0.3)

        view_mode_text.text = 'View: FPS'

        # 显示准星
        if hasattr(player, 'cursor'):
            player.cursor.enabled = True
        mouse.locked = True

        # 隐藏 TPS 特有元素
        ground_crosshair.enabled = False

    def set_third_person(self):
        """设置为第三人称"""
        self.mode = CameraMode.THIRD_PERSON

        # 保存当前的相机旋转（FPS 模式下）
        self.fps_camera_rotation = Vec3(camera.rotation_x, player.rotation_y, camera.rotation_z)

        player.visible = True

        # 将枪从相机移到玩家身上
        gun.parent = player
        gun.position = (0.3, 0.8, 0.2)
        gun.rotation = (0, 0, 0)

        camera.parent = scene
        self.update_camera()
        camera.animate('fov', self.fov[CameraMode.THIRD_PERSON], duration=0.3)

        view_mode_text.text = 'View: TPS'

        # 隐藏准星
        if hasattr(player, 'cursor'):
            player.cursor.enabled = False
        mouse.locked = False

        # 显示 TPS 特有元素
        ground_crosshair.enabled = True

    def update(self):
        """每帧更新"""
        if self.mode == CameraMode.THIRD_PERSON:
            self.update_camera()

    def update_camera(self):
        """更新第三人称相机位置（固定角度跟随玩家位置）"""
        # 相机固定在玩家后方，不随玩家旋转
        target_position = self.target.position + Vec3(0, self.camera_height, -self.camera_distance)
        camera.position = lerp(camera.position, target_position, self.transition_speed * time.dt)
        
        # 相机固定看向玩家前方（不随玩家旋转改变）
        look_target = self.target.position + Vec3(0, 1.5, 10)
        camera.look_at(look_target)

    def get_shoot_direction(self):
        """获取射击方向（v4: 方向跟随本体）"""
        if self.mode == CameraMode.FIRST_PERSON:
            return camera.forward
        else:
            # TPS 模式：直接使用玩家的 forward 方向
            return player.forward.normalized()


# 创建相机控制器
camera_controller = CameraController(player)


# ==================== Weapon 类（保持不变）====================

class Weapon(Entity):
    """武器类"""
    def __init__(self, bullet_damage=10, bullet_speed=35, fire_rate=0.15, **kwargs):
        super().__init__(**kwargs)

        self.bullet_damage = bullet_damage
        self.bullet_speed = bullet_speed
        self.fire_rate = fire_rate
        self.on_cooldown = False
        self.last_fire_time = 0

        # 枪口闪光
        self.muzzle_flash = Entity(
            parent=self,
            z=1,
            world_scale=0.5,
            model='quad',
            color=color.yellow,
            enabled=False
        )

    def shoot(self, target_direction=None):
        """开火"""
        if self.on_cooldown:
            return

        # 获取射击方向
        if target_direction is None:
            target_direction = camera_controller.get_shoot_direction()

        # 创建子弹
        bullet = Bullet(
            start_position=self.muzzle_flash.world_position,
            direction=target_direction,
            damage=self.bullet_damage,
            speed=self.bullet_speed
        )

        # 枪口闪光
        self.muzzle_flash.enabled = True
        invoke(self.muzzle_flash.disable, delay=0.05)

        # 播放射击音效
        self.play_shoot_sound()

        # 设置冷却
        self.on_cooldown = True
        invoke(setattr, self, 'on_cooldown', False, delay=self.fire_rate)

    def play_shoot_sound(self):
        """播放射击音效"""
        from ursina.prefabs.ursfx import ursfx
        ursfx(
            [(0.0, 0.0), (0.05, 0.8), (0.1, 0.4), (0.15, 0.2), (0.2, 0.0)],
            volume=0.5,
            wave='noise',
            pitch=random.uniform(-2, -1),
            speed=1.5
        )


# 创建枪支
gun = Weapon(
    model='cube',
    parent=camera,
    position=(.5, -.25, .25),
    scale=(.3, .2, 1),
    origin_z=-.5,
    color=color.red,
    bullet_damage=10,
    bullet_speed=35,
    fire_rate=0.15
)


# ==================== 玩家移动控制（v4 改进）====================

class TPSMovementController(Entity):
    """TPS 模式下的移动控制器（坦克式移动）"""
    def __init__(self):
        super().__init__()
        self.rotation_speed = 120  # 旋转速度（度/秒）
        self.move_speed = 8  # 移动速度

    def update(self):
        """每帧更新"""
        if camera_controller.mode != CameraMode.THIRD_PERSON:
            return

        # A/D 控制左右旋转
        if held_keys['a']:
            player.rotation_y -= self.rotation_speed * time.dt
        elif held_keys['d']:
            player.rotation_y += self.rotation_speed * time.dt

        # W/S 控制前后移动（沿玩家朝向）
        move_speed = self.move_speed * time.dt
        if held_keys['w']:
            ray = raycast(player.position, player.forward, distance=move_speed, ignore=(player,))
            if not ray.hit:
                player.position += player.forward * move_speed
        elif held_keys['s']:
            ray = raycast(player.position, -player.forward, distance=move_speed, ignore=(player,))
            if not ray.hit:
                player.position -= player.forward * move_speed


# 创建 TPS 移动控制器
tps_movement = TPSMovementController()


# ==================== 地面准星 ====================

ground_crosshair = Entity(
    model='circle',
    color=color.yellow,
    scale=1,
    y=0.1,
    enabled=False  # 初始隐藏
)

def update_crosshair():
    """更新地面准星位置"""
    if camera_controller.mode == CameraMode.THIRD_PERSON:
        ground_crosshair.position = player.position + player.forward * 10


# ==================== 敌人系统 ====================

class Enemy(Entity):
    def __init__(self, position=(0,0,0)):
        super().__init__(
            parent=shootables_parent,
            model='cube',
            origin_y=-.5,
            texture='white_cube',
            color=color.red,
            position=position,
            scale=1.5,
            collider='box'
        )
        self.hp = 30
        self.max_hp = 30

        # 健康条（参考 v2 实现）
        self.health_bar = Entity(
            parent=self,
            y=1.5,
            model='cube',
            color=color.red,
            world_scale=(1.5, 0.1, 0.1)
        )

    def update(self):
        if self.hp <= 0:
            destroy(self)
            return

        # 简单 AI：向玩家移动
        dist = distance(self.position, player.position)
        if dist > 2:
            self.look_at_2d(player.position, 'y')
            # 使用 raycast 检测碰撞（包括其他敌人、墙壁、玩家）
            move_distance = 2 * time.dt
            ray = raycast(self.position, self.forward, distance=move_distance, ignore=(self,))
            if not ray.hit:
                self.position += self.forward * move_distance

        # 更新健康条
        self.health_bar.world_scale_x = self.hp / self.max_hp * 1.5

# 创建敌人
enemies = [Enemy(position=(x*4, 0, 8)) for x in range(4)]


# ==================== 敌人生成器 ====================

class EnemySpawner(Entity):
    """敌人生成器：每隔 15 秒在随机位置生成敌人"""
    def __init__(self):
        super().__init__()
        self.spawn_interval = 15  # 生成间隔（秒）
        self.spawn_timer = 0

    def update(self):
        self.spawn_timer += time.dt
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_enemy()
            self.spawn_timer = 0

    def spawn_enemy(self):
        """在随机位置生成敌人"""
        x = random.uniform(-20, 20)
        z = random.uniform(-20, 20)
        enemy = Enemy(position=(x, 0, z))
        enemies.append(enemy)
        print(f'Enemy spawned at ({x:.1f}, 0, {z:.1f})')


# 创建敌人生成器
enemy_spawner = EnemySpawner()


# ==================== 游戏管理器 ====================

class GameManager(Entity):
    """游戏管理器：处理游戏重启等全局逻辑"""
    def __init__(self):
        super().__init__()
        self.restart_height = -10  # 重启高度阈值
        self.is_restarting = False

    def update(self):
        # 检查玩家是否跌落
        if player.y < self.restart_height and not self.is_restarting:
            self.restart_game()

    def restart_game(self):
        """重启游戏"""
        self.is_restarting = True
        print('Restarting game...')
        
        # 显示重启提示
        restart_text = Text(
            text='RESTARTING...',
            origin=(0, 0),
            scale=3,
            color=color.red
        )
        
        # 延迟后重启
        invoke(self._do_restart, restart_text, delay=1)

    def _do_restart(self, restart_text):
        """执行重启"""
        # 重置玩家位置
        player.position = Vec3(0, 0, -10)
        player.rotation = Vec3(0, 0, 0)
        
        # 清除所有敌人
        for enemy in enemies[:]:  # 使用副本遍历
            destroy(enemy)
        enemies.clear()
        
        # 重新创建初始敌人
        for x in range(4):
            enemy = Enemy(position=(x*4, 0, 8))
            enemies.append(enemy)
        
        # 销毁重启提示
        destroy(restart_text)
        
        self.is_restarting = False
        print('Game restarted!')


# 创建游戏管理器
game_manager = GameManager()


# ==================== UI ====================

controls_text = Text(
    text='FPS Controls:\n\n'
         'WASD - Move\n'
         'Space - Jump\n'
         'Mouse - Look around\n'
         'Left Click - Shoot\n'
         'V - Toggle FPS/TPS\n'
         'Tab - Toggle Editor Mode\n\n'
         'TPS Controls:\n\n'
         'W - Forward\n'
         'S - Backward\n'
         'A - Turn Left\n'
         'D - Turn Right\n'
         'Left Click - Shoot\n'
         'V - Toggle FPS/TPS\n'
         'Tab - Toggle Editor Mode',
    position=(-.85, .45),
    parent=camera.ui,
    color=color.white,
    background=True
)

view_mode_text = Text(
    text='View: FPS',
    position=(0, .45),
    parent=camera.ui,
    origin=(0, 0),
    scale=2,
    color=color.yellow,
    background=True
)


# ==================== 主循环 ====================

def update():
    update_crosshair()
    
    if held_keys['left mouse']:
        gun.shoot()


# ==================== 输入处理 ====================

def input(key):
    if key == 'tab':
        player.cursor.enabled = not player.cursor.enabled
        player.visible = not player.visible
        gun.enabled = not gun.enabled
        editor_camera.enabled = not editor_camera.enabled

    if key == 'v' and not editor_camera.enabled:
        camera_controller.toggle_mode()


# ==================== 运行游戏 ====================

if __name__ == '__main__':
    app.run()
