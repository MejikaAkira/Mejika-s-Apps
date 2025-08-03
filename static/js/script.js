// =====================
// DOM要素の取得（必ず最初に）
// =====================
const searchQuery = document.getElementById('searchQuery');
const searchButton = document.getElementById('searchButton');
const resultCount = document.getElementById('resultCount');
const statusMessage = document.getElementById('statusMessage');
const loadingIndicator = document.getElementById('loadingIndicator');
const resultsContainer = document.getElementById('resultsContainer');
const semanticModeBtn = document.getElementById('semanticModeBtn');
const dbModeBtn = document.getElementById('dbModeBtn');
const semanticSearchForm = document.getElementById('semanticSearchForm');
const dbSearchForm = document.getElementById('dbSearchForm');
const dbIdSelect = document.getElementById('dbIdSelect');
const dbPoetSelect = document.getElementById('dbPoetSelect');
const dbHeadSelect = document.getElementById('dbHeadSelect');
const dbQueryInput = document.getElementById('dbQueryInput');
const dbSearchButton = document.getElementById('dbSearchButton');
const resultCountDb = document.getElementById('resultCountDb');

let currentMode = 'semantic';

// =====================
// 共通APIリクエスト関数
// =====================
/**
 * APIリクエスト共通関数
 * @param {string} url - エンドポイント
 * @param {object} options - fetchオプション
 * @returns {Promise<object>} - レスポンスJSON
 */
async function apiRequest(url, options = {}) {
    try {
        const res = await fetch(url, options);
        const data = await res.json();
        if (!res.ok || data.status === 'error') {
            throw new Error(data.message || 'APIエラー');
        }
        return data;
    } catch (err) {
        throw err;
    }
}

// =====================
// システムステータス確認
// =====================
/**
 * システムの準備状況をAPI経由で確認し、UIに反映
 */
async function checkSystemStatus() {
    try {
        const data = await apiRequest('/api/status');
        if (data.ready) {
            showStatus(`システム準備完了 (${data.total_poems}件の歌で検索可能)`, 'success');
        } else {
            showStatus('システム準備中: embeddingの生成が必要です', 'error');
        }
    } catch (err) {
        showStatus('システム接続エラー: ' + err.message, 'error');
    }
}

// =====================
// DB検索用プルダウン初期化
// =====================
/**
 * DB検索用プルダウン（歌番号・歌人・歌冒頭5文字）をAPIから動的生成
 */
async function populateDbSearchDropdowns() {
    try {
        const data = await apiRequest('/api/poems');
        const poems = data.poems;
        console.log('poems:', poems); // デバッグ用
        dbIdSelect.innerHTML = '<option value="">歌番号で選択</option>' + poems.map(p => `<option value="${p.id}">${p.id}</option>`).join('');
        const poets = [...new Set(poems.map(p => p.poet))];
        dbPoetSelect.innerHTML = '<option value="">歌人で選択</option>' + poets.map(poet => `<option value="${poet}">${poet}</option>`).join('');
        const heads = [...new Set(poems.map(p => p.poem.slice(0,5)))];
        dbHeadSelect.innerHTML = '<option value="">歌冒頭5文字で選択</option>' + heads.map(h => `<option value="${h}">${h}</option>`).join('');
    } catch (err) {
        showStatus('歌データ取得エラー: ' + err.message, 'error');
    }
}

// =====================
// 検索モード切替UI
// =====================
semanticModeBtn.addEventListener('click', () => {
    currentMode = 'semantic';
    semanticModeBtn.classList.add('active');
    dbModeBtn.classList.remove('active');
    semanticSearchForm.classList.add('active');
    dbSearchForm.classList.remove('active');
    semanticSearchForm.style.display = 'block';
    dbSearchForm.style.display = 'none';
    semanticModeBtn.setAttribute('aria-selected', 'true');
    dbModeBtn.setAttribute('aria-selected', 'false');
    showStatus('意味検索モード', 'success');
});
dbModeBtn.addEventListener('click', () => {
    currentMode = 'db';
    dbModeBtn.classList.add('active');
    semanticModeBtn.classList.remove('active');
    dbSearchForm.classList.add('active');
    semanticSearchForm.classList.remove('active');
    semanticSearchForm.style.display = 'none';
    dbSearchForm.style.display = 'block';
    dbModeBtn.setAttribute('aria-selected', 'true');
    semanticModeBtn.setAttribute('aria-selected', 'false');
    showStatus('DB検索モード', 'success');
});

