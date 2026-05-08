# Session Handoff — `bkm` Project

**작성**: 2026-05-07
**즉시 트리거**: 현재 폴더 `bkm` → `BestKnownMethods`로 rename 예정. 새 Claude 세션에서 컨텍스트를 처음부터 만들 필요 없이 곧바로 작업을 이어가기 위한 인계 문서.

> 이 문서는 프로젝트 루트에 있으므로 폴더 rename 시 함께 이동합니다.

---

## 0. 즉시 해야 할 것 — 폴더 rename 직후 체크리스트

폴더를 `bkm` → `BestKnownMethods`로 옮긴 직후 발생하는 깨짐과 복구:

| 무엇이 깨지나 | 왜 | 복구 |
|---|---|---|
| **`import bkm`** (어떤 디렉토리에서든) | site-packages의 editable 포인터(.pth)가 옛 경로(`…\bkm\src`)를 가리킴 | 새 폴더에서 **`pip install -e .` 한 번 더 실행**. 같은 site-packages 엔트리가 새 경로로 갱신됨 |
| **`bkm-generator` 콘솔 커맨드** | 마찬가지로 editable wheel 메타가 옛 경로 참조 | 위 한 번으로 같이 해결 |
| **VSCode/IDE 워크스페이스** | 절대 경로 pinned | 워크스페이스 파일 경로 재설정 |
| **`generator.log` (project root)** | 옛 경로에 누적된 로그 | 그냥 지우거나 무시. 다음 실행 시 새 폴더에 생성됨 |
| **`__pycache__/`** | 컴파일된 .pyc | 다음 import 시 자동 재생성. 지워도 무방 |

**중요**: 패키지 **이름** `bkm`은 폴더 이름과 별개입니다.
- `pyproject.toml` `[project] name = "bkm"` ← 패키지 이름
- `src/bkm/` ← 패키지 디렉토리 이름
- 폴더만 `BestKnownMethods`로 바뀌어도 위 두 개는 그대로 → `import bkm`이 그대로 동작

만약 패키지 이름까지 `BestKnownMethods` (또는 snake_case `best_known_methods`)로 바꾸고 싶다면 별도 작업이 필요합니다 — §6 참조.

---

## 1. 프로젝트 한눈에

`bkm` (Best Known Method) — wafer parquet 데이터에서 공정 흐름 DAG를 자동 생성/매칭하는 Python 패키지. 핵심 단위는 **loaf**: 한 wafer의 raw 컬럼들(equipment + chamber + chamber_step + sensor)을 단일 식별자 문자열로 압축한 것 (`"eq1+eq2+ch1+ch2+cs1+cs2+se1+se2"`).

### 두 진입점

| 진입점 | 용도 | 어디 |
|---|---|---|
| `from bkm import BKM` | 단일 BKM DAG 직접 구성 | `src/bkm/bkm.py` |
| `bkm-generator` CLI 또는 `python -m bkm.generator` | 폴더 단위 batch 처리 + multi-BKM registry | `src/bkm/generator.py` |

### Examples 흐름

```
examples/
├── 00_generate_sample_data.py   합성 wafer parquet 생성
├── 01_run_training.py           CLI training (--update) + PNG/Mermaid 렌더
├── 02_run_inference.py          CLI inference (no --update)
└── 03_python_api_demo.py        Python API + 분기 BKM (loafA → {loafB, loafC}) 데모
```

산출물 → `examples/bkm_results/{bkm_directory.json, bkm_wafers.json, diagrams/}`

---

## 2. 현재 파일 맵 (실제로 무엇이 어디 있나)

