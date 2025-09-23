# 🔍 LogSense_v1 - RTX 3060向け超高速「間違い探し」AI

## 📝 プロジェクト概要
YOLO + CLIP + FAISS + OpenAI Realtime API を組み合わせて、**2枚の画像の差分を50ms以内に検出＆赤丸で可視化**し、**500ms以内に自然言語で音声出力**するシステム。

GPUは **RTX 3060 (12GB VRAM)** 前提で、解像度640px／FP16推論で最適化。

## 🚀 クイックスタート

### 1. 環境セットアップ
```bash
# 依存関係インストール
pip install -r requirements.txt
```

### 2. サンプル画像生成
```bash
python create_sample_images.py
```

### 3. 性能テスト実行
```bash
python test_performance.py
```

### 4. 手動実行
```bash
python diff_finder.py --a samples/image_a.png --b samples/image_b.png
```

## 📁 プロジェクト構造
```
LogSense_v1/
├── diff_finder.py          # メイン処理スクリプト
├── create_sample_images.py # テスト画像生成
├── test_performance.py     # 性能テスト
├── requirements.txt        # 依存関係
├── models/                 # YOLOモデル格納
├── out/                    # 出力ファイル
├── samples/                # テスト画像
└── README.md              # このファイル
```

## 🎯 性能目標
| 処理 | 目標時間 |
|------|----------|
| YOLO推論 A+B | ~30ms |
| CLIP埋め込み A+B | ~10ms |
| FAISS検索＋差分可視化 | ~10ms |
| **合計** | **~50ms以内** |
| LLM＋TTSストリーミング開始 | ~300ms開始、~500ms完了 |

## ⚙️ 技術仕様
- **GPU**: NVIDIA RTX 3060 12GB
- **CUDA**: 12.1
- **Python**: 3.10〜3.11
- **モデル**: YOLOv8s.pt + CLIP ViT-B-32
- **最適化**: FP16推論、バッチ処理、GPU FAISS

## 📊 出力ファイル
- `out/diff.png`: 差分を赤丸で可視化した画像
- `out/diff.json`: 差分情報（差分数、クラス一覧など）

## 🔧 カスタマイズ
- 解像度調整: `target_size` パラメータ（デフォルト640px）
- 類似度閾値: `threshold` パラメータ（デフォルト0.7）
- OpenAI API: `OPENAI_API_KEY` 環境変数で有効化

## 🎮 動作確認
1. サンプル画像でテスト実行
2. 50ms以内に差分画像が生成されることを確認
3. JSONに差分数・差分クラスが記録されることを確認
4. 音声応答（モックまたは実際のAPI）が開始されることを確認

## 🚀 将来拡張
- 動画入力対応（ByteTrackで追跡）
- Segmentationモデルに切替（精度強化）
- ユーザー別優先クラスフィルタ
