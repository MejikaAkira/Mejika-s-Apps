#!/usr/bin/env python3
"""
百人一首ベクトル検索システム - メインアプリケーション
summaryカラム対応・意味検索/DB検索切替・安全な無料枠制限対応
"""

from flask import Flask, render_template, request, jsonify
from database import Database
from vector_search import VectorSearch
import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import json
import calendar

app = Flask(__name__)

# 安全な無料枠制限設定（絶対に超えない値）
FREE_TIER_LIMITS = {
    'daily_searches': 50,  # 1日あたりの検索回数（保守的）
    'daily_tokens': 50000,  # 1日あたりのトークン数（保守的）
    'monthly_searches': 1000,  # 月間検索回数（保守的）
    'monthly_tokens': 800000,  # 月間トークン数（保守的）
    'cache_size_mb': 5  # キャッシュサイズ制限（MB）
}

# 使用量追跡（本番環境ではRedis等を使用）
usage_tracker = {
    'daily_searches': 0,
    'daily_tokens': 0,
    'monthly_searches': 0,
    'monthly_tokens': 0,
    'last_daily_reset': datetime.now().date(),
    'last_monthly_reset': datetime.now().replace(day=1).date()
}

def reset_usage_if_needed():
    """必要に応じて使用量をリセット"""
    today = datetime.now().date()
    first_day_of_month = today.replace(day=1)
    
    # 日次リセット
    if usage_tracker['last_daily_reset'] != today:
        usage_tracker['daily_searches'] = 0
        usage_tracker['daily_tokens'] = 0
        usage_tracker['last_daily_reset'] = today
    
    # 月次リセット
    if usage_tracker['last_monthly_reset'] != first_day_of_month:
        usage_tracker['monthly_searches'] = 0
        usage_tracker['monthly_tokens'] = 0
        usage_tracker['last_monthly_reset'] = first_day_of_month

def check_usage_limits() -> Dict[str, Any]:
    """使用量制限をチェック"""
    reset_usage_if_needed()
    
    return {
        'daily_searches_remaining': max(0, FREE_TIER_LIMITS['daily_searches'] - usage_tracker['daily_searches']),
        'daily_tokens_remaining': max(0, FREE_TIER_LIMITS['daily_tokens'] - usage_tracker['daily_tokens']),
        'monthly_searches_remaining': max(0, FREE_TIER_LIMITS['monthly_searches'] - usage_tracker['monthly_searches']),
        'monthly_tokens_remaining': max(0, FREE_TIER_LIMITS['monthly_tokens'] - usage_tracker['monthly_tokens']),
        'daily_limit_reached': usage_tracker['daily_searches'] >= FREE_TIER_LIMITS['daily_searches'],
        'daily_tokens_limit_reached': usage_tracker['daily_tokens'] >= FREE_TIER_LIMITS['daily_tokens'],
        'monthly_limit_reached': usage_tracker['monthly_searches'] >= FREE_TIER_LIMITS['monthly_searches'],
        'monthly_tokens_limit_reached': usage_tracker['monthly_tokens'] >= FREE_TIER_LIMITS['monthly_tokens']
    }

def estimate_tokens(text: str) -> int:
    """テキストのトークン数を概算（保守的）"""
    # 日本語の場合、文字数の約1.5倍がトークン数の目安
    # 安全のため2倍で計算
    return len(text) * 2

def get_db() -> Database:
    """DBインスタンスを返す（シングルトン）"""
    if not hasattr(app, 'db_instance'):
        app.db_instance = Database()
    return app.db_instance

def get_vector_search() -> VectorSearch:
    """VectorSearchインスタンスを返す（シングルトン）"""
    if not hasattr(app, 'vector_search_instance'):
        app.vector_search_instance = VectorSearch()
    return app.vector_search_instance

@app.route('/')
def index() -> str:
    """トップページを表示"""
    return render_template('index.html')

