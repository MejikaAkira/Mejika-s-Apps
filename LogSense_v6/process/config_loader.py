# -*- coding: utf-8 -*-
"""
設定ファイル読み込みユーティリティ
config.jsonを読み込んで、各モジュールに設定を提供
"""

import json
import os
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

# デフォルト設定
DEFAULT_CONFIG = {
    "feature_detector": {
        "type": "SIFT",  # "SIFT" or "ORB"
        "device": "CPU"  # "CPU" or "GPU" (ORBのみGPU対応、SIFTはCPUのみ)
    },
    "descriptor_matching": {
        "device": "GPU"  # "CPU" or "GPU"
    },
    "image_processing": {
        "sharpen": "CPU",      # "auto", "CPU", "GPU"
        "resize": "auto",      # "auto", "CPU", "GPU"
        "gaussian_blur": "auto",  # "auto", "CPU", "GPU"
        "warp_perspective": "auto",  # "auto", "CPU", "GPU"
        "absdiff": "auto"      # "auto", "CPU", "GPU"
    },
    "orb": {
        "nfeatures": 500,
        "scaleFactor": 1.2,
        "nlevels": 8
    },
    "sift": {
        "max_features": 0,
        "contrast_threshold": 0.04,
        "edge_threshold": 10,
        "sigma": 1.6
    },
    "realtime_video": {
        "camera": {
            "device_id": 0,
            "fps": 30
        },
        "difference": {
            "threshold_pixels": 5000,
            "threshold_ratio": 0.005,
            "noise_threshold": 20
        },
        "alignment": {
            "homography_reuse_seconds": 0.1
        },
        "save": {
            "archive_no_diff": True,
            "archive_path": "video_outputs/archive"
        },
        "buffer": {
            "frame_buffer_size": 10,
            "frame_queue_size": 5
        },
        "display": {
            "enable": True,
            "show": "both"
        },
        "streaming": {
            "enable": False,
            "protocol": "udp",
            "port": 8080,
            "address": "0.0.0.0"
        }
    }
}

def _remove_json_comments(text):
    """
    JSONファイルからコメントを除去（JSONC形式対応）
    
    Args:
        text: JSONファイルのテキスト
    
    Returns:
        str: コメントを除去したJSONテキスト
    """
    # 行コメント（//）を除去
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        # 文字列内の//は除去しない
        in_string = False
        escape_next = False
        cleaned_line = ""
        i = 0
        while i < len(line):
            char = line[i]
            if escape_next:
                cleaned_line += char
                escape_next = False
            elif char == '\\':
                cleaned_line += char
                escape_next = True
            elif char == '"' and not escape_next:
                in_string = not in_string
                cleaned_line += char
            elif char == '/' and i + 1 < len(line) and line[i + 1] == '/' and not in_string:
                # コメント開始（文字列外）
                break
            else:
                cleaned_line += char
            i += 1
        cleaned_lines.append(cleaned_line)
    
    return '\n'.join(cleaned_lines)

def load_config(config_path="config.json"):
    """
    config.jsonを読み込む（JSONC形式対応：コメント付きJSON）
    
    Args:
        config_path: 設定ファイルのパス（デフォルト: config.json）
    
    Returns:
        dict: 設定辞書
    """
    # プロジェクトルートからconfig.jsonを探す
    project_root = Path(__file__).parent.parent
    config_file = project_root / config_path
    
    if not config_file.exists():
        logging.warning(f"Config file not found: {config_file}. Using default config.")
        return DEFAULT_CONFIG.copy()
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            text = f.read()
        
        # コメントを除去
        cleaned_text = _remove_json_comments(text)
        
        # JSONをパース
        config = json.loads(cleaned_text)
        
        # デフォルト設定とマージ（存在しないキーはデフォルトを使用）
        merged_config = _merge_config(DEFAULT_CONFIG, config)
        
        logging.info(f"Config loaded from: {config_file}")
        return merged_config
        
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse config.json: {e}. Using default config.")
        return DEFAULT_CONFIG.copy()
    except Exception as e:
        logging.error(f"Failed to load config.json: {e}. Using default config.")
        return DEFAULT_CONFIG.copy()

def _merge_config(default, user):
    """
    デフォルト設定とユーザー設定をマージ
    
    Args:
        default: デフォルト設定
        user: ユーザー設定
    
    Returns:
        dict: マージされた設定
    """
    merged = default.copy()
    
    for key, value in user.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = value
    
    return merged

def validate_config(config):
    """
    設定値の検証
    
    Args:
        config: 設定辞書
    
    Returns:
        bool: 検証成功時True
    """
    # feature_detector.typeの検証
    if config["feature_detector"]["type"] not in ["SIFT", "ORB"]:
        logging.error(f"Invalid feature_detector.type: {config['feature_detector']['type']}. Must be 'SIFT' or 'ORB'.")
        return False
    
    # feature_detector.deviceの検証
    if config["feature_detector"]["device"] not in ["CPU", "GPU"]:
        logging.error(f"Invalid feature_detector.device: {config['feature_detector']['device']}. Must be 'CPU' or 'GPU'.")
        return False
    
    # SIFTはCPUのみ
    if config["feature_detector"]["type"] == "SIFT" and config["feature_detector"]["device"] == "GPU":
        logging.warning("SIFT does not support GPU. Switching to CPU.")
        config["feature_detector"]["device"] = "CPU"
    
    # descriptor_matching.deviceの検証
    if config["descriptor_matching"]["device"] not in ["CPU", "GPU"]:
        logging.error(f"Invalid descriptor_matching.device: {config['descriptor_matching']['device']}. Must be 'CPU' or 'GPU'.")
        return False
    
    # image_processingの検証
    for key in ["sharpen", "resize", "gaussian_blur", "warp_perspective", "absdiff"]:
        if config["image_processing"][key] not in ["auto", "CPU", "GPU"]:
            logging.error(f"Invalid image_processing.{key}: {config['image_processing'][key]}. Must be 'auto', 'CPU', or 'GPU'.")
            return False
    
    # realtime_videoセクションの検証（存在する場合）
    if "realtime_video" in config:
        if not _validate_realtime_video_config(config["realtime_video"]):
            return False
    
    return True

