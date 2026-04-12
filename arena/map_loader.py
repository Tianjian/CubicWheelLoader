"""地图加载器：从 JSON 文件加载地图数据，提供默认值和地图列表。"""

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
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


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


def _default_map():
    """返回内置默认地图数据（无文件依赖，用于 fallback）。

    Returns:
        dict: 默认地图数据
    """
    return {
        "name": "Arena Classic",
        "version": 1,
        "ground": {
            "size": 64,
            "texture": "grass",
            "texture_scale": [8, 8]
        },
        "red_base": {
            "position": [0, 0, -24],
            "radius": 6,
            "pillars": [[-2, -2], [2, -2], [-2, 2], [2, 2]],
            "pillar_height": 5
        },
        "blue_base": {
            "position": [0, 0, 24],
            "radius": 6,
            "pillars": [[-2, -2], [2, -2], [-2, 2], [2, 2]],
            "pillar_height": 5
        },
        "cover": [
            {"position": [-12, 0, -10], "scale": [2, 2.5, 1]},
            {"position": [-12, 0, 10], "scale": [2, 2.5, 1]},
            {"position": [12, 0, -10], "scale": [2, 2.5, 1]},
            {"position": [12, 0, 10], "scale": [2, 2.5, 1]},
            {"position": [-5, 0, 0], "scale": [2, 2.5, 1]},
            {"position": [5, 0, 0], "scale": [2, 2.5, 1]},
            {"position": [-8, 0, -5], "scale": [2, 2.5, 1]},
            {"position": [8, 0, 5], "scale": [2, 2.5, 1]},
            {"position": [-6, 0, -14], "scale": [2, 2.5, 1]},
            {"position": [6, 0, -14], "scale": [2, 2.5, 1]},
            {"position": [-6, 0, 14], "scale": [2, 2.5, 1]},
            {"position": [6, 0, 14], "scale": [2, 2.5, 1]}
        ],
        "boundary": {
            "thickness": 1,
            "height": 5
        }
    }
