# -*- coding: utf-8 -*-
# app.py - BS Segmentation Tool 백엔드 (Flask + 로컬 Whisper STT + MobileSAM)

import os
import sys
import re
import json
import string

import cv2
import numpy as np
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

# Whisper is loaded lazily on the first /api/stt call, not at import.
# Loading the "base" model costs several seconds every startup (and a ~140 MB
# download the very first time) - paying that before the server can serve a
# single page made the tool feel like it was hanging on launch.
_whisper_mod = None
stt_model = None
_stt_load_failed = False


def get_stt_model():
    global _whisper_mod, stt_model, _stt_load_failed
    if stt_model is not None or _stt_load_failed:
        return stt_model
    try:
        import whisper as _w
        print(f"[STT] Loading Whisper model on [{device}] (first use only)...")
        _whisper_mod = _w
        stt_model = _w.load_model("base", device=device)
        print("[STT] Ready.")
    except Exception as e:
        _stt_load_failed = True
        print(f"[STT] Whisper unavailable ({e}). Voice input disabled.")
    return stt_model

# MobileSAM (only backend). ViT-Tiny distilled SAM 1 (~10M params, 39 MB weight).
# The weight ships bundled in the repo so offline installs work; if it's missing
# for any reason we fall back to a one-shot HuggingFace mirror download.
MOBILE_SAM_PATH = os.path.normpath(os.path.join(BASE_DIR, "mobile_sam.pt"))
MOBILE_SAM_URL  = "https://huggingface.co/dhkim2810/MobileSAM/resolve/main/mobile_sam.pt"
# Vendored package source lives here so no pip install of mobile_sam/timm is needed.
VENDOR_DIR = os.path.normpath(os.path.join(BASE_DIR, "vendor"))

_sam_predictor = None
_sam_last_error = None   # surfaced to the UI so failures are visible without the console
_cached_key = None


def _download(url: str, dest: str):
    print(f"[SAM] Downloading {url} -> {dest}")
    import urllib.request
    urllib.request.urlretrieve(url, dest)


def get_sam_predictor():
    """MobileSAM only, loaded from the vendored copy in vendor/.

    Nothing here needs pip: the package source lives in vendor/mobile_sam (with
    its timm dependency reimplemented in tiny_vit_sam.py) and the weight ships as
    mobile_sam.pt next to this file. Only torch/numpy/cv2 are required, and those
    are already core requirements.
    """
    global _sam_predictor, _sam_last_error
    if _sam_predictor is not None:
        return _sam_predictor
    try:
        # Prefer the vendored source over anything pip may have installed, so the
        # behaviour is identical on every machine.
        if VENDOR_DIR not in sys.path:
            sys.path.insert(0, VENDOR_DIR)
        from mobile_sam import sam_model_registry, SamPredictor

        if not os.path.exists(MOBILE_SAM_PATH):
            print(f"[MobileSAM] Bundled weight missing at {MOBILE_SAM_PATH}, downloading once...")
            _download(MOBILE_SAM_URL, MOBILE_SAM_PATH)
        model = sam_model_registry["vit_t"](checkpoint=MOBILE_SAM_PATH)
        model.to(device=device)
        model.eval()
        _sam_predictor = SamPredictor(model)
        _sam_last_error = None
        print(f"[MobileSAM] Predictor ready on [{device}] (vendored, no pip install needed).")
        return _sam_predictor
    except Exception as e:
        import traceback
        # Keep the reason so the UI can show it instead of telling the user to go
        # read a console they may not even have in front of them.
        _sam_last_error = f"{type(e).__name__}: {e}"
        if isinstance(e, ModuleNotFoundError):
            _sam_last_error += (
                f"  ->  '{e.name}' is missing. Install it into the venv: "
                f"pip install {e.name}"
            )
        elif not os.path.exists(MOBILE_SAM_PATH):
            _sam_last_error += f"  ->  weight not found at {MOBILE_SAM_PATH}"
        print(f"[MobileSAM] Init failed: {_sam_last_error}")
        traceback.print_exc()
        return None


@app.route('/api/sam_backend', methods=['GET'])
def sam_backend_info():
    """Report which backend is live so the UI can badge it."""
    get_sam_predictor()
    return jsonify({
        "backend": "mobile_sam" if _sam_predictor is not None else None,
        "device": device,
        "available": _sam_predictor is not None,
        "error": _sam_last_error,
    })


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


