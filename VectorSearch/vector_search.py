import os
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from openai import OpenAI
from dotenv import load_dotenv
from sklearn.metrics.pairwise import cosine_similarity
import json
import hashlib
import pickle

# 環境変数を読み込み
load_dotenv()

class VectorSearch:
    """
    embeddingファイル（embeddings.npy, embedding_ids.json）を使った意味検索専用クラス
    - DBアクセスは行わず、IDリストを返す
    - embeddingファイルが存在しない場合は初期化をスキップ（get_embeddingのみ使用可能）
    - クエリキャッシュ機能付き
    - 外部ストレージ対応
    """
    def __init__(self, embedding_path: str = None, id_path: str = None, cache_path: str = None) -> None:
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEYが設定されていません。.envファイルを確認してください。")
        self.client = OpenAI(api_key=api_key)
        self.model = "text-embedding-3-small"
        
        # ファイルパスの設定（環境変数優先）
        self.embedding_path = embedding_path or os.getenv('EMBEDDING_PATH', 'embeddings.npy')
        self.id_path = id_path or os.getenv('EMBEDDING_IDS_PATH', 'embedding_ids.json')
        self.cache_path = cache_path or os.getenv('CACHE_PATH', 'query_cache.pkl')
        
        # クエリキャッシュをロード
        self.query_cache = self._load_cache()
        
        # embeddingファイルが存在する場合のみロード
        if self._check_embedding_files():
            try:
                self.embeddings = np.load(self.embedding_path)
                with open(self.id_path, 'r', encoding='utf-8') as f:
                    self.id_list = json.load(f)
                if len(self.embeddings) != len(self.id_list):
                    raise ValueError("embeddings.npyとembedding_ids.jsonの件数が一致しません")
                self._embeddings_loaded = True
                print(f"✓ embeddingファイルをロードしました（{len(self.embeddings)}件）")
                print(f"✓ クエリキャッシュをロードしました（{len(self.query_cache)}件）")
            except Exception as e:
                print(f"⚠ embeddingファイルのロードに失敗: {e}")
                self._embeddings_loaded = False
        else:
            print("⚠ embeddingファイルが見つかりません。get_embeddingメソッドのみ使用可能です。")
            print(f"  期待されるパス: {self.embedding_path}, {self.id_path}")
            self._embeddings_loaded = False

    def _check_embedding_files(self) -> bool:
        """embeddingファイルの存在確認"""
        return os.path.exists(self.embedding_path) and os.path.exists(self.id_path)

    def _load_cache(self) -> Dict[str, List[float]]:
        """クエリキャッシュをロード"""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                print(f"⚠ キャッシュロードエラー: {e}")
        return {}

    def _save_cache(self) -> None:
        """クエリキャッシュを保存"""
        try:
            with open(self.cache_path, 'wb') as f:
                pickle.dump(self.query_cache, f)
        except Exception as e:
            print(f"⚠ キャッシュ保存エラー: {e}")

    def _get_cache_key(self, text: str) -> str:
        """テキストからキャッシュキーを生成"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def get_embedding(self, text: str) -> List[float]:
        """
        テキストをOpenAI APIでembedding（ベクトル化）
        キャッシュ機能付き
        """
        cache_key = self._get_cache_key(text)
        
        # キャッシュから取得を試行
        if cache_key in self.query_cache:
            print(f"✓ キャッシュからembeddingを取得: '{text[:20]}...'")
            return self.query_cache[cache_key]
        
        # API呼び出し
        try:
            print(f"🔄 APIからembeddingを取得: '{text[:20]}...'")
            response = self.client.embeddings.create(
                model=self.model,
                input=text
            )
            embedding = response.data[0].embedding
            
            # キャッシュに保存
            self.query_cache[cache_key] = embedding
            self._save_cache()
            
            return embedding
        except Exception as e:
            print(f"ベクトル化エラー: {e}")
            raise

    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """
        クエリに対し、embeddingファイルから類似度順に上位N件の(id, 類似度)を返す
        キャッシュ機能付き
        """
        if not self._embeddings_loaded:
            raise ValueError("embeddingファイルがロードされていません。init_db.pyを実行してください。")
        
        query_embedding = self.get_embedding(query)
        query_array = np.array(query_embedding).reshape(1, -1)
        # 全embeddingとコサイン類似度計算
        similarities = cosine_similarity(query_array, self.embeddings)[0]
        # 上位top_k件のインデックスを取得
        top_indices = similarities.argsort()[::-1][:top_k]
        # (ID, 類似度)のリストで返す
        return [(self.id_list[i], float(similarities[i])) for i in top_indices]

    def get_cache_stats(self) -> Dict[str, Any]:
        """キャッシュ統計を返す"""
        return {
            'cached_queries': len(self.query_cache),
            'cache_size_mb': os.path.getsize(self.cache_path) / (1024 * 1024) if os.path.exists(self.cache_path) else 0
        }

    def get_embedding_info(self) -> Dict[str, Any]:
        """embedding情報を返す"""
        return {
            'embeddings_loaded': self._embeddings_loaded,
            'embedding_path': self.embedding_path,
            'id_path': self.id_path,
            'total_embeddings': len(self.embeddings) if self._embeddings_loaded else 0,
            'files_exist': self._check_embedding_files()
        } 