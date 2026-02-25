# tests/unit/test_type_registry.py

import pytest
import msgpack
import io
from beautyspot import Spot
from beautyspot.serializer import SerializationError
from beautyspot.db import SQLiteTaskDB


@pytest.fixture
def spot():
    # Use in-memory DB for fast testing
    return Spot("test_spot", db=SQLiteTaskDB())


# ----------------------------------------------------------------
# 1. Normal Registration Tests (Happy Path)
# ----------------------------------------------------------------


def test_register_decorator_basic(spot):
    """Case 1: Standard registration with explicit encoder/decoder."""

    @spot.register(
        code=10,
        encoder=lambda obj: f"{obj.x},{obj.y}".encode(),
        decoder=lambda data: Point(*map(int, data.decode().split(","))),
    )
    class Point:
        def __init__(self, x, y):
            self.x = x
            self.y = y

        def __eq__(self, other):
            return isinstance(other, Point) and self.x == other.x and self.y == other.y

    p = Point(10, 20)
    serialized = spot.serializer.dumps(p)

    # Check raw structure
    unpacked_raw = msgpack.unpackb(serialized)
    assert unpacked_raw.code == 10

    # Check payload
    payload_content = msgpack.unpackb(unpacked_raw.data)
    assert payload_content == b"10,20"

    # Verify round-trip
    restored = spot.serializer.loads(serialized)
    assert restored == p


def test_register_decorator_late_binding_custom(spot):
    """Case 2: Late binding using decoder_factory (without Pydantic)."""

    @spot.register(
        code=11,
        encoder=lambda obj: obj.value.encode(),
        decoder_factory=lambda cls: cls.from_bytes,
    )
    class Wrapper:
        def __init__(self, value: str):
            self.value = value

        @classmethod
        def from_bytes(cls, data: bytes):
            return cls(value=data.decode())

    w = Wrapper("test")
    restored = spot.serializer.loads(spot.serializer.dumps(w))
    assert restored.value == "test"


# ----------------------------------------------------------------
# 2. Pydantic Integration Tests (Real World Use Case)
# ----------------------------------------------------------------


def test_register_pydantic_complex(spot):
    """
    Case 3: Complex Pydantic model.
    Using importorskip to handle optional dependency cleanly.
    """
    # ここで判定！なければスキップ！ダミーコードは不要！
    pytest.importorskip("pydantic")

    # 型チェックのエラーを消すためだけに ignore を1つ置く (無い環境用)
    from pydantic import BaseModel  # type: ignore

    @spot.register(
        code=20,
        encoder=lambda obj: obj.model_dump_json().encode(),
        decoder_factory=lambda cls: cls.model_validate_json,
    )
    class ConfigModel(BaseModel):
        name: str
        params: dict[str, float]
        tags: list[str] = []

        def __eq__(self, other):
            return self.model_dump() == other.model_dump()

    original = ConfigModel(
        name="experiment-1", params={"lr": 0.01, "epochs": 10.0}, tags=["v1", "beta"]
    )

    data = spot.serializer.dumps(original)
    restored = spot.serializer.loads(data)

    assert restored == original
    assert restored.params["lr"] == 0.01


# ----------------------------------------------------------------
# 3. Error Handling & Edge Cases (Robustness)
# ----------------------------------------------------------------


def test_register_missing_args(spot):
    with pytest.raises(
        ValueError, match="Must provide either `decoder` or `decoder_factory`"
    ):

        @spot.register(code=30, encoder=lambda x: b"")
        class Broken:
            pass


def test_register_duplicate_code(spot):
    @spot.register(code=40, encoder=lambda x: b"", decoder=lambda b: None)
    class A:
        pass

    with pytest.raises(ValueError, match="ExtCode 40 is already registered"):

        @spot.register(code=40, encoder=lambda x: b"", decoder=lambda b: None)
        class B:
            pass


def test_register_factory_returning_none(spot):
    with pytest.raises(ValueError, match="Decoder resolution failed"):

        @spot.register(code=50, encoder=lambda x: b"", decoder_factory=lambda cls: None)
        class C:
            pass


def test_unregistered_object_error(spot):
    class Stranger:
        pass

    with pytest.raises(SerializationError) as excinfo:
        spot.serializer.dumps(Stranger())

    assert "Object of type 'Stranger' is not serializable" in str(excinfo.value)


# ----------------------------------------------------------------
# 4. Binary/NumPy Integration Tests
# ----------------------------------------------------------------


def test_register_numpy_binary(spot):
    """
    Case 5: NumPy array serialization.
    """
    # ここで判定！戻り値としてモジュールを受け取れるので、そのまま使える
    np = pytest.importorskip("numpy")

    def npy_encoder(arr):
        with io.BytesIO() as f:
            np.save(f, arr, allow_pickle=False)
            return f.getvalue()

    def npy_decoder(data):
        with io.BytesIO(data) as f:
            return np.load(f, allow_pickle=False)

    spot.register_type(
        type_class=np.ndarray, code=50, encoder=npy_encoder, decoder=npy_decoder
    )

    original_arr = np.random.rand(3, 3).astype(np.float32)
    packed = spot.serializer.dumps(original_arr)

    # Verify binary structure
    unpacked_ext = msgpack.unpackb(packed)
    actual_binary_payload = msgpack.unpackb(unpacked_ext.data)
    assert isinstance(actual_binary_payload, bytes)
    assert actual_binary_payload.startswith(b"\x93NUMPY")

    restored_arr = spot.serializer.loads(packed)

    assert isinstance(restored_arr, np.ndarray)
    assert np.array_equal(restored_arr, original_arr)
