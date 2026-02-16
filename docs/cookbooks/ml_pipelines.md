## レシピ: 大規模 ML パイプラインの高速化

中間データの保存に時間がかかる ML パイプラインにおいて、計算と並行して保存を行うパターンです。

```python
import beautyspot as bs

spot = bs.Spot("ml_pipeline", default_wait=False, io_workers=8)

@spot.mark(save_blob=True)
def preprocess(raw_data):
    # 巨大な特徴量行列の生成
    return features

@spot.mark(save_blob=True)
def train(features):
    # モデル訓練
    return model

def main():
    with spot:
        # preprocess の保存（S3へのアップロード等）を待たずに
        # すぐに train 処理を開始できる
        raw = load_data()
        feat = preprocess(raw)
        model = train(feat)
        
    # パイプライン全体の完了後、すべての保存が終わるのを待ってから終了
    print("Pipeline finished and all caches persisted.")

```
