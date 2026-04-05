from ursina import *
from ursina.shaders import lit_with_shadows_shader

app = Ursina()

# 设置默认着色器
Entity.default_shader = lit_with_shadows_shader

# 导入游戏模块
from arena.game_manager import game_manager

# 延迟初始化（等 Ursina 引擎就绪后）
def start():
    from arena.character_select import CharacterSelect
    CharacterSelect()

invoke(start, delay=0.1)

# ==================== 编辑器相机（调试用）====================
editor_camera = EditorCamera(enabled=False, ignore_paused=True)

# ==================== 主循环 ====================
def update():
    game_manager.update()

# ==================== 输入处理 ====================
def input(key):
    if key == 'tab':
        editor_camera.enabled = not editor_camera.enabled

# ==================== 运行游戏 ====================
if __name__ == '__main__':
    app.run()
