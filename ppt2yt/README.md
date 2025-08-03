# PPTX to YouTube 動画自動生成システム (ppt2yt)

PPTXファイルからYouTube動画を自動生成し、アップロードまでを自動化するシステムです。

## 🚀 機能概要

- **台本生成**: PPTXの内容を基に対話形式の台本を自動生成
- **画像・動画処理**: スライド画像の抽出と埋め込み動画の処理（MP4形式でのスライド保存、埋め込み動画の正しい抽出）
- **BGM選定**: 台本の雰囲気に合わせたBGM自動選定
- **動画合成**: 画像、動画、音声、BGMの自動合成
- **サムネイル生成**: 動画内容を表現するサムネイル自動生成
- **YouTube投稿**: 自動アップロードとメタデータ設定

## 📁 システムアーキテクチャ

```
ppt2yt/
├── src/
│   ├── script_generator/     # 処理1 台本生成モジュール
│   ├── image_processor/      # 処理2 画像生成・処理モジュール
│   ├── bgm_selector/         # 処理3 BGM選定モジュール
│   ├── video_composer/       # 処理4 動画合成モジュール
│   ├── thumbnail_creator/    # 処理5 サムネイル生成モジュール
│   ├── youtube_uploader/     # 処理6 YouTube投稿モジュール
│   ├── config/                  # 設定ファイル
│   └── utils/                   # 共通ユーティリティ
├── input/                       # 入力PPTXファイル
├── output/                      # 各工程の出力ファイル
├── logs/                        # ログファイル
└── requirements.txt             # 依存パッケージ
```

## 🎬 動画処理機能

### 新しい動画処理機能

システムは以下の動画処理機能を提供します：

1. **スライド全体をMP4として保存**
   - 動画を含むスライドをPowerPointのSaveAs機能を使用してMP4形式で保存
   - 高品質な動画出力を実現

2. **埋め込み動画の正しい抽出**
   - PPTXファイル構造から直接動画ファイルを抽出
   - 動画のメタデータのみではなく、実際の動画ファイルを取得

3. **統合処理方式**
   - 動画の有無を事前に確認し、適切な形式で処理
   - 動画がある場合はMP4、ない場合はPNGとして保存

### 設定オプション

`config/config.yaml`で以下の設定が可能です：

```yaml
video_processing:
  extract_embedded_videos: true
  video_format: "mp4"  # 動画形式（mp4, gif）
  save_slides_as_video: true      # 動画があるスライドをMP4として保存
  extract_embedded_videos_properly: true  # 埋め込み動画を正しく抽出
  use_unified_processing: true    # 統合処理方式を使用
```

## 🛠️ セットアップ

### 1. 環境要件

- Python 3.8以上
- FFmpeg（動画処理用）

### 2. インストール

```bash
# リポジトリをクローン
git clone <repository-url>
cd ppt2yt

# 仮想環境を作成（推奨）
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依存パッケージをインストール
pip install -r requirements.txt
```

### 3. 設定

#### 環境変数の設定

`.env`ファイルを作成し、以下の設定を追加：

```env
# OpenAI API設定
OPENAI_API_KEY=your_openai_api_key_here

# YouTube API設定
YOUTUBE_CLIENT_ID=your_youtube_client_id_here
YOUTUBE_CLIENT_SECRET=your_youtube_client_secret_here
```

#### APIキーの取得

