@echo off
REM =====================================================================
REM  search.bat - 질의어로 인덱스를 의미 검색
REM
REM  사용법:
REM    search.bat "임산부 시간외근로"
REM    search.bat --top 3 "전용통신망 수의계약"
REM    search.bat --json "방만경영 예산통제"
REM =====================================================================
setlocal
cd /d "%~dp0"

REM --- 인자 확인 ---
if "%~1"=="" (
    echo 사용법: search.bat "검색어"  [--top N] [--json]
    echo   예:   search.bat "임산부 시간외근로"
    exit /b 1
)

REM --- 가상환경 활성화 (embedding.bat 이 먼저 만들어 둔 것을 사용) ---
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo [warn] 가상환경이 없습니다. 먼저 embedding.bat 을 한 번 실행하세요.
)

REM --- 인덱스 확인 ---
if not exist "index\index.npz" (
    echo [error] index\index.npz 가 없습니다. 먼저 embedding.bat 을 실행하세요.
    exit /b 1
)

python scripts\search.py %*
exit /b %errorlevel%
