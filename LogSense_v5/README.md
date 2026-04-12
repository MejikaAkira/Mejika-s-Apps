# LogSense v5

リアルタイム動画差分検出システム。カメラからの入力に対して、フレーム間の差分をリアルタイムで検出・保存します。

## 概要

LogSense v5は、カメラからのリアルタイム動画入力に対して、連続するフレーム間の差分を検出するシステムです。以下の機能を提供します：

- **リアルタイム動画処理**: カメラからの入力フレームをリアルタイムで処理
- **位置補正**: カメラの微小な動きを補正して、正確な差分検出を実現
- **差分検出**: 直前のフレームとの差分を検出し、変化を検知
- **自動保存**: 差分が検出されたフレームを自動保存
- **ノイズ除去**: カメラノイズによる誤検出を削減

## 主な機能

- **リアルタイム動画処理**: カメラからの入力フレームをリアルタイムで処理
- **位置補正**: カメラの微小な動きを自動的に補正
- **差分検出**: 連続するフレーム間の差分を検出
- **自動保存**: 差分が検出されたフレームを自動保存
- **ノイズ除去**: カメラノイズによる誤検出を削減

## セットアップ

### 必要な環境
- Python 3.8以上
- OpenCV（CUDA対応推奨）
- NumPy
- カメラ（PC内蔵カメラまたはUSBカメラ）

**注意**: OpenCVのCUDA対応版を使用する場合は、システムにCUDAがインストールされている必要があります。CUDA非対応版でも動作しますが、GPU最適化は使用できません。

### インストール

1. **仮想環境の作成とアクティベート**：
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# または
source venv/bin/activate  # Linux/Mac
```

2. **依存パッケージのインストール**：
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### GPU環境の確認

GPUを使用する場合は、OpenCVがCUDA対応である必要があります。確認方法：

```bash
python -c "import cv2; print(cv2.cuda.getCudaEnabledDeviceCount())"
```

1以上が返ればGPUが使用可能です。

## 使用方法

### 基本的な使い方

1. **設定ファイルの確認**：
   - `config.json`でカメラデバイスIDや処理パラメータを設定
   - デフォルトでは、デバイスID 0（デフォルトPCカメラ）を使用

2. **アプリケーションの起動**：
```bash
python video_process/realtime_video_processor.py
```

3. **処理の停止**：
   - `Ctrl+C`で処理を停止

4. **結果の確認**：
   - 差分が検出されたフレーム: `video_outputs/{timestamp}/frame_XXXXX.png`
   - 差分画像: `video_outputs/{timestamp}/frame_XXXXX_diff.png`
   - 差分が検出されなかったフレーム: `video_outputs/archive/{timestamp}/frame_XXXXX.png`

## 設定ファイル（config.json）

`config.json`の`realtime_video`セクションで、リアルタイム動画処理のパラメータを設定できます。

### カメラ設定

```json
"camera": {
  "device_id": 0,  // カメラデバイスID（0=デフォルトPCカメラ）
  "fps": 30        // カメラのFPS
}
```

### 差分検出設定

```json
"difference": {
  "threshold_pixels": 5000,    // 差分ピクセル数の閾値
  "threshold_ratio": 0.005,     // 差分ピクセル率の閾値（0.5%）
  "noise_threshold": 20         // ノイズ除去の閾値
}
```

- **threshold_pixels**: 差分ピクセル数の閾値（画像サイズに応じて調整）
- **threshold_ratio**: 差分ピクセル率の閾値（0.0-1.0）
- **noise_threshold**: ノイズ除去の閾値（カメラノイズを除外）

### 位置補正の最適化設定

```json
"alignment": {
  "homography_reuse_seconds": 0.1  // 位置補正結果を再利用する時間（秒）
}
```

- **homography_reuse_seconds**: 位置補正結果を再利用する時間（デフォルト: 0.1秒）
  - 値を大きくすると処理速度が向上しますが、精度が低下する可能性があります
  - 値を小さくすると精度が向上しますが、処理時間が増加する可能性があります

### 保存設定

```json
"save": {
  "archive_no_diff": true,                    // 差分なしフレームをアーカイブに保存
  "archive_path": "video_outputs/archive"     // アーカイブフォルダのパス
}
```

### バッファ設定

```json
"buffer": {
  "frame_buffer_size": 10,  // フレームバッファの最大サイズ
  "frame_queue_size": 5     // フレームキューの最大サイズ
}
```

詳細は`config.json`内のコメントを参照してください。

## 出力ファイル

### 差分検出時
- **元のフレーム**: `video_outputs/{timestamp}/frame_XXXXX.png`
- **差分画像**: `video_outputs/{timestamp}/frame_XXXXX_diff.png`

### 差分なし時
- **元のフレーム**: `video_outputs/archive/{timestamp}/frame_XXXXX.png`

## トラブルシューティング

### カメラが認識されない

1. カメラが接続されているか確認
2. `config.json`の`camera.device_id`を変更（0, 1, 2...を試す）
3. 他のアプリケーションがカメラを使用していないか確認

### 処理が遅い

1. `config.json`の`alignment.homography_reuse_seconds`を増やす（例: 0.2秒）
2. GPUが使用可能か確認
3. カメラの解像度を下げる（カメラ設定で調整）

### 誤検出が多い

1. `config.json`の`difference.noise_threshold`を上げる（例: 30-40）
2. `difference.threshold_pixels`を上げる（例: 10000）
3. `difference.threshold_ratio`を上げる（例: 0.01）

### 検出されない

1. `config.json`の`difference.noise_threshold`を下げる（例: 10-15）
2. `difference.threshold_pixels`を下げる（例: 2000）
3. `difference.threshold_ratio`を下げる（例: 0.002）

## プロジェクト構成

```
LogSense_v5/
├── video_process/                    # リアルタイム動画処理モジュール
│   └── realtime_video_processor.py  # メイン処理モジュール
├── process/                         # 画像処理モジュール（既存）
│   ├── alignment_utils.py           # 位置補正
│   ├── calculate_difference.py      # 差分計算
│   └── config_loader.py             # 設定ファイル読み込み
├── test/                            # テストスクリプト
│   ├── test_realtime_video_processor.py
│   ├── test_warmup_with_camera.py
│   └── test_warmup_with_camera_parallel.py
├── video_outputs/                   # 出力フォルダ
│   ├── {timestamp}/                 # 差分検出時のフレーム
│   └── archive/                     # 差分なし時のフレーム
├── config.json                      # 設定ファイル
├── requirements.txt                 # 依存パッケージ
└── README.md                        # このファイル
```

## ライセンス

このプロジェクトは独自のライセンスの下で提供されています。
MIT lisence

## 更新履歴

### v5.0
- リアルタイム動画差分検出機能の実装
- 位置補正の最適化
- ノイズ除去機能の追加
- 自動保存機能の実装
- config.jsonによる設定の外部化
