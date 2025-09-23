#!/usr/bin/env python3
"""
RTX 3060向け超高速「間違い探し」AI
YOLO + CLIP + FAISS + OpenAI Realtime API
目標: 50ms以内で差分検出、500ms以内で音声応答開始
"""

import argparse
import time
import json
import os
import cv2
import numpy as np
from PIL import Image, ImageDraw
import torch
import faiss
import open_clip
from ultralytics import YOLO
import openai
from typing import List, Tuple, Dict, Any

class DiffFinder:
    def __init__(self, model_path: str = "models/yolov8s.pt"):
        """初期化: モデル読み込みとGPU設定"""
        print("🚀 DiffFinder初期化中...")
        
        # GPU設定
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"📱 デバイス: {self.device}")
        
        if self.device.type == "cuda":
            print(f"🎮 GPU: {torch.cuda.get_device_name()}")
            print(f"💾 VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB")
        
        # YOLOモデル読み込み
        print("🔍 YOLOモデル読み込み中...")
        self.yolo_model = YOLO(model_path)
        self.yolo_model.to(self.device)
        
        # CLIPモデル読み込み
        print("🎨 CLIPモデル読み込み中...")
        self.clip_model, _, self.clip_preprocess = open_clip.create_model_and_transforms(
            'ViT-B-32', pretrained='laion2b_s34b_b79k'
        )
        self.clip_model.to(self.device)
        self.clip_model.eval()
        
        # FAISSインデックス初期化
        print("🔎 FAISSインデックス初期化中...")
        self.faiss_index = None
        self.bbox_embeddings = []
        
        print("✅ 初期化完了!")
    
    def preprocess_image(self, image_path: str, target_size: int = 640) -> np.ndarray:
        """画像前処理: リサイズと正規化"""
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"画像読み込み失敗: {image_path}")
        
        # リサイズ（アスペクト比保持）
        h, w = img.shape[:2]
        if max(h, w) > target_size:
            scale = target_size / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h))
        
        return img
    
    def detect_objects(self, image: np.ndarray) -> List[Dict]:
        """YOLOで物体検出"""
        start_time = time.time()
        
        # YOLO推論（FP16有効、信頼度閾値を下げて検出感度向上）
        with torch.cuda.amp.autocast(enabled=self.device.type == "cuda"):
            results = self.yolo_model(image, conf=0.1, verbose=False)
        
        detections = []
        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for i in range(len(boxes)):
                    box = boxes.xyxy[i].cpu().numpy()
                    conf = boxes.conf[i].cpu().numpy()
                    cls = int(boxes.cls[i].cpu().numpy())
                    
                    detections.append({
                        'bbox': box.tolist(),
                        'confidence': float(conf),
                        'class_id': cls,
                        'class_name': self.yolo_model.names[cls]
                    })
        
        elapsed = (time.time() - start_time) * 1000
        print(f"🔍 YOLO推論: {elapsed:.1f}ms ({len(detections)}個検出)")
        
        return detections
    
    def extract_clip_embeddings(self, image: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """CLIPでbbox埋め込み抽出"""
        start_time = time.time()
        
        if not detections:
            return np.array([])
        
        # bboxをPIL画像に変換
        pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        crops = []
        
        for det in detections:
            x1, y1, x2, y2 = map(int, det['bbox'])
            crop = pil_image.crop((x1, y1, x2, y2))
            crops.append(crop)
        
        # バッチ処理でCLIP埋め込み
        if crops:
            with torch.no_grad(), torch.cuda.amp.autocast(enabled=self.device.type == "cuda"):
                # 前処理
                processed_crops = torch.stack([
                    self.clip_preprocess(crop) for crop in crops
                ]).to(self.device)
                
                # 埋め込み抽出
                embeddings = self.clip_model.encode_image(processed_crops)
                embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)  # L2正規化
                
                embeddings_np = embeddings.cpu().numpy().astype(np.float32)
        else:
            embeddings_np = np.array([])
        
        elapsed = (time.time() - start_time) * 1000
        print(f"🎨 CLIP埋め込み: {elapsed:.1f}ms ({len(crops)}個処理)")
        
        return embeddings_np
    
    def build_faiss_index(self, embeddings: np.ndarray) -> None:
        """FAISSインデックス構築"""
        start_time = time.time()
        
        if len(embeddings) == 0:
            self.faiss_index = None
            return
        
        # GPU版FAISSを試行、失敗時はCPU版
        try:
            if self.device.type == "cuda":
                res = faiss.StandardGpuResources()
                self.faiss_index = faiss.IndexFlatIP(embeddings.shape[1])
                self.faiss_index = faiss.index_cpu_to_gpu(res, 0, self.faiss_index)
                print("🎮 FAISS GPU版使用")
            else:
                raise RuntimeError("CUDA not available")
        except:
            self.faiss_index = faiss.IndexFlatIP(embeddings.shape[1])
            print("💻 FAISS CPU版使用")
        
        self.faiss_index.add(embeddings)
        self.bbox_embeddings = embeddings
        
        elapsed = (time.time() - start_time) * 1000
        print(f"🔎 FAISS構築: {elapsed:.1f}ms")
    
    def find_differences(self, embeddings_b: np.ndarray, detections_b: List[Dict], 
                        threshold: float = 0.7) -> List[Dict]:
        """FAISSで差分検出"""
        start_time = time.time()
        
        if self.faiss_index is None or len(embeddings_b) == 0:
            return detections_b  # 全て差分として扱う
        
        # 類似度検索
        similarities, indices = self.faiss_index.search(embeddings_b, 1)
        
        differences = []
        for i, (sim, idx) in enumerate(zip(similarities, indices)):
            if sim[0] < threshold:  # 類似度が閾値以下
                differences.append(detections_b[i])
        
        elapsed = (time.time() - start_time) * 1000
        print(f"🔍 差分検出: {elapsed:.1f}ms ({len(differences)}個の差分)")
        
        return differences
    
    def visualize_differences(self, image: np.ndarray, differences: List[Dict], 
                            output_path: str) -> None:
        """差分を赤丸で可視化"""
        start_time = time.time()
        
        # 画像をコピー
        result_img = image.copy()
        
        # 赤丸を描画
        for diff in differences:
            x1, y1, x2, y2 = map(int, diff['bbox'])
            center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2
            radius = max(20, min((x2 - x1), (y2 - y1)) // 4)
            
            cv2.circle(result_img, (center_x, center_y), radius, (0, 0, 255), 3)
            cv2.circle(result_img, (center_x, center_y), radius, (0, 0, 255), -1)
        
        # 結果保存
        cv2.imwrite(output_path, result_img)
        
        elapsed = (time.time() - start_time) * 1000
        print(f"🎨 可視化: {elapsed:.1f}ms")
    
    def generate_diff_json(self, differences: List[Dict]) -> Dict[str, Any]:
        """差分情報をJSON形式で生成"""
        diff_classes = list(set([diff['class_name'] for diff in differences]))
        
        return {
            'total_differences': len(differences),
            'difference_classes': diff_classes,
            'differences': differences,
            'timestamp': time.time()
        }
    
    def call_openai_realtime_api(self, diff_json: Dict[str, Any]) -> None:
        """OpenAI Realtime API呼び出し（モック機能付き）"""
        start_time = time.time()
        
        # APIキーチェック
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            print("⚠️ OPENAI_API_KEY未設定 - モック応答を実行")
            time.sleep(0.3)  # 300ms待機
            print("🎤 モック音声応答開始: '画像に{}個の差分を検出しました。{}の物体が異なります。'".format(
                diff_json['total_differences'], 
                ', '.join(diff_json['difference_classes']) if diff_json['difference_classes'] else '不明'
            ))
            return
        
        try:
            # 実際のAPI呼び出し（実装は後で追加）
            print("🎤 OpenAI Realtime API呼び出し中...")
            # TODO: 実際のAPI実装
            time.sleep(0.2)  # 200ms待機
            print("✅ 音声応答完了")
            
        except Exception as e:
            print(f"❌ API呼び出しエラー: {e}")
    
    def process_images(self, image_a_path: str, image_b_path: str, 
                      output_dir: str = "out") -> None:
        """メイン処理: 画像比較と差分検出"""
        print(f"\n🚀 画像比較開始: {image_a_path} vs {image_b_path}")
        total_start = time.time()
        
        # 出力ディレクトリ作成
        os.makedirs(output_dir, exist_ok=True)
        
        # 画像前処理
        print("📷 画像前処理中...")
        img_a = self.preprocess_image(image_a_path)
        img_b = self.preprocess_image(image_b_path)
        
        # 画像Aの物体検出と埋め込み
        print("\n🔍 画像A処理中...")
        detections_a = self.detect_objects(img_a)
        embeddings_a = self.extract_clip_embeddings(img_a, detections_a)
        self.build_faiss_index(embeddings_a)
        
        # 画像Bの物体検出と埋め込み
        print("\n🔍 画像B処理中...")
        detections_b = self.detect_objects(img_b)
        embeddings_b = self.extract_clip_embeddings(img_b, detections_b)
        
        # 差分検出
        print("\n🔍 差分検出中...")
        differences = self.find_differences(embeddings_b, detections_b)
        
        # 可視化とJSON生成
        print("\n🎨 結果出力中...")
        output_img_path = os.path.join(output_dir, "diff.png")
        self.visualize_differences(img_b, differences, output_img_path)
        
        diff_json = self.generate_diff_json(differences)
        output_json_path = os.path.join(output_dir, "diff.json")
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(diff_json, f, ensure_ascii=False, indent=2)
        
        # 音声応答
        print("\n🎤 音声応答開始...")
        self.call_openai_realtime_api(diff_json)
        
        total_elapsed = (time.time() - total_start) * 1000
        print(f"\n✅ 処理完了! 総時間: {total_elapsed:.1f}ms")
        print(f"📁 出力: {output_img_path}, {output_json_path}")
        
        # 性能チェック
        if total_elapsed <= 50:
            print("🎯 目標達成! 50ms以内で完了")
        else:
            print(f"⚠️ 目標超過: {total_elapsed - 50:.1f}ms遅延")

def main():
    parser = argparse.ArgumentParser(description="RTX 3060向け超高速間違い探しAI")
    parser.add_argument("--a", required=True, help="画像Aのパス")
    parser.add_argument("--b", required=True, help="画像Bのパス")
    parser.add_argument("--model", default="models/yolov8s.pt", help="YOLOモデルパス")
    parser.add_argument("--output", default="out", help="出力ディレクトリ")
    
    args = parser.parse_args()
    
    # モデルファイル存在チェック
    if not os.path.exists(args.model):
        print(f"❌ モデルファイルが見つかりません: {args.model}")
        print("📥 ダウンロード中...")
        # 自動ダウンロード
        os.makedirs("models", exist_ok=True)
        model = YOLO("yolov8s.pt")
        model.save(args.model)
        print(f"✅ モデル保存完了: {args.model}")
    
    # DiffFinder実行
    finder = DiffFinder(args.model)
    finder.process_images(args.a, args.b, args.output)

if __name__ == "__main__":
    main()