@app.route('/api/pick_folder', methods=['POST'])
def pick_folder():
    """Windows(또는 macOS/Linux) 네이티브 폴더 선택창을 띄운다.
    Flask가 로컬에서 돌 때만 의미가 있음 — tkinter 창은 서버 프로세스의 데스크톱에 뜬다."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)  # 브라우저 뒤로 숨는 문제 방지
        data = request.json or {}
        initialdir = data.get('initialdir', '') or os.path.expanduser('~')
        path = filedialog.askdirectory(initialdir=initialdir, title="Select folder", mustexist=True)
        root.destroy()
        if not path:
            return jsonify({"success": False, "cancelled": True})
        return jsonify({"success": True, "path": os.path.normpath(path)})
    except Exception as e:
        return jsonify({"success": False, "error": f"Native picker failed: {e}"}), 500


@app.route('/api/pick_file', methods=['POST'])
def pick_file():
    """네이티브 파일 선택창. 영상 확장자 필터를 미리 걸어둔다."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        data = request.json or {}
        initialdir = data.get('initialdir', '') or os.path.expanduser('~')
        filetypes = [
            ("Video files", "*.mp4 *.avi *.mkv *.mov"),
            ("Image files", "*.png *.jpg *.jpeg *.bmp"),
            ("All files", "*.*"),
        ]
        path = filedialog.askopenfilename(initialdir=initialdir, title="Select a video or image",
                                          filetypes=filetypes)
        root.destroy()
        if not path:
            return jsonify({"success": False, "cancelled": True})
        return jsonify({"success": True, "path": os.path.normpath(path)})
    except Exception as e:
        return jsonify({"success": False, "error": f"Native picker failed: {e}"}), 500


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





@app.route('/api/stt_status', methods=['GET'])
def stt_status():
    """Is voice input ready? Never triggers a load - just reports."""
    try:
        import whisper  # noqa: F401
        installed = True
    except Exception:
        installed = False
    return jsonify({"installed": installed, "loaded": stt_model is not None, "device": device})


@app.route('/api/stt_activate', methods=['POST'])
def stt_activate():
    """On-demand voice-input setup, triggered by the mic button.

    Whisper is not installed by the launcher any more: it is a ~100 MB package
    plus a ~140 MB model download that most sessions never use. This installs it
    the first time the user actually asks for voice input, then loads the model.
    """
    global _stt_load_failed
    _stt_load_failed = False   # let the user retry after a previous failure
    try:
        import whisper  # noqa: F401
    except ImportError:
        try:
            import subprocess
            print("[STT] Installing openai-whisper on demand...")
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", "openai-whisper"],
                capture_output=True, text=True, timeout=1800,
            )
            if proc.returncode != 0:
                return jsonify({
                    "success": False,
                    "error": "openai-whisper install failed",
                    "detail": (proc.stderr or "")[-1500:],
                }), 500
        except Exception as e:
            return jsonify({"success": False, "error": f"install error: {e}"}), 500

    model = get_stt_model()
    if model is None:
        return jsonify({"success": False, "error": "Whisper model failed to load"}), 500
    return jsonify({"success": True, "device": device})