// =====================
// 検索実行（意味検索/DB検索共通）
// =====================
/**
 * 検索実行（意味検索/DB検索共通）
 * @param {string} query - 検索クエリ
 * @param {number} topK - 上位件数
 * @param {string} mode - 'semantic' or 'db'
 */
async function performSearchUnified(query, topK, mode) {
    if (!query) {
        showStatus('検索クエリを入力してください', 'error');
        return;
    }
    showLoading(true);
    showStatus('検索中...', '');
    try {
        const data = await apiRequest('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, top_k: topK, mode })
        });
        displayResults(data);
        showStatus(`検索完了: ${data.total_found}件の結果`, 'success');
    } catch (err) {
        showStatus('検索エラー: ' + err.message, 'error');
        displayError(err.message);
    } finally {
        showLoading(false);
    }
}

/**
 * embedding生成が完了するまでリトライしながら検索を実行（最大5回、1.5秒間隔）
 */
async function performSearchWithRetry(query, topK, mode, maxRetry = 5, interval = 1500) {
    let attempt = 0;
    while (attempt < maxRetry) {
        try {
            const data = await apiRequest('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, top_k: topK, mode })
            });
            if (data.status === 'ok') {
                displayResults(data);
                showStatus(`検索完了: ${data.total_found}件の結果`, 'success');
                return;
            } else {
                showStatus('検索準備中...再試行します', 'info');
            }
        } catch (err) {
            showStatus('embedding生成待ち...再試行します', 'info');
        }
        attempt++;
        await new Promise(res => setTimeout(res, interval));
    }
    showStatus('embedding生成に時間がかかっています。しばらくしてから再度お試しください。', 'error');
}

// =====================
// イベントリスナー登録
// =====================
searchButton.addEventListener('click', () => {
    const query = searchQuery.value.trim();
    const topK = parseInt(resultCount.value);
    // 意味検索はリトライ付きで実行
    performSearchWithRetry(query, topK, 'semantic');
});
// 検索ボックスでEnterキー押下時に検索（デフォルト送信を防ぐ）
searchQuery.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        const query = searchQuery.value.trim();
        const topK = parseInt(resultCount.value);
        performSearchWithRetry(query, topK, 'semantic');
    }
});
// フォーム送信時もリロードを防ぐ
semanticSearchForm.addEventListener('submit', function(e) {
    e.preventDefault();
    const query = searchQuery.value.trim();
    const topK = parseInt(resultCount.value);
    performSearchWithRetry(query, topK, 'semantic');
});
resultCount.addEventListener('change', function() {
    if (resultsContainer.querySelector('.search-results')) {
        const query = searchQuery.value.trim();
        const topK = parseInt(resultCount.value);
        performSearchWithRetry(query, topK, 'semantic');
    }
});
if (dbSearchButton) {
    dbSearchButton.addEventListener('click', () => {
        let query = dbQueryInput.value.trim();
        if (!query) {
            if (dbIdSelect.value) query = dbIdSelect.value;
            else if (dbPoetSelect.value) query = dbPoetSelect.value;
            else if (dbHeadSelect.value) query = dbHeadSelect.value;
        }
        const topK = parseInt(resultCountDb.value);
        // DB検索は従来通り
        performSearchUnified(query, topK, 'db');
    });
}

// =====================
// 検索結果の表示
// =====================
/**
 * 検索結果を表示
 * @param {object} data - APIからのレスポンスデータ
 */
