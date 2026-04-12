結論：**そのプランは一部✗（誤りあり）→ 修正すれば◎。**
特に **`opencv-contrib-python(-headless)` は公式ではCUDA対応ではありません**。`pip`の公式wheelはCPU版のみで、CUDAを使うには **自前ビルド** か **コミュニティ製のCUDA対応wheel** を使う必要があります。([OpenCV][1])

以下、「技術的根拠の補強」「正しい変更計画（決定版）」「コピペ手順」「変更前/後コード」をまとめます。

---

# 技術的根拠（補強）

* `pip install opencv[-contrib][-headless]` の公式wheelは**CUDA無効**。GPUを使いたければ **ソースからCUDA有効でビルド**するか、**コミュニティ製CUDA wheel**を使う。([OpenCV][1])
* conda-forgeの `opencv` も既定ではCUDA無効のことが多く、**確実にCUDAを使いたいなら自前ビルド/専用wheelが堅実**。([Stack Overflow][2])
* Windows+PythonでのCUDA有効ビルドは、CMake/VSで**再現可能な手順が公開**されている。([OpenCV][3])
* 代替として、**コミュニティ製のCUDA対応OpenCV wheel**（例：`cudawarped/opencv-python-cuda-wheels`）が継続的にリリースされている（CUDA 12.8対応など）。([GitHub][4])

---

# 正しい変更計画（決定版）

## A. pip派（簡単・速い）：**コミュニティCUDA wheelを使う**

1. 既存の `opencv-*` を**アンインストール**
2. CUDA/cuDNNバージョンを**wheel要件と合わせる**
3. **CUDA対応wheel** を `pip` で導入
4. DNNや画像処理は **環境変数やフラグでCPU/GPUを切替**

## B. ビルド派（柔軟・安心）：**ソースからCUDA有効でビルド**

1. CUDA Toolkit / cuDNN / VS / CMake を用意
2. `opencv` + `opencv_contrib` を取得し、`-DWITH_CUDA=ON` 等で生成
3. `cv2` を Python 環境に組み込み
4. DNN/画像処理の切替はAと同様

> どちらでも **PyTorch(CUDA)** との一貫性は保てます。SAM2/YOLOの **DNN backend/target** 切替もOK。

---

# 具体手順（A案：コミュニティCUDA wheel利用）

> 例：`cudawarped/opencv-python-cuda-wheels`（CUDA 12.8 + cuDNN 9.7系のリリースがあり）([GitHub][4])

## 1) 旧OpenCVの除去

```bash
# 変更前（CPU版が入っている環境）
# pip show opencv-python opencv-contrib-python opencv-python-headless opencv-contrib-python-headless

# 変更後：CPU版を確実にアンインストール
pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless opencv-contrib-python-headless
```

## 2) CUDA/cuDNNをwheel要件に合わせる

* 例：上記リリースは **CUDA 12.8 / cuDNN 9.7.0** を要求（import時にDLL解決が必要）。([GitHub][4])

## 3) CUDA対応OpenCVのインストール

```bash
# 例：ローカルにwhlをダウンロード済みとして
# 変更前：CPU版をpipで入れていた
# pip install opencv-contrib-python-headless

# 変更後：CUDA対応のwhl（ファイル名は入手したものに置換）
pip install .\opencv_python_cuda-4.11.0.20250207-cp312-cp312-win_amd64.whl
```

> ⚠️ pipが依存解決でCPU版OpenCVを**上書き**してしまう問題に遭遇するケースあり。必要に応じて**constraintsファイル**を使い、`opencv-*` を明示的にpin/禁止して衝突を防ぐ。([Stack Overflow][5])

## 4) requirements.txt（最小修正版）

