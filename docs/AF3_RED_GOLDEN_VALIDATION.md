# AF3-ReD — tek gerçek run için golden validation hazırlığı

## Real output found?

**Hayır: projede tanımlanabilir gerçek AF3-ReD output run'ı bulunmadı.**
Proje kökü: `/Users/fatihyigitevyapan/Desktop/Forschungspraktikum`.
Gizli/ignore edilmiş dosyalar dahil dosya adları tarandı; `.git` içeriği ve
symlink hedefleri takip edilmedi. Arşivler açılmadı. Sonuçlar:

- `*_data.json`, `*ranking_scores.csv`, `af3red_adapter_metadata.json`: bulunmadı.
- `seed-*` veya `af_output*` isimli dizin: bulunmadı.
- Model CIF adı taramasının tek eşleşmesi sentetik `tests/fixtures/af3_native/multimodel.cif` idi.
- AF3-ReD checkout'undaki dört CIF, miniature PDB test veritabanına ait.
- Diğer örneklerden `1UBQ` teknik doğrulama kaynağı ve `IL7RA.cif` içindeki
  `AlphaFold v2.0` kaydı AF3-ReD run'ı olarak kullanılmadı.

İlgisiz CIF'lerin tamamı içerik açısından incelenmedi; bazı ek okumalarda yerel
dosya erişimi beklediği için bu kapsam dışı tarama durduruldu. Yukarıdaki run
işareti/dizin taramaları tamamlandı ve erişim hatası raporlamadı. Bu sonuç,
yeniden adlandırılmış veya arşiv içindeki bir dosyanın kaynağını belirlediğimiz
anlamına gelmez.

`build_red_manifest(literature/af3_red-main, profile="af3_native_v1")` çağrısı:
**0 run, 0 artifact**, diagnostics: `no_recognized_runs`, `no_structure_artifacts`.
Bu boş envanter gerçek output üzerinde golden başarı sayılmaz.

## Golden validation result

**NOT RUN — gerçek run ve incelenmiş baseline eksik.** Gerçek artifact için
`candidate/rejected/admitted` sayıları veya native reader provenance'ı raporlanamaz.
Sentetik fixture'lar bu iş paketinde gerçek output yerine kullanılmadı; yeni CIF,
fake run, sidecar veya beklenen sonuç dosyası üretilmedi.

Yeni [test_af3_red_golden.py](../tests/test_af3_red_golden.py) varsayılan olarak
`skipped` kalır. Gerçek run tanımlandıktan sonra discovery → inventory → açık
native readiness akışını tek sample binding'iyle çalıştırır. Diğer artifact'leri
de statü/gerekçe/hash/rol ile raporlar. Test dosya yazmaz, baseline oluşturmaz veya
güncellemez; konfigürasyon sağlanmış ama hatalıysa skip yerine başarısız olur.

Yerel kontrol: **343 test geçti, 1 golden test skipped** (344 test keşfedildi).
Golden testin gerçek veriyle çalışan dalı henüz çalıştırılmadı. İleride baseline
karşılaştırmasının geçmesi, kaydedilmiş `rejected` veya `candidate` sonucunu da
doğrulayabilir; tek başına native uyumluluk/admission başarısı anlamına gelmez.

## Schema differences

| Soru | Şimdiki sonuç | Gerçek run geldiğinde kontrol |
|---|---|---|
| Gerçek düzen assumed schema ile uyumlu mu? | Henüz gözlenmedi. | Tek `_data.json`, sample dizin/dosya adı, seed listesi, tam artifact envanteri |
| Native profil için yeni istisna gerekli mi? | Kanıt yok; istisna eklenmedi. | Explicit model ve author/label chain seçimiyle reader sonucunu incele |
| Root copy / sample copy davranışı? | Gerçek dosyada gözlenmedi. | Root kopyasının rolü/statüsü ve seçili sample ile byte hash eşitliği |
| Ligand/HETATM sorun çıkarıyor mu? | Gerçek dosyada bilinmiyor. | Seçili modelin HETATM satır sayısı ve varsa native ret gerekçesi |

Root/sample hash eşitsizliği farklı yapı veya farklı sample kanıtı değildir;
metadata farklı olabilir. Hash eşitliği yalnızca byte eşitliğini gösterir.
Root kopyasından seed/sample çıkarılmaz. HETATM sayısı ligand kimliğini,
input beyanıyla eşleşmesini veya target mapping'in doğruluğunu doğrulamaz.

## Dar golden-test planı

1. Tamamlanmış **tek gerçek AF3-ReD run dizini** ve gerçek çalışmayı belgeleyen
   mevcut log/kayıt sağlanır. Input JSON, bir sample CIF ve mevcutsa root kopyası
   orijinal ad/byte'larıyla yerinde tutulur. Mümkünse tüm run envanteri korunur.
   Başka kaynak dosyaları yeniden adlandırılarak AF3-ReD run'ı yapılmaz.
