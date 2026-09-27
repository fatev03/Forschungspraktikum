# Phase 2 — AF3-ReD external conformer adapter, v0.2

Bu değişiklik yalnızca **external conformer inventory / admission prep** yapar.
AF3-ReD bir external structure source olarak ele alınır. Adapter inference,
ranking, binder üretimi veya core-derived alan üretimi yapmaz.
Strict reader (`structures.py`), kaynak repo ve core sözleşmeleri değiştirilmedi.
External adapter/notebook'a açık `af3_native_v1` profili eklendi.

## Proposed notebook cells

Hazır Colab notebook: [af3_red_colab.ipynb](../examples/af3_red_colab.ipynb).
Python 3.10+ ve standart kütüphane yeterlidir; kurulum hücresi yoktur.

| Sıra | Hücre | İşlev |
|---|---|---|
| 1 | Records / helpers | `AF3ReDRunIdentity`, `StructureArtifact`, salt-okuma ve SHA-256 |
| 2 | Run discovery | `discover_red_runs(output_root)` |
| 3 | Structure inventory | `discover_structure_files(run)` |
| 4 | Readiness gate | `validate_basic_mapping_readiness(..., profile="strict")` |
| 5 | Manifest | `build_red_manifest(..., profile="strict")`; yalnızca bellekte |
| 6 | Native bridge | Ayrı, standart kütüphaneli `AF3NativeCIF` reader hücresi |
| 7 | `targets = [...]` | Üç reseptörün açık input paneli ve `READER_PROFILE` seçimi |
| 8 | Inventory | Önce binding olmadan inceleme |
| 9 | Explicit mapping preparation | Seçilen profile özgü açık binding |
| 10 | Checklist | Manifest kapsamı ve statü kontrolleri |

İlk beş hücre modülle birebir aynıdır; notebook parite testi bunu doğrular.
Altıncı hücre [af3_native_bridge.py](../src/structure_audit/af3_native_bridge.py)
ile birebir aynıdır. İlk altı hücrenin çalıştırılması dosya açmaz. Panel yolları `None` iken
notebook'un tamamı input dosyası okumadan çalışır.

## First implementation block

Tam implementasyon: [af3_red_adapter.py](../src/structure_audit/af3_red_adapter.py).
Dosyadaki `# %%` işaretleri beş yardımcı hücrenin sınırlarıdır. Paket kurmadan
bu hücreleri notebook'a yapıştırmak yeterlidir. Proje `src` dizini zaten Python
import yolundaysa eşdeğer kullanım:

```python
from structure_audit.af3_red_adapter import (
    AF3ReDRunIdentity, StructureArtifact,
    discover_red_runs, discover_structure_files,
    build_red_manifest, validate_basic_mapping_readiness,
)

# Mevcut gerçek output dizinini belirtin; bu bir assumed schema yoludur.
output_root = "/content/af_output"
manifest = build_red_manifest(output_root)
for artifact in manifest["artifacts"]:
    print(artifact["path"], artifact["status"], artifact["reasons"])
```

Minimal mimari:

- `AF3ReDRunIdentity`: kanonik run dizini, input JSON/hash, sanitized job name,
  seed listesi, input ligand beyanları, nullable sigma/weight, kaynak beyanı ve
  provenance. Run adı reseptör kimliği değildir. Kimlik hash'i dizin ve input
  byte hash'ine bağlıdır; klasörü taşımak yerel run ID'sini değiştirir.
- `StructureArtifact`: run ID, kanonik dosya yolu/hash, format, dosya rolü,
  nullable seed/sample, statü, gerekçeler, açık binding ve `read_provenance`.
- `discover_red_runs`: yalnızca tek `*_data.json` ile belirlenen dizinler;
  AF3 input dialect/version ve metadata kontrolleri. Genel bir CIF taramasından
  run kimliği uydurmaz. Çıktısız data-pipeline run'ı görülebilir.
- `discover_structure_files`: `.cif`, `.mmcif`, `.pdb` envanteri; bu uzantıların
  `.gz` biçimleri görünür ancak reddedilir. Sıkıştırma açılmaz, dönüştürme yapılmaz.
- `build_red_manifest`: deterministic, JSON uyumlu, ayrı
  `af3red_external_inventory/0.2` sözleşmesi; core `run_manifest` değildir.
  Eklenen `reader_profile` ve artifact `read_provenance` nedeniyle external sürüm
  artırıldı; input sidecar şeması `0.1` olarak kaldı.
  Hiçbir manifest dosyası yazmaz. SHA-256, `manifest_sha256` alanı hariç sorted,
  compact, UTF-8 JSON üzerinde hesaplanır; `ensure_ascii=False`, `allow_nan=False`.
