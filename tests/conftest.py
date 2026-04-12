import pytest


@pytest.fixture(scope='session')
def ursina_app():
    """会话级 Ursina 实例（Layer 2/3 测试需要）"""
    from ursina import Ursina
    app = Ursina(title='Test', borderless=False, development_mode=False)
    yield app
