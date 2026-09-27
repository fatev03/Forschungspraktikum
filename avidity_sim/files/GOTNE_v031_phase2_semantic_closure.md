# GOTNE v0.3.1 — Phase 2 Semantic Closure ve Implementation Contract

**Kapsam.** Bu doküman yalnızca iki semantik boşluğu kapatır (A: empty closure-pair
semantics, B: unengaged intervening module / physical path semantics), Phase 2
implementation sözleşmesini sabitler ve bir coding agent'a verilebilir implementation
prompt üretir. D6 / D8 / §18.2 / §20.5 / §20.6 / §10.7 kararları ve mevcut Phase 2
public API imzaları **değiştirilmemiştir**. Yeni probability API, kinetic API,
interval API, yeni `status_reason` ailesi veya yeni model parametresi
**eklenmemiştir**.

**Doğrulanan taban.** Aşağıdaki denetim, `gotne/` paketindeki fiilî kod okunarak
yapılmıştır: `cassette_schema.py`, `cassette_topology.py`, `status.py`,
`identity.py`, `mode_applicability.py` ve üç test modülü.

---

## 1. Phase 2 readiness audit

| # | Kontrol | Durum |
|---|---|---|
| 1 | Phase 1c purity contract fiilen tutuyor: `cassette_topology.py` geometri ve numerik hesap içermiyor, `math` / `numpy` / evaluation modülü import etmiyor. Phase 2 için temiz taban. | ✔ |
| 2 | Field pattern tek noktadan uygulanıyor: `apply_status_field_pattern` (§10.1 / §3.6) tek implementation ve `Status` dışı argümanı `TypeError` ile reddediyor. Phase 2 kendi zeroing/nulling mantığını yazmamalı, bu fonksiyona delege etmeli. | ✔ |
| 3 | `CANONICAL_VALUE_FIELDS` beş alanda sabit: `conditional_probability`, `effective_local_concentration`, `capture_integral`, `survival_correction`, `joint_score`. Phase 2 yeni canonical alan eklemez. | ✔ |
| 4 | Veto/unknown kümeleri Phase 2 semantiğiyle uyumlu: `VETO_SET = {INFEASIBLE, UNREACHABLE, BLOCKED}` → chain-closure veto `UNREACHABLE` ile `zeroed_due_to_status=True`; `UNKNOWN_SET = {DEGENERATE, NUMERIC_FAILURE, NOT_EVALUATED}` → `ENGAGED_POSE_UNDERDETERMINED` `DEGENERATE` ile `nulled_due_to_status=True`. Ayrıca `DENSITY_LIKE_FIELDS` veto altında null kalıyor. | ✔ |
| 5 | `EngagementOrderPolicy` üç değerle mevcut (`STRICT_PROXIMAL_TO_DISTAL`, `ANY_ORDER`, `EXPLICIT_PARTIAL_ORDER`). T83'ün iki varyantı için yeterli; yeni enum üyesi gerekmiyor. | ✔ |
| 6 | `UnresolvedUpstreamPolicy.EXCLUDED_SHELL_BOUND` mevcut ve Phase 1c'de D4 konfigürasyon kontrolü zaten çalışıyor (`cassette_topology.py`, per-module occupancy fraction kontrolü). Phase 2 bu politika altında yalnızca diagnostic üretecek. | ✔ |
| 7 | `Exactness.UNDEFINED` mevcut; başarılı Phase 2 `StateResult` için `exact_or_approximate=UNDEFINED` ifade edilebilir. | ✔ |
| 8 | `value_intervals` `EvaluationResult` üzerinde mevcut ve veto/unknown statülerinde dolu interval'ı reddeden bir invariant `__post_init__` içinde zaten var. Phase 2 bu alanı her durumda boş bırakacak; ek kod gerekmiyor. | ✔ |
| 9 | **BULGU — karar gerekli, kod bloker değil.** `vetoing_state_result_id` kod tabanında hiçbir yerde tanımlı değil. `EvaluationResult` frozen dataclass ve mevcut testlerin tamamı onun alan şeklini varsayıyor. **Çözüm (bu dokümanda sabitlenir):** yeni top-level alan açılmaz; taşıyıcı mevcut `upstream_state` mapping'i içindeki `"vetoing_state_result_id"` anahtarıdır. Bkz. §20.7.4 N7 ve §20.7.5 N10. | Kapatıldı |
| 10 | **BULGU — karar gerekli, kod bloker değil.** `status_reason` düz `str`; `CHAIN_CLOSURE_VIOLATED`, `ENGAGED_POSE_UNDERDETERMINED`, `ENGAGEMENT_ORDER_VIOLATION` literalleri kodda henüz tanımlı değil. **Çözüm:** Phase 2 bu üçünü ve yalnızca bu üçünü tek bir merkezî sabit kümesinde (`cassette_state.py` içinde modül düzeyi `Final[str]` sabitler) tanımlar, kümeyi genişletmez, yeni reason ailesi açmaz. | Kapatıldı |
| 11 | **BULGU — regression gate'i etkiler.** Belirtilen "46 test geçiyor" tabanı, klasördeki snapshot ile uyuşmuyor: toplanan 141, geçen 139 (`test_phase1c_closure` 63, `test_phase1c_remediation` 31, `test_cassette_topology` 45). İki hata mantık hatası değil, harness kaynaklı: `test_phase1c_remediation` hash-stability testi `<root>/gotne/` + `<root>/tests/` yerleşimini varsayıyor, klasör düz. Phase 2'ye başlamadan önce gerçek repo düzeninde `python -m pytest` çıktısı alınıp **kesin baseline sayısı** sabitlenmeli; "tüm mevcut testler geçmeye devam eder" gate'i bu sayıya bağlanır. | Aksiyon: baseline'ı repo düzeninde bir kez ölç |
| 12 | A ve B semantik boşlukları bu dokümanın §2'sinde normatif olarak kapatıldı; T79 ve T83 §3'te yeniden tanımlandı; Phase 2 modül/API/non-goal sınırı §4'te sabitlendi. | ✔ |

