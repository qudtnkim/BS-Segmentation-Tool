# BS Segmentation Tool

Flask 기반 수술 영상/이미지 세그멘테이션 어노테이션 툴. 로컬 Whisper STT와 SAM 2 기반 마스크 propagation을 선택적으로 지원한다.

## Requirements

- Python 3.10 - 3.12
- (선택) SAM 2 기반 AI 마스크 보조 기능을 쓰려면 Git 설치 필요

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
1. `python`이 PATH에 없어도 `py` 런처(Windows) / `python3`(macOS·Linux)를 자동으로 찾는다.
2. 프로젝트 폴더에 `.venv` 가상환경을 만들어 시스템 Python과 분리 설치한다 (다른 프로젝트와 패키지 버전 충돌 방지).
3. `requirements.txt`에 고정된 버전으로 Flask/OpenCV/pandas 등 핵심 의존성을 설치한다.
4. ffmpeg를 시스템 전역(PATH)에 설치한다 — winget이 있으면 winget으로, 없으면 `imageio-ffmpeg`가 받아둔 바이너리를 `C:\ffmpeg\bin`에 복사하고 시스템 PATH에 등록한다. 이 단계가 실패해도 app.py가 자체적으로 `imageio-ffmpeg` 바이너리를 사용하도록 폴백하므로 앱 자체는 계속 동작한다.
5. PyTorch(CPU), Whisper(STT)는 선택 의존성이라 설치 실패해도 서버는 정상 실행되고 해당 기능만 비활성화된다.
6. 브라우저에서 `http://localhost:5000` 이 자동으로 열린다.

> 관리자 계정이 없는 PC(사내 정책으로 UAC 상승이 완전히 막힌 경우)에서는 `run.bat`이 실행되지 않는다. 이런 환경에서는 `run.sh` 방식처럼 venv 안에서만 동작하도록 관리자 권한 요구 부분을 빼고 써야 한다.

## SAM 2 (선택, AI 마스크 보조)

기본 설치에는 포함되지 않는다. 필요하면 가상환경 활성화 후:

```
.venv\Scripts\pip install "git+https://github.com/facebookresearch/sam2.git"   # Windows
.venv/bin/pip install "git+https://github.com/facebookresearch/sam2.git"      # macOS/Linux
```

가중치(`sam2_hiera_tiny.pt`)는 최초 실행 시 자동 다운로드된다. 설치되지 않으면 AI 보조 없이 수동 브러시 툴만 사용 가능하다.

## Known limitations

- GPU(CUDA) 사용 시 PyTorch를 CPU 대신 CUDA 빌드로 별도 설치해야 한다.
- Whisper STT는 브라우저의 마이크 녹음(webm) 포맷에 의존한다.
