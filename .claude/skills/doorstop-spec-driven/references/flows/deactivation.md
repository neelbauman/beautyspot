# [G] 非活性化フロー

機能削除や要件取り下げの要望があったとき。
アイテムを物理削除せず、`active: false` に設定して非活性化する。

## 手順

1. **影響確認** — `trace_query.py <dir> chain <UID>` で下流アイテムを確認
2. **ユーザー確認** — 非活性化対象と影響範囲をユーザーに提示し、合意を得る
3. **チェーン非活性化** — `doorstop_ops.py <dir> deactivate-chain <UID>`
   - 下流アイテムのうち、他に活性な親を持たないものも連鎖的に非活性化される
   - 他に活性な親があっても強制する場合は `--force`
4. **検証** — `validate_and_report.py --strict` で整合性確認
5. **報告** — 非活性化されたアイテム数と影響範囲を報告

## 再活性化

取り下げた要件を復活させる場合:

```bash
doorstop_ops.py <dir> activate-chain <UID>
```

## 注意事項

- 物理削除（YAMLファイルの削除）は行わない。`active: false` で管理する
- 非活性化アイテムはカバレッジ計算やバリデーションから除外される
- `baseline_manager.py diff` で非活性化の記録を追跡できる
