# FPS Demo 实体子弹升级设计文档

## 1. 升级目标

将当前的射线检测射击系统升级为实体子弹系统，使子弹具有物理飞行轨迹，增加游戏真实感和策略性。

### 当前实现（射线检测）
```
开火 → 瞬间检测鼠标指向的实体 → 立即判定命中 → 扣血
```

### 升级后实现（实体子弹）
```
开火 → 创建子弹实体 → 子弹飞行 → 碰撞检测 → 判定命中 → 扣血 → 子弹销毁
```

## 2. slow_motion.py 样例分析

### 核心实现思路

```python
def input(key):
    if key == 'left mouse down' and player.gun:
        gun.blink(color.orange)
        bullet = Entity(
            parent=gun,           # 先作为枪的子对象
            model='cube',
            scale=.1,
            color=color.black
        )
        bullet.world_parent = scene  # 转换为世界坐标
        bullet.animate_position(     # 动画移动
            bullet.position + (bullet.forward * 50),
            curve=curve.linear,
            duration=1
        )
        destroy(bullet, delay=1)    # 延迟销毁
```

### 关键技术点

1. **父子关系切换**
   - `parent=gun` - 初始作为枪的子对象，位置相对枪口
   - `world_parent = scene` - 转换为世界坐标，脱离枪的父子关系

2. **动画飞行**
   - `animate_position()` - 使用动画系统移动子弹
   - `curve.linear` - 线性轨迹（匀速飞行）
   - `duration` - 飞行持续时间

3. **自动销毁**
   - `destroy(bullet, delay=1)` - 延迟销毁避免内存泄漏

## 3. 升级设计方案

### 3.1 子弹类设计

```python
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
        
        # 子弹轨迹效果
        self.trail = Entity(
            parent=self,
            model='quad',
            color=color.orange,
            scale=(0.05, 1, 0.05),
            z=-0.5
        )
    
    def update(self):
        """每帧更新子弹位置"""
        # 检查是否超出射程
        if distance(self.position, self.start_position) > self.max_distance:
            destroy(self)
            return
        
        # 移动子弹
        move_step = self.direction * self.speed * time.dt
        hit_info = raycast(
            self.position,
            self.direction,
            distance=self.speed * time.dt * 1.5,
            ignore=(self,)
        )
        
        # 碰撞检测
        if hit_info.hit:
            if hasattr(hit_info.entity, 'hp'):
                # 击中敌人
                hit_info.entity.hp -= self.damage
                hit_info.entity.blink(color.red)
            
            # 击中效果
            self.on_hit(hit_info)
            destroy(self)
            return
        
        # 继续飞行
        self.position += move_step
    
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
            particle.animate_position(
                position + (normal + Vec3(random.uniform(-1,1), random.uniform(-1,1), random.uniform(-1,1))).normalized() * 0.5,
                duration=0.3
            )
            particle.animate_scale(0, duration=0.3)
            destroy(particle, delay=0.3)
    
    def play_impact_sound(self):
        """播放击中音效"""
        from ursina.prefabs.ursfx import ursfx
        ursfx(
            [(0.0, 0.0), (0.05, 0.5), (0.1, 0.2), (0.2, 0.0)],
            volume=0.3,
            wave='noise',
            pitch=random.uniform(-8, -6),
            speed=2.0
        )
```

### 3.2 武器系统升级

```python
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
        muzzle_position = self.world_position + (self.world_forward * 0.5)
        
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
```

### 3.3 游戏主循环修改

```python
def update():
    # 修改前：直接射线检测
    # if held_keys['left mouse']:
    #     shoot()

    # 修改后：创建实体子弹
    if held_keys['left mouse']:
        gun.shoot()
```

### 3.4 敌人系统优化

敌人系统基本无需修改，因为 Enemy 类已经有 `hp` 属性和相应的处理逻辑。

## 4. 实现步骤

### 第一步：创建 Bullet 类
- [ ] 定义子弹基本属性（模型、大小、颜色、碰撞器）
- [ ] 实现飞行逻辑（每帧移动）
- [ ] 实现碰撞检测（射线检测前方）
- [ ] 实现击中效果（粒子、音效）
- [ ] 实现自动销毁（射程限制）

### 第二步：创建 Weapon 类
- [ ] 重构现有枪支逻辑为 Weapon 类
- [ ] 添加可配置的武器属性（伤害、速度、射速）
- [ ] 实现开火方法（创建子弹）
- [ ] 保留枪口闪光和音效

