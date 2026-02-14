import pytest
from pydantic import BaseModel
from beautyspot import Spot

@pytest.fixture
def spot():
    return Spot(name="pydantic_test")

def test_pydantic_direct_decoder(spot):
    """
    Case: Using Pydantic model with direct decoder reference.
    """
    
    # ユーザーさんが仰る通り、この書き方で通るか検証します
    @spot.register(
        code=30,
        encoder=lambda obj: obj.model_dump(),  # dictを返す
        decoder=lambda data: User.model_validate(data) # ここで User を参照
    )
    class User(BaseModel):
        id: int
        name: str

    user = User(id=1, name="Alice")
    
    # シリアライズ
    packed = spot.serializer.dumps(user)
    # デシリアライズ
    restored = spot.serializer.loads(packed)

    assert isinstance(restored, User)
    assert restored.id == 1
    assert restored.name == "Alice"

def test_pydantic_with_factory(spot):
    """
    Case: Using decoder_factory for more robust late-binding.
    """
    
    @spot.register(
        code=31,
        encoder=lambda obj: obj.model_dump(),
        # クラス定義後に 'cls' (Item) を受け取ってからメソッドを指定する
        decoder_factory=lambda cls: cls.model_validate
    )
    class Item(BaseModel):
        sku: str
        price: float

    item = Item(sku="BS-001", price=1200.0)
    
    packed = spot.serializer.dumps(item)
    restored = spot.serializer.loads(packed)

    assert isinstance(restored, Item)
    assert restored.sku == "BS-001"