def _validate_realtime_video_config(realtime_config):
    """
    realtime_videoセクションの検証
    
    Args:
        realtime_config: realtime_video設定辞書
    
    Returns:
        bool: 検証成功時True
    """
    # camera設定の検証
    if "camera" in realtime_config:
        camera = realtime_config["camera"]
        if "device_id" in camera:
            if not isinstance(camera["device_id"], int) or camera["device_id"] < 0:
                logging.error(f"Invalid realtime_video.camera.device_id: {camera['device_id']}. Must be a non-negative integer.")
                return False
        if "fps" in camera:
            if not isinstance(camera["fps"], (int, float)) or camera["fps"] <= 0:
                logging.error(f"Invalid realtime_video.camera.fps: {camera['fps']}. Must be a positive number.")
                return False
    
    # difference設定の検証
    if "difference" in realtime_config:
        diff = realtime_config["difference"]
        if "threshold_pixels" in diff:
            if not isinstance(diff["threshold_pixels"], int) or diff["threshold_pixels"] < 0:
                logging.error(f"Invalid realtime_video.difference.threshold_pixels: {diff['threshold_pixels']}. Must be a non-negative integer.")
                return False
        if "threshold_ratio" in diff:
            if not isinstance(diff["threshold_ratio"], (int, float)) or not (0.0 <= diff["threshold_ratio"] <= 1.0):
                logging.error(f"Invalid realtime_video.difference.threshold_ratio: {diff['threshold_ratio']}. Must be between 0.0 and 1.0.")
                return False
        if "noise_threshold" in diff:
            if not isinstance(diff["noise_threshold"], int) or diff["noise_threshold"] < 0 or diff["noise_threshold"] > 255:
                logging.error(f"Invalid realtime_video.difference.noise_threshold: {diff['noise_threshold']}. Must be an integer between 0 and 255.")
                return False
    
    # alignment設定の検証
    if "alignment" in realtime_config:
        align = realtime_config["alignment"]
        if "homography_reuse_seconds" in align:
            if not isinstance(align["homography_reuse_seconds"], (int, float)) or align["homography_reuse_seconds"] <= 0:
                logging.error(f"Invalid realtime_video.alignment.homography_reuse_seconds: {align['homography_reuse_seconds']}. Must be a positive number.")
                return False
    
    # save設定の検証
    if "save" in realtime_config:
        save = realtime_config["save"]
        if "archive_no_diff" in save:
            if not isinstance(save["archive_no_diff"], bool):
                logging.error(f"Invalid realtime_video.save.archive_no_diff: {save['archive_no_diff']}. Must be a boolean.")
                return False
        if "archive_path" in save:
            if not isinstance(save["archive_path"], str):
                logging.error(f"Invalid realtime_video.save.archive_path: {save['archive_path']}. Must be a string.")
                return False
    
    # display設定の検証
    if "display" in realtime_config:
        display = realtime_config["display"]
        if "enable" in display:
            if not isinstance(display["enable"], bool):
                logging.error(f"Invalid realtime_video.display.enable: {display['enable']}. Must be a boolean.")
                return False
        if "show" in display:
            if display["show"] not in ["original", "difference", "both"]:
                logging.error(f"Invalid realtime_video.display.show: {display['show']}. Must be 'original', 'difference', or 'both'.")
                return False
    
    # streaming設定の検証
    if "streaming" in realtime_config:
        stream = realtime_config["streaming"]
        if "enable" in stream:
            if not isinstance(stream["enable"], bool):
                logging.error(f"Invalid realtime_video.streaming.enable: {stream['enable']}. Must be a boolean.")
                return False
        if "protocol" in stream:
            if stream["protocol"] not in ["udp", "websocket"]:
                logging.error(f"Invalid realtime_video.streaming.protocol: {stream['protocol']}. Must be 'udp' or 'websocket'.")
                return False
        if "port" in stream:
            if not isinstance(stream["port"], int) or not (1 <= stream["port"] <= 65535):
                logging.error(f"Invalid realtime_video.streaming.port: {stream['port']}. Must be between 1 and 65535.")
                return False
        if "address" in stream:
            if not isinstance(stream["address"], str):
                logging.error(f"Invalid realtime_video.streaming.address: {stream['address']}. Must be a string.")
                return False
    
    return True

def get_config(config_path="config.json"):
    """
    設定を読み込んで検証
    
    Args:
        config_path: 設定ファイルのパス
    
    Returns:
        dict: 検証済み設定辞書
    """
    config = load_config(config_path)
    
    if not validate_config(config):
        logging.warning("Config validation failed. Using default config.")
        return DEFAULT_CONFIG.copy()
    
    return config
