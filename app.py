# -*- coding: utf-8 -*-
# app.py - Lightweight Flask backend for BS Segmentation Tool.

import os
import json
import glob
import re
import string
import csv
import tkinter as tk
from tkinter import filedialog
from flask import Flask, render_template, request, jsonify, send_file, Response

import torch
import cv2
import numpy as np
import pandas as pd
import whisper

app = Flask(__name__)

IMAGE_EXTENSIONS = ('.bmp', '.png', '.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG', '.BMP')
VIDEO_EXTENSIONS = ('.mp4', '.avi', '.mkv', '.mov', '.MP4', '.AVI', '.MKV', '.MOV')

# Load localized high-accuracy Whisper model on launch
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"\n[STT ENGINE] Loading local Whisper Model on [{device}]...")
stt_model = whisper.load_model("base", device=device)
print("[STT ENGINE] Whisper engine ready to process voice input.\n")

from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

CHECKPOINT_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "sam2_hiera_tiny.pt"))
CONFIG_NAME = "configs/sam2/sam2_hiera_t.yaml"

sam2_model = None
sam2_predictor = None
cached_image_path = None

def get_sam_predictor():
    global sam2_model, sam2_predictor
    if sam2_predictor is None:
        try:
            if not os.path.exists(CHECKPOINT_PATH):
                print(f"[SAM 2] Weights not found. Downloading to {CHECKPOINT_PATH}...")
                import urllib.request
                url = "https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_tiny.pt"
                urllib.request.urlretrieve(url, CHECKPOINT_PATH)
            sam2_model = build_sam2(CONFIG_NAME, CHECKPOINT_PATH, device=device)
            sam2_predictor = SAM2ImagePredictor(sam2_model)
            print("[SAM 2] Predictor initialized successfully.")
        except Exception as e:
            print(f"[SAM 2 ERROR] Failed to initialize SAM 2: {str(e)}")
            # 에러 발생 시 프로그램이 터지지 않고 None을 반환하도록 처리
    return sam2_predictor

def decode_rle(rle_list, width, height):
    mask = np.zeros(width * height, dtype=np.uint8)
    curr = 0
    for i in range(0, len(rle_list), 2):
        val = rle_list[i]
        length = rle_list[i+1]
        mask[curr : curr + length] = val
        curr += length
    return mask.reshape((height, width))

def rle_encode(mask_2d):
    flat = mask_2d.flatten()
    if len(flat) == 0: return []
    starts = np.r_[0, np.flatnonzero(flat[1:] != flat[:-1]) + 1]
    lengths = np.diff(np.r_[starts, len(flat)])
    values = flat[starts]
    rle = np.empty(2 * len(values), dtype=np.int32)
    rle[0::2] = values
    rle[1::2] = lengths
    return rle.tolist()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/browse_directory', methods=['POST'])
def browse_directory():
    data = request.json or {}
    target_path = data.get('path', '').strip() or os.getcwd()
    target_path = os.path.abspath(target_path)
    if not os.path.exists(target_path) or not os.path.isdir(target_path):
        return jsonify({"success": False, "error": f"Not found: {target_path}"}), 404
    try:
        parent_dir = os.path.dirname(target_path)
        if parent_dir == target_path: parent_dir = None
        drives = []
        if os.name == 'nt':
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive): drives.append(drive)
        items = os.listdir(target_path)
        directories, files = [], []
        for item in items:
            item_path = os.path.join(target_path, item)
            try:
                if os.path.isdir(item_path): directories.append(item)
                elif os.path.isfile(item_path):
                    is_media = (item.endswith(IMAGE_EXTENSIONS) or item.endswith(VIDEO_EXTENSIONS)) and not any(k in item for k in ['_mask', '_overlay'])
                    files.append({"name": item, "is_media": is_media})
            except: continue
        directories.sort()
        files.sort(key=lambda x: x['name'])
        return jsonify({"success": True, "current_path": os.path.normpath(target_path), "parent_path": os.path.normpath(parent_dir) if parent_dir else None, "drives": drives, "directories": directories, "files": files})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/load_directory', methods=['POST'])