**OpenAI API**
1. [OpenAI Platform](https://platform.openai.com/)にアクセス
2. APIキーを生成
3. クレジットを追加

**YouTube API**
1. [Google Cloud Console](https://console.cloud.google.com/)にアクセス
2. プロジェクトを作成
3. YouTube Data API v3を有効化
4. OAuth 2.0クライアントIDを作成

### 4. FFmpegのインストール

**Windows:**
```bash
# Chocolateyを使用
choco install ffmpeg

# または公式サイトからダウンロード
# https://ffmpeg.org/download.html
```

**macOS:**
```bash
# Homebrewを使用
brew install ffmpeg
```

**Linux:**
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install ffmpeg

# CentOS/RHEL
sudo yum install ffmpeg
```

## 使用方法

### 簡単な実行手順（Windows）

1. **環境設定**：
   ```bash
   # 初回のみ実行
   setup_environment.bat
   ```

2. **APIキーの設定**：
   - `.env`ファイルを編集してAPIキーを設定
   - OpenAI APIキーとYouTube API設定が必要

3. **PPTXファイルの配置**：
   - `input`ディレクトリにPPTXファイルを配置

4. **スクリプト生成の実行**：
   ```bash
   run_script_generation.bat
   ```

### 手動実行（上級者向け）

```bash
# PPTXファイルから動画を生成
python main.py input/presentation.pptx

# 出力名を指定
python main.py input/presentation.pptx -o my_video

# 設定の検証のみ実行
python main.py --validate-only
```

### 出力ファイル

処理が完了すると、以下のファイルが生成されます：

- `output/scripts/`: 生成された台本（JSON形式）
- `output/images/`: 処理済み画像
- `output/audio/`: 音声・BGMファイル
- `output/videos/`: 合成動画
- `output/thumbnails/`: サムネイル画像

## 設定カスタマイズ

`config/config.yaml`ファイルで各種設定をカスタマイズできます：

- 動画品質設定
- 音声設定
- ログ設定
- エラーハンドリング設定

## 開発

### プロジェクト構造

```
src/
├── 01_script_generator/
│   ├── __init__.py
│   └── script_generator.py      # 台本生成ロジック
├── 02_image_processor/
│   ├── __init__.py
│   └── image_processor.py       # 画像処理ロジック
├── 03_bgm_selector/
│   ├── __init__.py
│   └── bgm_selector.py          # BGM選定ロジック
├── 04_video_composer/
│   ├── __init__.py
│   └── video_composer.py        # 動画合成ロジック
├── 05_thumbnail_creator/
│   ├── __init__.py
│   └── thumbnail_creator.py     # サムネイル生成ロジック
├── 06_youtube_uploader/
│   ├── __init__.py
│   └── youtube_uploader.py      # YouTube投稿ロジック
└── utils/
    ├── __init__.py
    ├── config.py                # 設定管理
    └── logger.py                # ログ管理
```

# 補足
OpenAIクライアントの初期化でproxiesパラメータを明示的に除外します

### テスト

```bash
# テストを実行
pytest

# 特定のテストを実行
pytest tests/test_script_generator.py
```

### コードフォーマット

```bash
# コードをフォーマット
black src/

# リンターを実行
flake8 src/
```

## トラブルシューティング

### よくある問題

1. **API制限エラー**
   - OpenAI APIのクレジット残高を確認
   - YouTube APIのクォータを確認

2. **FFmpegエラー**
   - FFmpegが正しくインストールされているか確認
   - パスが通っているか確認

3. **設定エラー**
   - `.env`ファイルの設定を確認
   - APIキーが正しく設定されているか確認

### ログの確認

ログファイルは`logs/app.log`に出力されます。エラーが発生した場合は、このファイルを確認してください。

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## 貢献

プルリクエストやイシューの報告を歓迎します。貢献する前に、以下の点を確認してください：

1. コードスタイルガイドに従う
2. テストを追加する
3. ドキュメントを更新する

## 動画処理機能

### 埋め込み動画の処理

PPTXファイルに埋め込まれた動画は自動的に検出され、以下の処理が行われます：

1. **動画検出**: スライド内の埋め込み動画を自動検出
2. **動画抽出**: 埋め込み動画を個別ファイルとして抽出
3. **GIF変換**: 動画をGIF形式に変換（設定可能）
4. **動画合成**: GIF動画を最終動画に組み込み

### 設定オプション

`config/config.yaml`の`video_processing`セクションで以下の設定が可能です：

```yaml
video_processing:
  extract_embedded_videos: true    # 埋め込み動画の抽出を有効化
  video_format: "gif"             # 動画形式（gif推奨）
  gif_fps: 10                     # GIFのフレームレート
  gif_quality: 85                 # GIFの品質
  max_video_duration: 30          # 最大動画長（秒）
  video_scale: "640x360"          # 動画のスケール
```

### 対応動画形式

- MP4
- AVI
- MOV
- WMV
- その他FFmpegが対応する形式

## 更新履歴

- v0.1.0: 初期バージョン（台本生成機能のみ実装）
- v0.2.0: 埋め込み動画処理機能を追加
- 今後のバージョンで各モジュールを順次実装予定 