# dataweb — 감사문서 임베딩 & 의미검색

한국 공공기관 **감사 문서**(감사보고서 · 지적사항 · 처분요구서)를 대상으로,
Hugging Face 임베딩 모델을 이용해 문서를 벡터로 바꾸고(임베딩) 자연어로
**의미 검색**을 하는 최소 파이프라인입니다.

- **문서 → 임베딩**: `embedding.bat`
- **질문 → 검색**: `search.bat`
- **설정/키**: `.env`

지원 형식: `.pdf`, `.hwp`, `.hwpx`, `.txt`, `.md`

---

## 1. 준비

```bat
copy .env.example .env
```

`.env` 를 열어 Hugging Face 토큰을 넣습니다
(발급: https://huggingface.co/settings/tokens — Read 권한이면 충분):

```
HUGGINGFACEHUB_API_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
```

> 파이썬(3.9+)만 설치돼 있으면 됩니다. 나머지 패키지는 `embedding.bat` 이
> 최초 실행 때 자동으로 `.venv` 에 설치합니다.

## 2. 임베딩 (색인 생성)

`data\` 폴더에 문서를 넣고:

```bat
embedding.bat
```

→ 각 문서를 텍스트로 추출하고, 겹치는 조각(chunk)으로 나눈 뒤 임베딩하여
`index\index.npz` 에 저장합니다.

## 3. 검색

```bat
search.bat "임산부 시간외근로"
search.bat --top 3 "전용통신망 수의계약 케이티"
search.bat --json "방만경영 예산통제"
```

→ 질문을 같은 모델로 임베딩해 **코사인 유사도**가 높은 문서 조각을 순위대로 보여줍니다.

---

## 모델 선택

`.env` 의 `EMBEDDING_MODEL` 한 줄로 교체합니다.

| 모델 | 특징 | 언제 |
|------|------|------|
| `BAAI/bge-m3` (기본) | 다국어(한국어 강함), 8192토큰 긴 문맥, dense 검색 | 범용 권장 |
| `nlpai-lab/KURE-v1` | 한국어 검색 특화(bge-m3 파인튜닝) | 한국어만 다룰 때 |
| `intfloat/multilingual-e5-large` | 다국어 e5 | e5 계열 선호 시(아래 프리픽스 필요) |

> e5 계열은 `.env` 에서 `QUERY_PREFIX=query:` / `PASSAGE_PREFIX=passage:` 로 설정하세요.
> bge-m3 / KURE 는 프리픽스가 필요 없습니다.

## 백엔드 선택 (`EMBEDDING_BACKEND`)

- `hf_api` (기본): Hugging Face 서버에 요청. **토큰 필요**, 로컬 GPU 불필요.
- `local`: 이 PC에서 직접 실행. 토큰 불필요·오프라인 가능하지만 최초 1회 모델을
  내려받습니다. `requirements.txt` 의 `sentence-transformers` 주석을 해제해 설치하세요.

## 스캔본 PDF (OCR)

이미지로만 된 스캔 PDF(예: `2023_감사보고서_스캔본.pdf`)는 추출 가능한
텍스트가 없어 자동으로 건너뜁니다. OCR을 켜려면:

1. Tesseract 설치 + 한국어 데이터(`kor`)
2. `requirements.txt` 의 `pytesseract`, `pillow` 주석 해제 후 설치
3. `.env` 에서 `ENABLE_OCR=1`

---

## 구조

```
dataweb/
├─ embedding.bat        # 임베딩 실행(가상환경 자동 구성)
├─ search.bat           # 검색 실행
├─ .env / .env.example  # 설정·키 (.env 는 git 에 올라가지 않음)
├─ requirements.txt
├─ data/                # 원본 문서(샘플 포함)
├─ index/              # 생성된 벡터 인덱스(index.npz)
└─ scripts/
   ├─ common.py         # 설정 + 임베딩 백엔드
   ├─ extract.py        # PDF/HWP/HWPX 텍스트 추출
   ├─ embed.py          # 추출→청킹→임베딩→저장
   └─ search.py         # 질의 임베딩→유사도 검색
```

## 동작 원리 (요약)

1. **추출**: PDF는 PyMuPDF, HWPX는 XML 파싱, HWP(바이너리)는 OLE 스트림을
   zlib 해제 후 `PARA_TEXT` 레코드에서 텍스트를 복원합니다.
2. **청킹**: 문단 경계를 우선하여 문서를 겹치는 조각으로 나눕니다.
3. **임베딩**: 각 조각을 모델로 벡터화하고 L2 정규화합니다.
4. **검색**: 질문 벡터와 모든 조각 벡터의 내적(=코사인 유사도)으로 순위를 매깁니다.
