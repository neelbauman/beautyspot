# src/beautyspot/dashboard.py

import streamlit as st
import pandas as pd
import sqlite3
import json
import argparse
import os

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
except:
    st.error("Database path not provided. Run via `beautyspot ui <db>`")
    st.stop()

# プロジェクトインスタンスの作成（DBを読むだけなのでStorage設定はDummyで可）
# ただしLoad機能を使うなら正しいStorage設定が必要だが、
# ここではDB内のパス情報を見て動的に判断する簡易版を実装
from beautyspot.storage import LocalStorage, S3Storage

st.set_page_config(page_title="beautyspot Dashboard", layout="wide", page_icon="🌑")
st.title("🌑 beautyspot Dashboard")
st.caption(f"Database: `{DB_PATH}`")

# --- Data Loading ---
def load_data():
    if not os.path.exists(DB_PATH):
        st.error(f"DB file not found: {DB_PATH}")
        return pd.DataFrame()
    
    try:
        conn = sqlite3.connect(DB_PATH)
        query = "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT 1000"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
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

funcs = st.sidebar.multiselect("Function", df["func_name"].unique())
if funcs: df = df[df["func_name"].isin(funcs)]

result_types = st.sidebar.multiselect("Result Type", df["result_type"].unique())
if result_types: df = df[df["result_type"].isin(result_types)]

search = st.sidebar.text_input("Search Input ID")
if search: df = df[df["input_id"].str.contains(search, na=False)]


# --- Main Table ---
st.subheader("📋 Tasks")
event = st.dataframe(
    df[["cache_key", "updated_at", "func_name", "input_id", "result_type", "result_value"]],
    width="stretch",
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

# --- Detail & Restore ---
st.markdown("---")
st.subheader("🔍 Restore Data")

selected_key = None

if len(event.selection.rows) > 0:
    row_idx = event.selection.rows[0]
    selected_key = df.iloc[row_idx]["cache_key"]

if selected_key:
    st.info(f"Selected from table: `{selected_key}`")
else:
    st.info("Select Record from Table")

if selected_key:
    row = df[df["cache_key"] == selected_key].iloc[0]
    
    r_type = row["result_type"]
    r_val = row["result_value"]
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Metadata**")
        st.json(row.to_dict())
        
    with col2:
        st.write("**Content**")
        
        try:
            data = None
            if r_type == "DIRECT":
                data = json.loads(r_val)
            elif r_type == "FILE":
                # Auto Storage Detection
                with st.spinner("Loading Blob..."):
                    if r_val.startswith("s3://"):
                        storage = S3Storage(r_val) # 初期化時にバケット解析させる
                        data = storage.load(r_val)
                    else:
                        # ローカルパスの場合、実行場所との相対パス問題があるため
                        # 絶対パスか確認しつつ読み込む
                        if os.path.exists(r_val):
                            with open(r_val, 'rb') as f:
                                import pickle
                                data = pickle.load(f)
                        else:
                            st.error(f"File not found on this machine: {r_val}")
            
            if data:
                st.success("Restored successfully!")
                if isinstance(data, (dict, list)):
                    st.json(data)
                else:
                    st.text(str(data))
                    
        except Exception as e:
            st.error(f"Restore Failed: {e}")

