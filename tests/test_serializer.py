# tests/test_serializer.py

import pytest
import msgpack
from beautyspot.serializer import MsgpackSerializer, SerializationError

class MyCustomData:
    def __init__(self, x, y):
        self.x = x
        self.y = y
    
    def __eq__(self, other):
        return self.x == other.x and self.y == other.y

def test_basic_types():
    """基本型(int, str, list, dict)がシリアライズできるか"""
    s = MsgpackSerializer()
    data = {"a": 1, "b": [2, 3], "c": "hello"}
    
    packed = s.dumps(data)
    assert isinstance(packed, bytes)
    
    unpacked = s.loads(packed)
    assert unpacked == data

def test_unregistered_type_error():
    """未登録の型を渡したときにSerializationErrorが出るか"""
    s = MsgpackSerializer()
    obj = MyCustomData(10, 20)
    
    with pytest.raises(SerializationError) as excinfo:
        s.dumps(obj)
    
    # エラーメッセージに型名が含まれているか確認
    assert "MyCustomData" in str(excinfo.value)
    assert "register_type" in str(excinfo.value)

def test_custom_type_registration():
    """カスタム型を登録してシリアライズ/デシリアライズできるか"""
    s = MsgpackSerializer()
    
    # エンコーダ/デコーダの定義
    def encoder(obj):
        return msgpack.packb([obj.x, obj.y])
        
    def decoder(data):
        x, y = msgpack.unpackb(data)
        return MyCustomData(x, y)
    
    # 登録 (ID=10)
    s.register(MyCustomData, 10, encoder, decoder)
    
    original = MyCustomData(123, 456)
    packed = s.dumps(original)
    
    # 正しくExtTypeとして保存されているか検証(オプション)
    unpacked_raw = msgpack.unpackb(packed, raw=False)
    assert isinstance(unpacked_raw, msgpack.ExtType)
    assert unpacked_raw.code == 10
    
    # 復元
    restored = s.loads(packed)
    assert isinstance(restored, MyCustomData)
    assert restored == original

def test_duplicate_registration_error():
    """同じIDを登録しようとしたらエラーになるか"""
    s = MsgpackSerializer()
    s.register(int, 1, lambda x: b"", lambda x: 0)
    
    with pytest.raises(ValueError):
        s.register(str, 1, lambda x: b"", lambda x: "")

