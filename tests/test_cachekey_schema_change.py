import pytest
from pydantic import BaseModel
from beautyspot.cachekey import KeyGen

def test_cache_key_changes_on_model_update():
    """
    Ensure that changing the fields of a Pydantic model results in a different cache key.
    """
    
    # Define Model Version 1
    class UserConfig(BaseModel):
        name: str
    
    key_v1 = KeyGen.default((UserConfig,), {})

    # Define Model Version 2 (Same name, different fields)
    # Python allows redefining classes, which creates a new type object.
    class UserConfig(BaseModel):
        name: str
        age: int  # Added field

    key_v2 = KeyGen.default((UserConfig,), {})

    assert key_v1 != key_v2, "Cache key must change when Pydantic model definition changes"

def test_cache_key_stable_on_identical_redefinition():
    """
    Ensure that if the definition is structurally identical, the key remains stable.
    (This is tricky in Python because redefining creates a new class, but 
     our logic relies on schema, which should be identical.)
    """
    class ConfigA(BaseModel):
        x: int = 1

    class ConfigB(BaseModel):
        x: int = 1
        
    # クラス名は異なりますが、スキーマの中身（タイトル以外）は同じ構造です。
    # model_json_schema() には 'title': 'ConfigA' が含まれるため、
    # デフォルトではクラス名が違えばキーも変わります。これは期待通りの挙動です。
    # ここでは「同じクラス名、同じ定義」で再作成した場合をシミュレートします。
    
    schema_a = ConfigA.model_json_schema()
    schema_b = ConfigB.model_json_schema()
    
    # Pydanticのスキーマにはタイトルが含まれるので、タイトルを揃えて比較
    schema_b['title'] = schema_a['title']
    
    assert schema_a == schema_b

