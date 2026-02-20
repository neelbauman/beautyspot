## ☁️ . Cloud Storage via Rclone (Google Drive as S3)

**"無限のストレージを、無料で。"**

[Rclone](https://rclone.org/) を使って Google Drive などを S3 互換 API として公開し、それを `beautyspot` の保存先として利用するテクニックです。

### Step 1: Rclone の準備

以下のコマンドで、最新の安定版（Stable）をインストールします。

```bash
curl https://rclone.org/install.sh | sudo bash
```

rcloneで、Google Drive をリモート接続先として設定します。

```bash
rclone config

# 以後、指示に従ってGoogle Driveを選択。gdriveという名前で作成する。
```

ターミナルで Rclone を S3 ゲートウェイモードで起動します。

```bash
# Google Drive のリモート名が "gdrive" の場合
rclone serve s3 gdrive: \
    --addr 127.0.0.1:8080 \
    --auth-key my_access_key,my_secret_key \
    --vfs-cache-mode full \
    --vfs-cache-max-age 24h
```

### Step 2: Spot の設定

`s3_opts` で `endpoint_url` をローカルに向けます。

Google Drive へのアクセス制限を考えて、late limit をかけても良いでしょう。

```python
import beautyspot as bs

spot = bs.Spot(
    name="gdrive_project",
    tpm=60,
    # s3://{bucket_name} の形式で指定
    # Rcloneの場合、Google Drive直下のフォルダ名がバケット名として認識されます
    # Google Drive 直下に observability-storage という名前のディレクトリを作成した場合の Example
    storage_path="s3://observability-storage",
    
    # S3互換接続のためのオプション (Boto3 clientへの引数となります)
    s3_opts={
        "endpoint_url": "http://localhost:8080",
        "aws_access_key_id": "my_access_key",       # Rcloneの --auth-key で指定したID #pragma: allowlist secret
        "aws_secret_access_key": "my_secret_key",   # Rcloneの --auth-key で指定したSecret #pragma: allowlist secret
        "region_name": "us-east-1"        # ダミーでOKですが指定推奨
    }
)

@spot.mark(save_blob=True, version="v0.1.0")
@spot.consume(cost=1)
def generate_large_dataset():
    # 戻り値は自動的に Google Drive 上の 'beautyspot-data' フォルダ内に保存されます
    return b"..." * 1024 * 1024


if __name__ == "__main__":
    generate_large_dataset()

```
