"""変更影響分析の出力フォーマッタ。

impact_analysis.py の分析結果を各種形式（コンソール・JSON・HTML）で出力する。
"""

import html as html_mod
import json
from collections import defaultdict
from datetime import datetime


# ---------------------------------------------------------------------------
# Output: コンソール
# ---------------------------------------------------------------------------

def print_console(results, tree):
    """コンソールに影響分析結果を出力する。"""
    if not results:
        print("変更されたアイテムは検出されませんでした。")
        return

    print(f"\n{'='*60}")
    print("  変更影響分析レポート")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  変更アイテム: {len(results)}件")
    print(f"{'='*60}")

    for r in results:
        print(f"\n{'─'*60}")
        print(f"■ {r['uid']} [{'/'.join(r.get('groups', ['?']))}] ({r['prefix']})")
        print(f"  {r['text']}")
        if r["ref"]:
            print(f"  ref: {r['ref']}")

        if r["upstream"]:
            print("\n  [上流 ← なぜ変わった？]")
            for u in r["upstream"]:
                indent = "    " + "  " * u["depth"]
                print(f"{indent}← {u['uid']} [{'/'.join(u.get('groups', ['?']))}] ({u['prefix']})")
                print(f"{indent}  {u['text']}")

        if r["downstream"] or r["suspect_children"]:
            print("\n  [下流 → 何に影響する？]")
            for d in r["downstream"]:
                indent = "    " + "  " * d["depth"]
                suspect_mark = " ⚠ suspect" if d["uid"] in {s["uid"] for s in r["suspect_children"]} else ""
                print(f"{indent}→ {d['uid']} [{'/'.join(d.get('groups', ['?']))}] ({d['prefix']}){suspect_mark}")
                print(f"{indent}  {d['text']}")
                if d.get("ref"):
                    print(f"{indent}  ref: {d['ref']}")

        if r["actions"]:
            print("\n  [対応アクション]")
            for i, action in enumerate(r["actions"], 1):
                print(f"    {i}. {action}")

    # グループ別サマリ
    group_impact = defaultdict(lambda: {"changed": 0, "suspect": 0, "affected": 0})
    for r in results:
        for g in r["groups"]:
            group_impact[g]["changed"] += 1
        for s in r["suspect_children"]:
            for g in s["groups"]:
                group_impact[g]["suspect"] += 1
        for d in r["downstream"]:
            for g in d["groups"]:
                group_impact[g]["affected"] += 1

    print(f"\n{'─'*60}")
    print("[グループ別影響サマリ]")
    for g, data in sorted(group_impact.items()):
        print(f"  {g}: 変更={data['changed']}  suspect={data['suspect']}  影響={data['affected']}")

    print()


# ---------------------------------------------------------------------------
# Output: JSON
# ---------------------------------------------------------------------------

def write_json(results, output_path):
    """JSON形式で影響分析結果を出力する。"""
    # action_plan のサマリを集約
    all_files = set()
    all_review = []
    all_clear = []
    for r in results:
        ap = r.get("action_plan", {})
        all_files.update(ap.get("files_to_check", []))
        all_review.extend(ap.get("review_commands", []))
        all_clear.extend(ap.get("clear_commands", []))

    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "changed_items": len(results),
            "total_suspects": sum(len(r["suspect_children"]) for r in results),
            "total_downstream": sum(len(r["downstream"]) for r in results),
            "total_actions": sum(len(r["actions"]) for r in results),
        },
        "action_plan_summary": {
            "review_commands": all_review,
            "clear_commands": all_clear,
            "files_to_check": sorted(all_files),
            "validation": results[0]["action_plan"]["validation"] if results else None,
        },
        "impacts": results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"JSON出力: {output_path}")


# ---------------------------------------------------------------------------
# Output: HTML
# ---------------------------------------------------------------------------

