# ml_ops（YOLO 学習・本番重みの管理）

`app.py` とは別系統です。ここで学習した `.pt` を、リポジトリ直下の **`yolo_stream_config.json`** の `model.weights` に書いたパスへ置く／指すだけで、GUI・デモはそのモデルを読みます。

## 必要なもの

- Python 3.10+（プロジェクトの venv で可）
- GPU 推奨（CPU でも動くが遅い）
- `pip install -r requirements-train.txt`

## データの置き場

- **学習用（ラベル付き）** … `datasets/curated/<名前>/` に YOLO 形式（`images/train` `images/val` `labels/train` `labels/val` と `data.yaml`）
- **未ラベル** … `datasets/incoming/`（任意）

## アプリとの関係

- **`app.py` や `video_process` は変更しない。**
- 推論でどの重みを使うかは、リポジトリ直下の **`yolo_stream_config.json`** の `"model": { "weights": "..." }` だけ編集する（例: `models/yolov8_custom.pt`）。

## 手順（ざっくり）

1. `datasets/curated/<自分のデータセット>/` に画像・ラベル・`data.yaml` を用意する（`example/` は空のスケルトンのみ）。
2. （任意）`python ml_ops/scripts/validate_dataset.py --data .../data.yaml`
3. 学習を実行する。

   ```bash
   cd LogSense_v5
   python ml_ops/scripts/train_batch.py --data ml_ops/datasets/curated/myset/data.yaml
   ```

4. 出力は `registry/candidates/<実行名>/weights/best.pt`。
5. 本番に採用する:

   ```bash
   python ml_ops/scripts/promote_weights.py --src registry/candidates/<実行名>/weights/best.pt --copy-to-models
   ```

   `--copy-to-models` で `models/yolov8_custom.pt` にもコピー（`yolo_stream_config.json` でこのパスを指せる）。

6. 推論で使う重みを変える: **`yolo_stream_config.json`** の `"model": { "weights": "..." }` を編集。

## ファイル

| パス | 役割 |
|------|------|
| `registry/manifest.json` | 最後に `promote_weights.py` で採用した重みの記録 |
| `registry/production/best.pt` | 本番採用コピー（promote 時） |
| `configs/train.default.yaml` | 学習パラメータの例（`train_batch.py` のデフォルト参照用） |

## スケジュール

定期実行は OS のタスクスケジューラや cron で `train_batch.py` を叩く。間隔は `configs/schedule.example.yaml` にメモ。
