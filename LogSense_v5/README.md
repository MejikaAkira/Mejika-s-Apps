# LogSense v4

画像間の差分検出システム。位置補正、特徴点検出、差分計算を自動実行します。

## 概要

LogSense v4は、2枚以上の画像を比較して差分を検出するシステムです。以下の機能を提供します：

- **画像位置補正**: SIFT/ORB特徴点検出による自動位置補正
- **差分計算**: 位置補正後の画像間の差分を計算
- **GPU/CPUハイブリッド最適化**: 処理速度を最適化
- **設定ファイル管理**: `config.json`による柔軟な設定

## 主な機能

### 1. 画像位置補正
- **特徴点検出**: SIFTまたはORBを使用（`config.json`で選択可能）
- **特徴点マッチング**: GPU/CPUで高速マッチング
- **ホモグラフィ計算**: RANSACアルゴリズムによる位置補正

### 2. 差分計算
- **パディング除外**: リサイズ時のパディング領域を正確に除外
- **輪郭抽出**: 差分領域の輪郭を抽出してJSON形式で保存
- **可視化**: 差分画像をPNG形式で保存

### 3. GPU/CPUハイブリッド最適化
- **自動デバイス選択**: 画像サイズに応じてGPU/CPUを自動選択
- **転送オーバーヘッド最小化**: GPU転送回数を最小化して高速化
- **設定可能**: `config.json`で各処理のデバイスを指定可能

## セットアップ

### 必要な環境
- Python 3.8以上
- OpenCV（CUDA対応推奨）
- NumPy

**注意**: OpenCVのCUDA対応版を使用する場合は、システムにCUDAがインストールされている必要があります。CUDA非対応版でも動作しますが、GPU最適化は使用できません。

### インストール

