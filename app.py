# -*- coding: utf-8 -*-
# app.py - BS Segmentation Tool 백엔드 (Flask + 로컬 Whisper STT + SAM 2)

import os
import re
import csv
import json
import string

import cv2
import numpy as np
import pandas as pd
from flask import Flask, render_template, request, jsonify, send_file, Response

app = Flask(__name__)

BASE_DIR = os.path.dirname(__file__)
IMAGE_EXTENSIONS = ('.bmp', '.png', '.jpg', '.jpeg')
VIDEO_EXTENSIONS = ('.mp4', '.avi', '.mkv', '.mov')
DERIVED_MARKERS = ('_mask', '_overlay')

# 시스템에 ffmpeg가 없어도 (winget/관리자권한 불필요) whisper가 동작하도록
# imageio-ffmpeg가 받아둔 정적 바이너리를 PATH 맨 앞에 꽂아준다.
try:
    import imageio_ffmpeg
    _ffmpeg_dir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
    os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
except Exception as e:
    print(f"[FFMPEG] imageio-ffmpeg unavailable ({e}). Falling back to system ffmpeg if present.")

# torch / whisper 는 선택적 의존성 — 없어도 서버는 정상 실행된다.
try:
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
except ImportError:
    torch = None
    device = "cpu"

try:
    import whisper as _whisper_mod
    print(f"\n[STT] Loading Whisper model on [{device}]...")
    stt_model = _whisper_mod.load_model("base", device=device)
    print("[STT] Ready.\n")
except Exception as e:
    _whisper_mod = None
    stt_model = None
    print(f"[STT] Whisper not available ({e}). STT disabled.\n")

CHECKPOINT_PATH = os.path.normpath(os.path.join(BASE_DIR, "sam2_hiera_tiny.pt"))
CONFIG_NAME = "configs/sam2/sam2_hiera_t.yaml"
WEIGHTS_URL = "https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_tiny.pt"

_sam_predictor = None
_cached_key = None


def get_sam_predictor():
    """SAM 2 predictor를 지연 로드한다. 패키지/가중치가 없으면 None을 돌려준다."""
    global _sam_predictor
    if _sam_predictor is not None:
        return _sam_predictor
    try:
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        if not os.path.exists(CHECKPOINT_PATH):
            print(f"[SAM2] Weights not found. Downloading to {CHECKPOINT_PATH}...")
            import urllib.request
            urllib.request.urlretrieve(WEIGHTS_URL, CHECKPOINT_PATH)

        model = build_sam2(CONFIG_NAME, CHECKPOINT_PATH, device=device)
        _sam_predictor = SAM2ImagePredictor(model)
        print("[SAM2] Predictor initialized.")
    except Exception as e:
        print(f"[SAM2] Init failed: {e}")
        _sam_predictor = None
    return _sam_predictor


# ---- 공통 유틸 -------------------------------------------------------------

def is_image(name):
    return name.lower().endswith(IMAGE_EXTENSIONS) and not any(m in name for m in DERIVED_MARKERS)


def is_video(name):
    return name.lower().endswith(VIDEO_EXTENSIONS)


def media_path(data, key='video_name'):
    return os.path.normpath(os.path.join(data.get('directory', ''), data.get(key, '')))


def annotation_path(data, suffix, image_default):
    """비디오면 '<이름><suffix>', 이미지면 image_default 파일 경로를 만든다."""
    directory = data.get('directory', '')
    video_name = data.get('video_name', '')
    if video_name:
        base = os.path.splitext(video_name)[0]
        return os.path.join(directory, f"{base}{suffix}")
    return os.path.join(directory, image_default)


def read_video_frame(video_path, frame_index):
    cap = cv2.VideoCapture(video_path)
    if frame_index:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def decode_rle(rle_list, width, height):
    """[값, 길이, 값, 길이, ...] 형태(행 우선)를 2D 마스크로 복원한다."""
    mask = np.zeros(width * height, dtype=np.uint8)
    pos = 0
    for i in range(0, len(rle_list) - 1, 2):
        value, length = rle_list[i], rle_list[i + 1]
        mask[pos:pos + length] = value
        pos += length
    return mask.reshape((height, width))


def rle_encode(mask_2d):
    """2D 마스크를 [값, 길이, ...] 형태(행 우선)로 압축한다."""
    flat = mask_2d.flatten()
    if flat.size == 0:
        return []
    starts = np.r_[0, np.flatnonzero(flat[1:] != flat[:-1]) + 1]
    lengths = np.diff(np.r_[starts, len(flat)])
    values = flat[starts]
    rle = np.empty(2 * len(values), dtype=np.int32)
    rle[0::2] = values
    rle[1::2] = lengths
    return rle.tolist()


def load_json(path, default=None):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default