- `validate_basic_mapping_readiness`: dosya/hash/model ve profile göre açık ATOM
  author-chain/segment veya author/label-chain varlığı; duplicate kimlik, nonfinite koordinat ve altloc
  belirsizliğini reddeder. Koordinatlardan geometri metrikleri hesaplamaz.

Strict profil ön kabulü yalnızca incelemeyle sağlanan binding üzerinden yapılır:

```python
bindings = {
    "<inventory artifact_id>": {
        "artifact_sha256": "<exact file SHA-256>",
        "target_id": "<explicit receptor ID>",
        "model_id": "<structure model ID>",
        "auth_chain_id": "<author chain ID>",
        "segment": 0,
    }
}
# Proje okuyucusu zaten erişilebiliyorsa:
from structure_audit.structures import read_structure
prepared = build_red_manifest(output_root, bindings=bindings, reader=read_structure)
```

Bu örnek placeholder'lar doldurulmadan çalıştırılmaz. `reader` güvenilen yerel
bir fonksiyondur ve mevcut `read_structure` API'sini uygulamalıdır; dinamik
modül indirme, otomatik parser seçme veya fallback yoktur. Parser callback'i
verilmemesi strict inventory kullanımını engellemez, strict admission'ı engeller.

### Açık AF3-native profil seçimi

Her iki public fonksiyona yalnızca bir keyword eklendi: `profile="strict"`.
Bu ek, native namespace sözleşmesini strict callback sözleşmesinden ayırır.
Varsayılan strict yol korunur. `profile="af3_native_v1"` sabit bridge reader'ı
seçer ve `reader=None` gerektirir; otomatik algılama/fallback yoktur. Native
reader'ı `reader=` callback olarak geçirmek konfigürasyon hatasıdır. Bilinmeyen
profil veya karışık callback/profil seçimi hiçbir input okunmadan `ValueError`
üretir. Diğer run, artifact ve statü kontrolleri korunur.

```python
native_bindings = {
    "<inventory artifact_id>": {
        "artifact_sha256": "<exact file SHA-256>",
        "target_id": "<explicit receptor ID>",
        "model_id": "<explicit CIF model ID>",
        "auth_asym_id": "<explicit author chain ID>",
        "label_asym_id": "<explicit label chain ID>",
    }
}
prepared = build_red_manifest(
    output_root, bindings=native_bindings, profile="af3_native_v1")
```

Native binding'de `segment` bulunmaz; strict binding alanları native yolda
reddedilir. Bir manifest çağrısı tek profil kullanır; farklı profiller ayrı
çağrılarla değerlendirilir. Notebook'ta aynı seçim `READER_PROFILE` üzerinden
yapılır; bridge hücresi çalıştırılmadan native okuma istenirse kabul verilmez.

Standalone `read_af3_native_cif(path, model_id="...")`, strict `Structure`
yerine `AF3NativeCIF` döndürür. `rows[].fields` yalnızca mevcut `_atom_site.*`
tag'lerini içerir. Tag anahtarları CIF'in case-insensitive kuralına göre küçük
harfe çevrilir; orijinal kolon adları/sırası `columns` içinde saklanır. Alan
değerleri string token olarak korunur; satır konumları ve quoted alanlar ayrı
tutulur. Placeholder `.` ile `?` satır çıktısında ayrıdır. Eksik alanlar için
değer eklenmez. Sayısal/placeholder yorumlama sadece kontrollerin içinde yapılır.

Native v1: bir named CIF 1.1 data block, bir atom-site loop; author atom/component
alanlarının ikisi de yok; model numarası, author/label chain ve author residue
kimliği açıkça mevcut olmalıdır. Her modelde chain ilişkileri ve dosyada gözlenen
residue kimlikleri tek anlamlı olmalıdır. Bu kontrol sequence correspondence
üretmez. HETATM satırları korunur, label_seq_id eksikliği doldurulmaz; HETATM
zinciri target ATOM binding olarak kabul edilmez. Reader tüm modellerin satırlarını
kontrol ettikten sonra yalnızca açıkça seçilen modelin satırlarını döndürür.

`read_provenance` her değerlendirmede profili ve `read_completed` bilgisini
kaydeder. Başarılı native okumada reader sürümü, kaynak hash/yol, seçili ve
mevcut modeller, kolonlar ve `absent_fields` listesi eklenir. Bu liste author
alanı üretimi değildir. `read_completed=True` yalnızca okumanın tamamlandığını
gösterir; binding/metadata kontrolü yine reddedebilir veya `candidate` bırakabilir.
Kaynağın gerçekten AF3/AF3-ReD olduğu doğrulanmaz (`producer_verified=False`).

