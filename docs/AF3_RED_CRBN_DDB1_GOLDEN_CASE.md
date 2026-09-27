# CRBN-DDB1 — ilk reviewed gerçek-run golden case

## Golden case path

[af3_red_crbn_ddb1_seed57_sample2.reviewed.json](../tests/golden/af3_red_crbn_ddb1_seed57_sample2.reviewed.json)

Case SHA-256: `009d6d83db6271c3a72531a4fd74dee0b5a126defccf7235cddfb9e31415a6fd`.
Testten önce ayrı discovery, inventory, readiness ve native-reader çağrılarıyla
gözlem yapıldı. 301 artifact'in sabit beklenen kayıtları bundan sonra yazıldı;
golden test baseline üretmek veya güncellemek için kullanılmadı.

## Golden test result

**PASS — 1 test, 11.324 saniye, exit code 0.** Yalnızca aşağıdaki test çalıştırıldı:

```sh
AF3_RED_GOLDEN_CASE='/Users/fatihyigitevyapan/Desktop/Forschungspraktikum/tests/golden/af3_red_crbn_ddb1_seed57_sample2.reviewed.json' \
PYTHONPATH=src python3 -B -m unittest discover -s tests -p 'test_af3_red_golden.py' -v
```

Baseline ile fark çıkmadı; test sonrasında case değiştirilmedi. Bu sonuç,
okunabilirliği ve mevcut fail-closed statü davranışını doğrular; `admitted`
sonucu veya core kabulü değildir.

## Observed artifact counts

Tek run: `af_output/crbn_20251015_034523`.

- 300 `native_sample`, 1 `upstream_selected_copy`; toplam 301 artifact.
- 301 `candidate`, 0 `rejected`, 0 `admitted`.
- Seçili sample: `seed-57_sample-2/crbn_seed-57_sample-2_model.cif`.
- Seçili sample'ın native okuması tamamlandı (`read_completed=true`). Statü
  gerekçeleri: `af3red_execution_declaration_missing`, `bias_sigma_unknown`,
  `bias_weight_unknown`.
- Diğer 299 sample'da bunlara ek olarak
  `explicit_target_model_chain_binding_required` var; bu dosyaların atom
  tabloları golden akışında okunmadı.
- Root copy gerekçesi: `root_copy_not_an_independent_sample`.

## Selected binding

Kullanıcının açıkça verdiği seçim aynen kullanıldı; zincirden reseptör kimliği
çıkarılmadı veya bağımsız olarak doğrulanmadı.

```json
{
  "artifact_sha256": "58f38cc8f279fb827851c27ff735bdc4b310ca22276a6a2cf8ebbb2414a882ed",
  "target_id": "crbn",
  "model_id": "1",
  "auth_asym_id": "A",
  "label_asym_id": "A"
}
```

## Baseline fields recorded

- `source`: tam olarak `AF3-ReD`.
- `real_output_record`: mevcut `external_artifacts/af3_red/CRBN-DDB1.tar.gz`;
  SHA-256 `06647cd51103fa02a10032dd92767820aff009e7d629c2d27e4c46b9856297bb`.
  Zenodo kökeni kullanıcının kaynak beyanıdır; burada ağ üzerinden yeniden
  doğrulanmadı. Arşiv içeriği değiştirilmedi.
- `expected_input_sha256`:
  `bf35c577897af0595f7dc3cd65d09bf9ddfe345bc4e01093199efe8a04da94f1`.
- `expected_sidecar_sha256`: `null`; sidecar gerçekten yok. Script/klasör adından
  sigma/weight türetilmedi; yeni sidecar oluşturulmadı.
- `expected_artifacts`: 301 relative path için hash, role, status, reasons.
- `expected_read_provenance`: `af3_native_v1`, reader `0.1`, model `1`, gerçek
  kolon listesi ve bulunmayan author atom/component alanları dahil tam gözlem.
  Yalnız golden karşılaştırması için `source_path` run-relative tutulur.
- `expected_hetatm_rows`: `1`; yalnızca seçili modeldeki HETATM satır sayısıdır.
- `expected_root_copy`: `crbn_model.cif`, SHA-256
  `c89b1ce35264bc82310be016a528aa2362816877ad10d197f538103cdf1a9ef5`,
  `byte_equal_to_selected_sample=false`. Bu farktan yapısal sonuç çıkarılmadı.

## Input/output immutability result

Golden testin kendi before/after SHA-256 ve tam nanosecond mtime kontrolü geçti:
301 yapı dosyası, run input JSON'u, kaynak arşiv ve case JSON'u (304 dosya).

Ek gözlem kontrolünde run içindeki 306 dosyanın hash/mtime/boyutu aynı kaldı;
run dosya setine ekleme veya silme olmadı. Kaynak arşiv, üç reader/adapter
modülü, golden test ve notebook dahil izlenen 312 mevcut dosyanın içerik hash'i
ve boyutu değişmedi. Case'in test öncesi ve sonrası hash'i yukarıdaki değerle aynı.

Yalnızca reviewed case JSON ve bu dokümantasyon kaydı eklendi. Parser, bridge,
adapter, test kodu, notebook, CIF, input/output ve kaynak arşiv değiştirilmedi.

## Exact next narrow step

Bu case'i mevcut eksik-metadata/candidate davranışının sabit regresyon baseline'ı
olarak korumak. Admission ilerletilecekse ayrı bir iş paketinde gerçek çalışma
kayıtlarına bağlı metadata beyanını incelemek; bu testin beklenen sonucunu
kendiliğinden `admitted` yapmamak.
