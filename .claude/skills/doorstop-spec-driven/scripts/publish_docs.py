#!/usr/bin/env python3
"""Standalone human-readable document generator.

Converts Doorstop documents into beautiful, readable HTML files,
leveraging the `level` attribute and `normative: false` as structural headers.

Usage:
    python publish_docs.py <project-dir> [--output-dir ./specification/reports/publish]
"""

import argparse
import os
import sys
import re
from datetime import datetime

try:
    import doorstop
except ImportError:
    print("ERROR: doorstop is not installed.", file=sys.stderr)
    sys.exit(1)

from reporting import (
    h,
    get_groups,
    get_references,
    is_normative,
    render_markdown,
    find_item,
    build_children_map,
)

def natural_sort_key(s):
    """Natural sorting for levels like '1.0', '1.1', '1.10'."""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', s)]

def build_document_html(doc, tree, children_map, single_file=False):
    """Generates the HTML content for a single document."""
    items = list(doc)
    
    # Filter active items and sort by level
    items = [i for i in items if i.active]
    items.sort(key=lambda i: natural_sort_key(str(i.level)))
    
    html = ""
    for item in items:
        uid = str(item.uid)
        level = str(item.level)
        header = h(item.header or "")
        groups = get_groups(item)
        text_html = render_markdown(item.text)
        refs = get_references(item)
        ref_text = h(item.ref or "")
        is_norm = is_normative(item)
        
        is_heading = not is_norm and level.endswith('.0')
        level_depth = len(level.split('.'))
        
        parent_links = []
        for link in item.links:
            parent_uid = str(link)
            parent_item = find_item(tree, parent_uid)
            if parent_item:
                p_prefix = parent_item.document.prefix
                href = f"#{parent_uid}" if single_file else f"{p_prefix}.html#{parent_uid}"
                parent_links.append(f'<a href="{href}" class="link-tag">{h(parent_uid)}</a>')
            else:
                parent_links.append(f'<span class="link-tag">{h(parent_uid)}</span>')
                
        child_uids = children_map.get(uid, [])
        child_links = []
        for child_uid in sorted(child_uids):
            child_item = find_item(tree, child_uid)
            if child_item:
                c_prefix = child_item.document.prefix
                href = f"#{child_uid}" if single_file else f"{c_prefix}.html#{child_uid}"
                child_links.append(f'<a href="{href}" class="link-tag">{h(child_uid)}</a>')
            else:
                child_links.append(f'<span class="link-tag">{h(child_uid)}</span>')
                
        links_html = ""
        if parent_links or child_links:
            links_html += '<div class="item-links" style="margin-top: 8px; font-size: 0.85em; color: #555;">'
            if parent_links:
                links_html += f'<div style="margin-bottom: 2px;"><strong>Parents:</strong> {", ".join(parent_links)}</div>'
            if child_links:
                links_html += f'<div><strong>Children:</strong> {", ".join(child_links)}</div>'
            links_html += '</div>'
        
        if is_heading:
            if level_depth == 1:
                h_tag = "h1"
                border = "2px solid #1a73e8"
                color = "#1a73e8"
                font_size = "1.8em"
            elif level_depth == 2:
                h_tag = "h2"
                border = "1px solid #ddd"
                color = "inherit"
                font_size = "1.4em"
            else:
                h_tag = "h3"
                border = "1px solid #ddd"
                color = "inherit"
                font_size = "1.2em"
                
            html += f"""
            <div id="{h(uid)}" class="doc-heading" style="margin-top: 32px; border-bottom: {border}; padding-bottom: 8px; margin-bottom: 16px;">
                <{h_tag} style="margin: 0; color: {color}; font-size: {font_size};">
                    {h(level)} {header}
                    <a href="#{h(uid)}" style="float: right; font-size: 0.5em; font-weight: normal; color: #999; text-decoration: none;">{h(uid)}</a>
                </{h_tag}>
                {f'<div class="doc-text" style="margin-top: 12px;">{text_html}</div>' if item.text else ''}
                {links_html}
            </div>
            """
        else:
            ml = (level_depth - 1) * 20
            border_color = "#1a73e8" if is_norm else "#ccc"
            
            group_tag = ''.join(f'<span class="group-tag">{h(g)}</span>' for g in groups if g != '(未分類)')
            
            ref_html = ""
            if refs:
                ref_html = f'<div style="margin-top: 8px; font-size: 0.85em; color: #666;"><strong>Ref:</strong> {", ".join(h(r.get("path", "")) for r in refs)}</div>'
            elif ref_text:
                ref_html = f'<div style="margin-top: 8px; font-size: 0.85em; color: #666;"><strong>Ref:</strong> {ref_text}</div>'
                
            normative_badge = '' if is_norm else '<span class="non-normative-tag">Non-normative</span>'
                
            html += f"""
            <div id="{h(uid)}" class="doc-item" style="margin-left: {ml}px; border-left: 3px solid {border_color};">
                <div class="item-header">
                    <strong>{h(level)} {header}</strong>
                    <a href="#{h(uid)}" class="uid-tag" style="text-decoration: none;">{h(uid)}</a>
                </div>
                <div style="margin-bottom: 8px;">
                    {group_tag}
                    {normative_badge}
                </div>
                <div class="doc-text">{text_html}</div>
                {links_html}
                {ref_html}
            </div>
            """
            
    return html

