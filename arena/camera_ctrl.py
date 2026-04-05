from ursina import *
from arena.constants import CameraMode, Config


class CameraController(Entity):
    """相机控制器（TPS 为主，适配 Team Arena）"""

    def __init__(self, target_entity):
        super().__init__()
        self.target = target_entity
        self.mode = CameraMode.THIRD_PERSON
        self.is_far = False  # 近/远视角

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
        camera.parent = scene
        camera.position = Vec3(0, 40, 0)
        camera.look_at(Vec3(0, 0, 0))
        camera.animate('fov', 45, duration=0.5)

    def set_third_person(self):
        """恢复 TPS 视角"""
        camera.parent = scene
        target_position = self.target.position + Vec3(0, self.camera_height, -self.camera_distance)
        camera.position = target_position
        look_target = self.target.position + Vec3(0, 1.5, 10)
        camera.look_at(look_target)
        camera.animate('fov', self.fov, duration=0.3)

    def update(self):
        """每帧更新"""
        if self.mode == CameraMode.THIRD_PERSON and self.target:
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
