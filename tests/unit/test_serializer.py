# tests/test_serializer.py

import pytest
from pydantic import BaseModel
from beautyspot.serializer import MsgpackSerializer, SerializationError


# --- テスト用の Pydantic モデル ---
class User(BaseModel):
    name: str
    age: int


class Group(BaseModel):
    title: str
    leader: User
    members: list[User]


# --- テストケース ---


def test_pydantic_v2_dict_flow():
    """
    推奨パターン: Encoderがdictを返し、Decoderがdictを受け取る。
    Serializerが自動的にpack/unpackを行うことを検証する。
    """
    serializer = MsgpackSerializer()

    # 登録: dictを返すだけでよい
    serializer.register(
        User,
        code=10,
        encoder=lambda obj: obj.model_dump(),
        decoder=lambda data: User.model_validate(data),
    )

    original = User(name="Alice", age=30)

    # シリアライズ (User -> dict -> bytes -> ExtType)
    packed = serializer.dumps(original)

    # デシリアライズ (ExtType -> bytes -> dict -> User)
    restored = serializer.loads(packed)

    assert restored == original
    assert isinstance(restored, User)


def test_pydantic_v2_json_str_flow():
    """
    バリエーション: EncoderがJSON文字列(str)を返す場合。
    Serializerがstrも自動的にpack(bytes化)して処理できることを検証する。
    """
    serializer = MsgpackSerializer()

    serializer.register(
        User,
        code=10,
        # Encoder: JSON文字列を返す
        encoder=lambda obj: obj.model_dump_json(),
        # Decoder: 文字列を受け取ってパースする
        decoder=lambda data: User.model_validate_json(data),
    )

    original = User(name="Bob", age=25)

    packed = serializer.dumps(original)
    restored = serializer.loads(packed)

    assert restored == original
    assert restored.name == "Bob"


def test_nested_custom_types():
    """
    ネストされたカスタム型（Groupの中にUser）が正しく処理されるか検証する。
    再帰的な _default_packer の呼び出しを確認。
    """
    serializer = MsgpackSerializer()

    # Userの登録
    serializer.register(
        User,
        code=10,
        encoder=lambda u: u.model_dump(mode="json"),
        decoder=lambda d: User.model_validate(d),
    )

    # Groupの登録
    serializer.register(
        Group,
        code=11,
        encoder=lambda g: g.model_dump(mode="json"),
        decoder=lambda d: Group.model_validate(d),
    )

    original = Group(
        title="Engineering",
        leader=User(name="Charlie", age=40),
        members=[User(name="Dave", age=22), User(name="Eve", age=28)],
    )

    packed = serializer.dumps(original)
    restored = serializer.loads(packed)

    assert restored == original
    assert isinstance(restored.leader, User)
    assert restored.members[0].name == "Dave"


def test_guardrail_invalid_return_type():
    """
    Encoderがmsgpackでシリアライズ不可能なオブジェクトを返した場合、
    親切なエラーメッセージが出るか検証する。
    """
    serializer = MsgpackSerializer()

    class Unserializable:
        pass

    serializer.register(
        User,
        code=10,
        # Encoderが関数オブジェクト（シリアライズ不可）を返してしまうミス
        encoder=lambda u: lambda x: x,
        decoder=lambda d: User(name="error", age=0),
    )

    obj = User(name="Fail", age=99)

    with pytest.raises(SerializationError) as exc_info:
        serializer.dumps(obj)

    error_msg = str(exc_info.value)
    assert (
        "Encoder for 'User' returned a value that msgpack cannot serialize" in error_msg
    )
    assert "Hint: Ensure your encoder returns a primitive type" in error_msg


def test_decoder_failure_raises_critical_error():
    """
    Decoderが失敗した場合、SerializationErrorとして再送出されるか検証する。
    """
    serializer = MsgpackSerializer()

    serializer.register(
        User,
        code=10,
        encoder=lambda u: {"name": u.name, "age": u.age},
        # 必ず失敗するデコーダ
        decoder=lambda d: (_ for _ in ()).throw(ValueError("Invalid data format")),
    )

    packed = serializer.dumps(User(name="Ghost", age=0))

    with pytest.raises(SerializationError) as exc_info:
        serializer.loads(packed)

    assert "CRITICAL: Failed to decode custom type" in str(exc_info.value)


def test_raw_bytes_support():
    """
    Encoderがbytesを返した場合でも動作することを検証する。
    （Nested Protocolにより、bytesもさらにpackされるが、動作としては正しいはず）
    """
    serializer = MsgpackSerializer()

    serializer.register(
        User,
        code=10,
        encoder=lambda u: u.name.encode("utf-8"),
        decoder=lambda b: User(name=b.decode("utf-8"), age=0),
    )

    original = User(name="BytesUser", age=0)
    restored = serializer.loads(serializer.dumps(original))

    assert restored.name == "BytesUser"
