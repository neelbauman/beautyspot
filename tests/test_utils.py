# tests/test_utils.py

import pytest
import time
from beautyspot.utils import KeyGen

class SimpleObj:
    def __init__(self, x):
        self.x = x

def test_stable_hash_types():
    """順序を持たない型(Set, Dict)が安定してハッシュ化されるか"""
    # Set: 定義順序が違っても同じハッシュになるべき
    args1 = ({3, 1, 2},)
    args2 = ({1, 2, 3},)
    assert KeyGen.default(args1, {}) == KeyGen.default(args2, {})

    # Dict: キー順序が違っても同じハッシュになるべき
    d1 = {"a": 1, "b": 2}
    d2 = {"b": 2, "a": 1}
    assert KeyGen.default((d1,), {}) == KeyGen.default((d2,), {})

    # Bytes
    assert KeyGen.default((b"hello",), {}) == KeyGen.default((b"hello",), {})

def test_custom_object_hash():
    """カスタムオブジェクトの中身が同じなら同じハッシュになるか"""
    o1 = SimpleObj(10)
    o2 = SimpleObj(10)
    # メモリアドレスが違っても、中身(x=10)が同じなら同一視したい
    assert KeyGen.default((o1,), {}) == KeyGen.default((o2,), {})

    # 中身が違えば別のハッシュ
    o3 = SimpleObj(11)
    assert KeyGen.default((o1,), {}) != KeyGen.default((o3,), {})

def test_file_hash(tmp_path):
    """ファイルパスと中身のハッシュ生成"""
    f = tmp_path / "test.txt"
    f.write_text("content_A")
    
    # 1. Path Stat Hash
    h1 = KeyGen.from_path_stat(str(f))
    
    # 2. Content Hash
    h2 = KeyGen.from_file_content(str(f))
    
    # ファイル更新 (mtimeを変えるため少し待つか、os.utimeを使う手もあるが簡易的に)
    time.sleep(0.01)
    f.write_text("content_B")
    
    # 内容が変わればハッシュも変わるべき
    assert KeyGen.from_path_stat(str(f)) != h1
    assert KeyGen.from_file_content(str(f)) != h2

def test_missing_file():
    """存在しないファイルの扱い"""
    # エラーにならず、識別子(MISSING_...)が返ること
    assert "MISSING" in KeyGen.from_path_stat("nonexistent_file")
    assert "MISSING" in KeyGen.from_file_content("nonexistent_file")

