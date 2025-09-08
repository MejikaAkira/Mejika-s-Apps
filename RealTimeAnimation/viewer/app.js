(() => {
  const WIDTH = window.innerWidth;
  const HEIGHT = window.innerHeight;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0b0e12);

  const camera = new THREE.PerspectiveCamera(60, WIDTH / HEIGHT, 0.01, 1000);
  camera.position.set(0.25, 0.25, 0.6); // 小さなスケールに合わせる

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(WIDTH, HEIGHT);
  document.body.appendChild(renderer.domElement);
  // タッチデバイスでの回転/ズームを妨げないためのスタイル
  renderer.domElement.style.touchAction = 'none';

  // OrbitControls フォールバック
  let controls;
  function createControls() {
    if (THREE.OrbitControls) {
      const ctrl = new THREE.OrbitControls(camera, renderer.domElement);
      ctrl.enableDamping = true;
      ctrl.dampingFactor = 0.08;
      ctrl.rotateSpeed = 0.8;
      ctrl.zoomSpeed = 1.0;
      ctrl.panSpeed = 0.8;
      ctrl.minDistance = 0.05;
      ctrl.maxDistance = 5;
      ctrl.maxPolarAngle = Math.PI; // 真上から真下まで回転可能
      // タッチ/マウス操作のマッピング調整
      ctrl.enablePan = true;
      ctrl.enableZoom = true;
      ctrl.enableRotate = true;
      if (THREE.MOUSE) {
        ctrl.mouseButtons = {
          LEFT: THREE.MOUSE.ROTATE,
          MIDDLE: THREE.MOUSE.DOLLY,
          RIGHT: THREE.MOUSE.PAN
        };
      }
      if (THREE.TOUCH) {
        ctrl.touches = {
          ONE: THREE.TOUCH.ROTATE,
          TWO: THREE.TOUCH.DOLLY_PAN
        };
      }
      return ctrl;
    }
    // 簡易オービット実装(マウス/タッチ): 回転/ズーム/パン
    const target = new THREE.Vector3(0, 0, 0);
    const spherical = new THREE.Spherical();
    const tempVec3 = new THREE.Vector3();
    function setFromCamera() {
      tempVec3.copy(camera.position).sub(target);
      spherical.setFromVector3(tempVec3);
    }
    setFromCamera();
    const state = { pointers: new Map(), rotating: false, panning: false, pinching: false, startDist: 0, startRadius: spherical.radius, lastCenter: { x: 0, y: 0 } };
    const limits = { minDistance: 0.05, maxDistance: 5, minPolar: 0.0001, maxPolar: Math.PI - 0.0001 };
    const speeds = { rotate: 0.005, zoom: 0.002, pan: 0.0015 };
    function getPointersCenter() {
      let x = 0, y = 0, n = 0;
      state.pointers.forEach(p => { x += p.x; y += p.y; n++; });
      if (!n) return { x: 0, y: 0 };
      return { x: x / n, y: y / n };
    }
    function onPointerDown(e) {
      renderer.domElement.setPointerCapture(e.pointerId);
      state.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (state.pointers.size === 1) {
        state.rotating = true;
      } else if (state.pointers.size === 2) {
        const it = Array.from(state.pointers.values());
        const dx = it[0].x - it[1].x; const dy = it[0].y - it[1].y;
        state.startDist = Math.hypot(dx, dy) || 1;
        state.startRadius = spherical.radius;
        state.pinching = true;
        state.panning = true;
        state.lastCenter = getPointersCenter();
      }
    }
    function onPointerMove(e) {
      const prev = state.pointers.get(e.pointerId);
      state.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (!prev) return;
      if (state.pinching && state.pointers.size >= 2) {
        const it = Array.from(state.pointers.values());
        const dx = it[0].x - it[1].x; const dy = it[0].y - it[1].y;
        const dist = Math.hypot(dx, dy) || state.startDist;
        const scale = state.startDist / dist;
        spherical.radius = Math.min(limits.maxDistance, Math.max(limits.minDistance, state.startRadius * scale));
        const center = getPointersCenter();
        // 2本指パン
        const panDx = center.x - state.lastCenter.x;
        const panDy = center.y - state.lastCenter.y;
        if (panDx || panDy) {
          const panX = -panDx * speeds.pan * spherical.radius;
          const panY = panDy * speeds.pan * spherical.radius;
          // カメラの横/縦方向ベクトルでターゲットを移動
          camera.updateMatrixWorld();
          const xAxis = new THREE.Vector3();
          const yAxis = new THREE.Vector3();
          camera.getWorldDirection(tempVec3).normalize(); // -Z
          xAxis.crossVectors(camera.up, tempVec3).normalize();
          yAxis.copy(camera.up).normalize();
          target.add(xAxis.multiplyScalar(panX));
          target.add(yAxis.multiplyScalar(panY));
        }
        state.lastCenter = center;
      } else if (state.rotating && state.pointers.size === 1) {
        const dx = e.clientX - prev.x;
        const dy = e.clientY - prev.y;
        spherical.theta -= dx * speeds.rotate;
        spherical.phi -= dy * speeds.rotate;
        spherical.phi = Math.min(limits.maxPolar, Math.max(limits.minPolar, spherical.phi));
      }
    }
    function onPointerUp(e) {
      state.pointers.delete(e.pointerId);
      state.rotating = state.pointers.size === 1;
      if (state.pointers.size < 2) {
        state.pinching = false;
        state.panning = false;
      }
    }
    function onWheel(e) {
      e.preventDefault();
      const delta = e.deltaY;
      spherical.radius = Math.min(limits.maxDistance, Math.max(limits.minDistance, spherical.radius * (1 + delta * speeds.zoom)));
    }
    renderer.domElement.addEventListener('pointerdown', onPointerDown, { passive: true });
    renderer.domElement.addEventListener('pointermove', onPointerMove, { passive: true });
    renderer.domElement.addEventListener('pointerup', onPointerUp, { passive: true });
    renderer.domElement.addEventListener('pointercancel', onPointerUp, { passive: true });
    renderer.domElement.addEventListener('wheel', onWheel, { passive: false });
    function update() {
      tempVec3.setFromSpherical(spherical).add(target);
      camera.position.copy(tempVec3);
      camera.lookAt(target);
    }
    return { target, update };
  }
  controls = createControls();
  if (!THREE.OrbitControls) {
    camera.lookAt(controls.target);
  }

  // Lights
  const hemi = new THREE.HemisphereLight(0xffffff, 0x222233, 0.9);
  scene.add(hemi);
  const dir = new THREE.DirectionalLight(0xffffff, 0.8);
  dir.position.set(0.5, 1.0, 0.8);
  scene.add(dir);

  // Axes/Grid helpers
  const grid = new THREE.GridHelper(1.0, 20, 0x2a2f3a, 0x1a1f2a);
  grid.material.opacity = 0.25;
  grid.material.transparent = true;
  const root = new THREE.Group();
  scene.add(root);
  root.add(grid);
  const axes = new THREE.AxesHelper(0.1);
  root.add(axes);

  // 追加: 最適化設定と拡張用のグローバル
  const config = {
    display: {
      layout: 'helix', // 'grid' | 'helix' | 'sphere' | 'cylinder'
      showSurface: true,
      showTrails: true,
      trailLength: 20
    },
    performance: {
      targetFPS: 60,
      autoQuality: true,
      maxPixelRatio: 2
    }
  };
  let instancedNodes = null; // THREE.InstancedMesh
  let waveSurface = null;    // THREE.Mesh (ShaderMaterial)
  let trailSystem = null;    // Group wrapper

  // レイアウト生成
  function getLayoutPositions(layout) {
    const positions = [];
    switch(layout) {
      case 'helix': {
        for (let i = 0; i < nodeCount; i++) {
          const t = nodeCount > 1 ? (i / (nodeCount - 1)) : 0;
          const angle = t * Math.PI * 6;
          const radius = 0.15 + t * 0.1;
          const height = t * 0.4 - 0.2;
          positions.push(new THREE.Vector3(
            Math.cos(angle) * radius,
            height,
            Math.sin(angle) * radius
          ));
        }
        break;
      }
      case 'sphere': {
        const phi = Math.PI * (3 - Math.sqrt(5));
        for (let i = 0; i < nodeCount; i++) {
          const y = nodeCount > 1 ? 1 - (i / (nodeCount - 1)) * 2 : 0;
          const r = Math.sqrt(Math.max(0, 1 - y * y));
          const theta = phi * i;
          positions.push(new THREE.Vector3(
            Math.cos(theta) * r * 0.25,
            y * 0.25,
            Math.sin(theta) * r * 0.25
          ));
        }
        break;
      }
      case 'cylinder': {
        const rows = Math.ceil(Math.sqrt(nodeCount || 1));
        const cols = Math.ceil((nodeCount || 1) / rows);
        for (let i = 0; i < nodeCount; i++) {
          const row = Math.floor(i / cols);
          const col = i % cols;
          const angle = (col / cols) * Math.PI * 2;
          const y = (row / rows) * 0.4 - 0.2;
          positions.push(new THREE.Vector3(
            Math.cos(angle) * 0.2,
            y,
            Math.sin(angle) * 0.2
          ));
        }
        break;
      }
      default: { // grid
        const gs = Math.ceil(Math.sqrt(nodeCount || 1));
        for (let i = 0; i < nodeCount; i++) {
          const x = (i % gs) / gs - 0.5;
          const z = Math.floor(i / gs) / gs - 0.5;
          positions.push(new THREE.Vector3(x * 0.4, 0, z * 0.4));
        }
      }
    }
    return positions;
  }

  // トレイルシステム
  class TrailSystem {
    constructor(count, length = 20) {
      this.count = count;
      this.length = length;
      this.trails = [];
      this.group = new THREE.Group();
      for (let i = 0; i < count; i++) {
        const points = new Array(length).fill(0).map(() => new THREE.Vector3());
        const geo = new THREE.BufferGeometry().setFromPoints(points);
        const mat = new THREE.LineBasicMaterial({
          color: new THREE.Color().setHSL(i / Math.max(1, count), 0.8, 0.6),
          transparent: true,
          opacity: 0.3,
          blending: THREE.AdditiveBlending
        });
        const line = new THREE.Line(geo, mat);
        this.group.add(line);
        this.trails.push({ line, points, idx: 0 });
      }
    }
    update(positions) {
      for (let i = 0; i < Math.min(this.count, positions.length); i++) {
        const tr = this.trails[i];
        tr.points[tr.idx] = positions[i].clone();
        tr.idx = (tr.idx + 1) % this.length;
        const ordered = [];
        for (let j = 0; j < this.length; j++) {
          const k = (tr.idx + j) % this.length;
          ordered.push(tr.points[k]);
        }
        tr.line.geometry.setFromPoints(ordered);
      }
    }
  }

  // サーフェス（波形）
  function createWaveSurface() {
    if (waveSurface) { scene.remove(waveSurface); waveSurface.geometry.dispose(); waveSurface.material.dispose(); waveSurface = null; }
    const width = 0.6;
    const height = 0.4;
    const seg = Math.max(nodeCount * 2, 40);
    const geo = new THREE.PlaneGeometry(width, height, seg, seg);
    geo.rotateX(-Math.PI / 2);
    const vs = `
      uniform float amplitudes[${Math.max(1, nodeCount)}];
      uniform float nodeCount;
      varying float vH;
      varying vec2 vUv;
      float interpAmp(float x){
        float s = x * (nodeCount - 1.0);
        int i1 = int(floor(s));
        int i2 = min(i1 + 1, ${Math.max(0, nodeCount - 1)});
        float f = fract(s);
        float a1 = amplitudes[i1];
        float a2 = amplitudes[i2];
        return mix(a1, a2, smoothstep(0.0,1.0,f));
      }
      void main(){
        vUv = uv;
        vec3 p = position;
        float a = interpAmp(uv.x);
        p.y = a * 0.15;
        vH = a;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(p,1.0);
      }
    `;
    const fs = `
      varying float vH; varying vec2 vUv;
      void main(){
        float t = clamp(vH*0.5+0.5, 0.0, 1.0);
        vec3 col = vec3(smoothstep(0.5,0.8,t), sin(t*3.14159), smoothstep(0.8,0.5,t));
        gl_FragColor = vec4(col, 0.75);
      }
    `;
    const mat = new THREE.ShaderMaterial({
      uniforms: {
        amplitudes: { value: new Float32Array(nodeCount) },
        nodeCount: { value: nodeCount }
      },
      vertexShader: vs,
      fragmentShader: fs,
      transparent: true,
      side: THREE.DoubleSide
    });
    waveSurface = new THREE.Mesh(geo, mat);
    waveSurface.position.y = -0.05;
    waveSurface.visible = config.display.showSurface;
    scene.add(waveSurface);
  }

  // InstancedMesh 作成
  function createInstancedNodes() {
    if (instancedNodes) { scene.remove(instancedNodes); instancedNodes.geometry.dispose(); instancedNodes.material.dispose(); instancedNodes = null; }
    const geometry = new THREE.SphereGeometry(0.008, 16, 12);
    const material = new THREE.MeshPhysicalMaterial({ metalness: 0.2, roughness: 0.4, clearcoat: 0.3, clearcoatRoughness: 0.2 });
    instancedNodes = new THREE.InstancedMesh(geometry, material, nodeCount);
    instancedNodes.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    const matrix = new THREE.Matrix4();
    const color = new THREE.Color();
    // 初期配置は basePositions（後で確定）で埋める
    for (let i = 0; i < nodeCount; i++) {
      matrix.makeTranslation(0, 0, 0);
      instancedNodes.setMatrixAt(i, matrix);
      color.setHSL(i / Math.max(1, nodeCount), 0.7, 0.5);
      instancedNodes.setColorAt(i, color);
    }
    scene.add(instancedNodes);
    // 旧メッシュは非表示
    nodes.forEach(n => n.visible = false);
  }

  // ノード配置設定
  // 既定: 3x5 の長方格子。config.json の nodes.{rows,cols} または nodes.count を優先
  let cols = 3;
  let rows = 5;
  let configuredCount = null;
  (function loadConfigSync(){
    try {
      const xhr = new XMLHttpRequest();
      xhr.open('GET', './config.json', false);
      xhr.send(null);
      if (xhr.status === 200) {
        const cfg = JSON.parse(xhr.responseText);
        if (cfg && cfg.nodes) {
          if (typeof cfg.nodes.count === 'number' && cfg.nodes.count > 0) {
            configuredCount = Math.floor(cfg.nodes.count);
          } else {
            const c = parseInt(cfg.nodes.cols, 10);
            const r = parseInt(cfg.nodes.rows, 10);
            if (Number.isFinite(c) && c > 0) cols = c;
            if (Number.isFinite(r) && r > 0) rows = r;
          }
        }
      }
    } catch (e) {}
  })();
  const spacing = 0.05; // 50mm
  const width = (cols - 1) * spacing;
  const height = (rows - 1) * spacing;
  const startX = -width / 2;
  const startZ = -height / 2;

  // 平面/ワイヤは後回し: 当面は点のみ
  const useSurface = false;
  let plane = null;
  let wire = null;

  // ラベルスプライト作成
  function createLabelSprite(text) {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    ctx.font = '16px Arial';
    const textWidth = ctx.measureText(text).width;
    canvas.width = Math.ceil(textWidth + 12);
    canvas.height = 22;
    const ctx2 = canvas.getContext('2d');
    ctx2.font = '16px Arial';
    ctx2.fillStyle = 'rgba(0,0,0,0.6)';
    ctx2.fillRect(0, 0, canvas.width, canvas.height);
    ctx2.fillStyle = '#fff';
    ctx2.fillText(text, 6, 16);
    const tex = new THREE.CanvasTexture(canvas);
    tex.minFilter = THREE.LinearFilter;
    const mat = new THREE.SpriteMaterial({ map: tex, transparent: true });
    const sprite = new THREE.Sprite(mat);
    sprite.renderOrder = 10;
    sprite.scale.set(0.04, 0.014, 1);
    return sprite;
  }

  // 初期ノード数（configが読めなかった場合は格子=15）
  let nodeCount = configuredCount != null ? configuredCount : (cols * rows);
  const sphereGeometry = new THREE.SphereGeometry(0.006, 16, 12);
  const baseMaterial = new THREE.MeshStandardMaterial({ color: 0x4fc3f7, metalness: 0.1, roughness: 0.6 });
  const nodes = [];
  const labels = [];
  const nodeMaterials = [];
  const basePositions = [];

  let idx = 0;
  if (useSurface) {
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const x = startX + c * spacing;
        const z = startZ + r * spacing;
        const y = 0;
        const matClone = baseMaterial.clone();
        const mesh = new THREE.Mesh(sphereGeometry, matClone);
        // 入力Z(上下)をThree.jsのY(上下)へ適用するため、基本平面はXZではなくXYへ置く
        // ただし現在はサーフェス無効のため、初期点配置だけXYへマップ
        mesh.position.set(x, z, y);
        mesh.material.color.setHSL(idx / nodeCount, 0.6, 0.55);
        root.add(mesh);
        nodes.push(mesh);
        nodeMaterials.push(matClone);
        basePositions.push(mesh.position.clone());
        const sprite = createLabelSprite(`N${idx}`);
        sprite.position.set(x, z + 0.015, y);
        sprite.visible = false;
        root.add(sprite);
        labels.push(sprite);
        idx++;
      }
    }
  } else {
    // 任意点数: 初期配置は円周上（後でCSVや受信で上書き）
    const radius = Math.max(width, height) || 0.1;
    for (let i = 0; i < nodeCount; i++) {
      const t = (i / nodeCount) * Math.PI * 2;
      const x = Math.cos(t) * radius * 0.5;
      const z = Math.sin(t) * radius * 0.5;
      const y = 0;
      const matClone = baseMaterial.clone();
      const mesh = new THREE.Mesh(sphereGeometry, matClone);
      mesh.position.set(x, z, y);
      mesh.material.color.setHSL(i / nodeCount, 0.6, 0.55);
      root.add(mesh);
      nodes.push(mesh);
      nodeMaterials.push(matClone);
      basePositions.push(mesh.position.clone());
      const sprite = createLabelSprite(`N${i}`);
      sprite.position.set(x, z + 0.015, y);
      sprite.visible = false;
      root.add(sprite);
      labels.push(sprite);
    }
  }

  // Center controls to surface center
  controls.target.set(0, 0, 0);
  controls.update();

  // UI
  const scaleEl = document.getElementById('scale');
  const ampEl = document.getElementById('amp');
  const labelsEl = document.getElementById('labels');
  const resetEl = document.getElementById('reset');
  const nodesCsvEl = document.getElementById('nodesCsv');
  // 追加UI: レイアウト切替ボタン
  (function addLayoutButton(){
    try {
      const ui = document.getElementById('ui');
      if (!ui) return;
      const btn = document.createElement('button');
      btn.textContent = 'Layout: ' + config.display.layout;
      btn.style.marginLeft = '8px';
      btn.addEventListener('click', () => {
        const layouts = ['grid','helix','sphere','cylinder'];
        const idx = layouts.indexOf(config.display.layout);
        config.display.layout = layouts[(idx + 1) % layouts.length];
        btn.textContent = 'Layout: ' + config.display.layout;
        createInstancedNodes();
        createWaveSurface();
        if (trailSystem) { scene.remove(trailSystem.group); trailSystem = null; }
        if (config.display.showTrails) { trailSystem = new TrailSystem(nodeCount, config.display.trailLength); scene.add(trailSystem.group); }
      });
      ui.appendChild(btn);
    } catch (e) { /* ignore */ }
  })();
  const visPlaneEl = document.getElementById('visPlane');
  const visWireEl = document.getElementById('visWire');
  const visGridEl = document.getElementById('visGrid');
  const visAxesEl = document.getElementById('visAxes');
  const toggleEl = document.getElementById('toggle');
  const statsEl = document.getElementById('stats');
  let running = true;
  if (toggleEl) {
    toggleEl.addEventListener('click', () => {
      running = !running;
      toggleEl.textContent = running ? 'Pause' : 'Resume';
    });
  }
  if (resetEl) {
    resetEl.addEventListener('click', () => {
      camera.position.set(0.25, 0.25, 0.6);
      if (controls) {
        controls.target.set(0, 0, 0);
        controls.update();
      } else {
        camera.lookAt(0, 0, 0);
      }
    });
  }
  if (visPlaneEl) visPlaneEl.addEventListener('change', () => { if (plane) plane.visible = visPlaneEl.checked; });
  if (visWireEl) visWireEl.addEventListener('change', () => { if (wire) wire.visible = visWireEl.checked; });
  if (visGridEl) visGridEl.addEventListener('change', () => grid.visible = visGridEl.checked);
  if (visAxesEl) visAxesEl.addEventListener('change', () => axes.visible = visAxesEl.checked);

  // CSVからノード座標を読み込み適用
  function parseCsvText(text) {
    const lines = text.split(/\r?\n/).filter(l => l.trim().length > 0);
    let start = 0;
    if (/^\s*id\s*,/i.test(lines[0])) start = 1; // ヘッダ行スキップ
    const newPositions = [];
    for (let i = start; i < lines.length; i++) {
      const cols = lines[i].split(',');
      if (cols.length < 4) continue;
      const id = parseInt(cols[0].trim(), 10);
      const x = parseFloat(cols[1]);
      const y = parseFloat(cols[2]);
      const z = parseFloat(cols[3]);
      if (!Number.isFinite(id) || id < 0 || id >= nodeCount) continue;
      if ([x, y, z].some(v => !Number.isFinite(v))) continue;
      // 入力系(X左右, Y前後, Z上下) → Three.js系(X, Y(up), Z(depth)) へマッピング
      // worldX = X, worldY = Z, worldZ = Y
      newPositions[id] = new THREE.Vector3(x, z, y);
    }
    for (let i = 0; i < nodeCount; i++) {
      if (!newPositions[i]) newPositions[i] = basePositions[i].clone();
    }
    return newPositions;
  }

  function applyPositions(newPositions) {
    for (let i = 0; i < nodeCount; i++) {
      const p = newPositions[i];
      basePositions[i].copy(p);
      // 旧メッシュが残っている場合は同期（非表示運用だが安全のため）
      if (nodes[i]) nodes[i].position.copy(p);
      if (labels[i]) labels[i].position.set(p.x, p.y + 0.015, p.z);
    }
    if (instancedNodes) {
      const matrix = new THREE.Matrix4();
      for (let i = 0; i < nodeCount; i++) {
        matrix.setPosition(basePositions[i]);
        instancedNodes.setMatrixAt(i, matrix);
      }
      instancedNodes.instanceMatrix.needsUpdate = true;
    }
    if (controls) { controls.target.set(0, 0, 0); controls.update(); }
  }

  async function loadNodesFromCsv(file) {
    try {
      const text = await file.text();
      const newPositions = parseCsvText(text);
      applyPositions(newPositions);
    } catch (e) {
      console.error('CSV load error', e);
    }
  }

  async function tryLoadDefaultCsv() {
    try {
      const res = await fetch('./nodes.csv', { cache: 'no-store' });
      if (res.ok) {
        const text = await res.text();
        // 行数チェック
        const n = text.split(/\r?\n/).filter(l => l.trim().length > 0 && !/^\s*id\s*,/i.test(l)).length;
        if (n !== nodeCount) {
          alert(`警告: nodes.csv の行数(${n})と設定ノード数(${nodeCount})が一致しません。`);
        }
        const newPositions = parseCsvText(text);
        applyPositions(newPositions);
      }
    } catch (e) { /* ignore */ }
  }

  if (nodesCsvEl) {
    nodesCsvEl.addEventListener('change', async () => {
      if (nodesCsvEl.files && nodesCsvEl.files[0]) {
        await loadNodesFromCsv(nodesCsvEl.files[0]);
        // CSVの行数チェック
        try {
          const text = await nodesCsvEl.files[0].text();
          const n = text.split(/\r?\n/).filter(l => l.trim().length > 0 && !/^\s*id\s*,/i.test(l)).length;
          if (n !== nodeCount) {
            alert(`警告: nodes.csv の行数(${n})と設定のノード数(${nodeCount})が一致しません。`);
          }
        } catch (e) {}
      }
    });
  }

  // 起動時に既定のCSVがあれば自動適用（countモードの初期円配置を上書き）
  tryLoadDefaultCsv();

  // 初期作成: InstancedMesh / WaveSurface / Trail
  createInstancedNodes();
  createWaveSurface();
  if (config.display.showTrails) {
    trailSystem = new TrailSystem(nodeCount, config.display.trailLength);
    scene.add(trailSystem.group);
  }

  // ダブルクリックで最寄りノードへ注視&ハイライト
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let highlightedIndex = -1;
  function setHighlight(index) {
    if (highlightedIndex === index) return;
    if (highlightedIndex >= 0) {
      nodeMaterials[highlightedIndex].emissive = new THREE.Color(0x000000);
      nodeMaterials[highlightedIndex].emissiveIntensity = 0.0;
      nodeMaterials[highlightedIndex].metalness = 0.1;
      nodeMaterials[highlightedIndex].roughness = 0.6;
    }
    highlightedIndex = index;
    if (highlightedIndex >= 0) {
      nodeMaterials[highlightedIndex].emissive = new THREE.Color(0xffcc00);
      nodeMaterials[highlightedIndex].emissiveIntensity = 0.8;
      nodeMaterials[highlightedIndex].metalness = 0.3;
      nodeMaterials[highlightedIndex].roughness = 0.4;
    }
  }
  renderer.domElement.addEventListener('dblclick', (event) => {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const intersects = raycaster.intersectObjects(nodes, false);
    if (intersects.length > 0) {
      const obj = intersects[0].object;
      const index = nodes.indexOf(obj);
      if (index >= 0) {
        setHighlight(index);
        const target = nodes[index].position.clone();
        if (controls) {
          controls.target.copy(target);
          controls.update();
        } else {
          camera.lookAt(target);
        }
      }
    }
  });

  // Simple FPS counter
  let lastTime = performance.now();
  let frames = 0;
  let fps = 0;
  function updateFps(now) {
    frames++;
    if (now - lastTime >= 1000) {
      fps = frames / ((now - lastTime) / 1000);
      frames = 0;
      lastTime = now;
      if (statsEl) statsEl.textContent = `FPS: ${fps.toFixed(0)}`;
    }
  }

  // Sine wave parameters per node（拡張に追随できるよう配列で管理）
  const amplitudes = Array.from({ length: nodeCount }, (_, i) => 0.006 + 0.004 * (i / nodeCount));
  const freqs = Array.from({ length: nodeCount }, (_, i) => 0.5 + 0.05 * i);
  const phases = Array.from({ length: nodeCount }, (_, i) => (i / nodeCount) * Math.PI * 2);

  // Color map by instantaneous amplitude (optional visual)
  function ampToColor(a) {
    const t = Math.min(1, Math.max(0, (a + 1) / 2));
    const hue = 0.66 * (1 - t); // blue->red
    const col = new THREE.Color().setHSL(hue, 0.9, 0.5);
    return col;
  }

  // Public hook for future UDP integration
  let latestAmplitudes = new Float32Array(nodeCount);
  let hasLiveData = false;
  let lastUpdateMs = 0;

  function ensureNodeCapacity(newCount) {
    if (!Number.isFinite(newCount) || newCount <= nodeCount) return;
    // config.countモード: 円周に追加配置
    const radius = Math.max(width, height) || 0.1;
    for (let i = nodeCount; i < newCount; i++) {
      const t = (i / newCount) * Math.PI * 2;
      const x = Math.cos(t) * radius * 0.5;
      const z = Math.sin(t) * radius * 0.5;
      const y = 0;
      const matClone = baseMaterial.clone();
      const mesh = new THREE.Mesh(sphereGeometry, matClone);
      mesh.position.set(x, z, y);
      mesh.material.color.setHSL(i / newCount, 0.6, 0.55);
      root.add(mesh);
      nodes.push(mesh);
      nodeMaterials.push(matClone);
      basePositions.push(mesh.position.clone());
      const sprite = createLabelSprite(`N${i}`);
      sprite.position.set(x, z + 0.015, y);
      sprite.visible = false;
      root.add(sprite);
      labels.push(sprite);

      // 波形パラメータを拡張
      amplitudes[i] = 0.006 + 0.004 * (i / newCount);
      freqs[i] = 0.5 + 0.05 * i;
      phases[i] = (i / newCount) * Math.PI * 2;
    }
    const next = new Float32Array(newCount);
    next.set(latestAmplitudes);
    latestAmplitudes = next;
    nodeCount = newCount;
  }

  // Python側からノード数を指示できるフック
  window.setNodeCount = function(n) {
    try { ensureNodeCapacity(Number(n)); } catch (e) { console.error(e); }
  }
  window.updateNodes = function(payload) {
    // payload: { nodes: [{ id, amplitude }], timestamp }
    try {
      if (!payload || !payload.nodes || !Array.isArray(payload.nodes)) {
        console.warn('Invalid payload received');
        return;
      }
      for (let i = 0; i < payload.nodes.length; i++) {
        const item = payload.nodes[i];
        const id = item.id | 0;
        if (id >= 0 && id < nodeCount) {
          const a = Number(item.amplitude);
          if (!Number.isNaN(a) && Number.isFinite(a)) {
            latestAmplitudes[id] = a;
          }
        }
      }
      hasLiveData = true;
      lastUpdateMs = performance.now();
    } catch (e) {
      console.error('updateNodes error', e);
    }
  }

  // Resize
  window.addEventListener('resize', () => {
    try {
      const w = window.innerWidth;
      const h = window.innerHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    } catch (e) {
      console.error('Resize error', e);
    }
  });

  // Animation loop
  const clock = new THREE.Clock();
  const posAttr = null; // 当面サーフェスは無効
  function animate() {
    try {
      const t = clock.getElapsedTime();
      if (controls && typeof controls.update === 'function') controls.update();

      if (running) {
        const scale = scaleEl ? parseFloat(scaleEl.value) : 1;
        const ampScale = ampEl ? parseFloat(ampEl.value) : 1;
        root.scale.setScalar(scale || 1);

        // レイアウトに基づくベース位置
        const layoutPositions = getLayoutPositions(config.display.layout);
        for (let i = 0; i < nodeCount; i++) {
          basePositions[i].copy(layoutPositions[i] || basePositions[i]);
        }

        // InstancedMesh 位置・色更新
        if (instancedNodes) {
          const matrix = new THREE.Matrix4();
          const color = new THREE.Color();
          const useLive = hasLiveData && (performance.now() - lastUpdateMs) <= 500;
          for (let i = 0; i < nodeCount; i++) {
            const a = useLive ? (latestAmplitudes[i] * ampScale) : 0;
            const pos = basePositions[i].clone();
            pos.y += a * 0.2;
            matrix.identity();
            matrix.setPosition(pos);
            instancedNodes.setMatrixAt(i, matrix);
            const hue = 0.66 - Math.max(-0.5, Math.min(0.5, a)) * 0.33;
            color.setHSL(hue, 0.8, 0.5 + a * 0.2);
            instancedNodes.setColorAt(i, color);
          }
          instancedNodes.instanceMatrix.needsUpdate = true;
          instancedNodes.instanceColor.needsUpdate = true;
        }

        // ラベル（任意）
        if (labelsEl && labelsEl.checked) {
          for (let i = 0; i < nodeCount; i++) {
            const a = latestAmplitudes[i] * (ampEl ? parseFloat(ampEl.value) : 1);
            const p = basePositions[i];
            const sprite = labels[i];
            if (sprite) {
              sprite.visible = true;
              sprite.position.set(p.x, p.y + a * 0.2 + 0.015, p.z);
            }
          }
        } else {
          for (let i = 0; i < labels.length; i++) if (labels[i]) labels[i].visible = false;
        }

        // サーフェス
        if (waveSurface && config.display.showSurface) {
          const arr = waveSurface.material.uniforms.amplitudes.value;
          if (arr.length !== nodeCount) {
            createWaveSurface();
          } else {
            arr.set(latestAmplitudes);
            waveSurface.material.uniforms.amplitudes.needsUpdate = true;
          }
        }

        // トレイル
        if (trailSystem && config.display.showTrails) {
          const posList = [];
          const useLive = hasLiveData && (performance.now() - lastUpdateMs) <= 500;
          for (let i = 0; i < nodeCount; i++) {
            const a = useLive ? (latestAmplitudes[i] * ampScale) : 0;
            const p = basePositions[i].clone();
            p.y += a * 0.2;
            posList.push(p);
          }
          trailSystem.update(posList);
        }
      }

      // ラベルは半透明マテリアルのため描画順最後
      renderer.render(scene, camera);
      updateFps(performance.now());
    } catch (e) {
      console.error('Animation error', e);
    } finally {
      requestAnimationFrame(animate);
    }
  }

  // グローバルエラーハンドリング
  const errorEl = document.getElementById('error');
  function showError(message) {
    if (!errorEl) return;
    errorEl.textContent = message;
    errorEl.style.display = 'block';
  }
  window.addEventListener('error', (e) => {
    showError(`Error: ${e.message}`);
  });
  window.addEventListener('unhandledrejection', (e) => {
    showError(`Unhandled: ${e.reason}`);
  });

  animate();
})();