def write_html(results, output_path):
    """HTML形式で影響分析レポートを出力する。"""
    h = html_mod.escape
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total_suspects = sum(len(r["suspect_children"]) for r in results)
    total_downstream = sum(len(r["downstream"]) for r in results)
    total_actions = sum(len(r["actions"]) for r in results)

    # グループ別サマリ
    group_impact = defaultdict(lambda: {"changed": 0, "suspect": 0, "affected": 0})
    for r in results:
        for g in r["groups"]:
            group_impact[g]["changed"] += 1
        for s in r["suspect_children"]:
            for g in s["groups"]:
                group_impact[g]["suspect"] += 1
        for d in r["downstream"]:
            for g in d["groups"]:
                group_impact[g]["affected"] += 1

    group_rows = ""
    for g, d in sorted(group_impact.items()):
        group_rows += f"<tr><td><span class='group-tag'>{h(g)}</span></td>"
        group_rows += f"<td>{d['changed']}</td><td>{d['suspect']}</td><td>{d['affected']}</td></tr>"

    # 変更アイテム詳細
    impact_cards = ""
    for r in results:
        # 上流
        upstream_html = ""
        if r["upstream"]:
            items_html = ""
            for u in r["upstream"]:
                items_html += (
                    f"<div class='trace-item' style='margin-left:{u['depth']*20}px'>"
                    f"← <strong>{h(u['uid'])}</strong> "
                    f"<span class='group-tag'>{h('/'.join(u.get('groups', ['?'])))}</span> "
                    f"<span class='prefix-tag'>{h(u['prefix'])}</span>"
                    f"<br><span class='text-preview'>{h(u['text'])}</span></div>"
                )
            upstream_html = f"<h4>上流 ← なぜ変わった？</h4>{items_html}"

        # 下流
        suspect_uids = {s["uid"] for s in r["suspect_children"]}
        downstream_html = ""
        if r["downstream"]:
            items_html = ""
            for d in r["downstream"]:
                suspect_cls = " suspect" if d["uid"] in suspect_uids else ""
                suspect_badge = " <span class='suspect-badge'>⚠ suspect</span>" if d["uid"] in suspect_uids else ""
                ref_html = f"<br><span class='ref-tag'>{h(d.get('ref', ''))}</span>" if d.get("ref") else ""
                items_html += (
                    f"<div class='trace-item{suspect_cls}' style='margin-left:{d['depth']*20}px'>"
                    f"→ <strong>{h(d['uid'])}</strong> "
                    f"<span class='group-tag'>{h('/'.join(d.get('groups', ['?'])))}</span> "
                    f"<span class='prefix-tag'>{h(d['prefix'])}</span>"
                    f"{suspect_badge}"
                    f"<br><span class='text-preview'>{h(d['text'])}</span>"
                    f"{ref_html}</div>"
                )
            downstream_html = f"<h4>下流 → 何に影響する？</h4>{items_html}"

        # アクション
        actions_html = ""
        if r["actions"]:
            al = "".join(f"<li>{h(a)}</li>" for a in r["actions"])
            actions_html = f"<h4>対応アクション</h4><ol>{al}</ol>"

        ref_html = f"<br><span class='ref-tag'>{h(r['ref'])}</span>" if r["ref"] else ""

        _r_groups_str = '/'.join(r.get('groups', ['?']))
        impact_cards += f"""
        <div class="impact-card" data-group="{h(_r_groups_str)}">
            <div class="impact-header">
                <strong>{h(r['uid'])}</strong>
                <span class="group-tag">{h(_r_groups_str)}</span>
                <span class="prefix-tag">{h(r['prefix'])}</span>
            </div>
            <div class="impact-body">
                <p>{h(r['text'])}{ref_html}</p>
                {upstream_html}
                {downstream_html}
                {actions_html}
            </div>
        </div>"""

    report_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>変更影響分析レポート</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 1200px; margin: 0 auto; padding: 20px; background: #fafafa; }}
  h1 {{ border-bottom: 3px solid #e65100; padding-bottom: 10px; color: #e65100; }}
  h2 {{ color: #e65100; margin-top: 30px; }}
  h4 {{ margin: 12px 0 6px; color: #555; font-size: 0.95em; }}
  table {{ border-collapse: collapse; width: 100%; margin: 10px 0; background: #fff; }}
  th {{ background: #e65100; color: #fff; padding: 8px 12px; text-align: left; }}
  td {{ border: 1px solid #ddd; padding: 8px 12px; }}
  .summary {{ display: flex; gap: 15px; margin: 15px 0; flex-wrap: wrap; }}
  .card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px;
           padding: 15px 20px; flex: 1; min-width: 100px; text-align: center; }}
  .card h3 {{ margin: 0 0 5px; font-size: 0.85em; color: #666; }}
  .card .value {{ font-size: 1.6em; font-weight: bold; color: #e65100; }}
  .timestamp {{ color: #999; font-size: 0.85em; }}
  .group-tag {{ display: inline-block; background: #e3f2fd; color: #1565c0; padding: 2px 8px;
                border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
  .prefix-tag {{ display: inline-block; background: #f3e5f5; color: #7b1fa2; padding: 2px 6px;
                 border-radius: 3px; font-size: 0.75em; }}
  .ref-tag {{ display: inline-block; background: #e8f5e9; color: #2e7d32; padding: 1px 6px;
              border-radius: 3px; font-size: 0.75em; font-family: monospace; }}
  .suspect-badge {{ background: #fff3e0; color: #e65100; padding: 1px 6px; border-radius: 3px;
                    font-size: 0.8em; font-weight: bold; }}
  .impact-card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px;
                  margin: 15px 0; overflow: hidden; }}
  .impact-header {{ background: #fff3e0; padding: 12px 16px; border-bottom: 1px solid #ddd; }}
  .impact-body {{ padding: 12px 16px; }}
  .trace-item {{ padding: 6px 10px; margin: 4px 0; border-left: 3px solid #ddd; }}
  .trace-item.suspect {{ border-left-color: #e65100; background: #fff8e1; }}
  .text-preview {{ color: #666; font-size: 0.85em; }}
  ol {{ padding-left: 20px; }}
  li {{ margin: 4px 0; }}
</style>
</head>
<body>
<h1>変更影響分析レポート</h1>
<p class="timestamp">生成日時: {now}</p>

<div class="summary">
  <div class="card">
    <h3>変更アイテム</h3>
    <div class="value">{len(results)}</div>
  </div>
  <div class="card">
    <h3>Suspect</h3>
    <div class="value" style="color:{'#e65100' if total_suspects else '#4caf50'}">{total_suspects}</div>
  </div>
  <div class="card">
    <h3>影響先</h3>
    <div class="value">{total_downstream}</div>
  </div>
  <div class="card">
    <h3>要アクション</h3>
    <div class="value">{total_actions}</div>
  </div>
</div>

<h2>グループ別影響サマリ</h2>
<table>
<tr><th>グループ</th><th>変更</th><th>Suspect</th><th>影響先</th></tr>
{group_rows}
</table>

<h2>変更アイテム詳細</h2>
{impact_cards}

</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_html)
    print(f"HTMLレポート: {output_path}")
