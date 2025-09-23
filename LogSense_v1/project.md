# LogSense_v1: RTX 3060向け超高速「間違い探し」AI

【目的】
- 画像A/B比較 → YOLOv8sで物体検出
- CLIPでbbox埋め込み → FAISSで類似マッチング
- マッチしなかったbboxを「間違い」として赤丸描画
- 高速で結果画像出力、差分JSON生成
- JSONをOpenAI Realtime APIに渡し、音声応答開始
- GUIアプリで直感的な操作を提供

【GPU前提】
- NVIDIA RTX 3060 (12GB)
- CUDA 12.1
- FP16推論有効化

【ライブラリ・バージョン】
- torch==2.3.1 + torchvision==0.18.1
- ultralytics==8.2.73
- open_clip_torch==2.24.0
- faiss-cpu==1.7.4 (Windows対応)
- opencv-python==4.9.0.80
- numpy==1.26.4, pillow==10.3.0
- openai==1.51.0

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
- メインスクリプト（diff_finder.py）- CLIP+FAISS版
- GUIアプリ（yolo_diff_gui_fixed.py）- YOLO差分検出版
- 引数: --a 画像A --b 画像B --model yolov8s.pt
- 出力: out/diff.png, out/diff.json
- 各処理ステップのms計測をprint
- CLIPはバッチ処理
- FAISSはCPU版（Windows対応）
- OpenAI Realtime APIは未設定時にモック応答
- GUIで直感的な画像選択・差分可視化

【性能テスト】
- GUIアプリで画像選択・差分検出が正常に動作すること
- 左側画像に赤丸で差分が表示されること
- 処理時間・検出数・詳細情報が表示されること
- コマンドライン版でも同様の結果が得られること
- OPENAI_API_KEYがある場合は音声応答が始まる、ない場合はモックがログを出力

【注意】
- 640pxで遅い場合は512pxへダウンサンプリング切替
- bbox数が多い場合は上位30件に制限