### 第三步：修改主循环
- [ ] 替换 shoot() 函数调用为 Weapon.shoot()
- [ ] 移除直接的射线检测代码

### 第四步：测试和优化
- [ ] 测试子弹飞行轨迹
- [ ] 测试碰撞检测准确性
- [ ] 优化子弹性能（批量销毁、对象池）
- [ ] 调整游戏平衡（伤害、射速、子弹速度）

## 5. 性能优化方案

### 5.1 子弹对象池

```python
class BulletPool:
    """子弹对象池"""
    def __init__(self, max_bullets=100):
        self.max_bullets = max_bullets
        self.active_bullets = []
        self.inactive_bullets = []
        
        # 预创建子弹
        for _ in range(max_bullets):
            bullet = Bullet(enabled=False)
            self.inactive_bullets.append(bullet)
    
    def get_bullet(self, start_position, direction, damage, speed):
        """获取子弹"""
        if len(self.inactive_bullets) == 0:
            # 对象池耗尽，创建新子弹
            return Bullet(start_position, direction, damage, speed)
        
        bullet = self.inactive_bullets.pop()
        bullet.enabled = True
        bullet.position = start_position
        bullet.direction = direction
        bullet.damage = damage
        bullet.speed = speed
        bullet.start_position = start_position
        self.active_bullets.append(bullet)
        return bullet
    
    def return_bullet(self, bullet):
        """回收子弹"""
        bullet.enabled = False
        self.active_bullets.remove(bullet)
        self.inactive_bullets.append(bullet)
```

### 5.2 批量更新优化

```python
class BulletManager(Entity):
    """子弹管理器"""
    def __init__(self):
        super().__init__()
        self.bullets = []
    
    def update(self):
        """批量更新所有子弹"""
        # 使用倒序遍历，安全删除
        for i in range(len(self.bullets) - 1, -1, -1):
            bullet = self.bullets[i]
            if not bullet.enabled:
                self.bullets.pop(i)
```

### 5.3 视觉效果优化

```python
# 使用 LOD（距离层次细节）
if distance(bullet.position, camera.position) > 20:
    bullet.model = 'sphere_low_poly'  # 远距离使用低模
else:
    bullet.model = 'sphere'           # 近距离使用高模

# 使用实例化渲染（大量子弹时）
# 将所有子弹合并为一个网格
```

## 6. 扩展功能

### 6.1 弹道下坠

```python
class Bullet(Entity):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.velocity = direction * speed
        self.gravity = -9.81  # 重力
    
    def update(self):
        # 应用重力
        self.velocity.y += self.gravity * time.dt
        
        # 移动
        self.position += self.velocity * time.dt
```

### 6.2 子弹穿透

```python
class Bullet(Entity):
    def __init__(self, penetration_power=1, **kwargs):
        super().__init__(**kwargs)
        self.penetration_power = penetration_power  # 穿透力
        self.penetration_count = 0
    
    def on_hit(self, hit_info):
        if hasattr(hit_info.entity, 'hp'):
            hit_info.entity.hp -= self.damage
            self.penetration_count += 1
            
            # 还可以穿透
            if self.penetration_count < self.penetration_power:
                self.damage *= 0.7  # 每穿透一次伤害降低
            else:
                destroy(self)
        else:
            destroy(self)  # 击中墙壁直接销毁
```

### 6.3 多种武器类型

```python
class Pistol(Weapon):
    def __init__(self):
        super().__init__(
            bullet_damage=10,
            bullet_speed=50,
            fire_rate=0.3
        )

class MachineGun(Weapon):
    def __init__(self):
        super().__init__(
            bullet_damage=5,
            bullet_speed=60,
            fire_rate=0.08
        )

class Shotgun(Weapon):
    def __init__(self):
        super().__init__(
            bullet_damage=8,
            bullet_speed=40,
            fire_rate=0.8
        )
    
    def shoot(self):
        # 散弹枪发射多发子弹
        for _ in range(5):
            spread = Vec3(
                random.uniform(-0.1, 0.1),
                random.uniform(-0.1, 0.1),
                random.uniform(-0.1, 0.1)
            )
            direction = camera.forward + spread
            super().shoot(direction)
```

### 6.4 子弹时间效果

