#!/usr/bin/env python3
"""
PPTX to YouTube 動画自動生成システム - GUIアプリケーション
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import shutil
import os
from pathlib import Path
import sys
import time

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import PPT2YTProcessor
from src.utils.logger import get_logger


class PPT2YTGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PPTX to YouTube 動画自動生成システム")
        self.root.geometry("600x400")
        self.root.resizable(True, True)
        
        # ロガーの初期化
        self.logger = get_logger("GUI")
        
        # 処理状態
        self.processing = False
        self.selected_file = None
        
        # UIの初期化
        self.setup_ui()
        
    def setup_ui(self):
        """UIの初期化"""
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # タイトル
        title_label = ttk.Label(main_frame, text="PPTX to YouTube 動画自動生成システム", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # ファイル選択セクション
        file_frame = ttk.LabelFrame(main_frame, text="PPTXファイル選択", padding="10")
        file_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 20))
        
        # ファイルパス表示
        self.file_path_var = tk.StringVar()
        self.file_path_label = ttk.Label(file_frame, textvariable=self.file_path_var, 
                                        wraplength=500)
        self.file_path_label.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # ファイル選択ボタン
        select_button = ttk.Button(file_frame, text="PPTXファイルを選択", 
                                  command=self.select_file)
        select_button.grid(row=1, column=0, padx=(0, 10))
        
        # ファイル情報表示
        self.file_info_var = tk.StringVar()
        self.file_info_label = ttk.Label(file_frame, textvariable=self.file_info_var, 
                                        foreground="blue")
        self.file_info_label.grid(row=1, column=1, sticky=(tk.W, tk.E))
        
        # 処理セクション
        process_frame = ttk.LabelFrame(main_frame, text="動画生成", padding="10")
        process_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 20))
        
        # 開始ボタン
        self.start_button = ttk.Button(process_frame, text="動画生成開始", 
                                      command=self.start_processing)
        self.start_button.grid(row=0, column=0, pady=(0, 10))
        
        # 進捗バー
        self.progress_var = tk.StringVar(value="待機中...")
        self.progress_label = ttk.Label(process_frame, textvariable=self.progress_var)
        self.progress_label.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        self.progress_bar = ttk.Progressbar(process_frame, mode='determinate', length=400)
        self.progress_bar.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # 詳細ステータス
        self.status_var = tk.StringVar(value="ファイルを選択してください")
        self.status_label = ttk.Label(process_frame, textvariable=self.status_var, 
                                     wraplength=500)
        self.status_label.grid(row=3, column=0, sticky=(tk.W, tk.E))
        
        # ログ表示エリア
        log_frame = ttk.LabelFrame(main_frame, text="処理ログ", padding="10")
        log_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        # スクロール可能なテキストエリア
        self.log_text = tk.Text(log_frame, height=10, width=70, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # グリッドの重み設定
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)
        file_frame.columnconfigure(1, weight=1)
        process_frame.columnconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
    def select_file(self):
        """PPTXファイルを選択"""
        file_path = filedialog.askopenfilename(
            title="PPTXファイルを選択",
            filetypes=[("PowerPoint files", "*.pptx"), ("All files", "*.*")]
        )
        
        if file_path:
            self.selected_file = file_path
            self.file_path_var.set(f"選択されたファイル: {file_path}")
            
            # ファイル情報を表示
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
            self.file_info_var.set(f"ファイルサイズ: {file_size:.1f} MB")
            
            self.status_var.set("ファイルが選択されました。動画生成を開始できます。")
            self.log_message(f"ファイル選択: {file_path}")
            
    def copy_file_to_input(self):
        """選択されたファイルをinputフォルダにコピー"""
        if not self.selected_file:
            return False
            
        try:
            input_dir = Path("input")
            input_dir.mkdir(exist_ok=True)
            
            # 既存のPPTXファイルをアーカイブ
            archive_dir = Path("input_archive")
            archive_dir.mkdir(exist_ok=True)
            
            for pptx_file in input_dir.glob("*.pptx"):
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                archive_name = f"{pptx_file.stem}_{timestamp}{pptx_file.suffix}"
                archive_path = archive_dir / archive_name
                shutil.move(str(pptx_file), str(archive_path))
                self.log_message(f"既存ファイルをアーカイブ: {archive_path}")
            
            # 新しいファイルをコピー
            source_path = Path(self.selected_file)
            dest_path = input_dir / source_path.name
            shutil.copy2(str(source_path), str(dest_path))
            
            self.log_message(f"ファイルをinputフォルダにコピー: {dest_path}")
            return str(dest_path)
            
        except Exception as e:
            self.log_message(f"ファイルコピーエラー: {e}")
            return False
    
    def start_processing(self):
        """動画生成処理を開始"""
        if not self.selected_file:
            messagebox.showerror("エラー", "PPTXファイルを選択してください。")
            return
            
        if self.processing:
            messagebox.showwarning("警告", "処理が既に実行中です。")
            return
        
        # ファイルをinputフォルダにコピー
        copied_path = self.copy_file_to_input()
        if not copied_path:
            messagebox.showerror("エラー", "ファイルのコピーに失敗しました。")
            return
        
        # 処理を別スレッドで開始
        self.processing = True
        self.start_button.config(state="disabled")
        self.progress_bar["value"] = 0
        
        thread = threading.Thread(target=self.run_processing, args=(copied_path,))
        thread.daemon = True
        thread.start()
    
    def run_processing(self, pptx_path):
        """動画生成処理を実行"""
        try:
            self.update_progress(0, "処理を開始しています...")
            
            # プロセッサーの初期化
            processor = PPT2YTProcessor()
            
            # 設定の検証
            self.update_progress(5, "設定を検証しています...")
            if not processor.validate_config():
                raise ValueError("設定が無効です。.envファイルを確認してください。")
            
            # 処理の実行
            self.update_progress(10, "台本を生成しています...")
            success = processor.process_pptx(pptx_path, progress_callback=self.update_progress)
            
            if success:
                self.update_progress(100, "処理が完了しました！")
                self.log_message("✅ 動画生成が正常に完了しました")
                messagebox.showinfo("完了", "動画生成が完了しました！")
            else:
                self.update_progress(0, "処理が失敗しました")
                self.log_message("❌ 動画生成に失敗しました")
                messagebox.showerror("エラー", "動画生成に失敗しました。")
                
        except Exception as e:
            self.update_progress(0, f"エラーが発生しました: {e}")
            self.log_message(f"❌ エラー: {e}")
            messagebox.showerror("エラー", f"処理中にエラーが発生しました:\n{e}")
            
        finally:
            self.processing = False
            self.start_button.config(state="normal")
    
    def update_progress(self, value, status):
        """進捗を更新"""
        def update():
            self.progress_bar["value"] = value
            self.status_var.set(status)
            self.log_message(status)
        
        self.root.after(0, update)
    
    def log_message(self, message):
        """ログメッセージを追加"""
        def add_message():
            timestamp = time.strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.log_text.see(tk.END)
        
        self.root.after(0, add_message)


def main():
    """メイン関数"""
    root = tk.Tk()
    app = PPT2YTGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main() 