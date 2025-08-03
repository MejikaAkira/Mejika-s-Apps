import sqlite3
import csv
import os
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse

class Database:
    """
    百人一首データベース操作クラス
    - PostgreSQL/SQLite両対応
    - summaryカラム対応
    - embeddingカラムは廃止
    """
    def __init__(self, db_path: str = None):
        self.db_type = self._get_db_type()
        if self.db_type == 'postgresql':
            self.connection_string = os.getenv('DATABASE_URL')
            if not self.connection_string:
                raise ValueError("DATABASE_URL環境変数が設定されていません")
        else:
            self.db_path = db_path or "hyakunin_isshu.db"
        self.init_database()

    def _get_db_type(self) -> str:
        """データベースタイプを判定"""
        return 'postgresql' if os.getenv('DATABASE_URL') else 'sqlite'

    def _get_connection(self):
        """データベース接続を取得"""
        if self.db_type == 'postgresql':
            return psycopg2.connect(self.connection_string)
        else:
            return sqlite3.connect(self.db_path)

    def init_database(self) -> None:
        """テーブルがなければ作成（summaryカラム含む, embeddingカラムなし）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if self.db_type == 'postgresql':
                # PostgreSQL用のテーブル作成
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS hyakunin_isshu (
                        id INTEGER PRIMARY KEY,
                        poet TEXT NOT NULL,
                        poem TEXT NOT NULL,
                        summary TEXT
                    )
                ''')
            else:
                # SQLite用のテーブル作成
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS hyakunin_isshu (
                        id INTEGER PRIMARY KEY,
                        poet TEXT NOT NULL,
                        poem TEXT NOT NULL,
                        summary TEXT
                    )
                ''')
            
            conn.commit()

    def load_csv_data(self, csv_path: str = "data/hyakunin_isshu.csv") -> None:
        """
        CSVファイルからデータを読み込み、DBに格納
        summaryカラムも対応
        既存データは全削除
        """
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSVファイルが見つかりません: {csv_path}")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 既存データを削除
            cursor.execute("DELETE FROM hyakunin_isshu")
            
            # CSVデータを読み込み
            with open(csv_path, 'r', encoding='utf-8') as file:
                csv_reader = csv.DictReader(file)
                for row in csv_reader:
                    if self.db_type == 'postgresql':
                        cursor.execute(
                            '''INSERT INTO hyakunin_isshu (id, poet, poem, summary) VALUES (%s, %s, %s, %s)''',
                            (int(row['id']), row['poet'], row['poem'], row.get('summary', ''))
                        )
                    else:
                        cursor.execute(
                            '''INSERT INTO hyakunin_isshu (id, poet, poem, summary) VALUES (?, ?, ?, ?)''',
                            (int(row['id']), row['poet'], row['poem'], row.get('summary', ''))
                        )
            
            conn.commit()
            print(f"CSVデータをデータベースに読み込みました: {csv_reader.line_num - 1}件")

    def get_poem_by_id(self, poem_id: int) -> Optional[Dict[str, Any]]:
        """指定IDの歌を返す。なければNone"""
        with self._get_connection() as conn:
            if self.db_type == 'postgresql':
                cursor = conn.cursor(cursor_factory=RealDictCursor)
            else:
                cursor = conn.cursor()
            
            if self.db_type == 'postgresql':
                cursor.execute('''
                    SELECT id, poet, poem, summary FROM hyakunin_isshu WHERE id = %s
                ''', (poem_id,))
            else:
                cursor.execute('''
                    SELECT id, poet, poem, summary FROM hyakunin_isshu WHERE id = ?
                ''', (poem_id,))
            
            row = cursor.fetchone()
            if row:
                if self.db_type == 'postgresql':
                    poem_data = dict(row)
                else:
                    poem_data = {
                        'id': row[0],
                        'poet': row[1],
                        'poem': row[2],
                        'summary': row[3]
                    }
                
                # NFT情報を追加
                poem_data['nft_image_url'] = self._get_nft_image_url(poem_data['id'])
                poem_data['opensea_url'] = self._get_opensea_url(poem_data['id'])
                
                return poem_data
            return None

    def _get_nft_image_url(self, poem_id: int) -> str:
        """NFT画像URLを生成"""
        return f"https://ipfs.io/ipfs/QmS1yK1Dsoaxo3nRCxzhunGab4DmqCmLQfv4PrLBRw8svN/{poem_id}.png"

    def _get_opensea_url(self, poem_id: int) -> str:
        """OpenSeaリンクを生成"""
        return f"https://opensea.io/item/matic/0x3369d47b17f2c76427435ab5524c546458aa7f47/{poem_id}"

    def get_all_poems(self) -> List[Dict[str, Any]]:
        """全ての歌（summary含む）をリストで返す"""
        with self._get_connection() as conn:
            if self.db_type == 'postgresql':
                cursor = conn.cursor(cursor_factory=RealDictCursor)
            else:
                cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, poet, poem, summary FROM hyakunin_isshu ORDER BY id
            ''')
            
            if self.db_type == 'postgresql':
                poems = [dict(row) for row in cursor.fetchall()]
            else:
                poems = []
                for row in cursor.fetchall():
                    poems.append({
                        'id': row[0],
                        'poet': row[1],
                        'poem': row[2],
                        'summary': row[3]
                    })
            
            # NFT情報を各歌に追加
            for poem in poems:
                poem['nft_image_url'] = self._get_nft_image_url(poem['id'])
                poem['opensea_url'] = self._get_opensea_url(poem['id'])
            
            return poems

    def get_db_info(self) -> Dict[str, Any]:
        """データベース情報を返す"""
        return {
            'type': self.db_type,
            'path': self.db_path if self.db_type == 'sqlite' else 'postgresql',
            'total_poems': len(self.get_all_poems())
        } 