### Verdict

**READY FOR PHASE 2 IMPLEMENTATION.**

A ve B dışında semantik implementation blocker yok. Madde 9 ve 10 karar
boşluklarıydı ve bu dokümanda çözülerek kapatıldı; ikisi de mevcut public API'yi
veya `EvaluationResult` şeklini değiştirmiyor. Madde 11 bir ölçüm işidir, tasarım
işi değildir: gerçek repo düzeninde baseline test sayısı bir kez sabitlenmeli,
implementation onu beklemek zorunda değil ama regression gate'i onu referans
almalı.

---

## 2. §20.7'ye eklenecek normatif metin

Aşağıdaki iki alt bölüm §20.7'ye **eklenir**. §20.7'nin mevcut gövdesi
(sequential engagement semantics, conditional reachability, order-policy
tanımları) değişmez. Tek istisna §20.7.3'e eklenen açıklayıcı N0 cümlesidir.

### §20.7.3 ek — VALID'in kapsamı (açıklayıcı ekleme)

> **N0.** Phase 2'de `evaluate_state` tarafından döndürülen `VALID` statüsü
> tam olarak şunu ifade eder: *the caller-supplied state passed Phase 1c
> configuration validation, state-schema validation, L2 admissibility, and all
> applicable Phase 2 deterministic veto checks.* `VALID` **MUST NOT** be read as
> observed engagement, binding success, binding probability, affinity, target
> occupancy, simultaneous occupancy, temporal persistence, kinetic accessibility
> veya herhangi bir olasılık iddiası olarak. Bu okuma yasağı, closure-pair
> setinin boş olduğu durumlar da dahil olmak üzere her `VALID` sonuç için
> geçerlidir.

---

### §20.7.4 (yeni) Empty closure-pair sets

**Tanım.** `S` admissible bir engagement state olsun. `ENGAGED(S)` state
içinde `ENGAGED` olarak deklare edilen modüllerin kümesi, `P(S)` ise §20.7'nin
consecutive-engaged-pair kuralıyla türetilen closure-pair setidir: iki modül
`D_i` ve `D_j` (`i < j`) bir pair oluşturur ancak ve ancak ikisi de `ENGAGED`
ise ve aralarında başka hiçbir `ENGAGED` modül yoksa. `|ENGAGED(S)| ≤ 1`
olduğunda `P(S) = ∅` olur; `P(S) = ∅` başka yapısal konfigürasyonlarda da
ortaya çıkabilir ve bu bölüm tüm bu durumları kapsar.

