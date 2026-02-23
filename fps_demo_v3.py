from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from ursina.shaders import lit_with_shadows_shader
from enum import Enum

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
    def __init__(self, start_position, direction, damage=10, speed=50, **kwargs):
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


# ==================== 第一步：创建相机控制器 ====================

class CameraMode(Enum):
    FIRST_PERSON = "first_person"
    THIRD_PERSON = "third_person"


class CameraController(Entity):
    """相机控制器"""
    def __init__(self, target_entity):
        super().__init__()
        self.target = target_entity
        self.mode = CameraMode.FIRST_PERSON
        self.tps_offset = Vec3(0, 15, -40)  # TPS 相机偏移：上15，后40（抬高，更大俯角）
        self.fov = {
            CameraMode.FIRST_PERSON: 90,
            CameraMode.THIRD_PERSON: 60
        }
        self.transition_speed = 10  # 相机平滑跟随速度

    def toggle_mode(self):
        """切换视角模式"""
        if self.mode == CameraMode.FIRST_PERSON:
            self.set_third_person()
        else:
            self.set_first_person()

    def set_first_person(self):
        """设置为第一人称"""
        self.mode = CameraMode.FIRST_PERSON

        # 隐藏玩家身体，显示武器
        player.visible = False
        gun.enabled = True

        # 设置相机到玩家头部
        camera.parent = player
        camera.position = (0, 0, 0)
        camera.rotation = (0, 0, 0)

        # FOV 平滑过渡
        camera.animate('fov', self.fov[CameraMode.FIRST_PERSON], duration=0.3)

        # 更新视角指示
        view_mode_text.text = 'View: FPS'

    def set_third_person(self):
        """设置为第三人称"""
        self.mode = CameraMode.THIRD_PERSON

        # 显示玩家身体，武器移到肩膀
        player.visible = True
        gun.position = (0.3, 0.8, 0.2)  # 移到右肩位置
        gun.rotation = (0, 0, 0)

        # 相机独立于玩家
        camera.parent = scene
        self.update_camera()

        # FOV 平滑过渡
        camera.animate('fov', self.fov[CameraMode.THIRD_PERSON], duration=0.3)

        # 更新视角指示
        view_mode_text.text = 'View: TPS'

    def update(self):
        """每帧更新"""
        if self.mode == CameraMode.THIRD_PERSON:
            self.update_camera()

    def update_camera(self):
        """更新第三人称相机位置"""
        # 目标位置：玩家身后上方
        target_position = self.target.position + self.tps_offset

        # 平滑移动相机
        camera.position = lerp(camera.position, target_position, self.transition_speed * time.dt)

        # 相机看向玩家头部
        look_target = self.target.position + Vec3(0, 1.5, 0)
        camera.look_at(look_target)

    def get_shoot_direction(self):
        """获取射击方向"""
        if self.mode == CameraMode.FIRST_PERSON:
            return camera.forward
        else:
            # TPS 模式：从枪口向相机前方射击
            # 计算枪口位置到相机前方远点的方向
            target_point = camera.world_position + camera.forward * 100
            return (target_point - gun.world_position).normalized()


# 创建相机控制器
camera_controller = CameraController(player)


# ==================== 第二步：升级 Weapon 类 ====================

class Weapon(Entity):
    """武器类（升级版）"""
    def __init__(self, bullet_damage=10, bullet_speed=50, fire_rate=0.15, **kwargs):
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
            [(0.0, 0.0), (0.1, 0.9), (0.15, 0.75), (0.3, 0.14), (0.6, 0.0)],
            volume=0.5,
            wave='noise',
            pitch=random.uniform(-13, -12),
            pitch_change=-12,
            speed=3.0
        )


# 创建武器实例
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


# ==================== 敌人类（保持不变）====================

class Enemy(Entity):
    """敌人类"""
    def __init__(self, **kwargs):
        super().__init__(parent=shootables_parent, model='cube', scale_y=2, origin_y=-.5, color=color.light_gray, collider='box', **kwargs)
        self.health_bar = Entity(parent=self, y=1.2, model='cube', color=color.red, world_scale=(1.5, .1, .1))
        self.max_hp = 100
        self.hp = self.max_hp

    def update(self):
        dist = distance_xz(player.position, self.position)
        if dist > 40:
            return

        self.health_bar.alpha = max(0, self.health_bar.alpha - time.dt)
        self.look_at_2d(player.position, 'y')
        hit_info = raycast(self.world_position + Vec3(0,1,0), self.forward, 30, ignore=(self,))

        if hit_info.entity == player:
            if dist > 2:
                self.position += self.forward * time.dt * 5

    @property
    def hp(self):
        return self._hp

    @hp.setter
    def hp(self, value):
        self._hp = value
        if value <= 0:
            destroy(self)
            return

        self.health_bar.world_scale_x = self.hp / self.max_hp * 1.5
        self.health_bar.alpha = 1


# 创建敌人
enemies = [Enemy(x=x*4) for x in range(4)]


# ==================== 第三步：更新主循环 ====================

def update():
    # 使用实体子弹系统
    if held_keys['left mouse']:
        gun.shoot()

    # 更新相机控制器
    camera_controller.update()


# ==================== 第四步：更新输入处理 ====================

def input(key):
    # V 键切换 FPS/TPS 视角
    if key == 'v':
        camera_controller.toggle_mode()

    # Tab 键切换编辑器模式
    if key == 'tab':
        editor_camera.enabled = not editor_camera.enabled
        player.visible_self = editor_camera.enabled
        player.cursor.enabled = not editor_camera.enabled
        gun.enabled = not editor_camera.enabled
        mouse.locked = not editor_camera.enabled
        editor_camera.position = player.position
        application.paused = editor_camera.enabled


# ==================== 第五步：更新 UI ====================

# 操作提示
controls_text = Text(
    text='Controls:\n\n'
         'WASD - Move\n'
         'Space - Jump\n'
         'Mouse - Look around\n'
         'Left Click - Shoot\n'
         'V - Toggle FPS/TPS View\n'
         'Tab - Toggle Editor Mode',
    position=(-.85, .45),
    parent=camera.ui,
    color=color.white,
    background=True
)

# 当前视角指示
view_mode_text = Text(
    text='View: FPS',
    position=(0, .45),
    parent=camera.ui,
    color=color.yellow,
    origin=(0, 0)
)


# ==================== 设置光照和天空 ====================

sun = DirectionalLight()
sun.look_at(Vec3(1, -1, -1))
Sky()


# 启动应用
app.run()
