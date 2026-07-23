@echo off
REM =====================================================================
REM  embedding.bat - data\ 폴더의 문서를 임베딩하여 index\index.npz 생성
REM
REM  사용법:
REM    embedding.bat                 data\ 안의 모든 문서 임베딩
REM    embedding.bat data\어떤파일.pdf   특정 파일만 임베딩
REM =====================================================================
setlocal
cd /d "%~dp0"

REM --- python 확인 ---
where python >nul 2>nul
if errorlevel 1 (
    echo [error] python 을 찾을 수 없습니다. https://www.python.org 에서 설치 후 PATH 에 추가하세요.
    exit /b 1
)

REM --- .env 확인 ---
if not exist ".env" (
    echo [warn] .env 파일이 없습니다. .env.example 을 복사해 .env 를 만들고 토큰을 넣으세요.
    echo        copy .env.example .env
)

REM --- 가상환경 준비 (최초 1회만 설치) ---
if not exist ".venv\Scripts\python.exe" (
    echo [setup] 가상환경을 생성합니다...
    python -m venv .venv || goto :fail
    call ".venv\Scripts\activate.bat"
    echo [setup] 의존성 패키지를 설치합니다...
    python -m pip install --upgrade pip >nul
    pip install -r requirements.txt || goto :fail
) else (
    call ".venv\Scripts\activate.bat"
)

REM --- 임베딩 실행 ---
python scripts\embed.py %*
if errorlevel 1 goto :fail

echo.
echo [done] 임베딩 완료. 이제 search.bat 으로 검색하세요.
exit /b 0

:fail
echo [error] 실행에 실패했습니다. 위 메시지를 확인하세요.
exit /b 1
