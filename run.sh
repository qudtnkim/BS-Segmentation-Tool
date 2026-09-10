#!/usr/bin/env bash
# BS Segmentation Tool - Setup and Launcher (macOS/Linux)
set -e

echo "==========================================================="
echo " BS Segmentation Tool Setup and Launcher"
echo "==========================================================="
echo

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---- 1. Find a working Python
PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "[ERROR] Python not found. Install Python 3.10+ from https://www.python.org/"
    exit 1
fi
echo "[OK] Python found: $($PY --version)"

# ---- 2. Isolated virtual environment (.venv)
VENV_DIR="$DIR/.venv"
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "[INFO] Creating virtual environment in .venv ..."
    "$PY" -m venv "$VENV_DIR"
fi
VENV_PY="$VENV_DIR/bin/python"
echo "[OK] Virtual environment ready."

# ---- 3. Core dependencies
echo "[INFO] Upgrading pip..."
"$VENV_PY" -m pip install --upgrade pip -q
echo "[INFO] Installing core dependencies (Flask, OpenCV, pandas, ffmpeg)..."
"$VENV_PY" -m pip install -r "$DIR/requirements.txt" -q
echo "[OK] Core dependencies installed."

# ---- 4. PyTorch (optional; the default PyPI wheel bundles CUDA support on Linux
#     and auto-detects the GPU at runtime, so no separate GPU/CPU index is needed there)
HAS_GPU=0
command -v nvidia-smi >/dev/null 2>&1 && HAS_GPU=1

if ! "$VENV_PY" -c "import torch" >/dev/null 2>&1; then
    echo "[INSTALL] Installing PyTorch..."
    "$VENV_PY" -m pip install torch -q || echo "[WARN] PyTorch install failed. GPU/AI features will be limited."
else
    TORCH_CUDA_OK=$("$VENV_PY" -c "import torch;print(torch.cuda.is_available())" 2>/dev/null)
    if [ "$HAS_GPU" = "1" ] && [ "$TORCH_CUDA_OK" = "False" ]; then
        echo "[INFO] NVIDIA GPU detected but the installed PyTorch build is CPU-only - reinstalling..."
        "$VENV_PY" -m pip install --force-reinstall torch -q
        TORCH_CUDA_OK=$("$VENV_PY" -c "import torch;print(torch.cuda.is_available())" 2>/dev/null)
    fi
    echo "[OK] PyTorch already available (CUDA: $TORCH_CUDA_OK)"
fi

# ---- 5. Whisper STT (optional; ffmpeg bundled via imageio-ffmpeg)
if ! "$VENV_PY" -c "import whisper" >/dev/null 2>&1; then
    echo "[INSTALL] openai-whisper for voice input..."
    "$VENV_PY" -m pip install openai-whisper -q || echo "[WARN] Whisper install failed. STT disabled."
else
    echo "[OK] Whisper already available."
fi

# ---- 6a. MobileSAM (primary, ~40MB weight bundled in-repo, 5-10x faster than SAM 2 Hiera Tiny on CPU)
# Full-import probe — mobile_sam pulls timm at import, so a shallow install-check misses that.
if ! "$VENV_PY" -c "from mobile_sam import sam_model_registry" >/dev/null 2>&1; then
    echo "[INSTALL] MobileSAM not found - installing from GitHub (offline-safe once cached)..."
    "$VENV_PY" -m pip install timm -q
    if "$VENV_PY" -m pip install git+https://github.com/ChaoningZhang/MobileSAM.git -q; then
        echo "[OK] MobileSAM installed."
    else
        echo "[WARN] MobileSAM install failed. Falling back to SAM 2 attempt."
    fi
else
    echo "[OK] MobileSAM already available. Weight file 'mobile_sam.pt' ships with the repo."
fi

# ---- 6b. SAM 2 (fallback backend - honored only when MobileSAM unavailable or BS_USE_MOBILESAM=0)
if ! "$VENV_PY" -c "from sam2.build_sam import build_sam2" >/dev/null 2>&1; then
    echo "[INSTALL] SAM 2 fallback not found - installing from PyPI..."
    if "$VENV_PY" -m pip install sam2 -q; then
        echo "[OK] SAM 2 fallback installed."
    else
        echo "[INFO] SAM 2 install skipped. MobileSAM will be the only AI backend."
    fi
else
    echo "[OK] SAM 2 fallback already available."
fi

echo
echo "==========================================================="
echo " All checks done. Starting server..."
echo "==========================================================="
(sleep 1 && (command -v open >/dev/null 2>&1 && open http://localhost:5000 || command -v xdg-open >/dev/null 2>&1 && xdg-open http://localhost:5000)) &
"$VENV_PY" "$DIR/app.py"