@app.route('/api/stt', methods=['POST'])
def native_stt_decode():
    model = get_stt_model()   # lazy: first call pays the load cost, not startup
    if model is None:
        return jsonify({"success": False, "error": "STT unavailable: Whisper not installed. Run: pip install openai-whisper soundfile"}), 503
    if 'audio' not in request.files:
        return jsonify({"success": False, "error": "Audio missing"}), 400

    temp_path = os.path.join(BASE_DIR, "temp_voice.webm")
    try:
        request.files['audio'].save(temp_path)
        result = model.transcribe(temp_path, language="ko")
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
                        "error": f"MobileSAM 로드 실패 - {_sam_last_error or 'unknown'}. 수동 브러시는 계속 사용 가능합니다."}), 500

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
                        "error": f"MobileSAM unavailable - {_sam_last_error or 'unknown'}. Use the manual brush."}), 500

    data = request.json or {}
    path = media_path(data)
    frame_index = int(data.get('frame_index', 0))
    class_id = int(data.get('class_id', 1))
    width, height = int(data.get('width', 800)), int(data.get('height', 600))

    # Only decode the frame when the SAM embedding cache misses. The hybrid CV pass
    # used to need raw pixels on every call, which forced a decode each time; without
    # it a cache hit skips the video seek entirely.
    key = f"{path}_{frame_index}"
    if _cached_key != key:
        frame_bgr = read_video_frame(path, frame_index) if path.lower().endswith(VIDEO_EXTENSIONS) else cv2.imread(path)
        if frame_bgr is None:
            return jsonify({"success": False, "error": "Frame read failed"}), 400
        predictor.set_image(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
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

        # MobileSAM's output is used as-is. A GrabCut + color-prior refinement pass
        # used to run here; it was removed because it hurt on surgical video - the
        # whole field of view is red-on-red, so GrabCut's color GMM cannot separate
        # foreground from background, and specular highlights, smoke and blood keep
        # poisoning it. It cost extra time per frame for worse masks.
        mask_binary = masks[0].astype(np.uint8)

        ys, xs = np.where(mask_binary > 0)
        refined_box = None
        if len(xs) > 0:
            refined_box = [int(xs.min()), int(ys.min()),
                           int(xs.max() - xs.min()), int(ys.max() - ys.min())]
        return jsonify({
            "success": True,
            "rle": rle_encode(mask_binary),
            "refined_box": refined_box,
        })
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


@app.route('/api/load_structures', methods=['POST'])
def load_structures():
    data = request.json or {}
    payload = load_json(annotation_path(data, "_structures.json", "image_structures.json"), default={})
    return jsonify({"success": True, "structures": payload})


@app.route('/api/save_structures', methods=['POST'])
def save_structures():
    data = request.json or {}
    try:
        dump_json(annotation_path(data, "_structures.json", "image_structures.json"), data.get('structures', {}))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/load_meta', methods=['POST'])
def load_meta():
    """비디오별 대카테고리(수술 종류) 등 metadata."""
    data = request.json or {}
    meta = load_json(annotation_path(data, "_meta.json", "image_meta.json"), default={})
    return jsonify({"success": True, "meta": meta})


@app.route('/api/save_meta', methods=['POST'])
def save_meta():
    data = request.json or {}
    try:
        dump_json(annotation_path(data, "_meta.json", "image_meta.json"), data.get('meta', {}))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/load_coaching', methods=['POST'])
def load_coaching():
    """Surgical coaching (수술 tip) — 프레임별 자유 텍스트."""
    data = request.json or {}
    payload = load_json(annotation_path(data, "_coaching.json", "image_coaching.json"), default={})
    return jsonify({"success": True, "coaching": payload})


@app.route('/api/save_coaching', methods=['POST'])
def save_coaching():
    data = request.json or {}
    try:
        dump_json(annotation_path(data, "_coaching.json", "image_coaching.json"), data.get('coaching', {}))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/log_events', methods=['POST'])
def log_events():
    """Append-only session log.

    Body: {directory, video_name, session_id, events: [[t_ms, type, ...args], ...]}
    Writes to <video>_sess_<session_id>.jsonl (one line per event; last line = session index
    with meta on start). The frontend batches events every ~2s so the write rate is low
    even for aggressive mouse-move sampling. Files are JSONL so any downstream analysis
    (paper stats, replay tools, tail -f monitoring) can stream them cheaply.

    Storage economy notes:
      - t_ms is int ms since session_start (relative, saves ~9 bytes per event vs epoch ms)
      - types are short string codes ("mm","md","kd",…) — see the frontend log() helper
      - mouse-move sampled to <=10Hz by the client with a 5-px displacement gate
    """
    data = request.json or {}
    directory = data.get('directory', '')
    if not directory or not os.path.isdir(directory):
        return jsonify({"success": False, "error": "Invalid directory"}), 400

    sess = str(data.get('session_id', '')).strip()
    if not sess or not re.fullmatch(r'[A-Za-z0-9_\-.]{1,64}', sess):
        return jsonify({"success": False, "error": "Invalid session_id"}), 400

    video_name = data.get('video_name', '')
    if video_name:
        base = os.path.splitext(video_name)[0]
        log_path = os.path.join(directory, f"{base}_sess_{sess}.jsonl")
    else:
        log_path = os.path.join(directory, f"session_{sess}.jsonl")

    events = data.get('events', [])
    if not isinstance(events, list) or not events:
        return jsonify({"success": True, "written": 0})

    try:
        # Append-only text write — the JSONL format tolerates a truncated write mid-line
        # (a single bad line at EOF is fine; the earlier events are recoverable).
        with open(log_path, 'a', encoding='utf-8') as f:
            for ev in events:
                # Cheap defensive cap so an eventual bug can't blow the log up
                if isinstance(ev, list) and len(ev) <= 32:
                    f.write(json.dumps(ev, ensure_ascii=False, separators=(',', ':')))
                    f.write('\n')
        return jsonify({"success": True, "written": len(events), "path": log_path})
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


if __name__ == '__main__':
    app.run(host='localhost', port=5000, debug=True)
