# CUDA(GPU)対応 作業記録 — CPU→GPU 移行

作成日: 2026-06-07 / 対象: LogSense_v6 (robot.py / app_gpu.py)

このファイルは「PyTorch を CPU 版から GPU(CUDA) 版へ入れ替えた作業」を、
あとから誰でも再現・切り戻しできるように、コマンドとバージョンを正確に記録するもの。

---

## 1. 背景・きっかけ

- VLM(画像認識) の実況が遅い問題を調査中、venv の PyTorch が **CPU 専用ビルド**だと判明。
  - 確認コマンド: `python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`
  - 結果(移行前): `2.11.0+cpu  False`
- 影響: **YOLO(ultralytics) もずっと CPU 実行**だった（起動ログの「CPUモード」と一致）。
- 補足: **ollama は別ランタイムで自前の CUDA を使う**ため、ollama 上のモデル
  (gemma4:e2b, qwen3-vl:2b 等) は GPU で動いていた。venv の torch とは無関係。

---

## 2. ハードウェア / ドライバ環境(確認済み)

| 項目 | 値 |
|---|---|
| GPU | NVIDIA GeForce RTX 3060 Laptop GPU (VRAM 6144 MiB = 6GB) |
| ドライバ | 560.94 |
| ドライバ対応 CUDA(最大) | 12.6 |
| OS | Windows 11 (10.0.26200) |
| ollama | 0.30.6 (別ランタイム・GPU使用) |

- 確認コマンド: `nvidia-smi`（"CUDA Version: 12.6" 表示）
- ドライバが 12.6 対応なので、torch は **cu124**(CUDA 12.4 ランタイム) を採用。
  cu124 は driver 12.6 で後方互換で動作する。cu128 は driver 12.8 以上が必要なため不採用。

---

## 3. バージョン(移行前 → 移行後) ※正確値

| パッケージ | 移行前(CPU) | 移行後(GPU) |
|---|---|---|
| torch | **2.11.0+cpu** | **2.6.0+cu124** |
| torchvision | **0.26.0+cpu** | **0.21.0+cu124** |
| sympy | 1.14.0 | **1.13.1**(torch 2.6 依存で自動ダウングレード) |
| numpy | 2.2.6 | 2.2.6(変化なし) |
| ultralytics | 8.4.41 | 8.4.41(変化なし・新torchで動作確認済み) |

> 注: torch は 2.11→2.6 へ下がる。cu124 公式 index の最新が 2.6.0 系のため。
> ultralytics / transformers いずれも torch 2.6 で動作するため問題なし。

---

## 4. 実施した手順(時系列・1つずつ)

### 手順0: 事前確認
```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# => 2.11.0+cpu False   (CPU専用と判明)
nvidia-smi   # ドライバ560.94 / CUDA 12.6 を確認
```

### 手順1(失敗): そのまま cu124 を install → 置き換わらなかった
```bash
python -m pip install --index-url https://download.pytorch.org/whl/cu124 torch torchvision
```
- **結果: 失敗(無効)**。pip は「torch は既にインストール済み(2.11.0+cpu)で要件を満たす」
  と判断し、**再インストールしなかった**。検証すると依然 `2.11.0+cpu / cuda False`。
- 教訓: 既存 torch があるときは、**先に uninstall** しないと CUDA 版へ置き換わらない。

### 手順2(成功): 明示的に削除 → cu124 を入れ直し
```bash
python -m pip uninstall -y torch torchvision
python -m pip install --index-url https://download.pytorch.org/whl/cu124 torch torchvision
```
- 結果: `Successfully installed torch-2.6.0+cu124 torchvision-0.21.0+cu124`
  （併せて sympy 1.14.0 → 1.13.1 に自動ダウングレード）

### 手順3: 検証(GPU有効化の確認)
```bash
python -c "import torch,torchvision; print(torch.__version__, torchvision.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# => 2.6.0+cu124 0.21.0+cu124 True NVIDIA GeForce RTX 3060 Laptop GPU
python -c "import ultralytics, torch; print(ultralytics.__version__, torch.cuda.is_available())"
# => 8.4.41 True   (YOLO が新torchで正常 import・CUDA認識)
```

---

## 5. 設計方針(GPU/CPU の役割分担) ※重要

- **差分画像処理は CPU が有利**（absdiff / 閾値 / モルフォロジ / カラーマップは軽量。
  GPU に送ると転送・同期のオーバーヘッドで逆に遅い）。→ **差分は CPU のまま**。
  - robot.py では既に毎フレーム `compute_difference_visual`(CPU) で描画。
- **GPU 化するのは YOLO 推論 と VLM(画像認識) のみ**。

---

## 6. タスク状況

- [x] `app_gpu.py` の YOLO を GPU(device=cuda) で動かすよう修正(完了)
      - 追加した関数 `build_streaming_yolo_pipeline_gpu()`：`yolo_stream_config.json` を
        読み、`model.device` を `"cuda"`(CUDA不可なら None=CPU) に上書きして構築。
        ※共有設定ファイルは変更せず、app_gpu.py 側だけで cuda 指定。
      - 呼び出し箇所を `build_streaming_yolo_pipeline()` →
        `build_streaming_yolo_pipeline_gpu()` に変更。ウィンドウタイトルに "(GPU)" 付与。
      - **差分処理は CPU のまま**（方針どおり）。
- [x] YOLO が実際に GPU で動くか確認(完了)
      - `p.model.device == cuda:0` を確認。
      - YOLO 推論時間: 初回 0.584s(ロード込) → **ウォーム 約0.010s/フレーム**(GPU)。
      - 備考: 起動時の "gpu_utils CPUモード" ログは差分整列用の別モジュール由来で、
        YOLO とは無関係(YOLO は cuda:0)。`expandable_segments not supported` 警告は
        Windows の無害な警告。
