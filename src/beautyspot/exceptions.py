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
