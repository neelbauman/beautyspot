import pytest
import msgpack
from beautyspot import Spot, SerializationError

# --- Pydantic Availability Check ---
try:
    from pydantic import BaseModel

    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

    class BaseModel:
        pass


@pytest.fixture
def spot():
    # Use in-memory DB for fast testing
    return Spot("test_spot", db=":memory:")


# ----------------------------------------------------------------
# 1. Normal Registration Tests (Happy Path)
# ----------------------------------------------------------------


def test_register_decorator_basic(spot):
    """
    Case 1: Standard registration with explicit encoder/decoder.
    """

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

    # Verify it's actually an ExtType with code 10
    unpacked_raw = msgpack.unpackb(serialized)
    assert unpacked_raw.code == 10

    # [FIXED] Nested Protocol: payload is packed bytes, so we must unpack it to verify content
    # encoder returns b"10,20", library packs it -> bin format wrapping b"10,20"
    payload_content = msgpack.unpackb(unpacked_raw.data)
    assert payload_content == b"10,20"

    # Verify round-trip
    restored = spot.serializer.loads(serialized)
    assert restored == p
    assert isinstance(restored, Point)


def test_register_decorator_late_binding_custom(spot):
    """
    Case 2: Late binding using decoder_factory (without Pydantic).
    This simulates a class method acting as a factory.
    """

    @spot.register(
        code=11,
        encoder=lambda obj: obj.value.encode(),
        decoder_factory=lambda cls: cls.from_bytes,  # Delayed access
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
    assert isinstance(restored, Wrapper)


# ----------------------------------------------------------------
# 2. Pydantic Integration Tests (Real World Use Case)
# ----------------------------------------------------------------


@pytest.mark.skipif(not HAS_PYDANTIC, reason="Pydantic not installed")
def test_register_pydantic_complex(spot):
    """
    Case 3: Complex Pydantic model with nested structures.
    Ensures JSON serialization via Pydantic works seamlessly with Msgpack ExtType.
    """

    @spot.register(
        code=20,
        encoder=lambda obj: obj.model_dump_json().encode(),
        decoder_factory=lambda cls: cls.model_validate_json,
    )
    class Config(BaseModel):
        name: str
        params: dict[str, float]
        tags: list[str] = []

        def __eq__(self, other):
            return self.model_dump() == other.model_dump()

    # 'lr': 0.01 is float, consistent with type definition
    original = Config(
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
    """
    Error Case 1: Neither decoder nor decoder_factory is provided.
    """
    with pytest.raises(
        ValueError, match="Must provide either `decoder` or `decoder_factory`"
    ):

        @spot.register(code=30, encoder=lambda x: b"")
        class Broken:
            pass


def test_register_duplicate_code(spot):
    """
    Error Case 2: Registering the same ExtCode twice should fail.
    This protects against collision bugs.
    """

    @spot.register(code=40, encoder=lambda x: b"", decoder=lambda b: None)
    class A:
        pass

    with pytest.raises(ValueError, match="ExtCode 40 is already registered"):

        @spot.register(code=40, encoder=lambda x: b"", decoder=lambda b: None)
        class B:
            pass


def test_register_factory_returning_none(spot):
    """
    Error Case 3: decoder_factory runs but returns None/Invalid value.
    This ensures the factory logic is correct.
    """
    with pytest.raises(ValueError, match="Decoder resolution failed"):

        @spot.register(code=50, encoder=lambda x: b"", decoder_factory=lambda cls: None)
        class C:
            pass


def test_unregistered_object_error(spot):
    """
    Error Case 4: Serializing an object that hasn't been registered.
    Should raise a clean SerializationError.
    """

    class Stranger:
        pass

    with pytest.raises(SerializationError) as excinfo:
        spot.serializer.dumps(Stranger())

    assert "Object of type 'Stranger' is not serializable" in str(excinfo.value)
    # [FIXED] Updated hint message to match current implementation
    assert "Use `spot.register(...)`" in str(excinfo.value)
