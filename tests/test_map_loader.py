"""map_loader 单元测试（Layer 1 — 纯逻辑）"""
import json
import os
import pytest
from arena.map_loader import load_map, list_maps, load_default_map


class TestLoadMap:
    """地图文件加载测试"""

    def test_load_valid_map(self, tmp_path, monkeypatch):
        """加载有效地图文件"""
        map_data = {"name": "Test Map", "version": 1, "ground": {"size": 48}, "cover": []}
        map_file = tmp_path / "test_map.json"
        map_file.write_text(json.dumps(map_data), encoding='utf-8')

        monkeypatch.setattr("arena.map_loader._MAPS_DIR", str(tmp_path))
        data = load_map("test_map")
        assert data["name"] == "Test Map"
        assert data["ground"]["size"] == 48

    def test_missing_map_raises(self, tmp_path, monkeypatch):
        """不存在的地图文件抛出 FileNotFoundError"""
        monkeypatch.setattr("arena.map_loader._MAPS_DIR", str(tmp_path))
        with pytest.raises(FileNotFoundError):
            load_map("nonexistent")

    def test_invalid_json_raises(self, tmp_path, monkeypatch):
        """无效 JSON 文件抛出 JSONDecodeError"""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{invalid json}", encoding='utf-8')

        monkeypatch.setattr("arena.map_loader._MAPS_DIR", str(tmp_path))
        with pytest.raises(json.JSONDecodeError):
            load_map("bad")

    def test_load_actual_arena_classic(self):
        """加载实际的 arena_classic.json"""
        data = load_map("arena_classic")
        assert data["name"] == "Arena Classic"
        assert len(data["cover"]) == 12

    def test_load_default_map(self):
        """加载默认地图（arena_classic）"""
        data = load_default_map()
        assert "ground" in data
        assert "red_base" in data
        assert "blue_base" in data
        assert "cover" in data
        assert "boundary" in data

    def test_missing_default_map_raises(self, tmp_path, monkeypatch):
        """默认地图不存在时抛出 FileNotFoundError"""
        monkeypatch.setattr("arena.map_loader._MAPS_DIR", str(tmp_path))
        with pytest.raises(FileNotFoundError):
            load_default_map()


class TestListMaps:
    """地图列表测试"""

    def test_lists_json_files(self, tmp_path, monkeypatch):
        """列出所有 .json 地图文件"""
        (tmp_path / "map_a.json").write_text("{}", encoding='utf-8')
        (tmp_path / "map_b.json").write_text("{}", encoding='utf-8')
        (tmp_path / "readme.txt").write_text("")

        monkeypatch.setattr("arena.map_loader._MAPS_DIR", str(tmp_path))
        maps = list_maps()
        assert "map_a" in maps
        assert "map_b" in maps
        assert "readme" not in maps

    def test_sorted_alphabetically(self, tmp_path, monkeypatch):
        """按字母排序"""
        (tmp_path / "zebra.json").write_text("{}", encoding='utf-8')
        (tmp_path / "alpha.json").write_text("{}", encoding='utf-8')

        monkeypatch.setattr("arena.map_loader._MAPS_DIR", str(tmp_path))
        maps = list_maps()
        assert maps == ["alpha", "zebra"]

    def test_empty_dir(self, tmp_path, monkeypatch):
        """空目录返回空列表"""
        monkeypatch.setattr("arena.map_loader._MAPS_DIR", str(tmp_path))
        maps = list_maps()
        assert maps == []

    def test_nonexistent_dir(self, monkeypatch):
        """不存在的目录返回空列表"""
        monkeypatch.setattr("arena.map_loader._MAPS_DIR", "/nonexistent/path")
        maps = list_maps()
        assert maps == []
