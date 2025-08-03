# Railway デプロイ手順

## 前提条件
- GitHubアカウント
- Railwayアカウント（GitHubでサインアップ可能）
- OpenAI APIキー

## 1. Railwayアカウント作成
1. [Railway](https://railway.app/) にアクセス
2. GitHubアカウントでサインアップ
3. 新しいプロジェクトを作成

## 2. GitHubリポジトリの準備
1. このプロジェクトをGitHubにプッシュ
2. `.env`ファイルは**絶対にプッシュしない**（既に.gitignoreに含まれています）

## 3. Railwayプロジェクトの設定

### 3.1 リポジトリの接続
1. Railwayダッシュボードで「New Project」→「Deploy from GitHub repo」
2. VectorSearchリポジトリを選択
3. 「Deploy Now」をクリック

### 3.2 環境変数の設定
1. プロジェクトダッシュボードで「Variables」タブを選択
2. 以下の環境変数を追加：

```
OPENAI_API_KEY=your_actual_openai_api_key_here
FLASK_ENV=production
```

### 3.3 PostgreSQLデータベースの追加
1. 「New」→「Database」→「PostgreSQL」を選択
2. データベースが作成されたら、接続情報が自動的に`DATABASE_URL`環境変数に設定されます

## 4. データベース初期化

### 4.1 初期化スクリプトの実行
Railwayのコンソールまたはローカルで以下を実行：

```bash
python init_db.py
```

このスクリプトは以下を実行します：
- PostgreSQLテーブルの作成
- CSVデータの読み込み
- embeddingファイルの生成

### 4.2 embeddingファイルの管理
embeddingファイルは以下の方法で管理できます：

1. **ローカル生成**: `init_db.py`で生成後、Railwayにアップロード
2. **環境変数指定**: 外部ストレージのパスを指定
   ```
   EMBEDDING_PATH=/path/to/embeddings.npy
   EMBEDDING_IDS_PATH=/path/to/embedding_ids.json
   CACHE_PATH=/path/to/query_cache.pkl
   ```

## 5. デプロイの確認

### 5.1 デプロイ状況の確認
1. Railwayダッシュボードでデプロイ状況を確認
2. ログでエラーがないかチェック

### 5.2 動作確認
1. 提供されたURLにアクセス
2. 検索機能が正常に動作するかテスト
3. 使用量制限が正しく表示されるか確認
4. システム情報でデータベースとembeddingの状態を確認

## 6. カスタムドメイン（オプション）
1. 「Settings」→「Domains」でカスタムドメインを設定
2. SSL証明書は自動で発行されます

## 7. 監視とメンテナンス

### 7.1 ログの確認
- Railwayダッシュボードでリアルタイムログを確認
- エラーや警告がないか定期的にチェック

### 7.2 使用量の監視
- OpenAI API使用量の監視
- Railway使用量の監視（無料枠内に収まっているか）

### 7.3 システム情報の確認
- `/api/status`エンドポイントでシステム状態を確認
- データベース接続、embeddingファイル、キャッシュ状態を監視

## 8. トラブルシューティング

### 8.1 よくある問題
- **環境変数が読み込まれない**: Railwayダッシュボードで再設定
- **データベース接続エラー**: PostgreSQL接続情報を確認
- **embeddingファイルが見つからない**: ファイルパスを確認
- **初期化エラー**: `init_db.py`の実行ログを確認

### 8.2 ログの確認方法
1. Railwayダッシュボードで「Deployments」を選択
2. 該当するデプロイメントのログを確認

## 9. セキュリティ注意事項

### 9.1 APIキーの管理
- OpenAI APIキーは絶対にGitHubにプッシュしない
- Railwayの環境変数で安全に管理
- 定期的にAPIキーをローテーション

### 9.2 アクセス制御
- 必要に応じて認証機能を追加
- レート制限の設定を確認

## 10. コスト管理

### 10.1 無料枠の活用
- 現在の制限設定で無料枠内に収まる設計
- 使用量を定期的に監視

### 10.2 スケーリング
- 必要に応じて有料プランにアップグレード
- 使用量に応じた適切なプラン選択

## 11. 技術仕様

### 11.1 対応データベース
- **開発環境**: SQLite
- **本番環境**: PostgreSQL（Railway）

### 11.2 embeddingファイル管理
- **ローカル**: ファイルシステム
- **本番**: 環境変数で指定可能

### 11.3 キャッシュ機能
- クエリキャッシュでAPIコール削減
- ファイルベースの永続化 