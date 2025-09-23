# Cursor 指示: RTX 3060向けに最適化した超高速「間違い探し」MVP

【目的】
- 画像A/B比較 → YOLOv8sで物体検出
- CLIPでbbox埋め込み → FAISSで類似マッチング
- マッチしなかったbboxを「間違い」として赤丸描画
- 50ms以内に結果画像出力、差分JSON生成
- JSONをOpenAI Realtime APIに渡し、500ms以内に音声応答開始

【GPU前提】
- NVIDIA RTX 3060 (12GB)
- CUDA 12.1
- FP16推論有効化

【ライブラリ・バージョン】
- torch==2.3.1 + torchvision==0.18.1
- ultralytics==8.2.73
- open_clip_torch==2.24.0
- faiss-gpu==1.7.4
- opencv-python==4.9.0.80
- numpy==1.26.4, pillow==10.3.0

【モデル】
- YOLO: yolov8s.pt（models/ に事前DL）
- CLIP: ViT-B-32 (laion2b_s34b_b79k)
- FAISS: IndexFlatIP (L2正規化ベクトル)

【速度目標】
- YOLO推論 A+B ≈ 30ms
- CLIP埋め込み A+B ≈ 10ms
- FAISS検索＋可視化 ≈ 10ms
- 合計 ≈ 50ms以内

【実装要件】
- 単一スクリプト（diff_finder.py）
- 引数: --a 画像A --b 画像B --model yolov8s.pt
- 出力: out/diff.png, out/diff.json
- 各処理ステップのms計測をprint
- CLIPはバッチ処理
- FAISSはGPUを使う（利用不可ならCPU fallback）
- OpenAI Realtime APIは未設定時にモック応答（300msスリープ後に開始ログ）
- コードは最小関数・console.log/print多め・変更前/後コメント付き

【性能テスト】
- サンプル画像で実行時、50ms以内に差分画像が生成されること
- JSONに差分数・差分クラスが記録されること
- OPENAI_API_KEYがある場合は音声応答が始まる、ない場合はモックがログを出力

【注意】
- 640pxで遅い場合は512pxへダウンサンプリング切替
- bbox数が多い場合は上位30件に制限