def main():
    parser = argparse.ArgumentParser(description="Generate human-readable HTML documents.")
    parser.add_argument("project_dir", help="Project root directory")
    parser.add_argument("--output-dir", default="./specification/reports/publish", help="Output directory")
    parser.add_argument("--single-file", action="store_true", help="Output all documents as a single HTML file")
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    os.chdir(project_dir)

    print("Building document tree...")
    tree = doorstop.build()
    children_map = build_children_map(tree)

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    css = """
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #fafafa; color: #333; line-height: 1.6; }
    .doc-item { background: #fff; border: 1px solid #ddd; border-radius: 4px; padding: 12px 16px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
    .item-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; font-size: 1.1em; }
    .uid-tag { font-size: 0.8em; background: #f1f3f4; padding: 2px 6px; border-radius: 4px; border: 1px solid #ddd; color: #555; }
    .group-tag { display: inline-block; background: #e8f0fe; color: #1a73e8; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; font-weight: 600; margin-right: 4px; }
    .non-normative-tag { display: inline-block; background: #f1f3f4; color: #5f6368; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; border: 1px dashed #dadce0; margin-right: 4px; }
    .doc-text p { margin: 6px 0; }
    .doc-text pre { background: #f5f5f5; padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 0.85em; }
    .doc-text code { background: #f5f5f5; padding: 1px 5px; border-radius: 3px; font-size: 0.9em; font-family: monospace; }
    .doc-text table { border-collapse: collapse; margin: 8px 0; width: 100%; }
    .doc-text table th, .doc-text table td { border: 1px solid #ddd; padding: 6px 10px; }
    .doc-text table th { background: #f0f0f0; }
    .link-tag { color: #1a73e8; text-decoration: none; border-bottom: 1px solid transparent; transition: border-color 0.2s; }
    .link-tag:hover { border-bottom: 1px solid #1a73e8; }
    """

    if args.single_file:
        all_html = ""
        for doc in tree:
            html_content = build_document_html(doc, tree, children_map, single_file=True)
            all_html += f"""
            <div style="margin-bottom: 24px; margin-top: 48px; border-bottom: 3px solid #333; padding-bottom: 12px;">
                <h1 style="margin: 0; font-size: 2.2em;">{h(doc.prefix)} Specification</h1>
            </div>
            {html_content}
            """
            
        full_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>Specification</title>
<style>
{css}
</style>
</head>
<body>
    <div style="margin-bottom: 24px;">
        <h1 style="margin: 0;">Doorstop Specifications</h1>
        <div style="color: #666; font-size: 0.9em;">Generated at {now}</div>
    </div>
    {all_html}
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{ startOnLoad: false, theme: 'default' }});

      document.querySelectorAll('code.language-mermaid, code.mermaid, pre.mermaid, div.mermaid').forEach((block, idx) => {{
        if (block.dataset.mermaidProcessed) return;
        block.dataset.mermaidProcessed = 'true';
        
        const id = 'mermaid-doc-' + idx + '-' + Date.now();
        const graphDef = block.textContent.trim();
        const target = (block.tagName === 'CODE' && block.parentElement && block.parentElement.tagName === 'PRE') ? block.parentElement : block;
        
        mermaid.render(id, graphDef).then(({{ svg }}) => {{
          const div = document.createElement('div');
          div.className = 'mermaid-diagram';
          div.style.textAlign = 'center';
          div.style.margin = '16px 0';
          div.innerHTML = svg;
          target.replaceWith(div);
        }}).catch(err => {{
          console.error('Mermaid render error:', err);
        }});
      }});
    </script>
</body>
</html>
"""
        out_path = os.path.join(output_dir, "specification.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(full_html)
        print(f"Generated: {out_path}")
        
    else:
        for doc in tree:
            html_content = build_document_html(doc, tree, children_map, single_file=False)
            
            full_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>{h(doc.prefix)} - Document View</title>
<style>
{css}
</style>
</head>
<body>
    <div style="margin-bottom: 24px;">
        <h1 style="margin: 0;">{h(doc.prefix)} Specification</h1>
        <div style="color: #666; font-size: 0.9em;">Generated at {now}</div>
    </div>
    {html_content}
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{ startOnLoad: false, theme: 'default' }});

      document.querySelectorAll('code.language-mermaid, code.mermaid, pre.mermaid, div.mermaid').forEach((block, idx) => {{
        if (block.dataset.mermaidProcessed) return;
        block.dataset.mermaidProcessed = 'true';
        
        const id = 'mermaid-doc-' + idx + '-' + Date.now();
        const graphDef = block.textContent.trim();
        const target = (block.tagName === 'CODE' && block.parentElement && block.parentElement.tagName === 'PRE') ? block.parentElement : block;
        
        mermaid.render(id, graphDef).then(({{ svg }}) => {{
          const div = document.createElement('div');
          div.className = 'mermaid-diagram';
          div.style.textAlign = 'center';
          div.style.margin = '16px 0';
          div.innerHTML = svg;
          target.replaceWith(div);
        }}).catch(err => {{
          console.error('Mermaid render error:', err);
        }});
      }});
    </script>
</body>
</html>
"""
            out_path = os.path.join(output_dir, f"{doc.prefix}.html")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(full_html)
            print(f"Generated: {out_path}")

    print(f"All documents published to {output_dir}")

if __name__ == "__main__":
    main()
