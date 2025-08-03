#!/usr/bin/env python3
"""
百人一首データベース初期化スクリプト
PostgreSQL/SQLite両対応・embeddingファイル生成
"""

import os
import sys
from database import Database
from vector_search import VectorSearch
from dotenv import load_dotenv

# 環境変数を読み込み
load_dotenv()

def main():
    print("=== 百人一首ベクトル検索システム - データベース初期化 ===")
    
    # データベース初期化
    try:
        print("\n1. データベースの初期化...")
        db = Database()
        db_info = db.get_db_info()
        print(f"✓ データベースタイプ: {db_info['type']}")
        print(f"✓ データベースパス: {db_info['path']}")
        
        # CSVデータの読み込み
        print("\n2. CSVデータの読み込み...")
        csv_path = "data/hyakunin_isshu.csv"
        if not os.path.exists(csv_path):
            print(f"❌ CSVファイルが見つかりません: {csv_path}")
            return False
        
        db.load_csv_data(csv_path)
        total_poems = len(db.get_all_poems())
        print(f"✓ 総歌数: {total_poems}")
        
        # embeddingファイルの生成
        print("\n3. embeddingファイルの生成...")
        vector_search = VectorSearch()
        
        # 各歌のembeddingを生成
        poems = db.get_all_poems()
        embeddings = []
        id_list = []
        
        for i, poem in enumerate(poems):
            print(f"  処理中: {i+1}/{len(poems)} - {poem['poet']}")
            
            # 歌のテキストを結合（歌人 + 歌 + 要約）
            text = f"{poem['poet']} {poem['poem']}"
            if poem.get('summary'):
                text += f" {poem['summary']}"
            
            try:
                embedding = vector_search.get_embedding(text)
                embeddings.append(embedding)
                id_list.append(poem['id'])
            except Exception as e:
                print(f"⚠ embedding生成エラー (ID {poem['id']}): {e}")
                continue
        
        # embeddingファイルの保存
        if embeddings:
            import numpy as np
            import json
            
            # embeddings.npyの保存
            embeddings_array = np.array(embeddings)
            embedding_path = os.getenv('EMBEDDING_PATH', 'embeddings.npy')
            np.save(embedding_path, embeddings_array)
            print(f"✓ embeddings.npyを保存: {embedding_path}")
            
            # embedding_ids.jsonの保存
            id_path = os.getenv('EMBEDDING_IDS_PATH', 'embedding_ids.json')
            with open(id_path, 'w', encoding='utf-8') as f:
                json.dump(id_list, f, ensure_ascii=False, indent=2)
            print(f"✓ embedding_ids.jsonを保存: {id_path}")
            
            print(f"✓ 生成完了: {len(embeddings)}件のembedding")
        else:
            print("❌ embeddingファイルの生成に失敗しました")
            return False
        
        # 最終確認
        print("\n4. 最終確認...")
        final_db = Database()
        final_vector_search = VectorSearch()
        
        db_info = final_db.get_db_info()
        embedding_info = final_vector_search.get_embedding_info()
        
        print(f"✓ データベース: {db_info['type']} ({db_info['total_poems']}件)")
        print(f"✓ embedding: {embedding_info['embeddings_loaded']} ({embedding_info['total_embeddings']}件)")
        
        if db_info['total_poems'] > 0 and embedding_info['embeddings_loaded']:
            print("\n🎉 初期化が完了しました！")
            print("サーバーを起動できます: python app.py")
            return True
        else:
            print("\n❌ 初期化に失敗しました")
            return False
            
    except Exception as e:
        print(f"\n❌ 初期化エラー: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 