```
bkm/  (rename 후: BestKnownMethods/)
├── pyproject.toml                 [project.scripts] bkm-generator = "bkm.generator:main"
├── README.md                      간단한 quick start
├── bkm.md                         BKM 클래스 API 상세
├── generator.md                   bkm.generator 모듈 (CLI) 상세
├── SESSION_HANDOFF.md             ← 이 파일
├── LICENSE / MANIFEST.in / .gitignore / upload.ps1
│
├── src/bkm/                       ← 진짜 패키지 (editable 설치됨)
│   ├── __init__.py                exports BKM, ProcessNode
│   ├── bkm.py                     BKM 클래스 + DAG 추론 알고리즘
│   ├── generator.py               (formerly bkm_generator.py) CLI + multi-BKM registry
│   └── utils.py                   TeeOutput, MyTimer 등
│
├── examples/                      ← 4-script 데모 묶음
│   ├── README.md                  ASCII tree, I/O 표, bkm_results 해석 가이드
│   ├── 00_generate_sample_data.py
│   ├── 01_run_training.py
│   ├── 02_run_inference.py
│   ├── 03_python_api_demo.py
│   ├── training_data/             generated, gitignored
│   ├── inference_data/            generated, gitignored
│   └── bkm_results/               generated, gitignored
│       ├── bkm_directory.json     BKM 버전 registry (top-level keys = bkm0001, bkm0002, …)
│       ├── bkm_wafers.json        wafer→BKM 매핑 (training이 별도 파일로 출력)
│       └── diagrams/              PNG (Graphviz) + .mmd (Mermaid) per BKM
│
├── legacy/                        ← 격리된 깨진 단일파일 사본 (use of project root shadow)
│   ├── bkm.py
│   └── bkm_generator.py           imports `common_names`, `common_utils` (없음 → 깨짐)
│
└── dist/, src/bkm.egg-info/       빌드 산출물
```

### 핵심 모듈 시그니처 (자주 참조하는 것들)

| 위치 | 무엇 |
|---|---|
| `bkm.py:66` | `class BKM` — 단일 BKM DAG. `process_data` dict로 직접 구성 가능 |
| `bkm.py:432` | `BKM.read_wafer_edges_from_df()` — multi-row DataFrame → edges (timing 기반 분기 추론) |
| `bkm.py:664` | `BKM.render(filename, fmt='png')` — Graphviz PNG |
| `generator.py:96` | `add_bkm_loaf()` — 1-row 합성 loaf DataFrame 생성 |
| `generator.py:160` | `find_or_create_bkm()` — frozenset hash로 BKM 매칭/생성 |
| `generator.py:216` | `save_bkm_directory()` — bkm_directory.json + bkm_wafers.json 기록 |
| `generator.py:267` | `load_bkm_directory()` — registry 로드 |
| `generator.py:327` | `parse_args()` — `--bkm_columns` 등 CLI 인자 |

---

## 3. 이번 세션에서 한 결정 (시간 순)

1. **`examples/` 폴더 신규 생성** (4 스크립트 + README)
2. **컬럼 rename** 패키지 전반:
   `lot_wf → wafer_id`, `eqp → equipment`, `ch → chamber`, `ch_step → chamber_step`
3. **루트 단일파일 격리** (shadow 문제 해결):
   `bkm.py`, `bkm_generator.py` → `legacy/`로 이동 + `pip install -e .`로 진짜 패키지 등록
4. **`--min_bkm_wafer_count` CLI 인자 제거** (rare BKM 보고 기능 폐기)
5. **`names.py` 삭제** (사용처 없어짐)
6. **JSON 포맷 변경**:
   - `bkm_directory.json`: `"bkm_versions"` wrapper 제거 → 최상위에 version 엔트리 직접
   - `wafer_bkms` → 별도 `bkm_wafers.json` 파일로 분리
7. **`bkm_data/` → `bkm_results/`** rename (출력 폴더)
8. **`demo_v1.json` 폐기** (03 데모는 인메모리만, 영속화 X)
9. **PNG/Mermaid 렌더링** 추가 (graphviz 옵션 dep, `BKM.render()` 사용)
10. **분기 DAG 데모** 03에 추가 (`in → loafA → {loafB, loafC} → out`)
11. **`--bkm_columns` 동작 수정**:
    - `type=list` 파서 버그 수정 → comma-split lambda
    - `add_bkm_loaf()`의 `sorted(columns)` 제거 → **컬럼 순서 보존** (사용자 순서가 곧 BKM 정체성)
12. **합성 데이터 값 명명 통일**:
    `eq1, eq2, ch1, ch2, cs1, cs2, se1, se2, …` 형식 (prefix로 컬럼 식별 가능)
13. **`bkm_generator.py → generator.py`** 모듈 rename (가장 최근). 콘솔 커맨드 `bkm-generator`는 그대로 유지.
14. **`bkm_generator.md → generator.md`** 동시에 rename.

