# force_sm86.cmake - CUDAアーキテクチャ強制設定
# OpenCVのcompute_8混入を防ぎ、sm_86を強制設定

# 変更前：OpenCV標準のアーキ自動判定に任せる
# （結果：compute_8 が紛れ込む場合がある）

# 変更後：sm_86 をキャッシュに"強制"注入
set(CUDA_ARCH_BIN "8.6" CACHE STRING "" FORCE)          # 追加：BINを8.6で固定
set(CMAKE_CUDA_ARCHITECTURES "86" CACHE STRING "" FORCE) # 追加：新CMake系も86で固定
set(CUDA_ARCH_PTX "" CACHE STRING "" FORCE)              # 追加：PTX生成を無効化（compute_8混入防止）
# 追加：万一のため nvcc フラグも明示（重複は無害）
set(CUDA_NVCC_FLAGS "--generate-code=arch=compute_86,code=sm_86" CACHE STRING "" FORCE)

# 追加：Pythonライブラリパスのエスケープ事故防止
set(PYTHON3_LIBRARIES "C:/Users/megap/AppData/Local/Programs/Python/Python310/libs/python310.lib" CACHE FILEPATH "" FORCE)
