// script.js
document.addEventListener('DOMContentLoaded', () => {
    /* ---------- 要素取得 ---------- */
    const logBtn        = document.getElementById('log-toggle-btn');
    const logArea       = document.getElementById('log-area');
    const logContent    = document.getElementById('log-content');
    const reloadBtn     = document.getElementById('log-reload-btn');

    const uploadForm    = document.getElementById('upload-form');
    const fileInput     = document.getElementById('file-input');   // ← ID 統一
    const uploadBtn     = document.getElementById('upload-button'); // ← ID 統一
    const loadingDiv    = document.getElementById('loading');
    const messageArea   = document.getElementById('message-area');

    const progressBox   = document.getElementById('progress-container');
    const progressBar   = document.getElementById('progress-bar');
    const progressText  = document.getElementById('progress-text');
    const statusDiv     = document.getElementById('status');
    
    // 処理状態表示用の要素
    const processingDetails = document.getElementById('processing-details');
    const currentStage = document.getElementById('current-stage');
    const currentFile = document.getElementById('current-file');
    const slideProgress = document.getElementById('slide-progress');
    const textProgress = document.getElementById('text-progress');

    /* ---------- ログ処理 ---------- */
    const fetchLogs = () => {
        fetch('/logs')
            .then(r => r.json())
            .then(d => {
                logContent.textContent = d.logs.join('\n');
                logContent.scrollTop  = logContent.scrollHeight; // 自動スクロール
            });
    };

    if (logBtn) {
        logBtn.addEventListener('click', () => {
            logArea.style.display = (logArea.style.display === 'none') ? 'block' : 'none';
            if (logArea.style.display === 'block') fetchLogs();
        });
    }
    if (reloadBtn) reloadBtn.addEventListener('click', fetchLogs);
    setInterval(fetchLogs, 5000); // 5秒毎に更新

    /* ---------- 処理状態の監視 ---------- */
    const startStatusPolling = () => {
        // 初期状態を確認
        checkStatus();
        
        // 3秒ごとに状態を更新
        setInterval(checkStatus, 3000);
    };
    
    // 処理状態を取得
    const checkStatus = async () => {
        try {
            const response = await fetch('/status');
            const data = await response.json();
            updateProcessingStatus(data);
        } catch (error) {
            console.error('状態取得エラー:', error);
        }
    };
    
    // 処理状態の表示を更新
    const updateProcessingStatus = (data) => {
        if (data.is_processing) {
            uploadBtn.disabled = true;
            loadingDiv.style.display = 'flex';
            progressBox.style.display = 'block';
            processingDetails.style.display = 'block';
            
            progressBar.value = data.progress;
            progressText.textContent = `${data.progress.toFixed(1)}% - ${data.message}`;
            
            currentStage.textContent = getStageText(data.stage);
            currentFile.textContent = data.current_file;
            slideProgress.textContent = `${data.current_slide} / ${data.total_slides}`;
            textProgress.textContent = `${data.translated_texts} / ${data.total_texts}`;
            
            statusDiv.textContent = data.message;
        } else {
            if (data.stage === 'completed') {
                statusDiv.textContent = '処理が完了しました！';
                progressBar.value = 100;
                progressText.textContent = '100% - 完了';
            } else if (data.stage === 'error') {
                statusDiv.textContent = data.message;
                showError(data.message);
            }
            
            // アップロード中でなければUIをリセット
            if (!uploadBtn.disabled) {
                resetUI();
            }
        }
    };
    
    // 処理ステージのテキスト表示を取得
    const getStageText = (stage) => {
        const stageMap = {
            'idle': '待機中',
            'loading': 'ファイル読み込み中',
            'extracting': 'テキスト抽出中',
            'translating': '翻訳中',
            'summarizing': 'サマリー生成中',
            'saving': '保存中',
            'completed': '完了',
            'error': 'エラー'
        };
        return stageMap[stage] || stage;
    };

    /* ---------- ファイルアップロード ---------- */
    uploadForm.addEventListener('submit', e => {
        e.preventDefault();

        const file = fileInput.files[0];
        if (!file) { alert('ファイルを選択してください'); return; }
        if (!file.name.toLowerCase().endsWith('.pptx')) {
            alert('.pptx 以外はアップロードできません'); return;
        }
        if (file.size > 500 * 1024 * 1024) { alert('500MB を超えています'); return; }

        // 大きなファイルの警告
        if (file.size > 50 * 1024 * 1024) { // 50MB以上
            if (!confirm('大きなファイルの処理には時間がかかる場合があります。続行しますか？')) {
                return;
            }
        }

        // UI ロック
        uploadBtn.disabled = true;
        uploadBtn.textContent = '処理中...';
        loadingDiv.style.display = 'flex';
        progressBox.style.display = 'block';
        processingDetails.style.display = 'block';
        progressBar.value = 0;
        progressText.textContent = '0% - アップロード中';

        const formData = new FormData();
        formData.append('file', file);

        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/upload', true);
        xhr.timeout = 30 * 60 * 1000;   // 30 分

        // アップロード進捗（全体の 10% とする）
        xhr.upload.onprogress = e => {
            if (e.lengthComputable) {
                const pct = (e.loaded / e.total) * 10;
                progressBar.value = pct;
                progressText.textContent = pct.toFixed(1) + '% - アップロード中';
            }
        };

        // ダウンロード進捗（残り 90% と見なす）
        xhr.onprogress = e => {
            if (e.lengthComputable && e.total > 0) {
                const pct = 10 + (e.loaded / e.total) * 90;
                progressBar.value = pct;
                progressText.textContent = pct.toFixed(1) + '% - ダウンロード中';
            }
        };

        xhr.onload = () => {
            if (xhr.status === 200) {
                const blob = xhr.response;
                const url  = URL.createObjectURL(blob);
                const a    = document.createElement('a');
                // ファイル名取得
                const cd   = xhr.getResponseHeader('Content-Disposition') || '';
                const m    = cd.match(/filename\*=UTF-8''(.+)|filename=\"?([^\";]+)\"?/);
                const fn   = decodeURIComponent(m?.[1] || m?.[2] || 'translated.pptx');
                a.href = url; a.download = fn; a.style.display = 'none';
                document.body.appendChild(a); a.click();
                URL.revokeObjectURL(url); document.body.removeChild(a);

                messageArea.textContent = '完了: ダウンロードが開始されました';
                messageArea.className   = 'message-success';
            } else {
                messageArea.textContent = 'エラー: ' + xhr.statusText;
                messageArea.className   = 'message-error';
            }
            resetUI();
        };

        xhr.onerror = () => { showError('ネットワークエラー'); };
        xhr.ontimeout = () => { showError('タイムアウトしました'); };
        xhr.responseType = 'blob';
        xhr.send(formData);
    });

    /* ---------- 補助関数 ---------- */
    const resetUI = () => {
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'アップロードして処理開始';
        loadingDiv.style.display = 'none';
    };
    
    const showError = msg => {
        messageArea.textContent = 'エラー: ' + msg;
        messageArea.className   = 'message-error';
        resetUI();
    };
    
    // 初期状態を確認してポーリングを開始
    startStatusPolling();
});