def load_directory():
    data = request.json
    target = data.get('directory', '').strip()
    if not target or not os.path.exists(target): return jsonify({"success": False, "error": "Invalid path"}), 400
    
    try:
        # 단일 비디오 파일이 선택된 경우의 처리 로직 추가
        if os.path.isfile(target):
            parent_dir = os.path.dirname(target)
            filename = os.path.basename(target)
            is_video = filename.endswith(VIDEO_EXTENSIONS)
            return jsonify({
                "success": True, 
                "directory": os.path.normpath(parent_dir),
                "images": [] if is_video else [filename],
                "videos": [filename] if is_video else []
            })
        else:
            all_files = os.listdir(target)
            image_files = sorted([f for f in all_files if f.endswith(IMAGE_EXTENSIONS) and not any(k in f for k in ['_mask', '_overlay'])])
            video_files = sorted([f for f in all_files if f.endswith(VIDEO_EXTENSIONS)])
            return jsonify({"success": True, "directory": os.path.normpath(target), "images": image_files, "videos": video_files})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/video_info', methods=['POST'])
def video_info():
    data = request.json
    video_path = os.path.normpath(os.path.join(data.get('directory', ''), data.get('video_name', '')))
    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = frame_count / fps if fps > 0 else 0
        cap.release()
        return jsonify({"success": True, "fps": fps, "frame_count": frame_count, "width": width, "height": height, "duration": duration})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/get_mask', methods=['POST'])
def get_mask():
    data = request.json
    mask_path = os.path.join(data.get('directory', ''), f"{os.path.splitext(data.get('image_name', ''))[0]}_mask.json")
    if os.path.exists(mask_path):
        with open(mask_path, 'r', encoding='utf-8') as f:
            return jsonify({"success": True, "has_mask": True, "mask_data": json.load(f)})
    return jsonify({"success": True, "has_mask": False})

