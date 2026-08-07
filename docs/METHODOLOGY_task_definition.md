# Methodology — Task Definition from Multi-Label Video Annotations

**Goal**: 대량의 taxonomy annotate된 비디오로부터
1. 각 task의 **mandatory core** (반드시 포함되는 label set)
2. **optional variant** (일부에만 나타나는 label)
3. **방향성/순서** (partial order, canonical sequence)
4. **anchor / standard** (prototypical instance)
5. **deviation detection** ("1,6,7만 있고 3이 빠졌다"를 정량적으로 flag)

를 **데이터 기반으로 정의**하는 파이프라인.

---

## 1. Problem Formulation

각 비디오 V_k → event log:
```
V_k = [(t_i, P_i, S_i, I_i) for i in frames]
```
- `P_i` ⊆ Phase taxonomy (multi-label)
- `S_i` ⊆ Structure taxonomy (multi-label)
- `I_i` ⊆ Instrument classes (multi-label)

**Task instance** = 의미 있는 시간 구간의 label bag/sequence.
사용자 시나리오의 `{1,3,5,6,7}`, `{1,3,6,7}` 등이 여기에 해당.

**우리가 답하고 싶은 4가지 질문:**
| Q | 예시 | 답할 도구 |
|---|---|---|
| Q1: 이 task type의 mandatory label은? | "6, 7은 항상 있다" | Frequent itemset mining, support 통계 |
| Q2: 순서는? | "3은 6보다 항상 먼저" | Sequence pattern mining, Inductive Miner |
| Q3: 새 인스턴스가 정상인가? | "3이 빠졌다 = 이상" | Conformance checking (alignment fitness) |
| Q4: label간 상호 규칙은? | "{6,7}이면 3도 87%" | Association rule mining (FP-Growth) |

---

## 2. 방법론 스택 (핵심)

### A. Process Mining (주력)
- **Alpha / Heuristics / Inductive Miner** — event log → Petri net/BPMN
- 특히 **Inductive Miner** (Leemans 2013)는 soundness 보장 + concurrency/loop/choice 자동 발견
- 도구: **pm4py** (Python)

### B. Frequent Pattern Mining (보조)
- **Apriori / FP-Growth** — itemset support 분석
- **PrefixSpan / SPADE** — sequence pattern 발견 (순서 고려)
- 도구: **mlxtend**, **prefixspan-py**

### C. Sequence Alignment (Bioinformatics-inspired)
- **Multiple Sequence Alignment** — 여러 task instance 정렬 → 보존된 position(mandatory) vs gap(optional)
- 도구: **Bio.pairwise2** (biopython), 자체 구현 (Needleman-Wunsch)

### D. Trace Clustering
- 같은 task type을 자동 분리 (수동 라벨 없이)
- **K-Modes** (categorical), **HDBSCAN** on Jaccard distance

### E. Conformance Checking
- 새 비디오 → 학습된 모델 대비 **fitness / precision** 점수
- **Alignment-based conformance** (Adriansyah 2014)
- 도구: **pm4py.conformance**

---

## 3. "Mandatory vs Optional"의 통계적 정의

Task type C의 각 label ℓ에 대해:
```
support(ℓ | C) = |{instance ∈ C : ℓ ∈ instance}| / |C|
```

**분류 기준 (조정 가능):**

| Support | 분류 | 해석 |
|---|---|---|
| ≥ 0.95 | **Mandatory core** | 이 label 없으면 정상 task 아님 |
| 0.70–0.95 | **Near-mandatory** | 일반적으로 있으나 skip 가능 |
| 0.30–0.70 | **Optional / variant** | 상황에 따라 |
| < 0.30 | **Rare / noise** | 예외 케이스 |

**통계적 검증**: Wilson score interval을 신뢰구간으로 사용
```python
# 예: 100 instance 중 90번 관측 → 95% CI = [0.826, 0.947]
# 하한이 0.8보다 크면 "mandatory"라고 주장 가능
```

**Task type별 최소 표본**:
- 0.9 vs 0.8 구분: 각 task type당 N ≥ 150
- 0.9 vs 0.7 구분: N ≥ 50
- Pilot 단계는 N ≥ 20이면 대략적 트렌드 파악 가능

---

## 4. Directionality (순서/방향성) 추출

### 4.1 Pairwise precedence graph
모든 label 쌍 (a, b)에 대해:
```
P(a → b) = (같은 task에서 a가 b보다 먼저 등장한 횟수) / (a,b가 같이 등장한 횟수)
```
- P > 0.9 → strong precedence a→b
- P ≈ 0.5 → concurrent / 순서 무관
- Bradley-Terry model로 partial ranking 학습 가능

### 4.2 Transitive reduction → canonical DAG
Precedence graph → DAG → transitive reduction = **minimal canonical workflow**

### 4.3 Inductive Miner로 직접 process tree 추출
concurrent block, loop, choice를 자동으로 발견해 BPMN으로 시각화

---

## 5. Anchor / Standard 정의

**"Anchor"** = task type의 prototypical instance (medoid).

```
anchor(C) = argmin_{v ∈ C} Σ_{u ∈ C} d(v, u)
```
- d = Jaccard distance (set) 또는 edit distance (sequence)

**"Standard sequence"** = alignment의 consensus:
- 각 position의 majority label
- MSA에서 conserved column을 뽑아냄