```txt
--index-url https://download.pytorch.org/whl/cu121
torch>=2.5.1
torchvision>=0.20.1

# 変更前：
# opencv-contrib-python-headless>=4.7.0   # CPU版（CUDA非対応）

# 変更後：OpenCVは "このファイルでは" 指定しない（手動でCUDA whlを入れるため）
# （pipの自動依存でCPU版に差し戻される事故を防ぐため）
numpy>=1.24.4,<2.5
tqdm>=4.66.1
hydra-core>=1.3.2
iopath>=0.1.10
pillow>=9.4.0
matplotlib>=3.9.1
scipy>=1.10.0
scikit-image>=0.20.0
imageio>=2.33.0
tifffile>=2022.8.12
lazy-loader>=0.4
```

> **理由**：`requirements.txt` に `opencv-*` を書くと、**CPU版に置き換わるリスク**が高まるため、CUDA wheelは**個別インストール**に分離。([Stack Overflow][5])

---

# 具体手順（B案：ソースからCUDAビルド）

```bash
# 1) 取得
git clone https://github.com/opencv/opencv.git
git clone https://github.com/opencv/opencv_contrib.git
cd opencv
# 任意でタグを合わせる：git checkout 4.11.0
cd ..

# 2) ビルドフォルダ
mkdir build && cd build

# 3) CMake構成（例：VS2022, x64）
cmake -G "Visual Studio 17 2022" -A x64 ^
  -DOPENCV_EXTRA_MODULES_PATH=../opencv_contrib/modules ^
  -DWITH_CUDA=ON ^
  -DOPENCV_DNN_CUDA=ON ^
  -DCUDA_ARCH_BIN=7.5;8.9 ^
  -DCUDA_ARCH_PTX= ^
  -DBUILD_opencv_python3=ON ^
  -DPYTHON3_EXECUTABLE=C:/Path/To/python.exe ^
  -DPYTHON3_INCLUDE_DIR=C:/Path/To/include ^
  -DPYTHON3_LIBRARIES=C:/Path/To/libs/python312.lib ^
  ../opencv

# 4) ビルド＆インストール
cmake --build . --config Release --target INSTALL
```

* 手順は公式フォーラムの**Windows + CUDA + Python再現ガイド**が詳細（DLL解決含む）。([OpenCV][3])

---

# 変更前/後コード（CPU⇄GPU切替・ログ入り）

```python
import os
import time
import cv2
import numpy as np

def log(msg):
    print(f"[INFO] {msg}")  # 追加：簡易ロガー

# 変更前：CPU固定
# net = cv2.dnn.readNet("model.onnx")
# net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
# net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

# 変更後：環境変数でCPU/GPU切替（オフロード制御を追加）
prefer = os.environ.get("PREFER", "CPU").upper()  # 例: set PREFER=CUDA or CUDA_FP16
net = cv2.dnn.readNet("model.onnx")

if prefer in ("CUDA", "CUDA_FP16") and hasattr(cv2, "cuda") and cv2.cuda.getCudaEnabledDeviceCount() > 0:
    log("CUDAが利用可能。DNNをGPUへオフロードします。")
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)       # 追加：GPU backend
    net.setPreferableTarget(
        cv2.dnn.DNN_TARGET_CUDA_FP16 if prefer == "CUDA_FP16" else cv2.dnn.DNN_TARGET_CUDA
    )  # 追加：FP16/FP32切替
else:
    log("CPUで実行します（CUDA無効 or 未指定）。")
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)     # CPU backend
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

# 追加：SIFTやフィルタのCPU/GPU併用サンプル
def smart_gaussian(img: np.ndarray, threshold=1280*720):
    h, w = img.shape[:2]
    pix = h * w
    log(f"Image {w}x{h} pix={pix}")
    if pix >= threshold and hasattr(cv2, "cuda") and cv2.cuda.getCudaEnabledDeviceCount() > 0:
        try:
            t0 = time.time()
            g = cv2.cuda_GpuMat()
            g.upload(img)  # 追加：GPUへオフロード
            gf = cv2.cuda.createGaussianFilter(g.type(), g.type(), (15,15), 0)
            out = gf.apply(g).download()  # 追加：結果をCPUへ戻す
            log(f"GPU Gaussian OK {1000*(time.time()-t0):.1f} ms")
            return out
        except Exception as e:
            log(f"GPU処理失敗 → CPUへフォールバック: {e}")
    t0 = time.time()
    out = cv2.GaussianBlur(img, (15,15), 0)  # CPU
    log(f"CPU Gaussian OK {1000*(time.time()-t0):.1f} ms")
    return out

# 追加：実行例
if __name__ == "__main__":
    dummy = np.random.randint(0,255,(1440,2560,3),np.uint8)
    dummy2 = smart_gaussian(dummy)
    blob = cv2.dnn.blobFromImage(dummy2, 1/255.0, (640,640), swapRB=True, crop=False)
    net.setInput(blob)
    t0 = time.time()
    out = net.forward()
    log(f"DNN forward {1000*(time.time()-t0):.1f} ms, out_has_shape={hasattr(out,'shape')}")
```