@app.route('/api/search', methods=['POST'])
def search() -> Any:
    """意味検索またはDB検索API（安全な無料枠制限付き）"""
    try:
        data = request.get_json()
        query: str = data.get('query', '').strip()
        top_k: int = int(data.get('top_k', 10))
        mode: str = data.get('mode', 'semantic')  # 'semantic' or 'db'
        
        if not query and mode == 'semantic':
            return jsonify({'status': 'error', 'message': '検索クエリが空です'}), 400
        if top_k not in [5, 10, 20]:
            top_k = 10
            
        # 使用量制限チェック
        usage_limits = check_usage_limits()
        
        if mode == 'semantic':
            # 意味検索の場合、全ての制限をチェック
            estimated_tokens = estimate_tokens(query)
            
            # 日次制限チェック
            if usage_limits['daily_limit_reached']:
                return jsonify({
                    'status': 'error', 
                    'message': '本日の検索回数上限に達しました。明日までお待ちください。',
                    'usage_limits': usage_limits
                }), 429
            
            if usage_limits['daily_tokens_limit_reached']:
                return jsonify({
                    'status': 'error', 
                    'message': '本日のトークン使用量上限に達しました。明日までお待ちください。',
                    'usage_limits': usage_limits
                }), 429
            
            # 月次制限チェック
            if usage_limits['monthly_limit_reached']:
                return jsonify({
                    'status': 'error', 
                    'message': '今月の検索回数上限に達しました。来月までお待ちください。',
                    'usage_limits': usage_limits
                }), 429
            
            if usage_limits['monthly_tokens_limit_reached']:
                return jsonify({
                    'status': 'error', 
                    'message': '今月のトークン使用量上限に達しました。来月までお待ちください。',
                    'usage_limits': usage_limits
                }), 429
            
            # 使用量を更新（検索実行前に）
            usage_tracker['daily_searches'] += 1
            usage_tracker['monthly_searches'] += 1
            usage_tracker['daily_tokens'] += estimated_tokens
            usage_tracker['monthly_tokens'] += estimated_tokens
        
        results: List[Dict] = []
        db = get_db()
        
        if mode == 'semantic':
            # 意味検索（embeddingファイルで検索→IDでDB参照）
            vector_search = get_vector_search()
            id_score_list = vector_search.search(query, top_k)
            for poem_id, similarity in id_score_list:
                poem = db.get_poem_by_id(poem_id)
                if poem:
                    poem['similarity'] = round(similarity, 4)
                    results.append(poem)
        elif mode == 'db':
            # DB検索（番号・歌人・歌冒頭5文字で部分一致）
            poems = db.get_all_poems()
            query_lower = query.lower()
            for poem in poems:
                if (
                    query_lower.isdigit() and str(poem['id']) == query_lower
                    or query_lower in poem['poet'].lower()
                    or poem['poem'].startswith(query)
                    or poem['poem'][:5] == query
                ):
                    results.append(poem)
            results = results[:top_k]
        else:
            return jsonify({'status': 'error', 'message': '検索モードが不正です'}), 400
            
        return jsonify({
            'status': 'ok',
            'query': query,
            'results': results,
            'total_found': len(results),
            'mode': mode,
            'usage_limits': usage_limits,
            'estimated_tokens': estimated_tokens if mode == 'semantic' else 0
        })
    except Exception as e:
        print(f"検索エラー: {e}")
        return jsonify({'status': 'error', 'message': '検索中にエラーが発生しました', 'error': str(e)}), 500

@app.route('/api/status')
def status() -> Any:
    """システム状態を返すAPI（使用量制限情報付き）"""
    try:
        db = get_db()
        db_info = db.get_db_info()
        
        # キャッシュ統計も取得
        vector_search = get_vector_search()
        cache_stats = vector_search.get_cache_stats()
        embedding_info = vector_search.get_embedding_info()
        
        # 使用量制限情報
        usage_limits = check_usage_limits()
        
        return jsonify({
            'status': 'ok',
            'database': db_info,
            'embedding': embedding_info,
            'cache_stats': cache_stats,
            'usage_limits': usage_limits,
            'free_tier_limits': FREE_TIER_LIMITS
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/poems')
def get_poems() -> Any:
    """全歌データを返すAPI（DB検索用）"""
    try:
        db = get_db()
        poems = db.get_all_poems()
        return jsonify({'status': 'ok', 'poems': poems, 'total': len(poems)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    print("=== 百人一首ベクトル検索システム ===")
    print("サーバーを起動中...")
    if not os.getenv('OPENAI_API_KEY'):
        print("警告: OPENAI_API_KEYが設定されていません。\n検索機能を使うには環境変数にAPIキーを設定してください。")
    try:
        db = get_db()
        total_poems = len(db.get_all_poems())
        print(f"データベース状態:\n  - 総歌数: {total_poems}")
        if total_poems == 0:
            print("\n警告: データがありません。CSVを確認してください。")
    except Exception as e:
        print(f"データベースエラー: {e}")
    
    # 本番環境用の設定
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    print(f"\nサーバーを起動します: http://localhost:{port}")
    app.run(debug=debug, host='0.0.0.0', port=port) 