# 🔍 LogSense_v1 - RTX 3060向け超高速「間違い探し」AI

## 📝 プロジェクト概要
YOLO + CLIP + FAISS + OpenAI Realtime API を組み合わせて、**2枚の画像の差分を高速検出＆赤丸で可視化**し、**自然言語で音声出力**するシステム。

GPUは **RTX 3060 (12GB VRAM)** 前提で、解像度640px／FP16推論で最適化。

## 🚀 クイックスタート

### 1. 環境セットアップ
```bash
# 仮想環境作成・アクティベート
python -m venv venv
.\venv\Scripts\Activate.ps1

# 依存関係インストール
pip install -r requirements.txt
```

### 2. GUIアプリ起動（推奨）
```bash
python yolo_diff_gui_fixed.py
```

### 3. コマンドライン実行
```bash
python diff_finder.py --a samples/bird_a.PNG --b samples/bird_b.PNG
```

## 📁 プロジェクト構造
```
LogSense_v1/
├── diff_finder.py          # メイン処理スクリプト（CLIP+FAISS版）
├── yolo_diff_gui_fixed.py  # GUIアプリ（YOLO差分検出）
├── requirements.txt        # 依存関係
├── project.md             # プロジェクト仕様
├── models/                 # YOLOモデル格納
│   └── yolov8s.pt         # YOLOモデル
├── out/                    # 出力ファイル
│   ├── diff.png           # 差分可視化画像
│   └── diff.json          # 差分情報JSON
├── samples/                # テスト画像
│   ├── bird_a.PNG         # テスト画像A
│   ├── bird_b.PNG         # テスト画像B
│   └── coco_sample.jpg    # COCOサンプル
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

## 🖥️ GUI機能
- **画像選択**: 左側・右側の画像を個別選択
- **差分検出**: YOLOで物体検出後、類似度比較
- **可視化**: 左側画像に赤丸で差分を表示
- **結果表示**: 検出数・処理時間・詳細情報を表示

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
1. GUIアプリで画像を選択して差分検出
2. 左側画像に赤丸で差分が表示されることを確認
3. 処理時間・検出数・詳細情報が表示されることを確認
4. コマンドライン版でも同様の結果が得られることを確認

## 🚀 将来拡張
- 動画入力対応（ByteTrackで追跡）
- Segmentationモデルに切替（精度強化）
- ユーザー別優先クラスフィルタ