- [ ] (別途) transformers + Qwen2.5-VL-3B-AWQ で VLM を GPU 実行するプロトタイプ計測

---

## 7. CPU 版へ戻す手順(切り戻し / ロールバック)

GPU 版で不具合が出た場合、以下で**移行前(CPU)状態に復元**できる。

### 7-1. torch を CPU 版へ戻す
```bash
python -m pip uninstall -y torch torchvision
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.11.0 torchvision==0.26.0
```
- 確認: `python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`
  → `2.11.0+cpu False` になれば復元成功。
- 補足: sympy は torch が必要版を自動解決する。明示的に戻すなら
  `python -m pip install sympy==1.14.0`。

### 7-2. アプリ側の切り戻し
- `app.py`(オリジナル)は**一切変更していない**。困ったら app.py を使えばよい。
- `app_gpu.py` は app.py のコピーに GPU 改修を加えたもの。GPU 改修を捨てたい場合は
  `app_gpu.py` を削除、または app.py から作り直す。
- robot.py の差分は CPU 処理なので torch の CPU/GPU に依存しない。

### 7-3. 注意
- `git` 管理外のファイルがあるため、切り戻しは**個別ファイル単位**で行う（一括 reset しない）。
- ollama は今回の作業と独立。torch を戻しても ollama 側の挙動は変わらない。

---

## 8. 既知の差異・メモ

- `requirements.txt` は `torch>=2.5.1` を **cu121** index 指定だが、今回は **cu124** を使用
  （driver 12.6 に合わせ、torch 2.6.0+cu124 を採用）。requirements の更新は未実施。
  必要なら別途、`requirements.txt` の index を cu124 / バージョンを 2.6.0 に揃える。
- VRAM 6GB のため、GPU 上のモデル同居数に注意（YOLO + VLM など）。

---

## 9. transformers VLM 化(Qwen2.5-VL) 依存導入 ※進行中

目標: ollama の 2モデル(gemma4:e2b + qwen3-vl:2b) をやめ、**transformers の
Qwen2.5-VL 1個で会話+画像を GPU 実行**(VRAM節約・vision高速化)。量子化は AWQ(autoawq)。

### 導入したもの / バージョン
| パッケージ | バージョン | 備考 |
|---|---|---|
| transformers | **4.49.0** | ※下記の理由で 5.x から固定 |
| accelerate | 1.13.0 | |
| qwen-vl-utils | 0.0.14 | Qwen-VL の画像入力前処理ヘルパ |
| tokenizers | 0.21.4 | transformers 4.49 依存 |
| huggingface-hub | 0.36.2 | |
| autoawq | (導入中) | AWQ 4bit を GPU 実行するための backend |

### ハマりどころ(記録)
- 最初 `pip install "transformers>=4.49.0"` が **transformers 5.10.2** を入れたが、
  5.x は **torch≥2.7 が必要**(`torch.float8_e8m0fnu` を参照) で、当環境の **torch 2.6.0+cu124
  では import 失敗**。
  - エラー: `module 'torch' has no attribute 'float8_e8m0fnu'`
  - 対処: **transformers==4.49.0 に固定**(Qwen2.5-VL 対応の初版・torch2.6/AWQ と相性良)。
- 検証: `transformers 4.49.0 / torch 2.6.0+cu124 / cuda True / Qwen2.5-VL import OK`。

### 切り戻し(この依存を外す)
```bash
python -m pip uninstall -y autoawq autoawq-kernels transformers accelerate qwen-vl-utils
# ollama 運用に戻す場合は robot.py の LLM を OllamaClient のまま使う
```

### autoawq は不採用(Windowsで導入失敗)
- Windows 用ビルド済み wheel なし → ソースビルド必須。
- ビルド分離環境に torch が無く失敗(`No module named 'torch'`)。`--no-build-isolation`でも
  `bdist_wheel` 不足。さらに **nvcc 11.8 と torch cu124(12.4) が不一致**でカーネル compile も困難。
- → **bitsandbytes 4bit に切替**(Windows 対応 wheel・コンパイル不要)。

### 採用: bitsandbytes 4bit + Qwen2.5-VL-3B-Instruct(公式BF16)
| パッケージ | バージョン |
|---|---|
| bitsandbytes | 0.49.2 |
| モデル | Qwen/Qwen2.5-VL-3B-Instruct (公式・safetensors・remote_code不要) |

読込: `BitsAndBytesConfig(load_in_4bit, nf4, compute_dtype=fp16, double_quant)` + `device_map=cuda:0`。

### プロトタイプ計測結果(GO) ※bench_qwen_vl.py で測定
| 項目 | 結果 |
|---|---|
| VRAM | allocated 2.42GB / reserved 2.59GB / **peak 3.03GB** |
| 会話 | 1.3s(初回) → **0.3s(ウォーム)** |
| 画像 | **2.5s → 2.2s**(日本語・正確) |

- ollama(qwen3-vl) の画像 15〜28秒に対し **約2秒(≒10倍速)**。
- VRAM ~3GB の 1モデルで会話+画像を兼用 → YOLO(~0.7GB)と同居しても 6GB に余裕。
- 結論: **GO**。robot.py の LLM を ollama → transformers(Qwen2.5-VL 4bit) へ置換する。

### 次の手順
1. transformers 版クライアント(会話ストリーム+画像キャプション、1モデル)を実装。
2. robot.py を OllamaClient → 新クライアントへ差し替え(ollama 2モデルは廃止)。
3. 実機確認。