### Üç reseptör paneli

```python
targets = [
    {"target_id": "RECEPTOR_1", "output_root": None, "reference_sequence": None, "bindings": {}},
    {"target_id": "RECEPTOR_2", "output_root": None, "reference_sequence": None, "bindings": {}},
    {"target_id": "RECEPTOR_3", "output_root": None, "reference_sequence": None, "bindings": {}},
]
```

Gerçek reseptörler bu iş paketinde belirtilmedi; paneldeki adlar placeholder'dır.
`reference_sequence` yalnızca sonraki açık sequence/residue mapping için ayrılmış
alandır; bu sürüm onu kullanmaz. `bindings`, artifact ID → yukarıdaki nesne
eşlemesidir. Panel hücresi target ID ile binding target ID eşitliğini kontrol eder.
Bir output kökü birden fazla run içeriyorsa hepsi envantere girer; hedef ilişkisi
yalnızca açık binding ile kurulur. Dosya adından veya sıradan hedef atanmaz.

### Kısa test / checklist

```sh
PYTHONPATH=src python3 -B -m unittest discover -s tests -p 'test_af3_red_adapter.py' -v
PYTHONPATH=src python3 -B -m unittest discover -s tests -p 'test_af3_native_bridge.py' -v
PYTHONPATH=src python3 -B -m unittest discover -s tests -q
```

v0.2 yerel doğrulama: 28 yeni native reader/adapter testi, 46 AF3 adapter/bridge
testi ve mevcut testlerle birlikte toplam **343 test geçti**. Notebook'un bütün
kod hücreleri placeholder panel ile ve standalone native admission çağrısı
sentetik fixture ile çalıştırıldı. `structures.py` SHA-256 değeri değişmedi:
`569007eec445c8d22e637995266f74665bd4b3b893ce72d98dd75ab75cd46410`. Yerel
`literature/af3_red-main` keşfi **0 run / 0 artifact** döndürdü.

- Metadata eksikliği otomatik değer üretmeden `candidate` bırakıyor.
- Açık binding + reader + kaynak/bias beyanı ile yalnızca mapping hazırlığı kabul ediliyor.
- Yanlış model/author chain/segment/hash, değişen input veya sidecar reddediliyor.
- Duplicate JSON anahtarı, NaN, belirsiz run, symlink ve stale binding fail-closed.
- Aynı native fixture strict yolda reddediliyor, açık native profilde namespace
  değiştirmeden mapping preparation kontrolünden geçiyor.
- Root seçili kopyası bağımsız sample olarak kabul edilmiyor.
- Adapter çağrıları öncesi/sonrası fixture dosya seti, içerik hash'leri ve mtime aynı.
- İki modül de notebook hücreleriyle birebir; gerçek AF3-ReD output uyumluluğu henüz test edilmedi.

## Repo gerçekleri ve kritik dosyalar

Yerel checkout `literature/af3_red-main` altında. Kullanılabilir inference output'u
yok. Dört CIF, `src/alphafold3/test_data/miniature_databases/pdb_mmcif/` içindeki
test veritabanına ait: `5y2e`, `6s61`, `6ydw`, `7rye`. Bunlar üretilmiş conformer
örnekleri değildir. `rccs/samples/af3-input.json` gerçek output değil, örnek
input'tur: `Tf1beta`, protein A, ligand B/ATP ve C/MG, seed 1–20.

| Dosya | Adapter açısından gerçek |
|---|---|
| `run_alphafold.py` | `write_fold_input_json`, `write_outputs`, `process_fold_input`: input/output isimleri, seed/sample, timestamp dizini ve ReD CLI flag'leri |
| `src/alphafold3/model/post_processing.py` | `{prefix}model.cif`, confidences ve summary dosyalarını yazan gerçek kod |
| `src/alphafold3/common/folding_input.py` | `sanitised_name`, `to_json`: `name`, `modelSeeds`, `sequences`, ligand `id/ccdCodes/smiles` |
| `src/alphafold3/structure/structure_tables.py` | Native atom-site alanları; author atom/component alanları üretilmiyor |
| `src/alphafold3/structure/structure.py`, `model/mmcif_metadata.py` | CIF tablo birleştirme ve ModelCIF metadata eklenmesi |
| `README.md`, `docs/input.md`, `docs/output.md` | Kullanım ve format açıklamaları; isimlerde yazıcı kodu esas alındı |
| `rccs/samples/af3-input.json`, `run-inference.sh`, `run-msa.sh` | Input ve iki aşamalı run örnekleri; gerçek çalışma kaydı değiller |
| `rccs/run-af-301-red.sh` | Flag aktarımı/komut echo; adapter bu shell dosyasını çalıştırmaz veya parse etmez |

