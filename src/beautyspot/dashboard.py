# type: ignore
# src/beautyspot/dashboard.py

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import argparse
import os
import msgpack
import html
from beautyspot.types import ContentType
from beautyspot.db import SQLiteTaskDB
from beautyspot.storage import S3Storage


# CLI引数の解析 (Streamlitのお作法として sys.argv をパース)
def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=str, required=True)
    # Streamlit引数との競合回避のため、知らない引数は無視
    args, _ = parser.parse_known_args()
    return args


try:
    args = get_args()
    DB_PATH = args.db
except Exception:
    st.error("Database path not provided. Run via `beautyspot ui <db>`")
    st.stop()


# --- Helper: Mermaid Renderer ---
def render_mermaid(code: str, height: int = 500):
    """
    Mermaid.jsをCDNから読み込んで描画するヘルパー。
    Streamlit標準でMermaidがないためのWorkaround。
    """
    html_code = f"""
    <div class="mermaid" style="display: flex; justify-content: center;">
        {html.escape(code)}
    </div>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
    """
    # scrolling=Trueにしておくと大きな図でも見切れない
    components.html(html_code, height=height, scrolling=True)


# プロジェクトインスタンスの作成（DBを読むだけなのでStorage設定はDummyで可）
# ただしLoad機能を使うなら正しいStorage設定が必要だが、
# ここではDB内のパス情報を見て動的に判断する簡易版を実装

st.set_page_config(page_title="beautyspot Dashboard", layout="wide", page_icon="🌑")
st.title("🌑 beautyspot Dashboard")
st.caption(f"Database: `{DB_PATH}`")


# --- Data Loading ---
def load_data():
    try:
        db = SQLiteTaskDB(DB_PATH)
        return db.get_history(limit=1000)
    except Exception as e:
        st.error(f"Error reading DB: {e}")
        return pd.DataFrame()


if st.button("🔄 Refresh"):
    st.cache_data.clear()

df = load_data()

if df.empty:
    st.info("No tasks recorded yet.")
    st.stop()

# --- Sidebar Filters ---
st.sidebar.header("Filter")
st.sidebar.metric("Total Records", len(df))

funcs = st.sidebar.multiselect(
    "Function",
    df["func_name"].unique().tolist(),  # type: ignore[union-attr]
)
if funcs:
    df = df[df["func_name"].isin(funcs)]  # type: ignore[union-attr]

result_types = st.sidebar.multiselect(
    "Result Type",
    df["result_type"].unique().tolist(),  # type: ignore[union-attr]
)
if result_types:
    df = df[df["result_type"].isin(result_types)]  # type: ignore[union-attr]

search = st.sidebar.text_input("Search Input ID")
if search:
    df = df[df["input_id"].str.contains(search, na=False)]  # type: ignore[union-attr]


