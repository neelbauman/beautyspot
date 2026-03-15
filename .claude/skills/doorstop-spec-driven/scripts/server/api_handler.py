import json
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

from data_store import DoorstopDataStore


# ===================================================================
# SPA HTML — assembled from external assets
# ===================================================================

_SERVE_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _load_spa_html():
    """assets/spa.css と assets/spa.js を読み込み、インラインHTMLとして組み立てる。"""
    css_path = os.path.join(_SERVE_ASSETS_DIR, "spa.css")
    js_path = os.path.join(_SERVE_ASSETS_DIR, "spa.js")
    with open(css_path, encoding="utf-8") as f:
        css = f.read()
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    return _SPA_HTML_TEMPLATE.replace("/* __SPA_CSS__ */", css).replace("/* __SPA_JS__ */", js)


_SPA_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Doorstop Traceability Dashboard</title>
<style>
/* __SPA_CSS__ */
</style>
</head>
<body>

<nav id="sidebar">
  <h2>Doorstop Dashboard</h2>
  <div id="nav-status-summary"></div>
  <ul>
    <li><a href="#/" data-nav="dashboard">Dashboard</a></li>
    <li><a href="#/matrix" data-nav="matrix">Matrix</a></li>
    <li><a href="#/tree" data-nav="tree">Tree Graph</a></li>
    <li><span class="nav-section-title">Documents</span></li>
  </ul>
  <ul id="doc-nav-list"></ul>
  <ul>
    <li><span class="nav-section-title">Groups</span></li>
  </ul>
  <ul id="group-nav-list"></ul>
  <ul>
    <li><a href="#/validation" data-nav="validation">Validation</a></li>
  </ul>
  <div style="padding:12px 16px; border-top:1px solid var(--border); margin-top:auto;">
    <button id="reload-btn" onclick="forceReload()" style="width:100%; padding:8px; border:1px solid var(--border); border-radius:6px; background:var(--bg); cursor:pointer; font-size:13px; display:flex; align-items:center; justify-content:center; gap:6px;" title="Reload from disk">
      <span style="font-size:16px;">&#x21bb;</span> <span>Reload</span>
    </button>
  </div>
</nav>

<main id="main">
  <div class="loading">Loading...</div>
</main>

<div id="item-panels-container"></div>

<script>
/* __SPA_JS__ */
</script>
</body>
</html>"""


# ===================================================================
# HTTP Handler
# ===================================================================

class ReportAPIHandler(BaseHTTPRequestHandler):
    store: DoorstopDataStore

    def do_GET(self):
        self.store.reload_if_changed()

        url = urlparse(self.path)
        path = url.path.rstrip("/")
        params = parse_qs(url.query)

        if path == "/api/overview":
            self._json_ok(self.store.get_overview())
        elif path == "/api/matrix":
            group = params.get("group", [None])[0]
            self._json_ok(self.store.get_matrix(group=group))
        elif path == "/api/groups":
            self._json_ok(self.store.get_groups())
        elif path.startswith("/api/group/"):
            name = unquote(path[len("/api/group/"):])
            data = self.store.get_group_detail(name)
            if data:
                self._json_ok(data)
            else:
                self._json_err(404, f"Group '{name}' not found")
        elif path == "/api/items":
            group = params.get("group", [None])[0]
            prefix = params.get("prefix", [None])[0]
            self._json_ok(self.store.get_all_items(group=group, prefix=prefix))
        elif path.startswith("/api/items/"):
            uid = path[len("/api/items/"):]
            data = self.store.get_item(uid)
            if data:
                self._json_ok(data)
            else:
                self._json_err(404, f"Item '{uid}' not found")
        elif path == "/api/documents":
            docs = [doc.prefix for doc in self.store.tree]
            self._json_ok(docs)
        elif path.startswith("/api/document/"):
            prefix = path[len("/api/document/"):]
            data = self.store.get_document_detail(prefix)
            if data:
                self._json_ok(data)
            else:
                self._json_err(404, f"Document '{prefix}' not found")
        elif path == "/api/graph":
            self._json_ok(self.store.get_graph_data())
        elif path.startswith("/api/graph/ego/"):
            uid = path[len("/api/graph/ego/"):]
            hops = int(params.get("hops", [2])[0])
            data = self.store.get_graph_ego(uid, hops=hops)
            if data:
                self._json_ok(data)
            else:
                self._json_err(404, f"Item '{uid}' not found")
        elif path == "/api/validation":
            self._json_ok(self.store.get_validation())
        elif path == "/api/coverage":
            self._json_ok(self.store.get_coverage())
        elif path in ("", "/", "/index.html"):
            self._serve_html(_load_spa_html())
        elif path == "/api/download_report":
            report_path = os.path.join(self.store.project_dir, "specification", "reports", "publish", "specification.html")
            if os.path.exists(report_path):
                with open(report_path, "r", encoding="utf-8") as f:
                    content = f.read()
                body = content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="specification.html"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404, "Report not found. Please generate it first.")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.rstrip("/") == "/api/reload":
            self.store.force_reload()
            self._json_ok({"ok": True, "message": "Tree reloaded"})
            return

        if self.path.rstrip("/") == "/api/generate_report":
            self.store.force_reload()
            script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "publish_docs.py")
            cmd = [
                sys.executable,
                script_path,
                self.store.project_dir,
                "--single-file"
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                self._json_ok({"ok": True, "message": "Report generated successfully.", "report_url": "/api/download_report"})
            except subprocess.CalledProcessError as e:
                self._json_err(500, f"Failed to generate report: {e.stderr}")
            return

        m = re.match(r"^/api/items/([\w]+)/(review|unreview|clear|edit|reorder|insert|delete|link|unlink)$", self.path)
        if not m:
            self._json_err(404, "Not found")
            return
        uid, action = m.groups()

        try:
            if action == "review":
                result, err = self.store.review_item(uid)
            elif action == "unreview":
                result, err = self.store.unreview_item(uid)
            elif action == "clear":
                result, err = self.store.clear_item(uid)
            elif action == "edit":
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                text = body.get("text")
                if text is None:
                    self._json_err(400, "text is required")
                    return
                result, err = self.store.edit_item(uid, body)
            elif action == "reorder":
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                reorder_action = body.get("action")
                if reorder_action not in ["up", "down", "indent", "outdent"]:
                    self._json_err(400, "Valid action is required")
                    return
                result, err = self.store.reorder_item(uid, reorder_action)
            elif action == "insert":
                result, err = self.store.insert_item(uid)
            elif action == "delete":
                result, err = self.store.delete_item(uid)
            elif action == "link":
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                parent_uid = body.get("parent")
                if not parent_uid:
                    self._json_err(400, "parent is required")
                    return
                result, err = self.store.link_item(uid, parent_uid)
            elif action == "unlink":
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                parent_uid = body.get("parent")
                if not parent_uid:
                    self._json_err(400, "parent is required")
                    return
                result, err = self.store.unlink_item(uid, parent_uid)
            else:
                self._json_err(400, f"Unknown action: {action}")
                return

            if err:
                self._json_err(404, err)
            else:
                self._json_ok({"ok": True, "item": result})
        except Exception as e:
            self._json_err(500, str(e))

    def _json_ok(self, data):
        body = json.dumps(data, ensure_ascii=False, default=list).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_err(self, code, message):
        body = json.dumps({"ok": False, "error": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_html(self, html_content):
        body = html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"  [{self.log_date_time_string()}] {format % args}")