`docs/output.md` içindeki genel metin `ranking_scores.csv` dese de gerçek
yazıcı ve aynı dokümanın ağaç örneği **`<job>_ranking_scores.csv`** kullanır.
Embeddings dosyası da seed/job öneklidir. Adapter ranking CSV, confidence JSON
ve embeddings içeriklerini açmaz; örnek ağaçta yalnızca bağlam için gösterilir.

### Metadata nereden alınabilir?

| Alan | Güvenli kaynak / sınır |
|---|---|
| Job/run | Run-local `<job>_data.json` + dosya hash'i + kanonik dizin; job adı tek başına benzersiz değil |
| Seed/sample | Tam eşleşen dizin ve CIF adı; seed ayrıca `modelSeeds` içinde olmalı. Sample, yapının model ID'si değil |
| Sigma/weight | Gerçek run'a bağlı kaydedilmiş CLI/config/log veya açık kullanıcı beyanı. Adapter yalnızca aşağıdaki hash'e bağlı sidecar'ı okur |
| Ligand | Input `sequences[].ligand`: ID ve CCD/SMILES. Bu, yapıda gözlenen ligand varlığı demek değil |
| Source revision/checkpoint | Gerçek run kaydı gerekir. Yerel kaynak dosyaları geçmiş output'un hangi commit/checkpoint ile üretildiğini kanıtlamaz |

`folding_input.Input.to_json()` ReD sigma/weight flag'lerini yazmaz. Kaynakta
varsayılanlar sigma=2.0, weight=100.0; örnek inference script'inde weight=90.0.
Bu fark nedeniyle hiçbir varsayılan gerçek run metadata'sı diye kullanılmaz.
`fit_all`, `fit_chain` ve diğer ReD ayarları bu küçük sözleşmede çıkarılmaz;
run yeniden üretilebilirliği iddiası yoktur. `bias_weight` model ağırlık dosyası
değildir. `source_revision=None` bilinmiyor olarak korunur.

### Kritik parser farkı

Native yazıcı `label_atom_id`, `label_comp_id`, `auth_asym_id`, `auth_seq_id`
üretir; **`auth_atom_id` ve `auth_comp_id` üretmez**. Projedeki
`src/structure_audit/structures.py` bunları zorunlu kılar. Strict profilde hâlâ
`rejected / unsupported` döner. v0.2'nin açık native profili author alanları
üretmeden ayrı bir kayıt üzerinden okur. Label alanları author alanları yerine
kopyalanmaz, CIF onarılmaz, core okuyucusu gevşetilmez. Her iki profilin kabul
testleri **sentetik** fixture'lara dayanır; gerçek output fixture'ı yoktur.

## Assumptions

### Beklenen klasör ağacı — **assumed schema**

Aşağıdaki ağaç, yerel run gözleminden değil incelenen upstream yazıcı kodundan
türetilmiş örnektir. `af_output`, `receptor_1`, seed 7 ve sample 0 örnek isimlerdir.
Sidecar ise tamamen adapter'a ait yeni, opsiyonel bir beyan şemasıdır.

```text
af_output/
└── receptor_1/                        # veya receptor_1_YYYYMMDD_HHMMSS
    ├── receptor_1_data.json
    ├── seed-7_sample-0/
    │   ├── receptor_1_seed-7_sample-0_model.cif
    │   ├── receptor_1_seed-7_sample-0_confidences.json
    │   └── receptor_1_seed-7_sample-0_summary_confidences.json
    ├── seed-7_embeddings/
    │   └── receptor_1_seed-7_embeddings.npz   # opsiyonel
    ├── receptor_1_model.cif                  # upstream seçili kopya
    ├── receptor_1_confidences.json
    ├── receptor_1_summary_confidences.json
    ├── receptor_1_ranking_scores.csv
    ├── TERMS_OF_USE.md
    └── af3red_adapter_metadata.json          # ASSUMED; upstream üretmez
```

Varsayılan upstream davranış dolu run dizinine timestamp eklemektir;
`--force_output_dir` bunu değiştirebilir. Adapter hiçbirini çalıştırmaz.
Kök model kopyasının seed/sample kimliği çıkarılmaz; ranking üzerinden seçim
yapılmaz. Timestamp metadata'sı nedeniyle kopyalar byte-identical olmayabilir.
Farklı sample kayıtlarında aynı hash bulunması otomatik birleştirme nedeni değildir.

Opsiyonel sidecar'ın tam alanları:

```json
{
  "schema_version": "0.1",
  "producer": "AF3-ReD",
  "declared_run_id": "operator-assigned-run-id",
  "input_sha256": "<exact SHA-256 of the run-local job_data.json>",
  "bias_sigma": null,
  "bias_weight": null,
  "source_revision": null,
  "evidence_note": "Operator declaration; identify the actual saved run record here"
}
```

Bu dosya adapter tarafından oluşturulmaz. Sigma/weight yalnızca çalışma kaydında
biliniyorsa doldurulur; null değerler admission'ı durdurur. Input hash uyuşmazlığı,
yanlış producer/schema, fazla alanlar veya bozuk sayılar çağrıyı durdurur. Hash,
beyan dosyasının ve ilişkilendirilen input'un byte kimliğini doğrular; geçmişte
AF3-ReD'nin gerçekten çalıştığını veya beyanın doğruluğunu kanıtlamaz. Aynı AF3
output düzeni tek başına AF3-ReD kaynağını ayırt edemez.

### Fail-closed statü anlamları

| Statü | Anlam |
|---|---|
| `candidate` | Envanterde; değerlendirilmemiş veya eksik provenance/binding/reader var. Downstream kullanıma otomatik geçmez |
| `admitted` | Sadece `external_mapping_preparation_only`: açık hash/model ve profile özgü chain binding kontrol edildi, ReD ve bias değerleri beyan edildi |
| `rejected` | Dosya/kimlik çelişkisi, desteklenmeyen reader formatı veya başarısız temel kontrol; kayıt gerekçeyle korunur |

Bu statüler tasarım adayı statüleri değildir. Root kopyası ve dönüştürülmüş/
yeniden adlandırılmış PDB/mmCIF dosyaları v0.2'de de `candidate` sınırını geçmez.
Geçersiz/ambiguous run metadata'sı tüm keşfi exception ile durdurur; kısmi manifest
dönmez. Tek yapıdaki başarısızlık ayrı `rejected` kaydıdır. Bilinmeyen/stale
artifact ID'li binding tüm manifest çağrısını durdurur.

Okumalar sabitlenmiş yerel output dizinleri içindir; symlink, iç içe run ve
bir run içinde birden çok input JSON desteklenmez. Aktif inference sırasında
atomik filesystem snapshot garantisi verilmez; tamamlanmış çıktılar kullanılmalı
ve handoff öncesi hash'ler tekrar doğrulanmalıdır. Manifest serileştirildikten
sonra sonsuza kadar geçerli bir kabul belgesi değildir.

Referans sequence, residue mapping, eksik residue envanteri, ligand atom
eşleştirmesi ve target kimliğinin bağımsız doğrulanması bu katmanda yapılmaz.
Tam mapping henüz mevcut `supplied_conformer_output_adapter` sözleşmesine
çevrilmez; Claude'dan gelecek nihai geometri sözleşmesi beklenir.

## Files inspected

AF3-ReD tarafı: yukarıdaki kritik dosya tablosunun tamamı; ayrıca
`rccs/README.md` ve `rccs/samples/run.sh`. Kaynak ağacı JSON/CIF/PDB/output
isimleri açısından tarandı; test veritabanı CIF'lerinin içerikleri yorumlanmadı.

Mevcut proje: `README.md`, `pyproject.toml`, `docs/API.md`, ilgili
`docs/HANDOFF.md` bölümleri, `src/structure_audit/__init__.py`,
`structures.py`, `mapping.py`, `provenance.py`,
`supplied_conformer_output_adapter.py`, `tests/fixtures/minimal.cif` ve
`minimal.pdb`. AF3-ReD modülleri import edilmedi veya çalıştırılmadı.

## Next narrow step

Tek reseptör için mevcut bir gerçek run'dan `<job>_data.json` ve bir sample CIF'i
açık native profil ve sağlanan model/author/label-chain binding ile okumak;
gerçek dosyayı izinli bir golden fixture olarak doğrulamak. Native v1 yalnızca
incelenen writer alan profilini destekler; author atom/component alanlarından
birinin/ikisinin mevcut olması, nontrivial altloc, çoklu block, belirsiz kimlik,
sıkıştırılmış CIF ve genel CIF varyantları desteklenmez. Otomatik strict fallback
yoktur. Bu adım inference kurulumu gerektirmez.

**Şimdi:** external conformer inventory/admission prep.
**Daha sonra:** backbone generation, sequence design, structure verification,
Claude sözleşmesi sonrasında geometry-core integration. Bu iş paketinde bunların
hiçbiri çalıştırılmadı veya adapter çıkışına dahil edilmedi.