> **N1.** An empty closure-pair set `P(S) = ∅` **MUST NOT** be treated as a
> closure failure. Boşluk, closure sweep'in sonucu değil, sweep'in üzerinde
> çalışacağı domain'in boş olmasıdır.
>
> **N2.** `evaluate_state` **MUST** complete the closure sweep successfully when
> `P(S) = ∅`. Implementation **MUST NOT** synthesize a closure result, a
> surrogate pair, a self-pair `(D_i, D_i)`, an anchor-to-module pair, or any new
> geometric predicate in order to give the sweep something to evaluate.
> `chain_closure_feasible` **MUST NOT** be invoked at all in this case.
>
> **N3.** Where the Phase 2 contract returns `VALID` for such a state, `VALID`
> carries exactly the scope fixed in §20.7.3 N0 and nothing further. In
> particular it **MUST NOT** be reported, logged, or documented as evidence of
> observed engagement, binding success, target occupancy, simultaneous
> occupancy, temporal persistence, or probability.
>
> **N4.** The result diagnostics **MUST** contain `closure_pairs` explicitly, with
> the value `[]`. The record **MUST** allow a reader to distinguish
> *"the pair set was empty, therefore the sweep had no work"* from
> *"the sweep did not run"*. Buna göre implementation **MUST** emit an `INFO`
> severity `DiagnosticRecord` whose `quantities` include `closure_pairs: []`
> and `closure_predicate_invocations: 0`, and whose message states that the
> sweep executed over an empty domain. Absence of the `closure_pairs` key
> **MUST NOT** be used to encode either meaning.
>
> **N5.** With `P(S) = ∅`, the five canonical prediction fields
> (`conditional_probability`, `effective_local_concentration`,
> `capture_integral`, `survival_correction`, `joint_score`) **MUST** be typed
> null, `value_intervals` **MUST** be empty, `exact_or_approximate` **MUST** be
> `UNDEFINED`, and both `zeroed_due_to_status` and `nulled_due_to_status`
> **MUST** be `false`. Bu kalıp §10.1 / §3.6'nın mevcut mekanizmasıyla, yani
> `apply_status_field_pattern(Status.VALID)` çağrısıyla üretilir; Phase 2
> **MUST NOT** kendi zeroing/nulling dalını yazmaz.
>
> **N6.** Phase 2 **MUST NOT** import or invoke any Phase 4 or Phase 5 module
> while handling an empty closure-pair set, and **MUST NOT** emit a
> `SHELL_BOUND` reason, a `BOUND_ONLY` provenance label, an at-risk weight, or a
> probability interval.
>
> **N7.** An empty closure-pair set produces no veto, therefore no
> `vetoing_state_result_id` is attached. When a veto *is* produced elsewhere in
> Phase 2, its identifier **MUST** be carried in the existing `upstream_state`
> mapping under the key `vetoing_state_result_id`; Phase 2 **MUST NOT** add a new
> top-level field to `EvaluationResult` for this purpose.

---

### §20.7.5 (yeni) Unengaged intervening modules and physical path membership

**Tanım.** `S = {D1@T1, D3@T3}` olsun, `D2` aynı lineer cassette üzerinde
`D1` ile `D3` arasında yer alsın ve `S` içinde `ENGAGED` olarak deklare
edilmemiş olsun. Bu bölüm bu sınıfın tamamını normatifleştirir.

