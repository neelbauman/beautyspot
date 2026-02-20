# src/beautyspot/exceptions.py

class BeautySpotError(Exception):
    """
    Base exception for all beautyspot errors.
    ユーザーが `except BeautySpotError:` でライブラリ起因のエラーを
    一括キャッチできるようにするための基底クラスです。
    """


class CacheCorruptedError(BeautySpotError):
    """
    Raised when cache data (DB record or Blob file) is lost, 
    unreadable, or logically corrupted.
    """


class SerializationError(BeautySpotError):
    """
    Raised when the serializer fails to encode or decode data.
    """


class ConfigurationError(BeautySpotError):
    """
    Raised when there is a logical error in the user's configuration
    (e.g., invalid retention policy, incompatible storage options).
    """

class ValidationError(ConfigurationError):
    """
    メソッド呼び出し時の引数やバリデーションエラー。
    ValueError/TypeError の代わりに、BeautySpotError 傘下として送出します。
    """

class IncompatibleProviderError(ConfigurationError):
    """
    注入された依存オブジェクト（Serializer, Storage, DB）が
    要求された機能を提供していない場合のエラー。
    """