---

# 変更点チェック（あなたの原案に対する回答）

* ✅ **「DNN処理の追加／将来のSAM2/YOLOに備える」**：その方針は正しい。上記 `setPreferableBackend/Target` でOK。
* ✅ **「大画像はGPU、小画像はCPU」**：ヒューリスティック切替は実務的に有効（転送コスト対策）。
* ✅ **「環境変数で切替」**：実装例どおりでOK。
* ❌ **「`opencv-contrib-python-headless` をCUDA対応として入れる」**：**誤り**（CPU版）。`pip`の公式wheelはCUDA無効。**CUDA対応wheel**または**自前ビルド**に修正してください。([OpenCV][1])
* ⚠️ **「conda-forge経由でCUDA対応になる」**：**保証なし**。確実性重視ならA/B案を推奨。([Stack Overflow][2])

---

## 最終提案（即実行用）

1. **A案（簡単）**に従い、CPU版OpenCVをアンインストール → **CUDA対応wheel**をインストール。
2. `requirements.txt` から `opencv-*` を**一旦外す**（pipの上書き事故防止）。([Stack Overflow][5])
3. 上の**切替コード**を導入（`PREFER=CPU/CUDA/CUDA_FP16` でテスト）。
4. `cv2.getBuildInformation()` に **`NVIDIA CUDA: YES`** が出るか、`cv2.cuda.getCudaEnabledDeviceCount()>0` をチェック。
5. 問題が出たら、**DLLパスやCUDA/cuDNNの整合**を確認（Windows特有の落とし穴）。([GitHub][6])

この方針でいけば、**PyTorch(CUDA)とOpenCV(CUDA)** の一貫性も担保されます。
必要なら、あなたの **CUDA/cuDNN/VS/Pythonの具体バージョン**に合わせて **最適なwheel選定 or CMakeフラグ**を “変更前/後コメント付き” で作るよ。

[1]: https://forum.opencv.org/t/how-to-get-opencv-contrib-binary-package-with-cuda/6708?utm_source=chatgpt.com "How to get opencv-contrib binary package with CUDA"
[2]: https://stackoverflow.com/questions/59973013/how-to-install-gpu-version-opencv-via-conda?utm_source=chatgpt.com "How to install GPU version OpenCV via conda?"
[3]: https://forum.opencv.org/t/build-opencv-with-cuda-not-working/15979?utm_source=chatgpt.com "Build opencv with cuda not working - Python"
[4]: https://github.com/cudawarped/opencv-python-cuda-wheels/releases?utm_source=chatgpt.com "Releases · cudawarped/opencv-python-cuda-wheels"
[5]: https://stackoverflow.com/questions/79742202/create-a-pip-wheel-for-opencv-built-from-source-to-prevent-overwriting-with-libr?utm_source=chatgpt.com "Create a Pip Wheel for OpenCV Built from Source to ..."
[6]: https://github.com/opencv/opencv/issues/25689?utm_source=chatgpt.com "Building OpenCV for Python with Cuda 12.5 and cuDNN ..."