> **N8.** Pair selection **MUST** draw only from `ENGAGED(S)`. For this state the
> closure-pair set **MUST** be exactly `[(D1, D3)]`. `D2`'nin unengaged olması
> pair seçimini etkilemez ve ara bir pair üretmez.
>
> **N9.** The unengaged status of an intervening module **MUST NOT** remove any
> element of the physical cassette path between the two paired modules from the
> contour budget. Engagement bir conditioning deklarasyonudur; polimer varlığını
> ortadan kaldırmaz. Bir modülün `ENGAGED` olmaması, onu taşıyan segment,
> spacer ve capture-offset elemanlarının fiziksel olarak yok olduğu anlamına
> **gelmez**.
>
> **N10.** §18.2 contour budget **MUST** be computed over the full element set
> `E(k, j)` on the physical path between the shielding ancestor `k` and the
> downstream engaged module `j`: every flexible segment, every rigid spacer, and
> the terminal capture offset on that path, exactly as §18.2 defines them, with
> no element omitted on engagement grounds. `cassette_contour_budget`'in
> element listesi engagement state'e göre **MUST NOT** daralt.
>
> **N11.** `unresolved_upstream_ids` **MUST NOT** be interpreted as a
> contour-budget element list and **MUST NOT** alter physical-path membership.
> İki liste farklı türdendir: biri diagnostic bağlam, diğeri geometrik budget
> domain'i. Implementation **MUST NOT** derive one from the other.
>
> **N12.** `unresolved_upstream_ids` **MUST** carry exactly one meaning: those
> intervening bodies which, in the downstream evaluation context, remain
> unresolved with respect to pose or occupancy. It is diagnostic context only.
>
> **N13.** In Phase 2 this diagnostic **MUST NOT** be converted into an obstacle
> term, a survival correction, a density, a probability, an interval, or a
> shell-bound quantity. Phase 2 **MUST NOT** attach any numeric weight to it.
>
> **N14.** Under `UnresolvedUpstreamPolicy.EXCLUDED_SHELL_BOUND`, Phase 2 **MAY**
> report exactly the following three diagnostic quantities and **MUST NOT**
> report more:
> - `unresolved_upstream_ids` — the identifiers of the unresolved intervening
>   bodies, e.g. `["D2"]`;
> - `unresolved_upstream_policy` — the declared policy, `EXCLUDED_SHELL_BOUND`;
> - `downstream_numerical_evaluation_deferred` — `true`.
>
> **N15.** Phase 2 **MUST NOT** produce a `SHELL_BOUND` status reason, a
> `BOUND_ONLY` provenance label, an at-risk weight, or any `value_intervals`
> entry. These belong to Phase 5 exclusively. Phase 2'nin
> `EXCLUDED_SHELL_BOUND` altındaki tek çıktısı N14'teki üç anahtar ve
> `downstream_numerical_evaluation_deferred=true` bayrağıdır.
>
> **N16.** Under `EngagementOrderPolicy.STRICT_PROXIMAL_TO_DISTAL`, the state
> `S = {D1@T1, D3@T3}` is not down-closed under
> `R_union = R_policy ∪ R_requires`, therefore per §20.7 it **MUST** yield
> `ENGAGEMENT_ORDER_VIOLATION` and the closure sweep **MUST NOT** run.
> `chain_closure_feasible` **MUST NOT** be invoked, `cassette_contour_budget`
> **MUST NOT** be invoked, and no closure-pair set is produced. Order-admissibility
> her zaman closure'dan önce gelir.
>
> **N17.** A geometric closure-feasible outcome for `(D1, D3)` **MUST NOT** be
> read as binding probability, successful binding, affinity, kinetic
> persistence, or an assertion of genuine simultaneous occupancy of `T1` and
> `T3`. It asserts only that the declared conditioning is not vetoed by the
> deterministic closure predicate under the declared configuration.

---

## 3. Revize test tanımları

Her iki test de `tests/test_phase2_state.py` içine yazılır. İkisi de
`unittest` stilinde, mevcut fixture yaklaşımıyla (`base_policy`, `replace`)
uyumludur ve Phase 4/5 modüllerini import etmez.

### T79 — Empty closure-pair set yields a successful, numerically empty state result

**Amaç.** `P(S) = ∅` durumunda closure sweep'in başarıyla tamamlandığını,
hiçbir geometric predicate çağrılmadığını ve sonucun sayısal olarak tamamen
boş olduğunu kanıtlamak. §20.7.4 N1–N6.

**Fixture.** Üç modüllü (`D1`, `D2`, `D3`) geçerli `LINEAR_ORDERED_CASSETTE`
konfigürasyonu. State: `S = {D1@T1}` — yalnızca bir `ENGAGED` modül.
Policy: `EngagementOrderPolicy.ANY_ORDER`. `S` L2-admissible olmalı.

**Enstrümantasyon.** `chain_closure_feasible` bir call-counting spy ile
sarılır. Spy, fonksiyonun hem çağrılarını hem de — F2/F16 sınıfı
silent-failure'lara karşı — herhangi bir geometri nesnesinin kurulumunu
sayar. Sıfır çağrı beklenir.

**Assertion listesi.**

1. `result.status is Status.VALID`.
2. `closure_pairs` diagnostic'i **mevcut** ve değeri tam olarak `[]`
   (anahtarın yokluğu kabul edilmez; `assertIn("closure_pairs", quantities)`
   ayrı bir assertion olarak yazılır).
3. `closure_predicate_invocations == 0` diagnostic'te raporlanır **ve** spy
   sayacı `0`.
4. Closure predicate hiç çağrılmadı: `spy.call_count == 0` ve
   `spy.construction_count == 0`.
5. Beş canonical prediction field'ın hepsi `None`:
   `conditional_probability`, `effective_local_concentration`,
   `capture_integral`, `survival_correction`, `joint_score`.
6. `dict(result.value_intervals) == {}`.
7. `result.exact_or_approximate is Exactness.UNDEFINED`.
8. `result.zeroed_due_to_status is False`.
9. `result.nulled_due_to_status is False`.
10. `result.upstream_state` içinde `vetoing_state_result_id` **yok** (veto
    üretilmedi).
