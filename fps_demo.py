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

# 武器模型
gun = Entity(model='cube', parent=camera, position=(.5,-.25,.25), scale=(.3,.2,1), origin_z=-.5, color=color.red, on_cooldown=False)
gun.muzzle_flash = Entity(parent=gun, z=1, world_scale=.5, model='quad', color=color.yellow, enabled=False)

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

def update():
    # 按住左键射击
    if held_keys['left mouse']:
        shoot()

def shoot():
    """射击函数"""
    if not gun.on_cooldown:
        gun.on_cooldown = True
        gun.muzzle_flash.enabled = True

        # 播放射击音效
        from ursina.prefabs.ursfx import ursfx
        ursfx([(0.0, 0.0), (0.1, 0.9), (0.15, 0.75), (0.3, 0.14), (0.6, 0.0)],
              volume=0.5, wave='noise', pitch=random.uniform(-13,-12), pitch_change=-12, speed=3.0)

        # 闪光效果和冷却
        invoke(gun.muzzle_flash.disable, delay=.05)
        invoke(setattr, gun, 'on_cooldown', False, delay=.15)

        # 检测是否击中敌人
        if mouse.hovered_entity and hasattr(mouse.hovered_entity, 'hp'):
            mouse.hovered_entity.blink(color.red)
            mouse.hovered_entity.hp -= 10


class Enemy(Entity):
    """敌人类"""
    def __init__(self, **kwargs):
        super().__init__(parent=shootables_parent, model='cube', scale_y=2, origin_y=-.5, color=color.light_gray, collider='box', **kwargs)
        self.health_bar = Entity(parent=self, y=1.2, model='cube', color=color.red, world_scale=(1.5,.1,.1))
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

# 设置光照和天空
sun = DirectionalLight()
sun.look_at(Vec3(1,-1,-1))
Sky()

# 启动应用
app.run()
