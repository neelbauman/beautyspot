# tests/test_cachekey.py

import pytest
import numpy as np
from dataclasses import dataclass
from beautyspot.cachekey import KeyGen, canonicalize


# --- Helper Classes for Testing ---

class SimpleObj:
    """__dict__ を持つ標準的なクラス"""
    def __init__(self, x, y):
        self.x = x
        self.y = y

class SlotsObj:
    """__slots__ を持つメモリ最適化クラス"""
    __slots__ = ['a', 'b']
    def __init__(self, a, b):
        self.a = a
        self.b = b

@dataclass
class DataClassObj:
    """Python標準のDataclass"""
    name: str
    value: int


# --- Test Cases ---

def test_stable_hash_dict_order():
    """辞書のキー順序が異なっても同じハッシュになるか"""
    d1 = {"a": 1, "b": 2, "c": {"x": 10, "y": 20}}
    d2 = {"c": {"y": 20, "x": 10}, "b": 2, "a": 1}
    
    # 正規化構造の一致確認
    assert canonicalize(d1) == canonicalize(d2)
    # ハッシュの一致確認
    assert KeyGen.default((d1,), {}) == KeyGen.default((d2,), {})


def test_stable_hash_set_order():
    """集合の順序が異なっても同じハッシュになるか"""
    s1 = {3, 1, 2}
    s2 = {1, 2, 3}
    assert KeyGen.default((s1,), {}) == KeyGen.default((s2,), {})


def test_custom_object_stability():
    """カスタムオブジェクト（__dict__）の属性定義順序に依存しないか"""
    o1 = SimpleObj(10, 20)
    o2 = SimpleObj(10, 20)
    
    # 強制的に__dict__の順序を変える（Python3.6+では挿入順維持のため）
    o2.__dict__ = {}
    o2.y = 20  # yを先に定義
    o2.x = 10
    
    # メモリアドレスが異なり、内部辞書の順序が違っても、内容は同じ
    assert KeyGen.default((o1,), {}) == KeyGen.default((o2,), {})
    
    # 値が違えば別ハッシュ
    o3 = SimpleObj(10, 21)
    assert KeyGen.default((o1,), {}) != KeyGen.default((o3,), {})


def test_slots_object_stability():
    """__slots__ を持つオブジェクトが正しく正規化されるか"""
    s1 = SlotsObj(1, 2)
    s2 = SlotsObj(1, 2)
    
    # Slotsは__dict__を持たないが、正しく値を拾えるか
    assert KeyGen.default((s1,), {}) == KeyGen.default((s2,), {})
    
    s3 = SlotsObj(1, 99)
    assert KeyGen.default((s1,), {}) != KeyGen.default((s3,), {})


def test_dataclass_stability():
    """Dataclassが正しく正規化されるか"""
    d1 = DataClassObj("test", 100)
    d2 = DataClassObj("test", 100)
    assert KeyGen.default((d1,), {}) == KeyGen.default((d2,), {})


def test_nested_complex_structure():
    """深くネストした複合構造の安定性"""
    # List -> Dict -> Set -> CustomObj
    complex1 = [
        {"ids": {1, 2, 3}, "meta": SimpleObj("foo", "bar")},
        np.array([1, 2, 3])
    ]
    
    complex2 = [
        # Set順序変更, CustomObjは同じ値
        {"meta": SimpleObj("foo", "bar"), "ids": {3, 1, 2}},
        np.array([1, 2, 3])
    ]
    
    assert KeyGen.default((complex1,), {}) == KeyGen.default((complex2,), {})


def test_numpy_collision_avoidance():
    """
    str()表現が同じになるような巨大なNumpy配列でも、
    正しく別のハッシュが生成されるか検証する（tobytes()の効果確認）。
    """
    size = 2000  # str() の省略閾値を超えるサイズ
    arr1 = np.zeros(size, dtype=int)
    arr2 = np.zeros(size, dtype=int)
    arr2[1000] = 999  # 真ん中を変更

    # 前提: 文字列化すると同じになってしまう
    if str(arr1) == str(arr2):
        pass # Expected behavior for large arrays

    hash1 = KeyGen.default((arr1,), {})
    hash2 = KeyGen.default((arr2,), {})
    
    assert hash1 != hash2, "Collision! Large numpy arrays must not hash to same key."


def test_numpy_structure():
    """正規化されたNumpy配列が期待通りのタプル構造になっているか"""
    arr = np.array([1, 2], dtype=np.uint8)
    normalized = canonicalize(arr)
    
    # ("__numpy__", shape, dtype, bytes)
    assert isinstance(normalized, tuple)
    assert normalized[0] == "__numpy__"
    assert normalized[1] == (2,)
    assert normalized[3] == b"\x01\x02"


def test_mixed_types_sorting():
    """異なる型が混在する辞書キーでもソートで落ちないか"""
    # int, str, float が混在
    d = {1: "one", "2": "two", 3.0: "three", None: "none"}
    
    # エラーにならず実行できること
    try:
        key = KeyGen.default((d,), {})
        assert isinstance(key, str)
    except TypeError:
        pytest.fail("KeyGen raised TypeError on mixed type sorting.")

def test_circular_reference_fallback():
    """循環参照がある場合もクラッシュせず、フォールバックで動作するか"""
    d = {}
    d["self"] = d  # 循環参照
    
    # RecursionErrorにならずにハッシュが返ること
    # (実装上は str(d) にフォールバックするはず)
    key = KeyGen.default((d,), {})
    assert isinstance(key, str)
    assert len(key) == 64  # SHA-256 hex digest length