11. Phase 4/5 çağrısı yok: test süresince `sys.modules` içine
    `composite_density`, `so3_grids`, `pose_marginalization`, `shell_bounds`,
    `intervals` modüllerinden hiçbiri girmedi.
12. `status_reason` bir failure reason değil; `CHAIN_CLOSURE_VIOLATED`,
    `ENGAGEMENT_ORDER_VIOLATION`, `ENGAGED_POSE_UNDERDETERMINED`
    literallerinden hiçbirine eşit değil.

**Negatif kontrol (aynı test sınıfında ayrı method).** Sentetik closure
üretimini yakalamak için: diagnostic'lerde `closure_pairs` uzunluğu `0`'dan
farklı hiçbir kayıt bulunmaz ve hiçbir diagnostic `SHELL_BOUND` veya
`BOUND_ONLY` içermez.

---

### T83 — Unengaged intervening module preserves contour-budget path membership

**Amaç.** `D2`'nin unengaged olmasının closure-pair seçimini `(D1, D3)`
olarak bıraktığını, contour budget'in fiziksel path elemanlarını
**kaybetmediğini** ve diagnostic'in numerik bir şeye dönüşmediğini
kanıtlamak. §20.7.5 N8–N17.

**Fixture.** Üç modüllü lineer cassette: `D1 — σ1 — D2 — σ2 — D3`, aralarda
tanımlı rigid spacer'lar ve `D3` için bir terminal capture offset.
State: `S = {D1@T1, D3@T3}`, `D2` unengaged.
Policy A: `EngagementOrderPolicy.ANY_ORDER`,
`UnresolvedUpstreamPolicy.EXCLUDED_SHELL_BOUND`.
Policy B: aynı konfigürasyon, `EngagementOrderPolicy.STRICT_PROXIMAL_TO_DISTAL`.

**Assertion listesi — Policy A (`ANY_ORDER`).**

1. `closure_pairs == [("D1", "D3")]` — tam eşitlik, ara pair yok, self-pair yok.
2. `unresolved_upstream_ids == ["D2"]`.
3. `unresolved_upstream_policy == "EXCLUDED_SHELL_BOUND"`.
4. `downstream_numerical_evaluation_deferred is True`.
5. **Path membership korunuyor.** *(Corrected by decision record rev. 3,
   amendment A1; AP-18 and N10 unchanged.)* In `S` the shielding ancestor of
   `D3` is `D1`, and `contour_budget_breakdown` lists the full physical path
   `D1 → D3`: `σ1`, the span of `D2`, `σ2` and the capture offset of `D3`. The
   unengaged status of `D2` removes none of them. The reference comparison uses
   a control state that selects the **same** ancestor for `D3` (for example
   `D2` declared explicitly `UNENGAGED`), and the two element id sets are
   asserted **equal**. A control state with `D2` `ENGAGED` makes `D2` the
   ancestor of `D3` (AP-18), so the path and its element ids change; no
   equality is required across states that select different ancestors.
6. `unresolved_upstream_ids` ile `contour_budget_breakdown` element listesi
   ayrı nesnelerdir: `D2`'nin `unresolved_upstream_ids` içinde olması
   breakdown'dan çıkarılmasına yol açmaz (5'in doğrudan sonucu, ayrı assertion
   olarak yazılır).
7. Phase 4/5 import/call yok: `sys.modules` kontrolü, T79 madde 11 ile aynı
   modül listesi üzerinden.
8. `dict(result.value_intervals) == {}` — hiçbir interval üretilmedi.
9. Hiçbir diagnostic `SHELL_BOUND` reason içermez; `result.status_reason` da
   `SHELL_BOUND` değildir.
10. Provenance etiketleri arasında `BOUND_ONLY` yok.
11. `D2` için hiçbir at-risk weight, occupancy fraction, survival veya obstacle
    sayısal değeri raporlanmadı: diagnostic `quantities` içinde `D2` ile
    ilişkili tek kayıt N14'teki üç anahtardır. *(Decision record rev. 3,
    amendment A2: this excludes only Phase-5-style downstream numeric records;
    span-accounting and path-membership records such as budget elements and
    `DERIVED_RIGID_SPAN` element ids are permitted.)*

**Assertion listesi — Policy B (`STRICT_PROXIMAL_TO_DISTAL`).**

12. `result.status_reason == "ENGAGEMENT_ORDER_VIOLATION"`.
13. Closure predicate'e girilmedi: `chain_closure_feasible` spy sayacı `0`.
14. `cassette_contour_budget` spy sayacı `0` — order violation budget
    hesabından önce gelir.