@app.route('/api/save_mask', methods=['POST'])
def save_mask():
    data = request.json
    mask_path = os.path.join(data.get('directory', ''), f"{os.path.splitext(data.get('image_name', ''))[0]}_mask.json")
    try:
        with open(mask_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/get_image', methods=['GET'])
def get_image():
    return send_file(request.args.get('path', ''))

@app.route('/api/get_video', methods=['GET'])
def get_video():
    path = request.args.get('path', '')
    range_header = request.headers.get('Range', None)
    if not range_header: return send_file(path)
    size = os.path.getsize(path)
    byte1 = 0
    m = re.search(r'(\d+)-(\d*)', range_header)
    g = m.groups()
    if g[0]: byte1 = int(g[0])
    length = size - byte1
    with open(path, 'rb') as f:
        f.seek(byte1)
        video_bytes = f.read(length)
    rv = Response(video_bytes, 206, mimetype='video/mp4', content_type='video/mp4', direct_passthrough=True)
    rv.headers.add('Content-Range', f'bytes {byte1}-{byte1 + len(video_bytes) - 1}/{size}')
    rv.headers.add('Accept-Ranges', 'bytes')
    return rv

@app.route('/api/get_coco_annotations', methods=['POST'])
def get_coco_annotations():
    data = request.json
    coco_path = os.path.join(data.get('directory', ''), f"{os.path.splitext(data.get('video_name', ''))[0]}_coco.json")
    if os.path.exists(coco_path):
        with open(coco_path, 'r', encoding='utf-8') as f:
            return jsonify({"success": True, "has_annotations": True, "coco_data": json.load(f)})
    return jsonify({"success": True, "has_annotations": False, "coco_data": {"info": {"video_name": data.get('video_name', '')}, "categories": [], "images": [], "annotations": []}})

@app.route('/api/save_coco_annotations', methods=['POST'])
def save_coco_annotations():
    data = request.json
    coco_path = os.path.join(data.get('directory', ''), f"{os.path.splitext(data.get('video_name', ''))[0]}_coco.json")
    try:
        with open(coco_path, 'w', encoding='utf-8') as f:
            json.dump(data.get('coco_data', {}), f, indent=4)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/get_csv_annotations', methods=['POST'])
def get_csv_annotations():
    data = request.json or {}
    directory = data.get('directory', '').strip()
    video_name = data.get('video_name', '').strip()
    if not directory or not os.path.exists(directory):
        return jsonify({"success": False, "error": "Invalid directory path."}), 400
        
    tasks_records, tools_records = [], []
    if video_name:
        video_base = os.path.splitext(video_name)[0]
        tasks_path = os.path.join(directory, f"tasks_{video_base}.csv")
        tools_path = os.path.join(directory, f"tools_{video_base}.csv")
        if not os.path.exists(tasks_path): tasks_path = os.path.join(directory, "tasks.csv")
        if not os.path.exists(tools_path): tools_path = os.path.join(directory, "tools.csv")
    else:
        tasks_path = os.path.join(directory, "tasks.csv")
        tools_path = os.path.join(directory, "tools.csv")
        
    if os.path.exists(tasks_path):
        try:
            with open(tasks_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader: tasks_records.append(row)
        except Exception: pass
            
    if os.path.exists(tools_path):
        try:
            with open(tools_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader: tools_records.append(row)
        except Exception: pass
            
    return jsonify({"success": True, "tasks": tasks_records, "tools": tools_records})

@app.route('/api/save_csv_annotations', methods=['POST'])
def save_csv_annotations():
    data = request.json or {}
    directory = data.get('directory', '').strip()
    video_name = data.get('video_name', '').strip()
    tasks_records = data.get('tasks', [])
    tools_records = data.get('tools', [])
    
    if not directory or not os.path.exists(directory):
        return jsonify({"success": False, "error": "Invalid directory path."}), 400
        
    if video_name:
        video_base = os.path.splitext(video_name)[0]
        tasks_path = os.path.join(directory, f"tasks_{video_base}.csv")
        tools_path = os.path.join(directory, f"tools_{video_base}.csv")
    else:
        tasks_path = os.path.join(directory, "tasks.csv")
        tools_path = os.path.join(directory, "tools.csv")
        
    try:
        if tasks_records:
            fieldnames = ['index', 'start_part', 'start_time', 'stop_part', 'stop_time', 'groundtruth_taskname']
            for idx, rec in enumerate(tasks_records): rec['index'] = idx
            with open(tasks_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(tasks_records)
                
        if tools_records:
            fieldnames = ['index', 'install_case_part', 'install_case_time', 'uninstall_case_part', 'uninstall_case_time', 'arm', 'commercial_toolname', 'groundtruth_toolname']
            for idx, rec in enumerate(tools_records): rec['index'] = idx
            with open(tools_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(tools_records)
                
        return jsonify({"success": True, "message": "CSV annotations saved successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/get_video_frame', methods=['GET'])
def get_video_frame():
    path = request.args.get('path', '')
    frame_index = request.args.get('frame_index', default=0, type=int)
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ret, frame = cap.read()
    cap.release()
    if not ret: return "Failed", 400
    _, jpeg = cv2.imencode('.jpg', frame)
    return Response(jpeg.tobytes(), mimetype='image/jpeg')

@app.route('/api/load_reports', methods=['POST'])
def load_reports():
    data = request.json or {}
    report_file = os.path.join(data.get('directory', ''), f"{os.path.splitext(data.get('video_name', ''))[0]}_reports.json" if data.get('video_name') else "image_reports.json")
    if os.path.exists(report_file):
        with open(report_file, 'r', encoding='utf-8') as f:
            return jsonify({"success": True, "reports": json.load(f)})
    return jsonify({"success": True, "reports": {}})

@app.route('/api/save_reports', methods=['POST'])
def save_reports():
    data = request.json or {}
    report_file = os.path.join(data.get('directory', ''), f"{os.path.splitext(data.get('video_name', ''))[0]}_reports.json" if data.get('video_name') else "image_reports.json")
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(data.get('reports', {}), f, indent=4, ensure_ascii=False)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/export_reports_excel', methods=['POST'])
def export_reports_excel():
    data = request.json or {}
    reports = data.get('reports', {})
    fps = float(data.get('fps', 30.0))
    excel_path = os.path.join(data.get('directory', ''), f"{os.path.splitext(data.get('video_name', ''))[0]}_diagnostic_report.xlsx" if data.get('video_name') else "image_diagnostic_report.xlsx")
    try:
        rows = []
        for f_idx, text in sorted(reports.items(), key=lambda x: int(x[0])):
            t_sec = int(f_idx) / fps
            rows.append({"Frame Index": int(f_idx), "Timestamp": f"{int(t_sec//60):02d}:{t_sec%60:05.2f}", "Report Description": text})
        pd.DataFrame(rows).to_excel(excel_path, index=False, engine='openpyxl')
        return jsonify({"success": True, "path": excel_path})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/stt', methods=['POST'])
def native_stt_decode():
    if 'audio' not in request.files: return jsonify({"success": False, "error": "Audio missing"}), 400
    audio_file = request.files['audio']
    temp_path = os.path.join(os.path.dirname(__file__), "temp_voice.webm")
    try:
        audio_file.save(temp_path)
        result = stt_model.transcribe(temp_path, language="ko")
        if os.path.exists(temp_path): os.remove(temp_path)
        return jsonify({"success": True, "text": result.get("text", "").strip()})
    except Exception as e:
        if os.path.exists(temp_path): os.remove(temp_path)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/sam_encode', methods=['POST'])
def sam_encode():
    global cached_image_path
    
    # 1. SAM 로드 실패 에러 방어코드
    predictor = get_sam_predictor()
    if predictor is None:
        return jsonify({"success": False, "error": "SAM 2 모델이 설치되지 않았거나 로드에 실패했습니다. 수동 작업을 진행해 주세요."}), 500
        
    data = request.json
    video_path = os.path.normpath(os.path.join(data.get('directory', ''), data.get('video_name', '')))
    frame_index = int(data.get('frame_index', 0))
    cache_key = f"{video_path}_{frame_index}"
    
    if cached_image_path == cache_key: return jsonify({"success": True, "cached": True})
    try:
        if video_path.lower().endswith(IMAGE_EXTENSIONS): image_bgr = cv2.imread(video_path)
        else:
            cap = cv2.VideoCapture(video_path)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ret, image_bgr = cap.read()
            cap.release()
        predictor.set_image(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        cached_image_path = cache_key
        return jsonify({"success": True, "cached": False})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/sam_refine', methods=['POST'])
def sam_refine():
    global cached_image_path
    
    # 2. SAM 로드 실패 에러 방어코드
    predictor = get_sam_predictor()
    if predictor is None:
        return jsonify({"success": False, "error": "SAM 2 모델 구동 실패. 수동 브러시를 이용해 주세요."}), 500
        
    data = request.json
    video_path = os.path.normpath(os.path.join(data.get('directory', ''), data.get('video_name', '')))
    frame_index = int(data.get('frame_index', 0))
    class_id = int(data.get('class_id', 1))
    width, height = int(data.get('width', 800)), int(data.get('height', 600))
    
    cache_key = f"{video_path}_{frame_index}"
    if cached_image_path != cache_key:
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ret, img = cap.read()
        cap.release()
        predictor.set_image(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        cached_image_path = cache_key

    try:
        if data.get('box'):
            bx, by, bw, bh = data.get('box')
            masks, scores, _ = predictor.predict(point_coords=None, point_labels=None, box=np.array([bx, by, bx+bw, by+bh], dtype=np.float32), multimask_output=False)
        else:
            mask = decode_rle(data.get('rle', []), width, height)
            y, x = np.where(mask > 0)
            if len(x) == 0: return jsonify({"success": False, "error": "Empty mask"}), 400
            box = np.array([max(0, x.min()-10), max(0, y.min()-10), min(width-1, x.max()+10), min(height-1, y.max()+10)], dtype=np.float32)
            samples = np.linspace(0, len(x)-1, min(8, len(x)), dtype=int)
            pts = [[float(x[i]), float(y[i])] for i in samples]
            masks, scores, _ = predictor.predict(point_coords=np.array(pts, dtype=np.float32), point_labels=np.ones(len(pts), dtype=np.int32), box=box, multimask_output=False)
            
        mask_binary = masks[0].astype(np.uint8)
        y_ref, x_ref = np.where(mask_binary > 0)
        refined_box = [int(x_ref.min()), int(y_ref.min()), int(x_ref.max()-x_ref.min()), int(y_ref.max()-y_ref.min())] if len(x_ref) > 0 else None
        return jsonify({"success": True, "rle": rle_encode(mask_binary * class_id), "refined_box": refined_box})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='localhost', port=5000, debug=True)