function displayResults(data) {
    const { query, results, total_found, mode } = data;
    
    const resultsContainer = document.getElementById('results');
    const resultsList = document.getElementById('results-list');
    const resultsTitle = document.getElementById('results-title');
    const resultsCount = document.getElementById('results-count');
    const searchModeBadge = document.getElementById('search-mode-badge');
    
    // 結果コンテナを表示
    resultsContainer.style.display = 'block';
    
    // タイトルとメタ情報を更新
    resultsTitle.textContent = `検索結果: "${query}"`;
    resultsCount.textContent = `${total_found}件`;
    
    // 検索モードバッジを更新
    searchModeBadge.textContent = mode === 'semantic' ? '意味検索' : 'DB検索';
    searchModeBadge.style.display = 'inline-block';
    
    // 結果リストをクリア
    resultsList.innerHTML = '';
    
    if (results.length === 0) {
        resultsList.innerHTML = `
            <div class="no-results">
                <p>検索結果が見つかりませんでした。</p>
                <p>別のキーワードでお試しください。</p>
            </div>
        `;
        return;
    }
    
    // テンプレートを取得
    const template = document.getElementById('result-template');
    
    // 各結果を表示
    results.forEach(result => {
        const resultElement = template.content.cloneNode(true);
        
        // 基本情報を設定
        resultElement.querySelector('.poem-number').textContent = result.id;
        resultElement.querySelector('.poet-name').textContent = result.poet;
        resultElement.querySelector('.poem-text').textContent = result.poem;
        
        // 要約がある場合は表示
        if (result.summary) {
            const summaryElement = resultElement.querySelector('.poem-summary');
            summaryElement.textContent = result.summary;
            summaryElement.style.display = 'block';
        }
        
        // 類似度スコアがある場合は表示（意味検索の場合）
        if (result.similarity !== undefined) {
            const similarityElement = resultElement.querySelector('.similarity-score');
            similarityElement.textContent = `類似度: ${(result.similarity * 100).toFixed(1)}%`;
            similarityElement.style.display = 'inline-block';
        }
        
        // NFT画像とOpenSeaリンクを設定
        if (result.nft_image_url) {
            const nftImage = resultElement.querySelector('.nft-image');
            nftImage.src = result.nft_image_url;
            nftImage.alt = `百人一首 #${result.id} NFT画像`;
            
            // 画像読み込みエラー時の処理
            nftImage.onerror = function() {
                this.style.display = 'none';
                this.parentElement.innerHTML = `
                    <div class="nft-placeholder">
                        <span class="placeholder-icon">🎨</span>
                        <span class="placeholder-text">NFT画像</span>
                    </div>
                `;
            };
        }
        
        if (result.opensea_url) {
            const openseaLink = resultElement.querySelector('.opensea-link');
            openseaLink.href = result.opensea_url;
            openseaLink.title = `OpenSeaで百人一首 #${result.id} を確認`;
        }
        
        // 結果リストに追加
        resultsList.appendChild(resultElement);
    });
    
    // 結果コンテナまでスクロール
    resultsContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// =====================
// エラー表示
// =====================
/**
 * エラーメッセージを表示
 * @param {string} message - エラーメッセージ
 */
function displayError(message) {
    resultsContainer.innerHTML = `
        <div class="error-state">
            <h3>エラーが発生しました</h3>
            <p>${escapeHtml(message)}</p>
        </div>
    `;
}

// =====================
// ステータスメッセージの表示
// =====================
/**
 * ステータスメッセージを表示
 * @param {string} message - メッセージ
 * @param {string} type - 'success', 'error', 'info'など
 */
function showStatus(message, type) {
    statusMessage.textContent = message;
    statusMessage.className = 'status-message';
    if (type) {
        statusMessage.classList.add(type);
    }
}

// =====================
// ローディング表示の制御
// =====================
/**
 * ローディングインジケータを表示/非表示する
 * @param {boolean} show - trueで表示、falseで非表示
 */
function showLoading(show) {
    if (show) {
        loadingIndicator.style.display = 'flex';
        searchButton.disabled = true;
        searchButton.textContent = '検索中...';
    } else {
        loadingIndicator.style.display = 'none';
        searchButton.disabled = false;
        searchButton.textContent = '検索';
    }
}

// =====================
// HTMLエスケープ
// =====================
/**
 * HTMLエスケープを行う
 * @param {string} text - エスケープ対象のテキスト
 * @returns {string} - エスケープ済みのテキスト
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// =====================
// デバッグ用: 全ての歌を表示
// =====================
/**
 * 全ての歌データをAPIから取得して表示
 */
async function debugShowAllPoems() {
    try {
        const response = await fetch('/api/poems');
        const data = await response.json();
        
        if (response.ok) {
            console.log('全ての歌:', data);
            showStatus(`デバッグ: ${data.total}件の歌を取得`, 'success');
        } else {
            console.error('デバッグエラー:', data.error);
        }
    } catch (error) {
        console.error('デバッグエラー:', error);
    }
}

// システム情報を更新
async function updateSystemInfo() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        if (data.status === 'ok') {
            // 基本情報
            document.getElementById('total-poems').textContent = data.database.total_poems;
            document.getElementById('cached-queries').textContent = data.cache_stats.cached_queries;
            document.getElementById('cache-size').textContent = `${data.cache_stats.cache_size_mb.toFixed(2)} MB`;
            
            // 使用量制限情報
            updateUsageLimits(data.usage_limits, data.free_tier_limits);
        }
    } catch (error) {
        console.error('システム情報の取得に失敗:', error);
    }
}