def dump_json(path, payload, ensure_ascii=False):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=4, ensure_ascii=ensure_ascii)


# ---- 라우트 ----------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/browse_directory', methods=['POST'])
def browse_directory():
    data = request.json or {}
    target = os.path.abspath(data.get('path', '').strip() or os.getcwd())
    if not os.path.isdir(target):
        return jsonify({"success": False, "error": f"Not found: {target}"}), 404

    try:
        parent = os.path.dirname(target)
        if parent == target:
            parent = None

        drives = []
        if os.name == 'nt':
            drives = [f"{c}:\\" for c in string.ascii_uppercase if os.path.exists(f"{c}:\\")]

        directories, files = [], []
        for item in os.listdir(target):
            full = os.path.join(target, item)
            try:
                if os.path.isdir(full):
                    directories.append(item)
                elif os.path.isfile(full):
                    files.append({"name": item, "is_media": is_image(item) or is_video(item)})
            except OSError:
                continue

        directories.sort()
        files.sort(key=lambda x: x['name'])
        return jsonify({
            "success": True,
            "current_path": os.path.normpath(target),
            "parent_path": os.path.normpath(parent) if parent else None,
            "drives": drives,
            "directories": directories,
            "files": files,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/load_directory', methods=['POST'])
def load_directory():
    data = request.json or {}
    target = data.get('directory', '').strip()
    if not target or not os.path.exists(target):
        return jsonify({"success": False, "error": "Invalid path"}), 400

    try:
        # 단일 비디오/이미지 파일을 직접 선택한 경우
        if os.path.isfile(target):
            parent = os.path.dirname(target)
            name = os.path.basename(target)
            video = is_video(name)
            return jsonify({
                "success": True,
                "directory": os.path.normpath(parent),
                "images": [] if video else [name],
                "videos": [name] if video else [],
            })

        names = os.listdir(target)
        return jsonify({
            "success": True,
            "directory": os.path.normpath(target),
            "images": sorted(n for n in names if is_image(n)),
            "videos": sorted(n for n in names if is_video(n)),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/video_info', methods=['POST'])
def video_info():
    data = request.json or {}
    try:
        cap = cv2.VideoCapture(media_path(data))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        return jsonify({
            "success": True, "fps": fps, "frame_count": frame_count,
            "width": width, "height": height,
            "duration": frame_count / fps if fps > 0 else 0,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/get_mask', methods=['POST'])
def get_mask():
    data = request.json or {}
    base = os.path.splitext(data.get('image_name', ''))[0]
    mask_path = os.path.join(data.get('directory', ''), f"{base}_mask.json")
    mask_data = load_json(mask_path)
    if mask_data is not None:
        return jsonify({"success": True, "has_mask": True, "mask_data": mask_data})
    return jsonify({"success": True, "has_mask": False})


@app.route('/api/save_mask', methods=['POST'])
def save_mask():
    data = request.json or {}
    base = os.path.splitext(data.get('image_name', ''))[0]
    mask_path = os.path.join(data.get('directory', ''), f"{base}_mask.json")
    try:
        dump_json(mask_path, data)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/get_image', methods=['GET'])
def get_image():
    path = request.args.get('path', '')
    if not os.path.isfile(path):
        return "Not found", 404
    return send_file(path)


@app.route('/api/get_video', methods=['GET'])
def get_video():
    path = request.args.get('path', '')
    if not os.path.isfile(path):
        return "Not found", 404

    range_header = request.headers.get('Range')
    if not range_header:
        return send_file(path)

    size = os.path.getsize(path)
    match = re.search(r'(\d+)-(\d*)', range_header)
    start = int(match.group(1)) if match and match.group(1) else 0
    length = size - start

    with open(path, 'rb') as f:
        f.seek(start)
        chunk = f.read(length)

    rv = Response(chunk, 206, mimetype='video/mp4', content_type='video/mp4', direct_passthrough=True)
    rv.headers.add('Content-Range', f'bytes {start}-{start + len(chunk) - 1}/{size}')
    rv.headers.add('Accept-Ranges', 'bytes')
    return rv


@app.route('/api/get_video_frame', methods=['GET'])
def get_video_frame():
    path = request.args.get('path', '')
    frame_index = request.args.get('frame_index', default=0, type=int)
    frame = read_video_frame(path, frame_index)
    if frame is None:
        return "Failed", 400
    _, jpeg = cv2.imencode('.jpg', frame)
    return Response(jpeg.tobytes(), mimetype='image/jpeg')


@app.route('/api/get_coco_annotations', methods=['POST'])
def get_coco_annotations():
    data = request.json or {}
    coco_data = load_json(annotation_path(data, "_coco.json", "image_coco.json"))
    if coco_data is not None:
        return jsonify({"success": True, "has_annotations": True, "coco_data": coco_data})
    empty = {"info": {"video_name": data.get('video_name', '')},
             "categories": [], "images": [], "annotations": []}
    return jsonify({"success": True, "has_annotations": False, "coco_data": empty})


@app.route('/api/save_coco_annotations', methods=['POST'])
def save_coco_annotations():
    data = request.json or {}
    try:
        dump_json(annotation_path(data, "_coco.json", "image_coco.json"), data.get('coco_data', {}))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# tasks/tools CSV는 '<video>_tasks.csv'(=video별) 또는 'tasks.csv'(=폴더 공용) 둘 다 지원한다.
TASK_FIELDS = ['index', 'start_part', 'start_time', 'stop_part', 'stop_time', 'groundtruth_taskname']
TOOL_FIELDS = ['index', 'install_case_part', 'install_case_time', 'uninstall_case_part',
               'uninstall_case_time', 'arm', 'commercial_toolname', 'groundtruth_toolname']


def csv_paths(directory, video_name):
    if video_name:
        base = os.path.splitext(video_name)[0]
        return (os.path.join(directory, f"tasks_{base}.csv"),
                os.path.join(directory, f"tools_{base}.csv"))
    return (os.path.join(directory, "tasks.csv"),
            os.path.join(directory, "tools.csv"))


def read_csv_rows(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def write_csv_rows(path, fieldnames, rows):
    for idx, row in enumerate(rows):
        row['index'] = idx
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


@app.route('/api/get_csv_annotations', methods=['POST'])
def get_csv_annotations():
    data = request.json or {}
    directory = data.get('directory', '').strip()
    if not directory or not os.path.exists(directory):
        return jsonify({"success": False, "error": "Invalid directory path."}), 400

    tasks_path, tools_path = csv_paths(directory, data.get('video_name', '').strip())
    # video별 파일이 없으면 폴더 공용 파일로 폴백
    if data.get('video_name', '').strip():
        shared_tasks, shared_tools = csv_paths(directory, '')
        if not os.path.exists(tasks_path):
            tasks_path = shared_tasks
        if not os.path.exists(tools_path):
            tools_path = shared_tools

    return jsonify({"success": True,
                    "tasks": read_csv_rows(tasks_path),
                    "tools": read_csv_rows(tools_path)})


@app.route('/api/save_csv_annotations', methods=['POST'])
def save_csv_annotations():
    data = request.json or {}
    directory = data.get('directory', '').strip()
    if not directory or not os.path.exists(directory):
        return jsonify({"success": False, "error": "Invalid directory path."}), 400

    tasks_path, tools_path = csv_paths(directory, data.get('video_name', '').strip())
    try:
        if data.get('tasks'):
            write_csv_rows(tasks_path, TASK_FIELDS, data['tasks'])
        if data.get('tools'):
            write_csv_rows(tools_path, TOOL_FIELDS, data['tools'])
        return jsonify({"success": True, "message": "CSV annotations saved successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/load_reports', methods=['POST'])
def load_reports():
    data = request.json or {}
    reports = load_json(annotation_path(data, "_reports.json", "image_reports.json"), default={})
    return jsonify({"success": True, "reports": reports})


@app.route('/api/save_reports', methods=['POST'])
def save_reports():
    data = request.json or {}
    try:
        dump_json(annotation_path(data, "_reports.json", "image_reports.json"), data.get('reports', {}))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500





@app.route('/api/stt', methods=['POST'])
def native_stt_decode():
    if stt_model is None:
        return jsonify({"success": False, "error": "STT unavailable: Whisper not installed. Run: pip install openai-whisper soundfile"}), 503
    if 'audio' not in request.files:
        return jsonify({"success": False, "error": "Audio missing"}), 400

    temp_path = os.path.join(BASE_DIR, "temp_voice.webm")
    try:
        request.files['audio'].save(temp_path)
        result = stt_model.transcribe(temp_path, language="ko")
        return jsonify({"success": True, "text": result.get("text", "").strip()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.route('/api/sam_encode', methods=['POST'])
def sam_encode():
    global _cached_key
    predictor = get_sam_predictor()
    if predictor is None:
        return jsonify({"success": False,
                        "error": "SAM 2 모델이 설치되지 않았거나 로드에 실패했습니다. 수동 작업을 진행해 주세요."}), 500

    data = request.json or {}
    path = media_path(data)
    frame_index = int(data.get('frame_index', 0))
    key = f"{path}_{frame_index}"
    if _cached_key == key:
        return jsonify({"success": True, "cached": True})

    try:
        if path.lower().endswith(IMAGE_EXTENSIONS):
            image_bgr = cv2.imread(path)
        else:
            image_bgr = read_video_frame(path, frame_index)
        if image_bgr is None:
            return jsonify({"success": False, "error": "Frame read failed"}), 400

        predictor.set_image(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        _cached_key = key
        return jsonify({"success": True, "cached": False})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/sam_refine', methods=['POST'])
def sam_refine():
    global _cached_key
    predictor = get_sam_predictor()
    if predictor is None:
        return jsonify({"success": False,
                        "error": "SAM 2 모델 구동 실패. 수동 브러시를 이용해 주세요."}), 500

    data = request.json or {}
    path = media_path(data)
    frame_index = int(data.get('frame_index', 0))
    class_id = int(data.get('class_id', 1))
    width, height = int(data.get('width', 800)), int(data.get('height', 600))

    key = f"{path}_{frame_index}"
    if _cached_key != key:
        frame = read_video_frame(path, frame_index)
        if frame is None:
            return jsonify({"success": False, "error": "Frame read failed"}), 400
        predictor.set_image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        _cached_key = key

    try:
        if data.get('box'):
            bx, by, bw, bh = data['box']
            box = np.array([bx, by, bx + bw, by + bh], dtype=np.float32)
            masks, _, _ = predictor.predict(point_coords=None, point_labels=None,
                                            box=box, multimask_output=False)
        else:
            mask = decode_rle(data.get('rle', []), width, height)
            ys, xs = np.where(mask > 0)
            if len(xs) == 0:
                return jsonify({"success": False, "error": "Empty mask"}), 400

            box = np.array([
                max(0, xs.min() - 10), max(0, ys.min() - 10),
                min(width - 1, xs.max() + 10), min(height - 1, ys.max() + 10),
            ], dtype=np.float32)
            sample_idx = np.linspace(0, len(xs) - 1, min(8, len(xs)), dtype=int)
            points = np.array([[float(xs[i]), float(ys[i])] for i in sample_idx], dtype=np.float32)
            labels = np.ones(len(points), dtype=np.int32)
            masks, _, _ = predictor.predict(point_coords=points, point_labels=labels,
                                            box=box, multimask_output=False)

        mask_binary = masks[0].astype(np.uint8)
        ys, xs = np.where(mask_binary > 0)
        refined_box = None
        if len(xs) > 0:
            refined_box = [int(xs.min()), int(ys.min()),
                           int(xs.max() - xs.min()), int(ys.max() - ys.min())]
        return jsonify({"success": True, "rle": rle_encode(mask_binary), "refined_box": refined_box})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/load_phases', methods=['POST'])
def load_phases():
    data = request.json or {}
    phases = load_json(annotation_path(data, "_phases.json", "image_phases.json"), default={})
    return jsonify({"success": True, "phases": phases})


@app.route('/api/save_phases', methods=['POST'])
def save_phases():
    data = request.json or {}
    try:
        dump_json(annotation_path(data, "_phases.json", "image_phases.json"), data.get('phases', {}))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/load_classes', methods=['POST'])
def load_classes():
    data = request.json or {}
    path = os.path.join(data.get('directory', ''), 'classes.json')
    classes = load_json(path)
    return jsonify({"success": True, "classes": classes})


@app.route('/api/save_classes', methods=['POST'])
def save_classes():
    data = request.json or {}
    path = os.path.join(data.get('directory', ''), 'classes.json')
    try:
        dump_json(path, data.get('classes', {}))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/export_reports_excel', methods=['POST'])
def export_reports_excel_v2():
    """operator별 컬럼을 나눠서 Excel로 내보낸다."""
    data = request.json or {}
    # reports 구조: { "op1_name": {"frame": "text", ...}, ... }  또는 레거시 flat {"frame": "text"}
    reports = data.get('reports', {})
    fps = float(data.get('fps', 30.0)) or 30.0
    excel_path = annotation_path(data, "_diagnostic_report.xlsx", "image_diagnostic_report.xlsx")
    try:
        # 레거시(flat) 포맷 감지
        first_val = next(iter(reports.values()), None) if reports else None
        if isinstance(first_val, str):
            operators = {"Operator": reports}
        else:
            operators = reports  # { op_name: {frame: text} }

        all_frames = sorted({int(f) for op_data in operators.values() for f in op_data}, key=int)
        rows = []
        for frame_idx in all_frames:
            seconds = frame_idx / fps
            row = {
                "Frame Index": frame_idx,
                "Timestamp": f"{int(seconds // 60):02d}:{seconds % 60:05.2f}",
            }
            for op_name, op_data in operators.items():
                row[op_name] = op_data.get(str(frame_idx), "")
            rows.append(row)

        pd.DataFrame(rows).to_excel(excel_path, index=False, engine='openpyxl')
        return jsonify({"success": True, "path": excel_path})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='localhost', port=5000, debug=True)