```python
class Bullet(Entity):
    def update(self):
        # 根据 application.time_scale 调整子弹速度
        adjusted_speed = self.speed * application.time_scale
        move_step = self.direction * adjusted_speed * time.dt
        self.position += move_step
```

### 6.5 子弹轨迹可视化

```python
class Bullet(Entity):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.trail_points = []
        self.max_trail_length = 10
    
    def update(self):
        # 记录轨迹点
        self.trail_points.append(Vec3(self.position))
        if len(self.trail_points) > self.max_trail_length:
            self.trail_points.pop(0)
        
        # 绘制轨迹
        self.draw_trail()
    
    def draw_trail(self):
        # 使用 Line 模型绘制轨迹
        pass
```

## 7. 游戏平衡性调整

### 7.1 武器参数调优

| 武器类型 | 伤害 | 射速 | 子弹速度 | 弹夹容量 | 换弹时间 |
|---------|------|------|---------|---------|---------|
| 手枪 | 10 | 0.3s | 50 | 12 | 1.5s |
| 突击步枪 | 8 | 0.1s | 60 | 30 | 2.0s |
| 霰弹枪 | 6*5 | 0.8s | 40 | 8 | 2.5s |
| 狙击枪 | 50 | 1.0s | 100 | 5 | 3.0s |

### 7.2 敌人平衡

```python
class Enemy(Entity):
    # 普通敌人
    hp = 100
    speed = 5
    damage = 10
    
    # 精英敌人
    hp = 200
    speed = 7
    damage = 20
    
    # Boss 敌人
    hp = 1000
    speed = 3
    damage = 50
```

### 7.3 难度曲线

```python
class GameDifficulty:
    wave = 1
    
    @staticmethod
    def get_enemy_count():
        return 5 + GameDifficulty.wave * 2
    
    @staticmethod
    def get_enemy_hp():
        return 100 + GameDifficulty.wave * 20
    
    @staticmethod
    def get_spawn_rate():
        return max(1.0, 3.0 - GameDifficulty.wave * 0.2)
```

## 8. 测试计划

### 8.1 单元测试

```python
def test_bullet_creation():
    bullet = Bullet(Vec3(0,0,0), Vec3(0,0,1), damage=10, speed=50)
    assert bullet.damage == 10
    assert bullet.speed == 50
    assert bullet.position == Vec3(0,0,0)

def test_bullet_movement():
    bullet = Bullet(Vec3(0,0,0), Vec3(0,0,1), speed=50)
    bullet.update()
    # 子弹应该向前移动
    assert bullet.z > 0

def test_bullet_collision():
    enemy = Enemy(position=Vec3(0,0,10))
    bullet = Bullet(Vec3(0,0,0), Vec3(0,0,1))
    bullet.update()
    # 击中敌人后子弹应该销毁
    assert not bullet.enabled
    assert enemy.hp < 100
```

### 8.2 集成测试

- [ ] 测试多颗子弹同时飞行
- [ ] 测试子弹击中多个敌人
- [ ] 测试子弹击中墙壁
- [ ] 测试子弹超出射程销毁
- [ ] 测试性能（FPS 保持在 60+）

## 9. 已知问题和解决方案

### 问题1：大量子弹导致的性能下降
**解决方案**：
- 使用对象池减少内存分配
- 限制同屏最大子弹数量
- 使用实例化渲染

### 问题2：子弹穿透敌人
**解决方案**：
- 提高射线检测频率
- 增加子弹碰撞体积
- 使用多层碰撞检测

### 问题3：子弹轨迹不精确
**解决方案**：
- 使用更小的时间步长
- 使用插值平滑轨迹
- 提高射线检测精度

## 10. 总结

本升级设计将 fps_demo 从简单的射线检测射击升级为完整的实体子弹系统，核心改进包括：

1. **真实性提升** - 子弹具有飞行时间和轨迹
2. **视觉效果增强** - 子弹模型、轨迹、击中效果
3. **游戏性提升** - 预判、掩体、弹道下坠等策略
4. **可扩展性** - 易于添加新武器类型和子弹效果
5. **性能优化** - 对象池、批量更新、视觉优化

升级后，玩家需要预判敌人移动、考虑子弹飞行时间，增加了游戏的技巧性和策略性，为后续 CubicWheelLoader 项目积累宝贵的游戏开发经验。