---

## 6. 새 비디오 Deviation Detection

학습된 process model M과 새 instance x에 대해:
```
fitness(x, M) ∈ [0, 1]
```
- 1.0 = 완벽히 M을 따름
- < 0.8 = 이상 → surgeon review

**Missing token analysis**:
- Alignment에서 "log에는 없지만 model에서 예상됨"인 transition = **누락된 필수 label**
- 정확히 사용자가 원한 "3이 빠졌다"를 알려줌

**Extra behavior**:
- 반대로 "log에 있으나 model에 없음" = 이례적 추가 행동

---

## 7. 실행 계획 (4-phase, 총 ~10주)

### Phase A — Data Pipeline (1-2주)
- [ ] BS-Segmentation-Tool JSON → **XES format** 변환 스크립트
  - XES = process mining 표준 event log format
  - `case_id = video_id`, `activity = label`, `timestamp = frame_no × fps`
- [ ] Task boundary 자동 검출:
  - **PELT** change-point detection on label vector time series
  - 또는 phase transition을 직접 boundary로 사용
- [ ] 각 task instance를 (label bag, label sequence) 두 형식으로 저장

### Phase B — Pilot Analysis (20-50 videos, 2-3주)
- [ ] Task clustering (K-Modes k=5~20)
- [ ] 각 cluster에 대해 support table 생성 → mandatory/optional 초안
- [ ] Frequent itemset mining (min_support=0.3)
- [ ] Sequence pattern mining (min_support=0.4, min_length=3)
- [ ] **Surgeon-in-the-loop**: 도출된 "mandatory core"가 임상적으로 맞는지 검증
- [ ] 이 단계에서 taxonomy 자체를 refine 할 수도 있음

### Phase C — Full-scale Mining (수백 videos, 4-6주)
- [ ] Inductive Miner로 각 task type별 process model 학습
- [ ] Confidence interval 좁히기 (N 증가로)
- [ ] Association rules (min_conf=0.8, min_lift=1.5)
- [ ] Cross-validation: 데이터 분할 후 mandatory core가 fold별로 일관되는지 확인
- [ ] 결과 → **Task Definition Catalog** (JSON/YAML)
  ```yaml
  task_type: "6번 LND"
  mandatory: [LND_6, RGEV_ligation]
  near_mandatory: [LND_3]  # support 0.87
  optional: [LND_5, LND_7]
  canonical_sequence: [LND_3, LND_6, RGEV_ligation, LND_7]
  n_instances: 214
  ```

### Phase D — Deployment & Monitoring (지속)
- [ ] Conformance API: 새 annotation 업로드 시 자동 fitness 계산
- [ ] Deviation queue: fitness < 0.8인 케이스는 second reviewer로 라우팅
- [ ] Concept drift 감시: 월별 mandatory core가 유의미하게 변하는지 tracking
- [ ] Model 재학습 주기 결정 (e.g. 3개월)

---

## 8. TMI 논문 방향과의 연결

기존 memory ([[research-direction-tmi]]) 기준으로:
- **Triplet grounding**: taxonomy set = (Verb=Phase, Instrument, Anatomy=Structure) triplet의 부분집합. Task type은 triplet 시퀀스의 canonical pattern.
- **Graph modality (Cholec)**: 여기서 학습한 DAG(canonical workflow)가 곧 graph supervision signal.
- **RAG Direction-2 transition gating**: canonical sequence의 next-state prior 분포가 곧 direction-2 gate의 target.

즉 이 mining pipeline의 산출물이 **TMI 논문의 graph/RAG modality를 supervise할 수 있는 라벨**을 자동 생성해줍니다.

---

## 9. 도구 stack

```
pip install pm4py mlxtend prefixspan hdbscan kmodes ruptures networkx biopython
```

| 목적 | 패키지 |
|---|---|
| Process mining (miner + conformance) | pm4py |
| Frequent itemset / association rules | mlxtend |
| Sequence pattern mining | prefixspan-py |
| Change-point detection | ruptures |
| Categorical clustering | kmodes, hdbscan |
| Sequence alignment | biopython |
| Graph ops (DAG, transitive reduction) | networkx |

---

## 10. 성공 지표

- [ ] Task type별 mandatory core가 surgeon review에서 ≥ 90% 승인
- [ ] Held-out 비디오 대해 fitness 평균 ≥ 0.85
- [ ] Deviation flag의 precision ≥ 0.7 (surgeon 검토 시 실제 이상)
- [ ] Task type 수와 taxonomy 커버리지 balance (너무 세분화 X, 너무 통합 X)

---

## 11. 흔한 함정

1. **Multi-label bag이라 순서 정보를 버리기 쉬움** — Phase B에서 반드시 sequence 형식도 병행 저장
2. **Rare task type이 mandatory core를 왜곡** — clustering 후 |C| ≥ 30 인 것만 정식 task type으로 채택
3. **Annotation noise가 곧 model noise로 이어짐** — pilot 단계에서 inter-annotator agreement (Cohen's κ ≥ 0.7) 먼저 확인
4. **Concept drift** — 술기 변화, surgeon 개인차. Surgeon ID를 covariate로 두고 stratified mining도 고려
5. **한 task instance ↔ 여러 task type 매핑** — soft clustering (GMM, LDA-style topic model) 고려
