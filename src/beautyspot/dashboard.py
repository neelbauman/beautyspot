# type: ignore
# src/beautyspot/dashboard.py

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import argparse
import html
from beautyspot.content_types import ContentType
from beautyspot.maintenance import MaintenanceService


# CLI引数の解析
def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=str, required=True)
    args, _ = parser.parse_known_args()
    return args


try:
    args = get_args()
    DB_PATH = args.db
except Exception:
    st.error("Database path not provided. Run via `beautyspot ui <db>`")
    st.stop()


# --- Service Initialization ---
# UIレイヤーは具体的なDBクラスやStorageクラスを知る必要がない
service = MaintenanceService.from_path(DB_PATH)


# --- Helper: Mermaid Renderer ---
def render_mermaid(code: str, height: int = 500):
    html_code = f"""
    <div class="mermaid" style="display: flex; justify-content: center;">
        {html.escape(code)}
    </div>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
    """
    components.html(html_code, height=height, scrolling=True)


st.set_page_config(page_title="beautyspot Dashboard", layout="wide", page_icon="🌑")
st.title("🌑 beautyspot Dashboard")
st.caption(f"Database: `{DB_PATH}`")


# --- Data Loading ---
def load_data():
    try:
        return service.get_history(limit=1000)
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

if "func_identifier" in df.columns and df["func_identifier"].notna().any():  # type: ignore[union-attr]
    func_col = "func_identifier"
else:
    func_col = "func_name"
funcs = st.sidebar.multiselect(
    "Function",
    df[func_col].dropna().unique().tolist(),  # type: ignore[union-attr]
)
if funcs:
    df = df[df[func_col].isin(funcs)]  # type: ignore[union-attr]

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
            func_col,
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
    # サービス経由でデータを取得（デシリアライズ済み）
    row = service.get_task_detail(selected_key, include_expired=True)

    if row:
        c_type = row.get("content_type")
        data = row.get("decoded_data")

        col1, col2 = st.columns([1, 2])

        with col1:
            st.write("**Metadata**")
            # メタデータ表示用にblobデータを隠す
            display_row = row.copy()
            if "result_data" in display_row:
                del display_row["result_data"]
            if "decoded_data" in display_row:
                del display_row["decoded_data"]
            st.json(display_row)

        with col2:
            st.write(f"**Content**: {c_type or 'Unknown Type'}")

            if data is not None:
                st.success("Restored successfully!")

                if c_type == ContentType.GRAPHVIZ:
                    try:
                        st.graphviz_chart(data)
                    except Exception:
                        st.error("Graphviz rendering failed.")
                        st.code(data)

                elif c_type == ContentType.MERMAID:
                    render_mermaid(data)
                    with st.expander("View Source"):
                        st.code(data, language="mermaid")

                elif c_type == ContentType.PNG or c_type == ContentType.JPEG:
                    st.image(data)

                elif c_type == ContentType.HTML:
                    # sandboxed iframe: 全制限で安全に HTML を表示
                    sandbox_html = (
                        '<iframe sandbox="" srcdoc="'
                        + html.escape(data, quote=True)
                        + '" style="width:100%;height:600px;border:none;"></iframe>'
                    )
                    components.html(sandbox_html, height=620, scrolling=True)

                elif c_type == ContentType.JSON:
                    st.json(data)

                elif c_type == ContentType.MARKDOWN:
                    st.markdown(data)

                else:
                    if isinstance(data, (dict, list)):
                        st.json(data)
                    else:
                        st.text(str(data))
            else:
                st.warning("Data could not be restored (decoding failed or empty).")
    else:
        st.error("Record not found in DB.")

st.markdown("---")
st.subheader("🗑️ Danger Zone")

if selected_key:
    with st.popover("Delete Record", use_container_width=True):
        st.markdown(f"Are you sure you want to delete **`{selected_key}`**?")
        st.warning(
            "This action cannot be undone. The database record and associated blob file will be removed."
        )

        if st.button("Confirm Delete", type="primary"):
            try:
                # サービス経由で削除
                if service.delete_task(selected_key):
                    st.success(f"Deleted `{selected_key}`")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Record not found or failed to delete.")

            except Exception as e:
                st.error(f"Failed to delete: {e}")
else:
    st.info("Select a record to enable deletion.")
