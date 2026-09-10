# BS Segmentation Tool

Flask 기반 수술 영상/이미지 세그멘테이션 어노테이션 툴. 로컬 Whisper STT와 MobileSAM 기반 마스크 propagation을 지원한다.

## Requirements

- Python 3.10 - 3.12 권장 (3.13+ 는 numpy/torch 등 일부 패키지의 사전 빌드된 wheel이 없어 설치가 느리거나 실패할 수 있음). **Python이 없어도** Windows에서는 `run.bat`이 winget으로 3.12를 자동 설치한다.

## Setup & Run

### Windows

```
run.bat
```

### macOS / Linux

```
chmod +x run.sh   # 최초 1회
./run.sh
```

Windows에서는 `run.bat` 실행 시 UAC 관리자 권한 승인 창이 뜬다 (ffmpeg를 시스템 전역에 설치하기 위함). 승인하면:
1. `py` 런처로 3.12 → 3.11 → 3.10 순으로 설치된 Python을 찾는다. 없으면 **winget으로 Python 3.12를 자동 설치**하고 `C:\Program Files\Python312\python.exe` 등 표준 경로에서 재감지한다. winget이 없는 환경(Win10 < 1809, Server 등)에서만 수동 설치가 필요하다.
2. 가상환경을 프로젝트 폴더가 아니라 `%USERPROFILE%\.bs_tool\venv`에 만든다. 사용자 계정명에 비ASCII 문자(한글 등)가 섞여 있으면 pip/torch 설치가 깨지는 경우가 있어, 그 경우 `C:\bs_tool_venv`로 자동 폴백한다.
3. `requirements.txt`의 핵심 의존성을 먼저 prebuilt wheel만으로 설치 시도하고(`--only-binary=:all:`), 실패하면 소스 빌드 허용 모드로 재시도한다.
4. ffmpeg를 시스템 전역(PATH)에 설치한다. winget이 있으면 winget으로, 없으면 `imageio-ffmpeg`가 받아둔 바이너리를 `C:\ffmpeg\bin`에 복사하고 시스템 PATH에 등록한다. 이 단계가 실패해도 app.py가 자체적으로 `imageio-ffmpeg` 바이너리를 사용하도록 폴백하므로 앱 자체는 계속 동작한다.
5. PyTorch는 `nvidia-smi`로 NVIDIA GPU 유무를 감지해서, GPU가 있으면 CUDA 지원 빌드를, 없으면 가벼운 CPU 전용 빌드를 설치한다. 이미 설치된 PyTorch가 CPU 전용인데 GPU가 감지되면 자동으로 재설치한다.
6. Whisper(STT), MobileSAM, SAM 2는 선택 의존성이라 설치 실패해도 서버는 정상 실행되고 해당 기능만 비활성화된다.
7. 브라우저에서 `http://localhost:5000` 이 자동으로 열린다.

> 관리자 계정이 없는 PC(사내 정책으로 UAC 상승이 완전히 막힌 경우)에서는 `run.bat`이 실행되지 않는다. 이런 환경에서는 `run.sh` 방식처럼 venv 안에서만 동작하도록 관리자 권한 요구 부분을 빼고 써야 한다.

## AI 마스크 보조 (MobileSAM, 선택)

기본 백엔드는 **MobileSAM** (SAM 1 계열 ViT-Tiny distilled, 10M params). CPU에서 SAM 2 Hiera Tiny 대비 5-10배 빠르며, 가중치(`mobile_sam.pt`, 39 MB)는 **리포에 함께 배포**되어 오프라인에서도 첫 실행이 가능하다. `run.bat`/`run.sh`가 다음을 순서대로 자동 설치한다:

```
pip install timm
pip install git+https://github.com/ChaoningZhang/MobileSAM.git
```

MobileSAM 설치가 실패하면 **SAM 2**로 자동 폴백한다(가중치 `sam2_hiera_tiny.pt`는 최초 실행 시 자동 다운로드). 환경변수 `BS_USE_MOBILESAM=0`으로 SAM 2를 강제할 수 있다. UI 우측 하단 "AI Mask Auto-Propose" 옆 배지가 현재 사용 중인 백엔드와 디바이스를 보여준다.

## Known limitations

- GPU(CUDA) 사용 시 PyTorch를 CPU 대신 CUDA 빌드로 별도 설치해야 한다.
- Whisper STT는 브라우저의 마이크 녹음(webm) 포맷에 의존한다.
