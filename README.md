# dataweb — 감사문서 임베딩 & 의미검색

한국 공공기관 **감사 문서**(감사보고서 · 지적사항 · 처분요구서)를 대상으로,
문서를 벡터로 바꾸고(임베딩) 자연어로 **의미 검색**을 하는 최소 파이프라인입니다.

지원 형식: `.pdf`, `.hwp`, `.hwpx`, `.txt`, `.md`

## 두 가지 사용 방법

| 방법 | 설치 | 키(토큰) | 어떻게 |
|------|------|----------|--------|
| **A. 웹 페이지** (`web/index.html`) | **불필요** | **불필요** | 크롬/엣지로 파일을 열기만 하면 됨. 임베딩이 브라우저 안에서 실행됨 |
| B. 배치 스크립트 (`embedding.bat`/`search.bat`) | 파이썬 필요 | HF 토큰 필요 | 대량 문서·자동화에 적합 |

> **설치가 안 되는 환경이면 방법 A를 쓰세요.** 파이썬·pip·서버·API 키가 전부 필요 없습니다.

---

## 방법 A — 웹 페이지 (설치 불필요) ⭐

1. `web/index.html` 파일을 **크롬 또는 엣지**로 엽니다(더블클릭).
2. **① 문서 넣기**: 파일을 드래그하거나, `샘플 감사문서 4건 불러오기`로 바로 체험.
3. **② 임베딩 시작**: 최초 1회 임베딩 모델(약 100MB)을 자동으로 내려받아 브라우저에 캐시합니다(인터넷 필요).
4. **③ 검색**: 예) `임산부 시간외근로`, `전용통신망 수의계약` → 유사도 순으로 결과 표시.

- 문서 내용은 **브라우저 밖으로 전송되지 않습니다**(완전 로컬).
- HWP·HWPX·PDF 추출과 임베딩·검색이 모두 페이지 안에서 동작합니다.
- `인덱스 저장(.json)` 으로 임베딩 결과를 파일로 보관하고, 다음에 `인덱스 불러오기`로 즉시 검색할 수 있습니다.
- 모델: `Xenova/multilingual-e5-small`(다국어·한국어, 브라우저용 경량).

---

## 방법 B — 배치 스크립트

- **문서 → 임베딩**: `embedding.bat`
- **질문 → 검색**: `search.bat`
- **설정/키**: `.env`

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
search.bat --alpha 1.0 "방만경영 예산통제"   :: 순수 벡터검색으로 비교
search.bat --json "방만경영 예산통제"
```

→ 질문을 같은 모델로 임베딩한 **코사인 유사도**와 **키워드(BM25)** 점수를 결합한
**하이브리드 순위**로 문서 조각을 보여줍니다. `--alpha 1.0` 이면 순수 벡터검색입니다.

## 4. 검색 품질 평가 (개선 전/후 비교)

```bat
python scripts\evaluate.py                :: 가능한 모든 모드, k=5
python scripts\evaluate.py --modes bm25   :: 임베딩 없이 키워드만 (오프라인)
python scripts\evaluate.py --alpha 0.5
```

`eval\queryset.json` 의 샘플 질의셋으로 **Precision@k · MRR · 변별력(관련/비관련 점수 차)**
을 모드별(bm25 / vector / hybrid)로 출력합니다. 8만 건 확장 시 감사실 업무자가 대표
질의와 정답 문서를 채워 넣으면 개선 전/후를 재현 가능하게 비교할 수 있습니다.

> 진단 배경과 근거는 [`docs/DIAGNOSIS.md`](docs/DIAGNOSIS.md) 참고 — 낮은 검색 품질의
> 실제 원인(웹 통째 임베딩 기본값, bge-m3 풀링 버그, 하이브리드 부재 등)을 코드 근거와
> 함께 정리했습니다.

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
├─ eval/                # 평가용 샘플 질의셋(queryset.json)
├─ docs/DIAGNOSIS.md     # 검색 품질 저하 원인 진단 보고서
└─ scripts/
   ├─ common.py         # 설정 + 임베딩 백엔드
   ├─ extract.py        # PDF/HWP/HWPX 텍스트 추출(+노이즈 제거)
   ├─ retrieval.py      # BM25 키워드 점수 + 하이브리드 결합
   ├─ embed.py          # 추출→청킹→임베딩→저장
   ├─ search.py         # 질의 임베딩→하이브리드 검색
   └─ evaluate.py       # 샘플 질의셋으로 품질 측정
```

## 동작 원리 (요약)

1. **추출**: PDF는 PyMuPDF, HWPX는 XML 파싱, HWP(바이너리)는 OLE 스트림을
   zlib 해제 후 `PARA_TEXT` 레코드에서 텍스트를 복원합니다. 반복되는 머리말/꼬리말·
   페이지번호는 임베딩 전에 제거합니다.
2. **청킹**: 문단 경계를 우선하여 문서를 겹치는 조각으로 나눕니다(너무 짧은 조각은 버림).
3. **임베딩**: 각 조각을 모델로 벡터화하고 L2 정규화합니다(hf_api 는 `POOLING` 로 CLS/mean 선택).
4. **검색**: 질문의 **코사인 유사도**와 **키워드(BM25)** 점수를 각각 정규화해
   `HYBRID_ALPHA` 로 가중 결합한 **하이브리드 점수**로 순위를 매깁니다.
   법 조항·기관명·금액 같은 정확 일치 토큰을 키워드 쪽이 잡아 줍니다.
