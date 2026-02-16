## 🧪 7. Testing

テスト実行時は、本番DBを汚さないように `tmp_path` やメモリ内DBを使用します。

```python
import pytest
import beautyspot as bs

@pytest.fixture
def spot(tmp_path):
    # テストごとに独立したDBとBlobストレージを作成
    return bs.Spot(
        name="test",
        db=str(tmp_path / "test.db"),
        storage_path=str(tmp_path / "blobs")
    )

def test_caching(spot):
    count = 0
    
    @spot.mark
    def func(x):
        nonlocal count
        count += 1
        return x * 2

    assert func(10) == 20
    assert count == 1
    
    # 2回目はキャッシュヒット
    assert func(10) == 20
    assert count == 1 

```
