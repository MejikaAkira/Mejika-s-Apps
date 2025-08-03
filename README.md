<<<<<<< HEAD
# VectorSearch
=======
# 百人一首ベクトル検索システム

美しい和風デザインとAI技術を融合した百人一首検索システムです。意味検索とDB検索の両方に対応し、各歌に対応するNFT画像とOpenSeaリンクも表示します。

## 🌸 特徴

### 🔍 検索機能
- **意味検索**: OpenAI APIを使用した自然言語検索
- **DB検索**: 番号・歌人・歌冒頭での高速検索
- **キャッシュ機能**: 重複クエリのAPIコール削減

### 🎨 NFT連携
- **美しいNFT画像**: 各歌に対応するNFT画像を表示
- **OpenSeaリンク**: 直接OpenSeaでNFTを確認可能
- **ホバーエフェクト**: 画像にマウスオーバーでOpenSeaリンク表示

### 💰 無料枠対応
- **安全な制限**: 絶対に無料枠を超えない設計
- **使用量表示**: リアルタイムで使用量を確認
- **コスト削減**: キャッシュ機能でAPIコール最小化

### 🎌 和風デザイン
- **美しいUI**: 桜・月・和紙風の装飾
- **レスポンシブ**: モバイル・デスクトップ対応
- **アクセシビリティ**: 読みやすいフォントとコントラスト

## 🚀 デプロイ対応

### 対応プラットフォーム
- **開発環境**: ローカル（SQLite）
- **本番環境**: Railway（PostgreSQL）
- **データベース**: SQLite/PostgreSQL両対応
- **embedding**: ファイルシステム/外部ストレージ対応

## 📦 インストール

### 1. リポジトリのクローン
```bash
git clone <repository-url>
cd VectorSearch
```

### 2. 依存関係のインストール
```bash
pip install -r requirements.txt
```

### 3. 環境変数の設定
```bash
cp env.example .env
# .envファイルを編集してOpenAI APIキーを設定
```

### 4. データベース初期化
```bash
python init_db.py
```

### 5. サーバー起動
```bash
python app.py
```

## 🔧 設定

### 環境変数
- `OPENAI_API_KEY`: OpenAI APIキー（必須）
- `DATABASE_URL`: PostgreSQL接続URL（本番環境）
- `EMBEDDING_PATH`: embeddingファイルパス
- `EMBEDDING_IDS_PATH`: embedding IDファイルパス
- `CACHE_PATH`: キャッシュファイルパス

### 無料枠制限
- **日次検索**: 50回
- **日次トークン**: 50K
- **月次検索**: 1,000回
- **月次トークン**: 800K

## 🎯 使用方法

### 意味検索
1. 検索ボックスに自然言語でクエリを入力
2. 「意味検索」を選択
3. 結果件数を選択（5/10/20件）
4. 検索実行

### DB検索
1. 番号・歌人・歌冒頭を入力
2. 「DB検索」を選択
3. 結果件数を選択
4. 検索実行

### NFT確認
- 検索結果のNFT画像にマウスオーバー
- OpenSeaリンクが表示される
- クリックでOpenSeaページに移動

## 📊 システム情報

### API エンドポイント
- `GET /`: メインページ
- `POST /api/search`: 検索API
- `GET /api/status`: システム状態
- `GET /api/poems`: 全歌データ

### データベース構造
```sql
CREATE TABLE hyakunin_isshu (
    id INTEGER PRIMARY KEY,
    poet TEXT NOT NULL,
    poem TEXT NOT NULL,
    summary TEXT
);
```

## 🛠️ 開発

### ファイル構造
```
VectorSearch/
├── app.py              # メインアプリケーション
├── database.py         # データベース操作
├── vector_search.py    # ベクトル検索
├── init_db.py          # 初期化スクリプト
├── requirements.txt    # 依存関係
├── data/
│   └── hyakunin_isshu.csv  # 歌データ
├── static/
│   ├── css/style.css   # スタイルシート
│   └── js/script.js    # JavaScript
└── templates/
    └── index.html      # メインテンプレート
```

### 技術スタック
- **バックエンド**: Flask, Python
- **データベース**: SQLite, PostgreSQL
- **AI**: OpenAI API (text-embedding-3-small)
- **フロントエンド**: HTML5, CSS3, JavaScript
- **デプロイ**: Railway

## 🔒 セキュリティ

### APIキー管理
- 環境変数での安全な管理
- GitHubへのプッシュ除外
- Railwayでの暗号化保存

### アクセス制御
- レート制限実装
- 使用量監視
- エラーハンドリング

## 📈 パフォーマンス

### 最適化
- クエリキャッシュ
- embedding事前計算
- データベースインデックス
- 画像遅延読み込み

### 監視
- リアルタイムログ
- 使用量統計
- エラー追跡

## 🤝 貢献

1. フォークを作成
2. フィーチャーブランチを作成
3. 変更をコミット
4. プルリクエストを作成

## 📄 ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## 🙏 謝辞

- 百人一首の歌データ提供者
- OpenAI API
- Railway プラットフォーム
- オープンソースコミュニティ

---

**美しい和風デザインと最新のAI技術で、百人一首の世界を体験してください。** 🌸
>>>>>>> daf9fe1 (initial commit for VectorSearch (NFT, Railway, PostgreSQL, semantic search, DB search, OpenSea link, Japanese UI))