// 使用量制限情報を更新
function updateUsageLimits(usageLimits, freeTierLimits) {
    // 日次検索回数
    const dailySearchesRemaining = usageLimits.daily_searches_remaining;
    const dailySearchesMax = freeTierLimits.daily_searches;
    const dailySearchesPercentage = ((dailySearchesMax - dailySearchesRemaining) / dailySearchesMax) * 100;
    
    document.getElementById('daily-searches-remaining').textContent = dailySearchesRemaining;
    document.getElementById('daily-searches-max').textContent = dailySearchesMax;
    
    const dailySearchesBar = document.getElementById('daily-searches-bar');
    dailySearchesBar.style.width = `${dailySearchesPercentage}%`;
    updateProgressBarColor(dailySearchesBar, dailySearchesPercentage);
    
    // 日次トークン数
    const dailyTokensRemaining = usageLimits.daily_tokens_remaining;
    const dailyTokensMax = freeTierLimits.daily_tokens;
    const dailyTokensPercentage = ((dailyTokensMax - dailyTokensRemaining) / dailyTokensMax) * 100;
    
    document.getElementById('daily-tokens-remaining').textContent = 
        Math.floor(dailyTokensRemaining / 1000) + 'K';
    document.getElementById('daily-tokens-max').textContent = 
        Math.floor(dailyTokensMax / 1000) + 'K';
    
    const dailyTokensBar = document.getElementById('daily-tokens-bar');
    dailyTokensBar.style.width = `${dailyTokensPercentage}%`;
    updateProgressBarColor(dailyTokensBar, dailyTokensPercentage);
    
    // 月次検索回数
    const monthlySearchesRemaining = usageLimits.monthly_searches_remaining;
    const monthlySearchesMax = freeTierLimits.monthly_searches;
    const monthlySearchesPercentage = ((monthlySearchesMax - monthlySearchesRemaining) / monthlySearchesMax) * 100;
    
    document.getElementById('monthly-searches-remaining').textContent = monthlySearchesRemaining;
    document.getElementById('monthly-searches-max').textContent = monthlySearchesMax;
    
    const monthlySearchesBar = document.getElementById('monthly-searches-bar');
    monthlySearchesBar.style.width = `${monthlySearchesPercentage}%`;
    updateProgressBarColor(monthlySearchesBar, monthlySearchesPercentage);
    
    // 月次トークン数
    const monthlyTokensRemaining = usageLimits.monthly_tokens_remaining;
    const monthlyTokensMax = freeTierLimits.monthly_tokens;
    const monthlyTokensPercentage = ((monthlyTokensMax - monthlyTokensRemaining) / monthlyTokensMax) * 100;
    
    document.getElementById('monthly-tokens-remaining').textContent = 
        Math.floor(monthlyTokensRemaining / 1000) + 'K';
    document.getElementById('monthly-tokens-max').textContent = 
        Math.floor(monthlyTokensMax / 1000) + 'K';
    
    const monthlyTokensBar = document.getElementById('monthly-tokens-bar');
    monthlyTokensBar.style.width = `${monthlyTokensPercentage}%`;
    updateProgressBarColor(monthlyTokensBar, monthlyTokensPercentage);
}

