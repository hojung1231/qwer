# 화음왕 추출 서버

휴대폰 앱이 보낸 mp3를 이 컴퓨터가 받아서 멜로디·화음·가사 위치를 계산해 돌려줍니다.
그래픽카드(NVIDIA)가 있으면 4분짜리 곡 하나에 1분 안팎, 없으면 5~10분쯤 걸립니다.

## 한 번만 하는 설치

1. **Python 3.10~3.12** 와 **ffmpeg** 설치 (둘 다 `PATH`에 있어야 합니다).
   - Windows: `winget install Python.Python.3.12` · `winget install Gyan.FFmpeg`
2. 이 저장소 폴더에서:

   ```
   python -m venv .venv
   .venv\Scripts\activate            (macOS/Linux: source .venv/bin/activate)
   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124    (NVIDIA 그래픽카드)
   pip install torch torchaudio                                                        (그래픽카드 없음)
   pip install -r hwaeumwang/server/requirements.txt
   ```

## 켜기

```
.venv\Scripts\activate
python hwaeumwang/server/server.py
```

창에 `앱의 서버 주소 칸에 넣을 주소:  http://192.168.x.x:8787` 이 나옵니다.
앱 → 내 음악창고 → 오른쪽 위 **서버** → 그 주소를 넣고 **연결 확인** → **저장**.
그다음 곡 카드의 **화음 추출**을 누르면 됩니다.

- 휴대폰과 컴퓨터가 **같은 와이파이**에 있어야 합니다.
- 처음 켤 때 Windows 방화벽이 물으면 **개인 네트워크 허용**을 누릅니다.
- 첫 곡은 분리 모델(약 80MB)을 내려받느라 더 걸립니다.
- 남이 쓰지 못하게 하려면 `python hwaeumwang/server/server.py --key 비밀단어` 로 켜고 앱에도 같은 단어를 넣습니다.

## 파일 하나만 바로 돌려 보기

```
python hwaeumwang/server/pipeline.py 노래.mp3 노래.hwaeum.json
```

결과 `.json`은 앱의 곡 추가로 mp3와 함께 넣을 수도 있습니다.
받은 mp3와 결과는 `hwaeumwang/server/data/`에 남습니다(저장소에는 올라가지 않습니다).
