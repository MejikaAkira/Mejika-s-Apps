#!/usr/bin/env python3
"""
YOLO差分検出GUI - リファクタリング版
左側と右側で画像選択 → YOLO検出 → 差分を赤丸で表示
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
import numpy as np
from PIL import Image, ImageTk
from ultralytics import YOLO
import os
import time

class YOLODiffGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("YOLO差分検出器 - 修正版")
        self.root.geometry("1400x900")
        
        # モデル読み込み
        self.model = None
        self.load_model()
        
        # 画像データ
        self.image_a_data = None
        self.image_b_data = None
        
        # GUI要素作成
        self.create_widgets()
        
    def load_model(self):
        """YOLOモデル読み込み"""
        try:
            self.model = YOLO("models/yolov8s.pt")
            print("✅ YOLOモデル読み込み完了")
        except Exception as e:
            messagebox.showerror("エラー", f"モデル読み込み失敗: {e}")
    
    def create_widgets(self):
        """GUI要素作成"""
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 画像選択ボタン
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=0, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, text="左側画像選択", command=self.select_image_a).grid(row=0, column=0, padx=10)
        ttk.Button(button_frame, text="右側画像選択", command=self.select_image_b).grid(row=0, column=1, padx=10)
        ttk.Button(button_frame, text="YOLO差分検出", command=self.detect_differences).grid(row=0, column=2, padx=10)
        
        # 閾値調整
        ttk.Label(button_frame, text="信頼度閾値:").grid(row=0, column=3, padx=10)
        self.threshold_var = tk.DoubleVar(value=0.1)
        threshold_scale = ttk.Scale(button_frame, from_=0.1, to=0.9, variable=self.threshold_var, orient=tk.HORIZONTAL, length=100)
        threshold_scale.grid(row=0, column=4, padx=10)
        
        # 画像表示エリア（左右分割）
        image_frame = ttk.Frame(main_frame)
        image_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        
        # 左側画像
        left_frame = ttk.LabelFrame(image_frame, text="左側画像 (基準)", padding="5")
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)
        
        self.image_a_label = ttk.Label(left_frame, text="左側画像を選択してください", anchor="center")
        self.image_a_label.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 右側画像
        right_frame = ttk.LabelFrame(image_frame, text="右側画像 (比較)", padding="5")
        right_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)
        
        self.image_b_label = ttk.Label(right_frame, text="右側画像を選択してください", anchor="center")
        self.image_b_label.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 結果表示エリア
        result_frame = ttk.LabelFrame(main_frame, text="検出結果", padding="10")
        result_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        
        # テキストエリア（スクロール付き）
        self.result_text = tk.Text(result_frame, height=10, width=100, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=scrollbar.set)
        
        self.result_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # グリッド設定
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        image_frame.columnconfigure(0, weight=1)
        image_frame.columnconfigure(1, weight=1)
        image_frame.rowconfigure(0, weight=1)
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(0, weight=1)
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)
    
    def select_image_a(self):
        """左側画像選択"""
        file_path = filedialog.askopenfilename(
            title="左側画像を選択",
            filetypes=[("画像ファイル", "*.png *.jpg *.jpeg *.bmp *.tiff")]
        )
        
        if file_path:
            self.load_and_display_image(file_path, "A")
    
    def select_image_b(self):
        """右側画像選択"""
        file_path = filedialog.askopenfilename(
            title="右側画像を選択",
            filetypes=[("画像ファイル", "*.png *.jpg *.jpeg *.bmp *.tiff")]
        )
        
        if file_path:
            self.load_and_display_image(file_path, "B")
    
    def load_and_display_image(self, file_path, image_type):
        """画像読み込みと表示"""
        try:
            # 画像読み込み
            image = cv2.imread(file_path)
            if image is None:
                messagebox.showerror("エラー", "画像読み込み失敗")
                return
            
            # 画像データ保存
            image_data = {
                'path': file_path,
                'image': image,
                'height': image.shape[0],
                'width': image.shape[1]
            }
            
            if image_type == "A":
                self.image_a_data = image_data
                label_widget = self.image_a_label
            else:
                self.image_b_data = image_data
                label_widget = self.image_b_label
            
            # 表示用画像作成（リサイズ）
            display_image = self.create_display_image(image)
            self.display_image_on_label(display_image, label_widget)
            
            # 結果表示
            self.result_text.insert(tk.END, f"📷 {image_type}画像読み込み完了: {os.path.basename(file_path)}\n")
            self.result_text.insert(tk.END, f"📐 サイズ: {image_data['width']} x {image_data['height']}\n\n")
            self.result_text.see(tk.END)
            
        except Exception as e:
            messagebox.showerror("エラー", f"画像表示失敗: {e}")
    
    def create_display_image(self, image, max_size=300):
        """表示用画像作成（リサイズ）"""
        height, width = image.shape[:2]
        if max(height, width) > max_size:
            scale = max_size / max(height, width)
            new_width = int(width * scale)
            new_height = int(height * scale)
            return cv2.resize(image, (new_width, new_height))
        return image
    
    def display_image_on_label(self, image, label_widget):
        """画像をラベルに表示"""
        # BGR → RGB変換
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        # PIL画像に変換
        pil_image = Image.fromarray(image_rgb)
        photo = ImageTk.PhotoImage(pil_image)
        
        # 表示
        label_widget.configure(image=photo, text="")
        label_widget.image = photo  # 参照保持
    
    def detect_differences(self):
        """YOLO差分検出実行"""
        if not self.image_a_data or not self.image_b_data:
            messagebox.showwarning("警告", "両方の画像を選択してください")
            return
        
        if not self.model:
            messagebox.showerror("エラー", "YOLOモデルが読み込まれていません")
            return
        
        try:
            # 検出実行
            self.result_text.insert(tk.END, "🔍 YOLO差分検出実行中...\n")
            self.root.update()
            
            start_time = time.time()
            
            # 画像A検出
            detections_a = self.detect_objects_in_image(self.image_a_data, "A")
            
            # 画像B検出
            detections_b = self.detect_objects_in_image(self.image_b_data, "B")
            
            # 差分検出（BにないAの物体 = 左側画像に赤丸を表示すべき物体）
            differences = self.find_differences(detections_b, detections_a)  # BにないAの物体
            
            # 左側画像にのみ赤丸を描画
            self.draw_differences_on_image_a(differences)
            
            elapsed = (time.time() - start_time) * 1000
            
            # 結果表示
            self.display_results(elapsed, detections_a, detections_b, differences)
            
        except Exception as e:
            messagebox.showerror("エラー", f"検出実行失敗: {e}")
    
    def detect_objects_in_image(self, image_data, image_type):
        """画像内の物体検出"""
        results = self.model(image_data['path'], conf=self.threshold_var.get(), verbose=False)
        
        detections = []
        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = box.conf[0].cpu().numpy()
                    cls = int(box.cls[0].cpu().numpy())
                    cls_name = self.model.names[cls]
                    
                    detections.append({
                        'bbox': [float(x1), float(y1), float(x2), float(y2)],
                        'confidence': float(conf),
                        'class_id': cls,
                        'class_name': cls_name
                    })
        
        return detections
    
    def find_differences(self, detections_a, detections_b):
        """差分検出（シンプルな方法）"""
        differences = []
        
        # 画像Bの検出結果で、画像Aにマッチしないものを探す
        for det_b in detections_b:
            is_match = False
            
            for det_a in detections_a:
                # 同じクラスで、位置が近い場合はマッチとみなす
                if (det_b['class_name'] == det_a['class_name'] and 
                    self.is_bbox_similar(det_b['bbox'], det_a['bbox'])):
                    is_match = True
                    break
            
            if not is_match:
                differences.append(det_b)
        
        return differences
    
    def is_bbox_similar(self, bbox1, bbox2, threshold=50):
        """バウンディングボックスが類似しているかチェック"""
        # 中心点の距離を計算
        center1 = [(bbox1[0] + bbox1[2]) / 2, (bbox1[1] + bbox1[3]) / 2]
        center2 = [(bbox2[0] + bbox2[2]) / 2, (bbox2[1] + bbox2[3]) / 2]
        
        distance = np.sqrt((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)
        return distance < threshold
    
    def draw_differences_on_image_a(self, differences):
        """左側画像に赤丸を描画（差分がある場合のみ）"""
        if not self.image_a_data or len(differences) == 0:
            # 差分がない場合は元画像を表示
            display_image = self.create_display_image(self.image_a_data['image'])
            self.display_image_on_label(display_image, self.image_a_label)
            return
        
        # 元画像をコピー
        result_img = self.image_a_data['image'].copy()
        
        # 赤丸を描画（線のみ、違いを囲うように位置調整）
        for diff in differences:
            bbox = diff['bbox']
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            
            # バウンディングボックスの中心を計算
            center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2
            
            # バウンディングボックスを囲うように半径を設定
            width = x2 - x1
            height = y2 - y1
            radius = int(max(width, height) * 0.6)  # バウンディングボックスの60%の半径
            
            # 線のみの赤丸を描画
            cv2.circle(result_img, (center_x, center_y), radius, (0, 0, 255), 3)
        
        # 結果画像を表示
        display_image = self.create_display_image(result_img)
        self.display_image_on_label(display_image, self.image_a_label)
    
    
    def display_results(self, elapsed_time, detections_a, detections_b, differences):
        """結果を表示"""
        self.result_text.insert(tk.END, "=" * 50 + "\n")
        self.result_text.insert(tk.END, f"⏱️ 処理時間: {elapsed_time:.1f}ms\n")
        self.result_text.insert(tk.END, f"🔍 画像A検出数: {len(detections_a)}\n")
        self.result_text.insert(tk.END, f"🔍 画像B検出数: {len(detections_b)}\n")
        self.result_text.insert(tk.END, f"🔴 差分検出数: {len(differences)}\n\n")
        
        # 画像Aの検出詳細
        if detections_a:
            self.result_text.insert(tk.END, "📋 画像A検出詳細:\n")
            for i, det in enumerate(detections_a):
                self.result_text.insert(tk.END, f"  {i+1}. {det['class_name']} (信頼度: {det['confidence']:.3f})\n")
        
        # 画像Bの検出詳細
        if detections_b:
            self.result_text.insert(tk.END, "\n📋 画像B検出詳細:\n")
            for i, det in enumerate(detections_b):
                self.result_text.insert(tk.END, f"  {i+1}. {det['class_name']} (信頼度: {det['confidence']:.3f})\n")
        
        # 差分詳細
        if differences:
            self.result_text.insert(tk.END, "\n📋 差分詳細:\n")
            for i, diff in enumerate(differences):
                self.result_text.insert(tk.END, f"  {i+1}. {diff['class_name']} (信頼度: {diff['confidence']:.3f})\n")
                self.result_text.insert(tk.END, f"     位置: ({diff['bbox'][0]:.1f}, {diff['bbox'][1]:.1f}) - ({diff['bbox'][2]:.1f}, {diff['bbox'][3]:.1f})\n")
        else:
            self.result_text.insert(tk.END, "\n✅ 差分なし\n")
        
        self.result_text.insert(tk.END, "\n" + "=" * 50 + "\n")
        self.result_text.see(tk.END)

def main():
    root = tk.Tk()
    app = YOLODiffGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