# --- Main Table ---
st.subheader("📋 Tasks")
event = st.dataframe(
    df[
        [
            "cache_key",
            "updated_at",
            "func_name",
            "input_id",
            "version",
            "result_type",
            "content_type",
            "result_value",
            "result_data",
        ]
    ],
    width="stretch",
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

# --- Detail & Restore ---
st.markdown("---")
st.subheader("🔍 Restore Data")

selected_key = None

if len(event.selection.rows) > 0:  # type: ignore[union-attr]
    row_idx = event.selection.rows[0]  # type: ignore[union-attr]
    selected_key = df.iloc[row_idx]["cache_key"]  # type: ignore[union-attr]

if selected_key:
    st.info(f"Selected from table: `{selected_key}`")
else:
    st.info("Select Record from Table")

if selected_key:
    row = df[df["cache_key"] == selected_key].iloc[0]  # type: ignore[union-attr]

    r_type = row["result_type"]
    r_val = row["result_value"]

    # Check if result_data exists (it might be NaN in pandas if not selected or null)
    # The get_history query selects result_data, so it should be there.
    # But pandas converts BLOB to bytes.
    r_blob = row.get("result_data") if "result_data" in row else None

    c_type = row.get("content_type")
    col1, col2 = st.columns([1, 2])

    with col1:
        st.write("**Metadata**")
        # Don't show raw blob in metadata view
        display_row = row.to_dict().copy()
        if "result_data" in display_row:
            del display_row["result_data"]
        st.json(display_row)

    with col2:
        st.write(f"**Content**: {c_type or 'Unknown Type'}")

        try:
            data = None
            if r_type == "DIRECT_BLOB":
                # New Native BLOB
                if r_blob is not None and not pd.isna(r_blob):
                    try:
                        data = msgpack.unpackb(r_blob, raw=False)
                    except Exception as e:
                        st.error(f"Failed to decode DIRECT_BLOB data: {e}")
                else:
                    st.warning("DIRECT_BLOB record found but data is empty.")

            elif r_type == "FILE":
                # Auto Storage Detection
                with st.spinner("Loading Blob..."):
                    if r_val.startswith("s3://"):
                        storage = S3Storage(r_val)  # 初期化時にバケット解析させる
                        data = storage.load(r_val)
                    else:
                        # ローカルパスの場合、実行場所との相対パス問題があるため
                        # 絶対パスか確認しつつ読み込む
                        if os.path.exists(r_val):
                            with open(r_val, "rb") as f:
                                data = msgpack.unpack(f, raw=False)
                        else:
                            st.error(f"File not found on this machine: {r_val}")

            if data is not None:
                """
                Rendering Strategy :
                We strictly separate the 'Storage Layer' (how to fetch bytes) from the 'Presentation Layer' (how to show it).
                The 'content_type' metadata drives the widget selection.
                If 'content_type' is missing (legacy records), we fallback to a generic text/json view.
                """
                st.success("Restored successfully!")

                if c_type == ContentType.GRAPHVIZ:
                    try:
                        st.graphviz_chart(data)
                    except Exception:
                        st.error("Graphviz rendering failed.")
                        st.warning(
                            "Hint: Is 'graphviz' installed on your OS? (e.g., `apt install graphviz`)"
                        )
                        st.code(data)  # フォールバックとしてソースを表示

                # === Mermaid ===
                elif c_type == ContentType.MERMAID:
                    render_mermaid(data)
                    with st.expander("View Source"):
                        st.code(data, language="mermaid")

                elif c_type == ContentType.PNG or c_type == ContentType.JPEG:
                    st.image(data)

                elif c_type == ContentType.HTML:
                    # Use components.html for sandboxed rendering to prevent XSS
                    components.html(data, height=600, scrolling=True)

                elif c_type == ContentType.JSON:
                    st.json(data)

                elif c_type == ContentType.MARKDOWN:
                    st.markdown(data)

                else:
                    # Fallback (Default Text Representation)
                    if isinstance(data, (dict, list)):
                        st.json(data)
                    else:
                        st.text(str(data))

        except Exception as e:
            st.error(f"Restore Failed: {e}")
            st.exception(e)

st.markdown("---")
st.subheader("🗑️ Danger Zone")

if selected_key:
    # 削除ボタンを Popover (確認ダイアログ的な挙動) でラップ
    with st.popover("Delete Record", use_container_width=True):
        st.markdown(f"Are you sure you want to delete **`{selected_key}`**?")
        st.warning(
            "This action cannot be undone. The database record and associated blob file will be removed."
        )

        if st.button("Confirm Delete", type="primary"):
            try:
                # 1. DB接続
                db = SQLiteTaskDB(DB_PATH)

                # 2. Blob削除のための情報取得
                # (load_data() の df から情報を取れるが、念のためDBから最新を引く)
                record = db.get(selected_key)

                if record:
                    # Blob削除
                    if record["result_type"] == "FILE" and record["result_value"]:
                        r_val = record["result_value"]
                        if r_val.startswith("s3://"):
                            storage = S3Storage(r_val)
                            storage.delete(r_val)
                        else:
                            # Local file
                            if os.path.exists(r_val):
                                os.remove(r_val)

                    # レコード削除
                    db.delete(selected_key)

                    st.success(f"Deleted `{selected_key}`")
                    # データをリフレッシュして再描画
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Record not found in DB.")

            except Exception as e:
                st.error(f"Failed to delete: {e}")
else:
    st.info("Select a record to enable deletion.")