2. Kaynak kaydı ve dosya SHA-256 değerleri incelenir. Bir sample, açık target ID,
   CIF model ID, `auth_asym_id`, `label_asym_id` seçilir. Seed/sample model ID
   yerine kullanılmaz; sequence correspondence veya segment türetilmez.
3. Ayrı bir case JSON'u **inceleme sonrası** hazırlanır. Beklenen değerler
   test tarafından üretilmez. Kaynak beyanının incelendiği `review_note` içinde
   belirtilir; bu, yazılımın bağımsız kaynak doğrulaması yaptığı anlamına gelmez.
4. Native profil çalıştırılır. Metadata eksikse `candidate`, reader/binding
   başarısızsa `rejected` geçerli gözlemlerdir; `admitted` zorunlu beklenen sonuç
   değildir. Adapter sidecar'ı yoksa bu test onu oluşturmaz.
5. Gerçek gözlem ile baseline karşılaştırılır. Fark varsa test başarısız olur;
   parser veya baseline otomatik değiştirilmez. Yeni istisna ancak gerçek ret
   gerekçesi ayrı değerlendirilerek kararlaştırılır.

### Case JSON sözleşmesi

Bir veri dosyası veya sahte değerli template eklenmedi. JSON şu alanları içerir:

- `run_directory`: tek run'ın kanonik mutlak dizin yolu; üst output kökü değil.
- `source`: `AF3-ReD`; `review_note`: gerçek kaynağın inceleme açıklaması.
- `real_output_record`: mevcut gerçek run kaydının kanonik mutlak `path` ve
  incelenmiş `sha256` değeri. Kaynak dosyası test tarafından çalıştırılmaz.
- `expected_input_sha256`: run-local `_data.json` dosyasının sabitlenmiş hash'i.
- `expected_sidecar_sha256`: adapter sidecar'ının hash'i; dosya yoksa `null`.
- `sample_relative_path`: yalnızca seçili native sample'ın run'a göre yolu.
- `binding`: `artifact_sha256`, `target_id`, `model_id`, `auth_asym_id`,
  `label_asym_id` alanlarının açık değerleri; `segment` yok.
- `expected_artifacts`: tüm keşfedilen yapı dosyaları için relative path →
  `{sha256, role, status, reasons}` eşlemesi. Yalnızca seçili sample bound olur.
- `expected_read_provenance`: seçili artifact'in tam `read_provenance` kaydı.
  Kaydın `source_path` alanı varsa yalnız golden karşılaştırmasında run-relative
  yola çevrilir; gerçek adapter manifesti değiştirilmez. Reader sürümü, kolonlar,
  eksik alanlar, profil ve diğer provenance alanları aynen karşılaştırılır.
- `expected_hetatm_rows`: okuma tamamlanmışsa seçili modelde incelenmiş HETATM
  satır sayısı; tamamlanmamışsa `null`. Sıfır otomatik varsayılmaz.
- `expected_root_copy`: yoksa `null`; varsa `relative_path`, `sha256` ve
  `byte_equal_to_selected_sample` alanları. Rol/statü ayrıca envanterde sabitlenir.

Konfigürasyonu etkinleştirmek için, mevcut gerçek case dosyasının yoluyla:

```sh
AF3_RED_GOLDEN_CASE='/absolute/path/to/reviewed-real-case.json' \
PYTHONPATH=src python3 -B -m unittest discover -s tests -p 'test_af3_red_golden.py' -v
```

Değişken tanımsızken aynı komutun `AF3_RED_GOLDEN_CASE=...` bölümü çıkarılır;
test açık bir missing-real-output gerekçesiyle skip olur. Değişken boş veya
yanlış dosyaya ayarlıysa test başarısız olur. Test seçili provenance'ı, tüm
artifact statü/gerekçelerini, root copy karşılaştırmasını ve HETATM sayısını
standart çıktıya basar; rapor dosyası oluşturmaz. Kaynak/kontrol dosyalarının
hash ve mtime değerlerinin değişmediğini ayrıca kontrol eder.

## Code changes made

Yalnızca bu plan/tespit belgesi ve opt-in golden test iskeleti eklendi.
Adapter, bridge, notebook ve strict reader değiştirilmedi. Aşağıdaki işlem öncesi
hash'lerin işlem sonunda aynı kaldığı doğrulandı:

```text
structures.py       569007eec445c8d22e637995266f74665bd4b3b893ce72d98dd75ab75cd46410
af3_red_adapter.py  38bb64c5f059050dd27eaa78a3b9db9be6a588ded8fec0b2e3d77148eca112a6
af3_native_bridge.py 101170c2403543e1422be6ca1e1c4f0faa60ee6a56c55733eebd4be4051a35f6
```

## Exact next narrow step

Tek gerçek run dizini, kaynağını belgeleyen mevcut kayıt ve açık sample/model/
author-label chain seçimi sağlandığında incelenmiş case JSON'unu doldurup bu
golden testi çalıştırmak. Gerçek dosya görülmeden parser istisnası veya admission
sonucu eklememek.
