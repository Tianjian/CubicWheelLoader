"""地图加载器：从 JSON 文件加载地图数据，提供地图列表。"""

import json
import os

# 地图文件目录（项目根目录下的 maps/）
_MAPS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'maps')


def load_map(name):
    """加载指定名称的地图数据。

    Args:
        name: 地图名称（不含 .json 后缀）

    Returns:
        dict: 地图数据字典

    Raises:
        FileNotFoundError: 地图文件不存在
        json.JSONDecodeError: JSON 格式错误
    """
    path = os.path.join(_MAPS_DIR, f'{name}.json')
    if not os.path.exists(path):
        available = list_maps()
        raise FileNotFoundError(
            f'Map file not found: {path}. Available maps: {available}'
        )
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_default_map():
    """加载默认地图（game_settings.json 中 map.default_name 指定的地图）。

    Returns:
        dict: 地图数据字典

    Raises:
        FileNotFoundError: 默认地图文件不存在
    """
    from arena.constants import Config
    return load_map(Config.DEFAULT_MAP_NAME)


def list_maps():
    """列出所有可用地图名称。

    Returns:
        list[str]: 地图名称列表（不含 .json 后缀），按字母排序
    """
    if not os.path.isdir(_MAPS_DIR):
        return []
    return sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(_MAPS_DIR)
        if f.endswith('.json')
    )
