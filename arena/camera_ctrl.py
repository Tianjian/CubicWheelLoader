from ursina import *
from arena.constants import CameraMode, Config


class CameraController(Entity):
    """相机控制器（TPS 为主，适配 Team Arena）"""

    def __init__(self, target_entity):
        super().__init__()
        self.target = target_entity
        self.mode = CameraMode.THIRD_PERSON
        self.is_far = False  # 近/远视角
        self.active = True    # 是否启用跟随
        self._pending_enable = False  # 延迟启用跟随的标志

        # TPS 参数
        self.camera_distance = Config.CAMERA_DISTANCE
        self.camera_height = Config.CAMERA_HEIGHT
        self.fov = Config.CAMERA_FOV_TPS
        self.transition_speed = Config.CAMERA_TRANSITION_SPEED

    def set_far(self, far):
        """切换近/远视角"""
        self.is_far = far
        if far:
            self.camera_distance = Config.CAMERA_DISTANCE * 2.5
            self.camera_height = Config.CAMERA_HEIGHT * 2.5
            self.fov = Config.CAMERA_FOV_FAR
        else:
            self.camera_distance = Config.CAMERA_DISTANCE
            self.camera_height = Config.CAMERA_HEIGHT
            self.fov = Config.CAMERA_FOV_TPS

    def toggle_distance(self):
        """切换远近视角"""
        self.set_far(not self.is_far)
        camera.animate('fov', self.fov, duration=0.3)

    def set_spectator(self):
        """切换为旁观模式（玩家死亡时）"""
        self.active = False  # 禁用跟随，防止 lerp 抖动
        self._pending_enable = False  # 取消任何待执行的 _enable_follow
        camera.parent = scene
        camera.position = Vec3(0, 40, 0)
        camera.rotation = Vec3(90, 0, 0)  # 俯视：直接设旋转，不用 look_at
        camera.animate('fov', Config.CAMERA_FOV_SPECTATOR, duration=0.5)

    def set_third_person(self):
        """恢复 TPS 视角"""
        camera.parent = scene
        # 一次性设置位置和旋转，避免 lerp 过渡期间 look_at 倾斜
        target_position = self.target.position + Vec3(0, self.camera_height, -self.camera_distance)
        camera.position = target_position
        look_target = self.target.position + Vec3(0, 1.5, 10)
        camera.look_at(look_target)
        camera.animate('fov', self.fov, duration=0.3)
        # 延迟一帧后再启用跟随，确保位置和旋转已稳定
        self._pending_enable = True
        invoke(self._enable_follow, delay=Config.CAMERA_FOLLOW_ENABLE_DELAY)

    def _enable_follow(self):
        """启用相机跟随"""
        if not self._pending_enable:
            return  # 已被 set_spectator 取消
        self._pending_enable = False
        self.active = True

    def update(self):
        """每帧更新"""
        if self.active and self.mode == CameraMode.THIRD_PERSON and self.target:
            self._update_camera()

    def _update_camera(self):
        """更新 TPS 相机位置"""
        target_position = self.target.position + Vec3(0, self.camera_height, -self.camera_distance)
        camera.position = lerp(camera.position, target_position, self.transition_speed * time.dt)

        look_target = self.target.position + Vec3(0, 1.5, 10)
        camera.look_at(look_target)

    def get_shoot_direction(self):
        """获取射击方向"""
        if self.target:
            return self.target.forward.normalized()
        return camera.forward