---

## 4. 확립된 컨벤션

| 컨벤션 | 결정 사항 |
|---|---|
| **Loaf 합성 — 컬럼 외부 순서** | `--bkm_columns`에 적힌 순서 보존 (sorted() 안 함). 다른 순서 → 다른 BKM |
| **Loaf 합성 — 컬럼 내부 값 순서** | `sorted(unique())` 고정 (canonical) |
| **Loaf 대소문자** | 전부 lowercase (`BKM` 클래스가 정규화) |
| **합성 데이터 값 prefix** | `eq*` (equipment), `ch*` (chamber), `cs*` (chamber_step), `se*` (sensor) — 디코딩 가능 |
| **출력 폴더 이름** | `bkm_results/` (이전: `bkm_data/`) |
| **CLI 콘솔 커맨드** | `bkm-generator` (하이픈) — 모듈은 `bkm.generator` (점). 둘이 별개 |
| **Editable 설치 의존** | 모든 예제는 `pip install -e .` 전제. CWD 기반 import 회피 |
| **루트 단일파일 격리** | `legacy/`에 보관, 활성 코드 아님 |

---

## 5. 미해결/논의된 오픈 토픽

이 세션에서 사용자와 토론은 했지만 **구현은 안 한** 항목들:

### A. Timing tolerance (대화 #N)

**문제**: `BKM.read_wafer_edges_from_df()`의 predecessor 판정은 `tkout2 <= tkin` **엄격 비교**. 1ms 시계 skew가 분기/직선 결과를 뒤집을 수 있음.

**제안**: `BKM.__init__`에 `timing_tolerance: pd.Timedelta = pd.Timedelta(0)` 파라미터 추가, [bkm.py:408](src/bkm/bkm.py:408)과 [bkm.py:474](src/bkm/bkm.py:474) 두 줄을 `tkout2 <= tkin + self.timing_tolerance`로 수정.

**미결**: 기존 fingerprint들이 tolerance 값에 묶이게 되어 BKM 정체성이 변할 수 있음 → 도입 시 마이그레이션 정책 필요.

### B. CLI flow에서 timing 제거 (대화 #N+1)

**관찰**:
- `add_bkm_loaf()`는 wafer를 1-row DataFrame으로 collapse → `read_wafer_edges_from_df`의 timing 비교 자체가 일어나지 않음
- 합성된 `tkin_time = tkout - 60min`은 **dead weight** (어떤 값이든 결과 동일)

**제안**: CLI flow에서 timing-based 추론을 완전히 분리. parquet 스키마에서 `tkin_time` 합성을 빼고 (CLI는 1-row 보장이라 timing이 의미 없음), multi-row 분기 추론이 필요한 사용자만 별도 메서드/직접 `process_data`로 처리.

**미결**: 영향 범위 큼 (CLI 시그니처, parquet 스키마, examples, docs, 기존 `bkm_directory.json`의 labels 필드). 사용자 결정 대기.

### C. Branch vs join 한계

**관찰**: 현재 추론 알고리즘은 각 노드에 in_degree ≤ 1만 부여 → **트리 구조**. 두 가지가 한 노드로 합쳐지는 join은 표현 불가. 사용자가 진짜 join 필요 시 `process_data` dict로 직접 명시해야 함.

**미결**: 알고리즘 변경 시 deterministic한 추론 보장이 깨짐. 현재 설계의 의도된 트레이드오프.

### D. `--bkm_columns` 컬럼 내부 정렬 옵션

**관찰**: 현재 한 컬럼 안에서는 무조건 `sorted(unique())`. 사용자가 "row 순서대로" 또는 "tkin 순서대로" 같은 다른 정렬을 원할 수 없음.

**미결**: canonicality(같은 값 집합 → 같은 loaf) 보장 vs 사용자 유연성. 현 설계는 canonicality 우선.

### E. 콘솔 커맨드 이름 (`bkm-generator`)

**관찰**: 모듈은 `bkm.generator`로 단순화했지만 콘솔 커맨드는 `bkm-generator` 그대로. 일관성을 위해 `bkm-gen` 또는 `bkm` (sub-command 형식)로 줄일 수 있음.

