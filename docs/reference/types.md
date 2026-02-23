# Types

`beautyspot.types` モジュールでは、エラーハンドリングや拡張フックで利用されるデータクラスを定義しています。

::: beautyspot.types

## Hook Contexts
フックシステム（`HookBase`）の各メソッドに渡される、型安全なコンテキストオブジェクトです。

* **`PreExecuteContext`**: 関数実行（およびキャッシュ確認）の直前に渡されます。引数 (`args`, `kwargs`) にアクセスできます。
* **`CacheHitContext`**: キャッシュがヒットした直後に渡されます。キャッシュから復元された `result` にアクセスできます。
* **`CacheMissContext`**: キャッシュが存在せず、実関数が実行された直後に渡されます。新たに生成された `result` にアクセスできます。

## Error Contexts
* **`SaveErrorContext`**: バックグラウンド保存 (`wait=False`) 時にエラーが発生した場合、`on_background_error` ハンドラに渡されるコンテキストです。

::: beautyspot.content_types

