# tests/unit/test_serializer.py

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


def test_serializer_subclass_cache_eviction():
    """
    LRUキャッシュの追い出しテスト:
    動的に生成されたクラスの数が max_cache_size を超えた場合、
    キャッシュサイズが上限値に維持され、古いものが破棄されることを確認する。
    """
    # テスト用に小さな上限値を設定
    serializer = MsgpackSerializer(max_cache_size=5)

    class BaseType:
        pass

    # BaseType を登録
    serializer.register(BaseType, 10, lambda x: "base_data", lambda x: BaseType())

    subclasses = []
    # 上限(5)を超える10個の動的サブクラスを生成してシリアライズ
    for i in range(10):
        SubClass = type(f"DynamicClass_{i}", (BaseType,), {})
        subclasses.append(SubClass)
        serializer.dumps(SubClass())

    # キャッシュサイズが上限の5に保たれていることを確認
    assert len(serializer._subclass_cache) == 5

    # 最近使われた5つ（インデックス5〜9）がキャッシュに残っていることを確認
    for i in range(5, 10):
        assert subclasses[i] in serializer._subclass_cache

    # 古い5つ（インデックス0〜4）はキャッシュから追い出されていることを確認
    for i in range(5):
        assert subclasses[i] not in serializer._subclass_cache


def test_serializer_subclass_cache_lru_ordering():
    """
    LRUキャッシュの順序更新テスト:
    既存のキャッシュにヒットした際、その要素が最新（末尾）に移動し、
    後続の追い出し処理で保護されることを確認する。
    """
    serializer = MsgpackSerializer(max_cache_size=3)

    class BaseType:
        pass

    serializer.register(BaseType, 10, lambda x: "base_data", lambda x: BaseType())

    SubA = type("SubA", (BaseType,), {})
    SubB = type("SubB", (BaseType,), {})
    SubC = type("SubC", (BaseType,), {})
    SubD = type("SubD", (BaseType,), {})

    # キャッシュを上限まで埋める (順序: A -> B -> C)
    serializer.dumps(SubA())
    serializer.dumps(SubB())
    serializer.dumps(SubC())

    assert list(serializer._subclass_cache.keys()) == [SubA, SubB, SubC]

    # SubA を再度シリアライズ（キャッシュヒット）
    # これにより SubA が最新として末尾に移動するはず (順序: B -> C -> A)
    serializer.dumps(SubA())
    assert list(serializer._subclass_cache.keys()) == [SubB, SubC, SubA]

    # 新しい SubD をシリアライズして上限を超える
    # 最も古い SubB が追い出されるはず (順序: C -> A -> D)
    serializer.dumps(SubD())

    assert list(serializer._subclass_cache.keys()) == [SubC, SubA, SubD]
    assert SubB not in serializer._subclass_cache
    assert SubA in serializer._subclass_cache  # 一度アクセスされたSubAは生き残る


# tests/unit/test_serializer.py に追加


def test_mro_resolution_priority_child_over_parent():
    """
    親クラスと子クラスの両方が登録されている場合、
    子クラスのインスタンスに対しては、より近い「子クラス」のエンコーダーが選ばれることを検証。
    """
    serializer = MsgpackSerializer()

    class Parent:
        pass

    class Child(Parent):
        pass

    # 親と子の両方を登録
    serializer.register(Parent, 10, lambda x: "parent_data", lambda x: "parent_decoded")
    serializer.register(Child, 11, lambda x: "child_data", lambda x: "child_decoded")

    # Childインスタンスをシリアライズ
    # MROにより Child -> Parent の順で探索され、Childがヒットするはず
    packed = serializer.dumps(Child())

    # デコード結果がChildのものであることを確認
    assert serializer.loads(packed) == "child_decoded"


def test_mro_resolution_fallback_to_parent():
    """
    子クラス自体は未登録だが、親クラスが登録されている場合、
    親クラスのエンコーダーがフォールバックとして使用されることを検証。
    """
    serializer = MsgpackSerializer()

    class Parent:
        pass

    class Child(Parent):
        pass

    class GrandChild(Child):
        pass

    # 親だけを登録
    serializer.register(Parent, 10, lambda x: "parent_data", lambda x: "parent_decoded")

    # 未登録の孫クラスのインスタンスをシリアライズ
    # MRO: GrandChild -> Child -> Parent (hit!)
    packed = serializer.dumps(GrandChild())

    # 親のエンコーダー/デコーダーが適用されていることを確認
    assert serializer.loads(packed) == "parent_decoded"


def test_mro_resolution_multiple_inheritance():
    """
    多重継承において、Python標準のMRO順序に従って
    最初にマッチした基底クラスが採用されることを検証。
    """
    serializer = MsgpackSerializer()

    class BaseA:
        pass

    class BaseB:
        pass

    class MyClass(BaseA, BaseB):
        pass

    # 両方の基底クラスを登録
    serializer.register(BaseA, 10, lambda x: "A_data", lambda x: "A_decoded")
    serializer.register(BaseB, 11, lambda x: "B_data", lambda x: "B_decoded")

    # MyClass(BaseA, BaseB) なので、MROは [MyClass, BaseA, BaseB, object]
    # 先にヒットする BaseA が使われるはず
    packed = serializer.dumps(MyClass())
    assert serializer.loads(packed) == "A_decoded"


def test_mro_caching_after_resolution():
    """
    一度MROで解決されたサブクラスの結果がキャッシュに格納され、
    二回目以降のアクセスでMROスキャンをスキップできる状態になっているか検証。
    """
    serializer = MsgpackSerializer()

    class Base:
        pass

    class Sub(Base):
        pass

    serializer.register(Base, 10, lambda x: "data", lambda x: "decoded")

    # 初回アクセス（キャッシュにない状態）
    assert Sub not in serializer._subclass_cache
    serializer.dumps(Sub())

    # キャッシュに登録されていることを確認
    assert Sub in serializer._subclass_cache
    assert serializer._subclass_cache[Sub] == (10, serializer._encoders[Base][1])

    # 2回目アクセス：内部でキャッシュから即座に返される（振る舞いとして確認）
    packed = serializer.dumps(Sub())
    assert serializer.loads(packed) == "decoded"


def test_mro_no_match_raises_serialization_error():
    """
    どの親クラスも登録されていない場合、適切に SerializationError を投げることを確認。
    """
    serializer = MsgpackSerializer()

    class CompletelyUnregistered:
        pass

    with pytest.raises(SerializationError) as exc_info:
        serializer.dumps(CompletelyUnregistered())

    assert "is not serializable" in str(exc_info.value)
    assert "CompletelyUnregistered" in str(exc_info.value)