15. `closure_pairs` diagnostic'i ya hiç yok ya da `CHECK_SKIPPED` olarak
    işaretli; sentetik bir pair listesi üretilmedi.
16. Field pattern §10.1'e uygun: status veto/unknown sınıfına göre
    `zeroed_due_to_status` / `nulled_due_to_status` bayrakları
    `apply_status_field_pattern` çıktısıyla birebir tutarlı.

---

## 4. Final Phase 2 implementation contract

### 4.1 Yazılacak modüller

Mevcut paket adlandırma konvansiyonu snake_case'dir (`cassette_schema.py`,
`cassette_topology.py`, `mode_applicability.py`). Phase 2 modül adları buna
göre normalize edilir:

| Modül | Sorumluluk |
|---|---|
| `gotne/cassette_frames.py` | Effective-anchor propagation: modül referans çerçevelerinin state'e göre türetilmesi. |
| `gotne/cassette_budget.py` | §18.2 contour budget: shielding ancestor ile downstream engaged modül arasındaki fiziksel path element seti ve span aritmetiği. |
| `gotne/cassette_state.py` | State schema, L2 admissibility, down-closure kontrolü, `ENGAGEMENT_ORDER_VIOLATION`, reason sabitleri, `StateResult` / `StateCertificate` üretimi. |
| `gotne/closure.py` | Consecutive-engaged-pair seçimi ve deterministic chain-closure veto predicate'i. |
| `gotne/evaluate_node.py` | State certificate altında node düzeyi değerlendirme ve veto propagation. |

### 4.2 Mevcut public API imzaları (değiştirilmez)

```python
cassette_effective_anchor(module_id, state, cfg)
cassette_contour_budget(module_id, state, cfg)
chain_closure_feasible(i, j, state, cfg, policy)
evaluate_state(state, cfg, policy)
evaluate_node(node_id, state_certificate, cfg, policy)
```

Bu beş imza sabittir. Parametre eklenmez, çıkarılmaz, yeniden sıralanmaz,
keyword-only'ye çevrilmez. Dönüş tipleri mevcut `EvaluationResult` /
`StateResult` / `StateCertificate` sözleşmesine bağlıdır.

### 4.3 Phase 2 kapsamı

Phase 2 **yalnızca** şu katmandır: state admissibility, effective-anchor
propagation, contour budget, shielding ancestor, unresolved-upstream
diagnostics, deterministic chain-closure veto.

### 4.4 Kesin non-goals

Phase 2 **üretmez**: probability, density, capture integral, local
concentration, survival correction, pose marginalization, shell-bound
interval, kinetics, at-risk weight, `SHELL_BOUND` reason, `BOUND_ONLY`
provenance, herhangi bir `value_intervals` girdisi.

Composite density ve pose marginalization Phase 4'e, shell-bound /
obstacle-aware interval Phase 5'e aittir.

### 4.5 Yasak importlar

Phase 2 kodu ve Phase 2 testleri aşağıdaki modülleri **import etmez ve
invoke etmez**:

```
gotne/composite_density.py
gotne/so3_grids.py
gotne/pose_marginalization.py
gotne/shell_bounds.py
gotne/intervals.py
```

### 4.6 Zorunlu import-boundary testi

`tests/test_phase2_import_boundary.py` yazılır ve iki şeyi ayrı ayrı kanıtlar:

1. **Statik.** Beş Phase 2 modülünün kaynağı `ast` ile parse edilir; hiçbir
   `Import` / `ImportFrom` düğümü yasak modül adlarından birine işaret
   etmez. Dolaylı yol da kapatılır: transitive olarak import edilen
   `gotne.*` modüllerinin import kapanışı da taranır.
2. **Dinamik.** `evaluate_state` ve `evaluate_node` temiz bir interpreter
   durumunda çalıştırılır; çağrı sonrası `sys.modules` içinde yasak modül
   adlarının hiçbiri bulunmaz. Ayrıca yasak adlar için `sys.meta_path`'e
   yerleştirilen bir tuzak finder, herhangi bir import denemesinde testi
   düşürür.

---

## 5. PHASE 2 IMPLEMENTATION PROMPT