1. 仮想環境の作成とアクティベート：
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# または
source venv/bin/activate  # Linux/Mac
```

2. 依存パッケージのインストール：
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

1. **画像の配置**:
   - `image_inputs/`フォルダに、タイムスタンプ名のフォルダを作成
   - 基準画像を`*_base.png`（または`*_base.jpg`）として配置
   - 比較対象画像を同じフォルダに配置

   例：
   ```
   image_inputs/
     └── 20251107_231639/
         ├── room1_base.png
         └── room1_b.png
   ```

2. **パイプラインの実行**:
```bash
python process/pipeline.py
```

3. **結果の確認**:
   - 差分画像: `diff_outputs/{timestamp}/{base_name}_vs_{other_name}_difference.png`
   - 輪郭データ: `diff_outputs/{timestamp}/{base_name}_vs_{other_name}_contours.json`
   - 位置補正画像: `diff_outputs/{timestamp}/{base_name}_vs_{other_name}_aligned_base.png`

## 設定ファイル（config.json）

`config.json`で処理パラメータを設定できます。

### 特徴点検出設定

```json
"feature_detector": {
  "type": "ORB",  // "SIFT" または "ORB"
  "device": "CPU"  // "CPU" または "GPU"（SIFTはCPUのみ）
}
```

- **SIFT**: 高精度だが遅い（CPUのみ）
- **ORB**: 高速だが精度はやや低い（CPU/GPU対応）

### 記述子マッチング設定

```json
"descriptor_matching": {
  "device": "GPU"  // "CPU" または "GPU"
}
```

- **GPU**: 大規模データで高速（数千個の特徴点）
- **CPU**: 小規模データで高速（数百個の特徴点）

### 画像処理設定

```json
"image_processing": {
  "sharpen": "CPU",      // "auto", "CPU", "GPU"
  "resize": "CPU",       // "auto", "CPU", "GPU"
  "gaussian_blur": "CPU", // "auto", "CPU", "GPU"
  "warp_perspective": "CPU", // "auto", "CPU", "GPU"
  "absdiff": "CPU"       // "auto", "CPU", "GPU"
}
```

- **auto**: 画像サイズに応じて自動選択（1280x720以上でGPU）
- **CPU**: 常にCPUで処理（推奨：GPU転送オーバーヘッドを回避）
- **GPU**: 常にGPUで処理

### ORB設定

```json
"orb": {
  "nfeatures": 500,      // 最大特徴点数
  "scaleFactor": 1.2,    // スケールファクター
  "nlevels": 8          // ピラミッドレベル数
}
```

### SIFT設定

```json
"sift": {
  "max_features": 0,           // 最大特徴点数（0=無制限）
  "contrast_threshold": 0.04,  // コントラスト閾値
  "edge_threshold": 10,        // エッジ閾値
  "sigma": 1.6                 // ガウシアンシグマ
}
```

詳細は`config.json`内のコメントを参照してください。

## プロジェクト構成

```
LogSense_v4/
├── process/                    # 処理モジュール
│   ├── pipeline.py            # メインパイプライン
│   ├── sharpen_images.py      # 画像シャープ化
│   ├── alignment_utils.py     # 位置補正（特徴点検出、マッチング、ホモグラフィ）
│   ├── calculate_difference.py # 差分計算
│   ├── gpu_utils.py           # GPU/CPUユーティリティ
│   └── config_loader.py        # 設定ファイル読み込み
├── image_inputs/               # 入力画像フォルダ
│   └── {timestamp}/           # タイムスタンプ名のフォルダ
│       ├── {name}_base.png    # 基準画像
│       └── {name}_*.png       # 比較対象画像
├── diff_outputs/               # 差分結果出力フォルダ
│   └── {timestamp}/           # タイムスタンプ名のフォルダ
│       ├── {base}_vs_{other}_difference.png  # 差分画像
│       ├── {base}_vs_{other}_contours.json   # 輪郭データ
│       └── {base}_vs_{other}_aligned_base.png # 位置補正画像
├── config.json                # 設定ファイル
├── requirements.txt           # 依存パッケージ
└── README.md                 # このファイル
```

## 処理フロー

1. **画像読み込み**: `image_inputs/{timestamp}/`から画像を読み込み
2. **画像シャープ化**: アンシャープマスクによるシャープ化処理
3. **位置補正**:
   - 特徴点検出（SIFT/ORB）
   - 特徴点マッチング
   - ホモグラフィ計算
   - 画像変換（warpPerspective）
4. **差分計算**:
   - 位置補正後の画像間の差分を計算
   - パディング領域を除外
   - 輪郭抽出
5. **結果保存**: 差分画像、輪郭データ、位置補正画像を保存

## GPU/CPU最適化の詳細

### 最適化方針

- **GPU**: 並列処理が得意な処理（リサイズ、フィルタ、差分計算、画像変換）
- **CPU**: 複雑なアルゴリズム（特徴点検出、RANSAC、JSON処理）

### 転送オーバーヘッドの最小化

GPU転送には時間がかかるため、以下の方針で最適化：

1. **バッチ処理**: 複数の処理をGPU上で連続実行
2. **転送回数最小化**: 必要な時だけ`upload()`/`download()`を実行
3. **自動選択**: 画像サイズに応じてGPU/CPUを自動選択（`auto`モード）

### パフォーマンス

- **処理速度**: 画像サイズと設定に依存（通常0.3-0.8秒/画像ペア）
- **GPU使用時**: 大規模画像（1280x720以上）で高速化
- **CPU使用時**: 小規模画像でGPU転送オーバーヘッドを回避

## 出力ファイル

### 差分画像（`*_difference.png`）
位置補正後の画像間の差分を可視化した画像。白い部分が差分領域です。

### 輪郭データ（`*_contours.json`）
差分領域の輪郭座標をJSON形式で保存。以下の形式：

```json
{
  "contours": [
    {
      "points": [[x1, y1], [x2, y2], ...],
      "area": 1234.5
    },
    ...
  ]
}
```

### 位置補正画像（`*_aligned_base.png`）
基準画像を比較対象画像の位置に合わせて変換した画像。

## トラブルシューティング

### GPUが使用されない

1. OpenCVがCUDA対応か確認：
```bash
python -c "import cv2; print(cv2.cuda.getCudaEnabledDeviceCount())"
```

2. `config.json`で`device`が`"GPU"`または`"auto"`になっているか確認

3. 環境変数`USE_GPU=true`が設定されているか確認

### 位置補正が失敗する

- 特徴点が少ない場合、`config.json`で特徴点数を増やす
- ORB使用時: `orb.nfeatures`を増やす（例: 1000）
- SIFT使用時: `sift.contrast_threshold`を下げる（例: 0.03）

### 差分画像に不要な線が表示される

- パディング除外機能により、リサイズ時の黒い領域は自動的に除外されます
- 問題が続く場合は、`alignment_utils.py`のマスク処理を確認

## ライセンス

このプロジェクトは独自のライセンスの下で提供されています。

## 更新履歴

### v4.0
- GPU/CPUハイブリッド最適化の実装
- SIFT/ORB特徴点検出の選択可能化
- `config.json`による設定管理
- パディング除外機能の実装
- 動的画像読み込み（`_base`画像と他の画像の比較）
