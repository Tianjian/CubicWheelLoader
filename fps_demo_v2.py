from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from ursina.shaders import lit_with_shadows_shader

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


# ==================== 第一步：创建 Bullet 类 ====================

class Bullet(Entity):
    """实体子弹类"""
    def __init__(self, start_position, direction, damage=10, speed=50, **kwargs):
        super().__init__(
            model='sphere',           # 子弹模型
            scale=0.1,                # 子弹大小
            color=color.yellow,        # 子弹颜色
            position=start_position,   # 起始位置
            collider='sphere',         # 碰撞器
            **kwargs
        )

        self.direction = direction    # 飞行方向
        self.damage = damage          # 伤害值
        self.speed = speed            # 飞行速度
        self.max_distance = 100      # 最大射程
        self.start_position = start_position

    def update(self):
        """每帧更新子弹位置"""
        # 检查是否超出射程
        if distance(self.position, self.start_position) > self.max_distance:
            destroy(self)
            return

        # 射线检测前方
        move_distance = self.speed * time.dt * 1.5
        hit_info = raycast(
            self.position,
            self.direction,
            distance=move_distance,
            ignore=(self,)
        )

        # 碰撞检测
        if hit_info.hit:
            if hasattr(hit_info.entity, 'hp'):
                # 击中敌人
                hit_info.entity.hp -= self.damage
                # 使用颜色闪烁代替 blink
                original_color = hit_info.entity.color
                hit_info.entity.color = color.red
                hit_info.entity.animate_color(original_color, duration=0.1)

            # 击中效果
            self.on_hit(hit_info)
            destroy(self)
            return

        # 继续飞行
        self.position += self.direction * self.speed * time.dt

    def on_hit(self, hit_info):
        """击中效果"""
        # 创建击中粒子
        self.create_impact_effect(hit_info.world_point, hit_info.world_normal)

        # 播放击中音效
        self.play_impact_sound()

    def create_impact_effect(self, position, normal):
        """创建击中粒子效果"""
        for _ in range(5):
            particle = Entity(
                model='cube',
                scale=0.05,
                color=color.orange,
                position=position
            )
            # 粒子向四面八方飞溅
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
        """播放击中音效"""
        from ursina.prefabs.ursfx import ursfx
        ursfx(
            [(0.0, 0.0), (0.05, 0.5), (0.1, 0.2), (0.15, 0.1), (0.2, 0.0)],
            volume=0.3,
            wave='noise',
            pitch=random.uniform(-8, -6),
            speed=2.0
        )


# ==================== 第二步：创建 Weapon 类 ====================

class Weapon(Entity):
    """武器类"""
    def __init__(self, bullet_damage=10, bullet_speed=50, fire_rate=0.15, **kwargs):
        super().__init__(**kwargs)

        self.bullet_damage = bullet_damage    # 子弹伤害
        self.bullet_speed = bullet_speed     # 子弹速度
        self.fire_rate = fire_rate           # 射击间隔
        self.on_cooldown = False             # 冷却状态
        self.last_fire_time = 0              # 上次开火时间

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

        # 计算射击方向
        if target_direction is None:
            target_direction = camera.forward

        # 获取枪口世界位置
        # gun 是 camera 的子对象，直接使用枪口的世界坐标
        # 枪口闪光在 z=1 的位置，我们用它来获取枪口位置
        muzzle_position = self.muzzle_flash.world_position

        # 创建子弹
        bullet = Bullet(
            start_position=muzzle_position,
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


# ==================== 第三步：创建武器实例 ====================

gun = Weapon(
    model='cube',
    parent=camera,
    position=(.5, -.25, .25),
    scale=(.3, .2, 1),
    origin_z=-.5,
    color=color.red,
    bullet_damage=10,
    bullet_speed=35,  # 50 * 0.7 = 35，减慢30%
    fire_rate=0.15
)


# ==================== 敌人类 ====================

class Enemy(Entity):
    """敌人类"""
    def __init__(self, **kwargs):
        super().__init__(parent=shootables_parent, model='cube', scale_y=2, origin_y=-.5, color=color.light_gray, collider='box', **kwargs)
        self.health_bar = Entity(parent=self, y=1.2, model='cube', color=color.red, world_scale=(1.5, .1, .1))
        self.max_hp = 100
        self.hp = self.max_hp

    def update(self):
        # 计算到玩家的距离
        dist = distance_xz(player.position, self.position)
        if dist > 40:
            return

        # 血条淡出效果
        self.health_bar.alpha = max(0, self.health_bar.alpha - time.dt)

        # 面向玩家
        self.look_at_2d(player.position, 'y')

        # 检测视线
        hit_info = raycast(self.world_position + Vec3(0,1,0), self.forward, 30, ignore=(self,))

        # 如果看到玩家且距离足够，则移动
        if hit_info.entity == player:
            if dist > 2:
                self.position += self.forward * time.dt * 5

    @property
    def hp(self):
        """获取血量"""
        return self._hp

    @hp.setter
    def hp(self, value):
        """设置血量"""
        self._hp = value
        if value <= 0:
            destroy(self)
            return

        # 更新血条
        self.health_bar.world_scale_x = self.hp / self.max_hp * 1.5
        self.health_bar.alpha = 1


# 创建敌人
enemies = [Enemy(x=x*4) for x in range(4)]


# ==================== 操作提示 UI ====================

controls_text = Text(
    text='Controls:\n\n'
         'WASD - Move\n'
         'Space - Jump\n'
         'Mouse - Look around\n'
         'Left Click - Shoot\n'
         'Tab - Toggle Editor Mode',
    position=(-.85, .45),  # 左上角
    parent=camera.ui,
    color=color.white,
    background=True
)


# ==================== 第四步：修改主循环 ====================

def update():
    # 使用实体子弹系统
    if held_keys['left mouse']:
        gun.shoot()


# ==================== 编辑器模式切换 ====================

def pause_input(key):
    """暂停/编辑模式输入处理"""
    if key == 'tab':
        # 切换编辑/游玩模式
        editor_camera.enabled = not editor_camera.enabled

        player.visible_self = editor_camera.enabled
        player.cursor.enabled = not editor_camera.enabled
        gun.enabled = not editor_camera.enabled
        mouse.locked = not editor_camera.enabled
        editor_camera.position = player.position

        application.paused = editor_camera.enabled

# 暂停处理器
pause_handler = Entity(ignore_paused=True, input=pause_input)


# ==================== 设置光照和天空 ====================

sun = DirectionalLight()
sun.look_at(Vec3(1, -1, -1))
Sky()


# 启动应用
app.run()
