# 🤖 LLM Applications (LangChain / LlamaIndex)

LLM（大規模言語モデル）を活用したアプリケーションにおいて、`beautyspot` は API コストの節約、開発中の試行錯誤の高速化、およびプロバイダーのレート制限遵守を強力にサポートします。

## 🦜 1. LangChain との統合

LangChain のエコシステムでは、`beautyspot` をカスタムキャッシュとしてラップして使用するか、特定の Chain や Tool の実行を直接キャッシュするのが効果的です。

### 特定の関数をキャッシュする

最もシンプルな方法は、LLM を呼び出すラッパー関数を定義することです。

```python
import beautyspot as bs
from langchain_openai import ChatOpenAI

spot = bs.Spot("langchain_app")

@spot.mark(version="v1")  # プロンプトを変えたら version を更新
def get_llm_response(query: str):
    llm = ChatOpenAI(model="gpt-4")
    return llm.invoke(query).content

# 2回目以降は API を叩かずにキャッシュから返却
response = get_llm_response("富士山の高さは？")

```

## 🗂️ 2. LlamaIndex でのデータ埋め込み（Embeddings）のキャッシュ

RAG（検索拡張生成）アプリケーションにおいて、ドキュメントの埋め込み生成は最もコストと時間がかかる工程の一つです。

```python
import beautyspot as bs
from llama_index.embeddings.openai import OpenAIEmbedding

spot = bs.Spot("llamaindex_app")

# Embeddings 生成は大量に発生するため、save_blob=True を推奨
@spot.mark(save_blob=True)
def get_text_embedding(text: str):
    embed_model = OpenAIEmbedding()
    return embed_model.get_text_embedding(text)

# 大量のテキストを処理しても、一度計算したものは永続化される
embeddings = [get_text_embedding(t) for t in my_documents]

```

## ⏳ 3. レート制限とコスト管理

多くの LLM プロバイダーには TPM (Tokens Per Minute) や RPM (Requests Per Minute) の制限があります。`@spot.consume` を使うことで、これらの制限を超えないように自動調整できます。

```python
# 1分間に 20 リクエストに制限
@spot.mark
@spot.consume(cost=1)
def safe_llm_call(prompt: str):
    # API 呼び出し
    ...

# バッチ処理を行っても、自動的に適切な間隔で実行される
for p in heavy_prompts:
    safe_llm_call(p)

```

## 📝 4. プロンプトのバージョン管理

LLM アプリケーションにおいて、プロンプトは「コード」の一部です。プロンプトを微調整した際に古いキャッシュが返されないよう、`version` 引数を活用します。

```python
PROMPT_TEMPLATE = "あなたは誠実なアシスタントです。質問に答えてください: {query}"
PROMPT_VERSION = "2024-05-20-v1"

@spot.mark(version=PROMPT_VERSION)
def ask_assistant(query: str):
    prompt = PROMPT_TEMPLATE.format(query=query)
    # LLM 呼び出し...
    ...

```

> **Tip:** プロンプト文字列自体のハッシュ値を `version` に指定することで、プロンプトを変更した瞬間に自動的にキャッシュを無効化する運用も可能です。

## ⚡ 5. ユーザー体験の向上 (Non-blocking)

チャットアプリなどの対話型 UI では、推論結果をユーザーに返した後に、裏側でキャッシュを保存するのが理想的です。`default_wait=False` を設定することで、保存処理を待たずにレスポンスを返せます。

```python
# 保存をバックグラウンドスレッドへオフロード
spot = bs.Spot("chat_app", default_wait=False, io_workers=4)

```

