## 🕸️ . Web Scraping & Rate Limiting

スクレイピングにおける「マナー（アクセス頻度制限）」と「効率（キャッシュ）」を同時に実現します。

```python
import requests
import beautyspot as bs

# TPM (Tokens Per Minute) = 20 -> 3秒に1回のリクエスト制限
spot = bs.Spot("crawler", tpm=20)

@spot.mark
@spot.limiter(cost=1)
def fetch_page(url: str):
    print(f"Accessing {url}...")
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.text

# 連続で呼び出しても、自動的に待機時間が挿入されます
urls = [f"[https://example.com/page/](https://example.com/page/){i}" for i in range(10)]
for u in urls:
    html = fetch_page(u)

```