**미결**: 사용자 결정 안 함. 외부 인터페이스 변경이라 영향 큼.

---

## 6. **만약** 패키지 이름까지 `BestKnownMethods`로 바꾸고 싶다면

폴더만 rename하면 패키지는 그대로 `bkm`. 만약 패키지 이름도 바꾸려면 추가로:

1. **`pyproject.toml`**:
   - `[project] name = "bkm"` → `name = "best-known-methods"` (PyPI는 hyphen 허용)
   - `[project.scripts] bkm-generator = "bkm.generator:main"` → `... = "best_known_methods.generator:main"` (Python import는 underscore)
   - `[tool.setuptools.packages.find] where = ["src"]` → 그대로

2. **디렉토리**:
   - `src/bkm/` → `src/best_known_methods/`
   - `src/bkm.egg-info/` → 자동 재생성

3. **import 일괄 치환**:
   - `from bkm import BKM` → `from best_known_methods import BKM`
   - `from bkm.generator import ...` → `from best_known_methods.generator import ...`
   - `python -m bkm.generator` → `python -m best_known_methods.generator`

4. **영향 파일**: `examples/01_run_training.py`, `02_run_inference.py`, `03_python_api_demo.py`, `bkm.md`, `generator.md`, `examples/README.md`, `README.md`

5. **사후**: `pip install -e .` 재실행, 옛 `bkm` 패키지 site-packages에서 제거 (`pip uninstall bkm`).

**제 추천**: 굳이 안 바꾸는 게 좋습니다. `bkm`은 짧고 사용자가 이미 익숙하며, 폴더 이름만 바뀌어도 코드/문서는 그대로 동작합니다. `BestKnownMethods`는 폴더 레벨에서만 가독성/검색성을 높이고 코드 import는 짧은 `bkm`을 유지하는 편이 일관성 있습니다.

---

## 7. 다음 세션 시작 체크리스트

새 Claude 세션을 열면 다음 순서로 컨텍스트를 빠르게 흡수:

1. 이 파일(`SESSION_HANDOFF.md`) 읽기 — 5분
2. `examples/README.md` 읽기 — 흐름 + I/O 표 + 결과 해석
3. `generator.md` §3.1 (loaf 합성) 또는 §4 (registry) 필요 시 정독
4. 폴더가 rename 됐다면: `pip install -e .` 한 번 실행
5. 동작 검증: `rm -rf examples/bkm_results examples/training_data examples/inference_data && python examples/00_generate_sample_data.py && python examples/01_run_training.py && python examples/02_run_inference.py`
   - 기대: 18 wafers → 3 BKMs (`bkm0001`/`0002`/`0003`), inference Known=3 / Unknown=2
   - Loaf 예시: `eq1+eq2+ch1+ch2+cs1+cs2+se1+se2` 형식
6. 그 후 사용자 새 요구사항 듣기

---

## 8. 절대 잊지 말 것 (gotchas)

- 콘솔 커맨드 `bkm-generator`(**하이픈**) ≠ 모듈 `bkm.generator`(**점**). 둘 다 동작하지만 grep할 때 헷갈림.
- `bkm-generator.exe`는 `C:\Users\Asus\AppData\Roaming\Python\Python310\Scripts\`에 설치됨. PATH에 없을 수 있음 — `python -m bkm.generator`가 항상 안전.
- `pyproject.toml`의 `[project.scripts]` 엔트리를 바꾼 뒤에는 반드시 `pip install -e .`을 다시 실행. 그래야 새 entry point가 콘솔에 등록됨.
- `add_bkm_loaf()`는 wafer 한 개당 항상 1-row 결과 → CLI 흐름에서 분기 BKM은 절대 생기지 않음. 분기는 03 데모처럼 Python API로만.
- `examples/bkm_results/` 산출물은 .gitignore에 명시 안 되어 있지만 src/ 자체가 git untracked 상태 — 이 프로젝트는 git 적극 활용 안 하는 분위기. 변경 시 사용자에게 확인.
- BKM 노드명은 항상 lowercase (`BKM` 클래스가 강제). 디버깅할 때 raw 데이터 대문자랑 비교하지 말 것.

---

**End of handoff. Good luck, 새 세션!**
