# src/beautyspot/types.py


class ContentType:
    """
    Supported semantic content types for beautyspot tasks.
    Used by the dashboard to determine the appropriate rendering widget.
    """

    TEXT = "text/plain"
    JSON = "application/json"
    MARKDOWN = "text/markdown"
    PNG = "image/png"
    JPEG = "image/jpeg"
    MERMAID = "text/vnd.mermaid"
    GRAPHVIZ = "text/vnd.graphviz"
    HTML = "text/html"

    # 将来的な拡張 (例: Audio, Video, CSV...)
