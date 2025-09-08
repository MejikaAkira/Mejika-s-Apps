(function() {
  const wrap = document.getElementById('wrap');
  // UI elements
  const winEl = document.getElementById('win');
  const toggleEl = document.getElementById('toggle');
  const statsEl = document.getElementById('stats');
  const selectBtn = document.getElementById('selectNodes');
  const clearBtn = document.getElementById('clear');
  const reloadBtn = document.getElementById('reload');
  const modalMask = document.getElementById('modalMask');
  const modalGrid = document.getElementById('modalGrid');
  const modalOk = document.getElementById('modalOk');
  const modalCancel = document.getElementById('modalCancel');
  const modalClear = document.getElementById('modalClear');
  const tsModeEl = document.getElementById('tsMode');

  // サンプリングレート推定
  let sampleRateEstimator = {
    lastTime: null,
    sampleTimes: [],
    estimatedRate: 0,
    recommendedWindow: 5,
    maxSamplesPerNode: 300,
    autoAdjusted: false
  };

  function updateRateInfo() {
    const autoInfo = document.getElementById('autoInfo');
    if (autoInfo && sampleRateEstimator.estimatedRate > 0) {
      const rate = sampleRateEstimator.estimatedRate.toFixed(1);
      const recommended = sampleRateEstimator.recommendedWindow;
      autoInfo.textContent = `検出: ${rate}Hz (推奨: ${recommended}秒)`;
    }
  }

  function estimateSampleRate(timestamp) {
    const now = Number(timestamp);
    if (!Number.isFinite(now)) return;
    if (sampleRateEstimator.lastTime !== null) {
      const interval = now - sampleRateEstimator.lastTime;
      if (interval > 0 && interval < 10) {
        sampleRateEstimator.sampleTimes.push(interval);
        if (sampleRateEstimator.sampleTimes.length > 20) sampleRateEstimator.sampleTimes.shift();
        if (sampleRateEstimator.sampleTimes.length >= 10) {
          const sorted = [...sampleRateEstimator.sampleTimes].sort((a,b)=>a-b);
          const median = sorted[Math.floor(sorted.length/2)];
          if (median > 0) {
            sampleRateEstimator.estimatedRate = 1.0 / median;
            const target = sampleRateEstimator.maxSamplesPerNode;
            const recommended = Math.min(60, Math.max(0.5, target / sampleRateEstimator.estimatedRate));
            sampleRateEstimator.recommendedWindow = Math.round(recommended * 2) / 2;
            const shouldAdjust = Math.abs(windowSec - sampleRateEstimator.recommendedWindow) > 1.0;
            if (!sampleRateEstimator.autoAdjusted && shouldAdjust && windowSec > sampleRateEstimator.recommendedWindow) {
              const winEl = document.getElementById('win');
              if (winEl) winEl.value = sampleRateEstimator.recommendedWindow;
              windowSec = sampleRateEstimator.recommendedWindow;
              sampleRateEstimator.autoAdjusted = true;
              console.log(`Window auto-adjusted to ${windowSec}s for ${sampleRateEstimator.estimatedRate.toFixed(1)}Hz data`);
            }
            updateRateInfo();
          }
        }
      }
    }
    sampleRateEstimator.lastTime = now;
  }

  // TSモード変更 → Pythonへ橋渡し（pywebview）
  if (tsModeEl) {
    tsModeEl.addEventListener('change', async () => {
      const mode = tsModeEl.value;
      try {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_ts_mode) {
          await window.pywebview.api.set_ts_mode(mode);
        }
      } catch (e) { console.error(e); }
      const info = document.getElementById('autoInfo');
      if (info) info.textContent = `モード: ${mode}`;
      // 既存データはそのまま。必要なら Clear を押下
    });
  }

  // Config (初期は15、外部データを受けて自動拡張)
  let nodeCount = 15;
  const rowsEls = [];
  function addRow(i) {
    const row = document.createElement('div');
    row.className = 'row';
    const label = document.createElement('div');
    label.className = 'label';
    label.textContent = `N${i}`;
    const canvas = document.createElement('canvas');
    row.appendChild(canvas);
    row.appendChild(label);
    wrap.appendChild(row);
    rowsEls.push({ row, canvas, ctx: canvas.getContext('2d') });
  }
  for (let i = 0; i < nodeCount; i++) addRow(i);

  // 表示対象ノードの制御
  let visibleSet = new Set(Array.from({ length: nodeCount }, (_, i) => i));
  function applyVisibility() {
    for (let i = 0; i < rowsEls.length; i++) {
      rowsEls[i].row.style.display = visibleSet.has(i) ? '' : 'none';
    }
  }
  applyVisibility();

  function resize() {
    for (let i = 0; i < rowsEls.length; i++) {
      const rect = rowsEls[i].row.getBoundingClientRect();
      rowsEls[i].canvas.width = rect.width;
      rowsEls[i].canvas.height = rect.height;
    }
  }
  const ro = new ResizeObserver(() => resize());
  ro.observe(wrap);
  window.addEventListener('resize', resize);
  setTimeout(resize, 50);

  // ring buffer of points {t, y}
  let windowSec = Number(winEl.value);
  winEl.addEventListener('input', () => {
    const val = Number(winEl.value);
    if (val >= 0.5 && val <= 60) {
      windowSec = val;
      // 手動変更時は自動調整を無効化
      sampleRateEstimator && (sampleRateEstimator.autoAdjusted = true);
    }
  });

  let running = true;
  toggleEl.addEventListener('click', () => {
    running = !running;
    toggleEl.textContent = running ? 'Pause' : 'Resume';
  });

  // 全体ゲインで縦軸スケール

  const dataByNode = Array.from({ length: nodeCount }, () => []);

  function ensureNodeCapacity(n) {
    if (n <= nodeCount) return;
    for (let i = nodeCount; i < n; i++) {
      addRow(i);
      dataByNode[i] = [];
      visibleSet.add(i);
    }
    nodeCount = n;
    applyVisibility();
    resize();
  }

  function pushSample(nodeId, t, y) {
    const arr = dataByNode[nodeId];
    arr.push({ t, y });
    const cutoff = t - windowSec;
    while (arr.length && arr[0].t < cutoff) arr.shift();
    const maxSamples = (sampleRateEstimator?.maxSamplesPerNode || 300) * 2;
    if (arr.length > maxSamples) arr.splice(0, arr.length - maxSamples);
  }

  // 全ノードの履歴をクリアし、画面も消去
  function clearAllData() {
    for (let i = 0; i < nodeCount; i++) {
      dataByNode[i].length = 0;
      const { canvas, ctx } = rowsEls[i];
      if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
  }

  // Demo sine wave generator (same as 3D, but centralised)
  const amplitudes = Array.from({ length: nodeCount }, (_, i) => 0.006 + 0.004 * (i / nodeCount));
  const freqs = Array.from({ length: nodeCount }, (_, i) => 0.5 + 0.05 * i);
  const phases = Array.from({ length: nodeCount }, (_, i) => (i / nodeCount) * Math.PI * 2);

  const clock0 = performance.now() / 1000;
  // 送信側の絶対時刻(秒)の基準。最初に受け取ったtimestampを原点にする
  let t0Payload = null;
  let externalActive = false;
  let lastExternalSec = 0;
  function generateDemoSamples() {
    // 停止: 外部受信テストのため内部デモは生成しない
  }

  // 外部(UDP→Python→JS)からの取り込み口
  window.pushGraphSamples = function(payload) {
    try {
      if (!payload) return;
      // 送信側timestampがあれば相対化、無ければローカル秒
      let t;
      if (Number.isFinite(payload.timestamp)) {
        if (t0Payload == null) t0Payload = Number(payload.timestamp) || 0;
        t = Number(payload.timestamp) - t0Payload;
      } else {
        t = (performance.now() / 1000) - clock0;
      }
      if (Array.isArray(payload.nodes)) {
        ensureNodeCapacity(payload.nodes.length);
        for (let i = 0; i < Math.min(nodeCount, payload.nodes.length); i++) {
          const y = Number(payload.nodes[i]);
          if (Number.isFinite(y)) pushSample(i, t, y);
        }
      } else if (Array.isArray(payload.amps)) {
        ensureNodeCapacity(payload.amps.length);
        for (let i = 0; i < Math.min(nodeCount, payload.amps.length); i++) {
          const y = Number(payload.amps[i]);
          if (Number.isFinite(y)) pushSample(i, t, y);
        }
      }
      externalActive = true;
      lastExternalSec = t;
    } catch (e) {
      console.error('pushGraphSamples error', e);
    }
  }

  // バッチ取り込み: payload { ts: number[], frames: number[][] }
  window.pushGraphBatch = function(payload) {
    try {
      if (!payload || !Array.isArray(payload.ts) || !Array.isArray(payload.frames)) return;
      const ts = payload.ts;
      const frames = payload.frames;
      const nFrames = Math.min(ts.length, frames.length);
      // サンプリングレート推定（最初のタイムスタンプで）
      if (nFrames > 0) {
        const firstTs = Number(ts[0]);
        if (Number.isFinite(firstTs)) estimateSampleRate(firstTs);
      }
      // セッションの基準時刻
      if (t0Payload == null && nFrames > 0 && Number.isFinite(Number(ts[0]))) {
        t0Payload = Number(ts[0]);
      }
      for (let k = 0; k < nFrames; k++) {
        const tAbs = Number(ts[k]);
        if (!Number.isFinite(tAbs)) continue;
        const tRel = t0Payload != null ? (tAbs - t0Payload) : ((performance.now() / 1000) - clock0);
        const amps = frames[k];
        ensureNodeCapacity(amps.length);
        for (let i = 0; i < Math.min(nodeCount, amps.length); i++) {
          const y = Number(amps[i]);
          if (Number.isFinite(y)) pushSample(i, tRel, y);
        }
      }
      externalActive = true;
      lastExternalSec = dataByNode[0]?.length ? dataByNode[0][dataByNode[0].length - 1].t : lastExternalSec;
    } catch (e) {
      console.error('pushGraphBatch error', e);
    }
  }

  function drawAxes(ctx, x0, y0, x1, y1, xMin, xMax, yMin, yMax) {
    ctx.strokeStyle = '#334';
    ctx.lineWidth = 1;
    ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);

    // Y 軸目盛り
    ctx.fillStyle = '#99a';
    ctx.font = '10px Arial';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    const yTicks = 2;
    for (let i = 0; i <= yTicks; i++) {
      const ty = y0 + (y1 - y0) * (i / yTicks);
      const val = yMax - (yMax - yMin) * (i / yTicks);
      ctx.fillText(val.toFixed(3), x0 - 6, ty);
      ctx.beginPath();
      ctx.moveTo(x0, ty);
      ctx.lineTo(x1, ty);
      ctx.strokeStyle = i === 0 || i === yTicks ? '#556' : '#2a2e38';
      ctx.stroke();
    }

    // X 軸目盛り
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    const xTicks = 5;
    for (let i = 0; i <= xTicks; i++) {
      const tx = x0 + (x1 - x0) * (i / xTicks);
      const val = xMin + (xMax - xMin) * (i / xTicks);
      ctx.fillText(val.toFixed(1) + 's', tx, y1 + 4);
      ctx.beginPath();
      ctx.moveTo(tx, y0);
      ctx.lineTo(tx, y1);
      ctx.strokeStyle = '#2a2e38';
      ctx.stroke();
    }
  }

  function plotLine(ctx, points, x0, y0, x1, y1, xMin, xMax, yMin, yMax, color) {
    if (points.length === 0) return;
    const sx = (x1 - x0) / (xMax - xMin || 1);
    const sy = (y1 - y0) / (yMax - yMin || 1);
    ctx.beginPath();
    for (let i = 0; i < points.length; i++) {
      const px = x0 + (points[i].t - xMin) * sx;
      const py = y1 - (points[i].y - yMin) * sy;
      if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  let lastFpsTime = performance.now();
  let frames = 0;
  function updateFps() {
    frames++;
    const now = performance.now();
    if (now - lastFpsTime >= 1000) {
      const fps = frames / ((now - lastFpsTime) / 1000);
      if (statsEl) statsEl.textContent = `FPS: ${fps.toFixed(0)}`;
      frames = 0;
      lastFpsTime = now;
    }
  }

  function render() {
    try {
      // 受信がなければデータは増えない（静止）
      const xPaddingLeft = 60, xPaddingRight = 20, yPaddingTop = 10, yPaddingBottom = 18;
      const now = externalActive ? lastExternalSec : (performance.now() / 1000 - clock0);
      // 実データ範囲から横軸を決定
      let dataMinTime = Infinity;
      let dataMaxTime = -Infinity;
      for (let i = 0; i < nodeCount; i++) {
        const arr = dataByNode[i];
        if (arr.length > 0) {
          const firstTime = arr[0].t;
          const lastTime = arr[arr.length - 1].t;
          if (firstTime < dataMinTime) dataMinTime = firstTime;
          if (lastTime > dataMaxTime) dataMaxTime = lastTime;
        }
      }
      let xMin, xMax;
      if (isFinite(dataMinTime) && isFinite(dataMaxTime)) {
        const dataSpan = dataMaxTime - dataMinTime;
        if (dataSpan < windowSec) {
          const center = (dataMinTime + dataMaxTime) / 2;
          const halfWindow = windowSec / 2;
          xMin = Math.max(0, center - halfWindow);
          xMax = center + halfWindow;
        } else {
          xMax = dataMaxTime;
          xMin = Math.max(dataMinTime, dataMaxTime - windowSec);
        }
      } else {
        xMin = Math.max(0, now - windowSec);
        xMax = now;
      }
      for (let i = 0; i < nodeCount; i++) {
        if (!visibleSet.has(i)) continue;
        const { canvas, ctx } = rowsEls[i];
        const width = canvas.width, height = canvas.height;
        ctx.clearRect(0, 0, width, height);
        const x0 = xPaddingLeft, y0 = yPaddingTop, x1 = width - xPaddingRight, y1 = height - yPaddingBottom;
        const arr = dataByNode[i];
        if (arr.length < 2) {
          // 軽いプレースホルダ
          drawAxes(ctx, x0, y0, x1, y1, xMin, xMax, -0.02, 0.02);
          ctx.fillStyle = '#666';
          ctx.font = '12px Arial';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText('データ待機中...', (x0 + x1) / 2, (y0 + y1) / 2);
          continue;
        }
        let yMin = Infinity, yMax = -Infinity;
        for (let k = 0; k < arr.length; k++) {
          if (arr[k].y < yMin) yMin = arr[k].y;
          if (arr[k].y > yMax) yMax = arr[k].y;
        }
        if (!isFinite(yMin) || !isFinite(yMax) || yMin === yMax) {
          yMin = -0.02; yMax = 0.02;
        } else {
          const pad = (yMax - yMin) * 0.15; yMin -= pad; yMax += pad;
        }
        drawAxes(ctx, x0, y0, x1, y1, xMin, xMax, yMin, yMax);
        plotLine(ctx, arr, x0, y0, x1, y1, xMin, xMax, yMin, yMax, '#4fc3f7');
      }

      updateFps();
    } catch (e) {
      const errorEl = document.getElementById('error');
      if (errorEl) {
        errorEl.textContent = `Error: ${e.message}`;
        errorEl.style.display = 'block';
      }
      console.error(e);
    } finally {
      requestAnimationFrame(render);
    }
  }

  render();

  // モーダル構築
  function openModal() {
    // 初期描画
    modalGrid.innerHTML = '';
    for (let i = 0; i < nodeCount; i++) {
      const id = `chk-${i}`;
      const wrap = document.createElement('label');
      wrap.style.userSelect = 'none';
      wrap.style.display = 'inline-flex';
      wrap.style.alignItems = 'center';
      const inp = document.createElement('input');
      inp.type = 'checkbox';
      inp.id = id;
      inp.checked = visibleSet.has(i);
      inp.dataset.idx = String(i);
      const span = document.createElement('span');
      span.textContent = `N${i}`;
      span.style.marginLeft = '6px';
      wrap.appendChild(inp);
      wrap.appendChild(span);
      modalGrid.appendChild(wrap);
    }
    modalMask.style.display = 'flex';
  }
  function closeModal() {
    modalMask.style.display = 'none';
  }
  selectBtn.addEventListener('click', openModal);
  modalCancel.addEventListener('click', closeModal);
  modalClear.addEventListener('click', () => {
    const boxes = modalGrid.querySelectorAll('input[type="checkbox"]');
    boxes.forEach(b => (b.checked = false));
  });
  modalOk.addEventListener('click', () => {
    const boxes = modalGrid.querySelectorAll('input[type="checkbox"]');
    const next = new Set();
    boxes.forEach(b => { if (b.checked) next.add(Number(b.dataset.idx)); });
    // 少なくとも1つは残す
    if (next.size === 0) {
      alert('少なくとも1つのノードを選択してください');
      return;
    }
    visibleSet = next;
    applyVisibility();
    closeModal();
  });

  // クリア・リロードボタン
  if (clearBtn) clearBtn.addEventListener('click', () => clearAllData());
  if (reloadBtn) reloadBtn.addEventListener('click', () => {
    try { window.location.reload(); } catch (e) { /* ignore */ }
  });
})();