// プログレスバーの色を更新
function updateProgressBarColor(bar, percentage) {
    bar.classList.remove('warning', 'danger');
    if (percentage >= 80) {
        bar.classList.add('danger');
    } else if (percentage >= 60) {
        bar.classList.add('warning');
    }
}

// ページ読み込み時にシステム情報を更新
document.addEventListener('DOMContentLoaded', function() {
    updateSystemInfo();
    populateDbSearchDropdowns();
});

// 検索実行後にシステム情報を更新
async function performSearch(query, mode = 'semantic', topK = 10) {
    showLoading(true);
    showStatus('検索中...', '');
    
    try {
        const data = await apiRequest('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, top_k: topK, mode })
        });
        
        if (data.status === 'ok') {
            displayResults(data);
            showStatus(`検索完了: ${data.total_found}件の結果`, 'success');
            // 使用量制限情報も更新
            if (data.usage_limits) {
                updateUsageLimits(data.usage_limits, data.free_tier_limits);
            }
        } else {
            showStatus('検索エラー: ' + (data.message || '検索中にエラーが発生しました'), 'error');
            displayError(data.message || '検索中にエラーが発生しました');
            // エラー時も使用量制限情報を更新
            if (data.usage_limits) {
                updateUsageLimits(data.usage_limits, data.free_tier_limits);
            }
        }
    } catch (error) {
        console.error('検索エラー:', error);
        showStatus('検索エラー: ' + error.message, 'error');
        displayError(error.message);
    } finally {
        showLoading(false);
        // 検索後にシステム情報を更新（キャッシュ統計が変わるため）
        updateSystemInfo();
    }
}

// =====================
// 初期化
// =====================
// 検索ボックスでEnterキー押下時に検索（デフォルト送信を防ぐ）
searchQuery.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        const query = searchQuery.value.trim();
        const topK = parseInt(resultCount.value);
        performSearch(query, 'semantic', topK);
    }
});
// フォーム送信時もリロードを防ぐ
semanticSearchForm.addEventListener('submit', function(e) {
    e.preventDefault();
    const query = searchQuery.value.trim();
    const topK = parseInt(resultCount.value);
    performSearch(query, 'semantic', topK);
});
resultCount.addEventListener('change', function() {
    if (resultsContainer.querySelector('.search-results')) {
        const query = searchQuery.value.trim();
        const topK = parseInt(resultCount.value);
        performSearch(query, 'semantic', topK);
    }
});
if (dbSearchButton) {
    dbSearchButton.addEventListener('click', () => {
        let query = dbQueryInput.value.trim();
        if (!query) {
            if (dbIdSelect.value) query = dbIdSelect.value;
            else if (dbPoetSelect.value) query = dbPoetSelect.value;
            else if (dbHeadSelect.value) query = dbHeadSelect.value;
        }
        const topK = parseInt(resultCountDb.value);
        // DB検索は従来通り
        performSearch(query, 'db', topK);
    });
} 