```text
PHASE 2 IMPLEMENTATION PROMPT

Bağlam. GOTNE v0.3.1 Python paketi (gotne/) üzerinde çalışıyorsun. Phase 1c
tamamlandı: schema, policy, topology ve order-constraint validation uygulandı
ve mevcut test suite geçiyor. Phase 2 henüz uygulanmadı. Bu proje bir
hesaplamalı yapısal biyoloji modeli: lineer, çok-domainli tethered bir
assembly'nin hedef bölgelere geometrik olarak ulaşabilirliğini deterministik
biçimde doğrulayan bir katman.

İLK ADIM — KOD YAZMA. Önce kısa bir implementation planı sun: modül bazında
hangi fonksiyonu hangi sırayla yazacağın, veri akışı, ve mevcut
apply_status_field_pattern / EvaluationResult sözleşmesine nasıl bağlanacağın.
Planı onay için ver. Onay gelmeden tek satır kod yazma.

TESLİM BİÇİMİ. Tüm değişiklikler incremental patch olarak gelir. Dosyaları
baştan yazma; mevcut dosyalara dokunuyorsan minimal diff üret. Her patch tek
başına uygulanabilir ve test edilebilir olmalı.

YAZILACAK MODÜLLER
  gotne/cassette_frames.py   effective-anchor propagation
  gotne/cassette_budget.py   §18.2 contour budget
  gotne/cassette_state.py    state schema, L2 admissibility, down-closure,
                             reason sabitleri, StateResult / StateCertificate
  gotne/closure.py           consecutive-engaged-pair seçimi + chain-closure
                             veto predicate
  gotne/evaluate_node.py     node düzeyi değerlendirme + veto propagation

DEĞİŞTİRİLMEYECEK PUBLIC API İMZALARI
  cassette_effective_anchor(module_id, state, cfg)
  cassette_contour_budget(module_id, state, cfg)
  chain_closure_feasible(i, j, state, cfg, policy)
  evaluate_state(state, cfg, policy)
  evaluate_node(node_id, state_certificate, cfg, policy)
Parametre ekleme, çıkarma, yeniden sıralama veya keyword-only'ye çevirme yok.

KAPSAM. Phase 2 yalnızca şudur: state admissibility, effective-anchor
propagation, contour budget, shielding ancestor, unresolved-upstream
diagnostics, deterministic chain-closure veto.

NON-GOALS. Phase 2 üretmez: probability, density, capture integral, local
concentration, survival correction, pose marginalization, shell-bound
interval, kinetics, at-risk weight, SHELL_BOUND reason, BOUND_ONLY provenance,
herhangi bir value_intervals girdisi. Yeni probability/kinetic/interval API,
yeni status_reason ailesi veya yeni model parametresi eklemeyeceksin.

YASAK IMPORTLAR. Phase 2 kodu ve testleri şunları import veya invoke etmez:
gotne/composite_density.py, gotne/so3_grids.py,
gotne/pose_marginalization.py, gotne/shell_bounds.py, gotne/intervals.py

KORUNACAK SEMANTİK KARARLAR
- Engagement state caller-supplied bir conditioning deklarasyonudur. Model
  state üretmez, tamir etmez, completion yapmaz, target reassignment yapmaz.
- Engagement order temporal veya kinetic bir sıra değildir.
- State, R_union = R_policy ∪ R_requires altında down-closed değilse
  ENGAGEMENT_ORDER_VIOLATION olur ve closure sweep hiç çalışmaz.
- Closure yalnızca consecutive engaged pair'ler için çalışır: iki modül
  ENGAGED ve aralarında başka ENGAGED modül yoksa pair oluşturur.
- Chain closure failure, UNREACHABLE / CHAIN_CLOSURE_VIOLATED ile StateResult
  veto üretir ve downstream sonuçlara yayılır. Veto kimliği yeni bir
  top-level alan açılmadan, mevcut upstream_state mapping'i içinde
  "vetoing_state_result_id" anahtarıyla taşınır.
- Geometric closure-feasible sonucu binding probability, successful binding,
  affinity, kinetic persistence veya gerçek eşzamanlı occupancy iddiası
  değildir.
- Undetermined engaged pose Phase 2'de marginalize edilmez:
  DEGENERATE / ENGAGED_POSE_UNDERDETERMINED olur ve StateCertificate
  üretilmez.
- Başarılı StateResult'ta beş canonical prediction field (
  conditional_probability, effective_local_concentration, capture_integral,
  survival_correction, joint_score) null, exact_or_approximate UNDEFINED,
  zeroed_due_to_status ve nulled_due_to_status false olmalıdır. Veto/unknown
  kalıpları mevcut §10.1 / §3.6 mekanizmasıyla, yani
  apply_status_field_pattern üzerinden uygulanır; kendi zeroing/nulling
  dalını yazmayacaksın.
- EXCLUDED_SHELL_BOUND altında Phase 2 yalnızca üç diagnostic anahtar
  raporlar: unresolved_upstream_ids, unresolved_upstream_policy,
  downstream_numerical_evaluation_deferred.
- CHAIN_CLOSURE_VIOLATED, ENGAGED_POSE_UNDERDETERMINED ve
  ENGAGEMENT_ORDER_VIOLATION literalleri cassette_state.py içinde tek
  merkezî sabit kümesi olarak tanımlanır; bu küme genişletilmez.

İKİ NORMATİF SEMANTİK KURAL (yeni kapatıldı)
A. Empty closure-pair semantics. Closure-pair seti boş olan admissible bir
   state (örn. S = {D1@T1}) closure failure DEĞİLDİR. Sweep başarıyla
   tamamlanır, yeni geometric predicate veya sentetik closure sonucu
   üretilmez, chain_closure_feasible hiç çağrılmaz. Diagnostic'te
   closure_pairs=[] ve closure_predicate_invocations=0 explicit olarak yer
   alır; "pair yoktu" ile "sweep çalışmadı" ayrışır. Bu durumda dönen VALID
   yalnızca şunu ifade eder: the caller-supplied state passed Phase 1c
   configuration validation, state-schema validation, L2 admissibility, and
   all applicable Phase 2 deterministic veto checks. VALID observed
   engagement, binding success, target occupancy, temporal persistence veya
   probability iddiası DEĞİLDİR.
B. Unengaged intervening module semantics. S = {D1@T1, D3@T3} ve D2
   unengaged iken closure pair (D1, D3)'tür. D2'nin unengaged olması,
   D1–D3 arasındaki fiziksel cassette path'in segment, spacer ve
   capture-offset elemanlarını contour budget'dan ÇIKARMAZ. §18.2 budget,
   shielding ancestor ile downstream engaged modül arasındaki fiziksel path
   üzerindeki tüm bu elemanları kullanır. unresolved_upstream_ids bir
   contour-budget element listesi DEĞİLDİR ve physical-path membership'i
   değiştiremez; yalnızca downstream evaluation context'inde pose/occupancy
   yönünden çözülmemiş intervening body'ler için diagnostic bağlamdır ve
   Phase 2'de obstacle/survival/density/probability/interval/shell-bound
   hesabına dönüşmez. STRICT_PROXIMAL_TO_DISTAL altında aynı state
   ENGAGEMENT_ORDER_VIOLATION verir ve closure predicate'e hiç girilmez.

TESTLER
1. Mevcut testlerin TAMAMI geçmeye devam etmeli. Başlamadan önce baseline'ı
   ölç (python -m pytest ile toplanan ve geçen test sayısını raporla) ve her
   patch sonrası bu sayının düşmediğini göster. Mevcut bir testi
   değiştirmen gerekiyorsa önce gerekçesini sun ve onay al.
2. Phase 2 testleri eklenecek: tests/test_phase2_state.py içinde, bu
   dokümandaki T79 ve T83 tanımlarının tüm assertion'ları dahil olmak üzere.
   T79 closure predicate'in hiç çağrılmadığını bir spy ile kanıtlamalı.
   T83 contour_budget_breakdown'ın element kimlik kümesini, aynı shielding
   ancestor'ı seçen bir kontrol state'iyle (ör. D2 açıkça UNENGAGED)
   karşılaştırarak eşit olduğunu kanıtlamalı. D2'nin ENGAGED olduğu state
   D3'ün ancestor'ını D2 yapar (AP-18); bu durumda eşitlik aranmaz.
3. Import boundary testi ZORUNLU: tests/test_phase2_import_boundary.py.
   Statik olarak ast ile beş Phase 2 modülünün (ve transitive gotne.* import
   kapanışının) yasak modüllere referans vermediğini; dinamik olarak
   evaluate_state ve evaluate_node çağrısı sonrası sys.modules'ta yasak
   modül bulunmadığını ve sys.meta_path'e konan bir tuzak finder'ın hiç
   tetiklenmediğini kanıtla.

ÇALIŞMA DÜZENİ
- Saflık: Phase 2 modülleri deterministik olmalı; rastgelelik, global
  mutable state veya import-time yan etki yok.
- Her patch'ten sonra testleri çalıştır ve çıktıyı göster.
- Bir karar belirsizse uydurma: sor. Spesifikasyonu yeniden tasarlama,
  yukarıdaki kararların hiçbirini "iyileştirme" adına değiştirme.
```
