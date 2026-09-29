# Bilimsel verilerle güncellenen avidite modeli

Yeni Colab dosyası: `diffusion_trivalent_adaptive_colab_2026-09-29.ipynb`, bölüm **6B**.
Önceki notebook'ta yalnız elle tanımlanan termodinamik senaryo vardı. Bu sürüm aynı fiziksel modelin parametrelerini veriye uydurur. Modelin varsayımlarını veya biyolojik mekanizmayı kendiliğinden keşfetmez.

## Veriler geldiğinde

1. Modelin tam kasetini `CALIBRATION_VARIANT_INDEX` ile seç. Daha sonraki bir oturumda `CALIBRATION_VARIANT_FILE` alanına kaydettiğin `variant.json` dosyasını ver; tasarım/GPU aşamalarını tekrar çalıştırman gerekmez.
2. Teorik veya önceki başlangıç senaryosunu `CALIBRATION_BASELINE_FILE` ile yükle; boşsa `THERMODYNAMIC_SCENARIO` kullanılır. Kd'ler, dört J faktörü, sıcaklık ve çizilecek konsantrasyonlar önceden tanımlı olmalı. `calibration_context`, ölçümlerin koşullarıyla eşleşmeli.
3. Hücrenin ürettiği boş `measurements_TEMPLATE.csv` ve `metadata_TEMPLATE.json` dosyalarını doldur. Doldurulmuş dosyaların yollarını ayarla. Birimleri M ve M²'ye açıkça dönüştür; örneğin nM → M için 1e-9 ile çarp.
4. `FIT_PARAMETERS` ve bunların `PARAMETER_BOUNDS` sınırlarını belirle. Varsayılan seçim yalnız `J123_M2`'dir; sınırlar otomatik tahmin edilmez. Üç monovalent Kd'yi de güncellemek istiyorsan uygun Kd veya tek hedefli denge verilerini ekleyip o Kd parametrelerini listeye al.
5. `RUN_CALIBRATION=True` yap ve 6B hücrelerini çalıştır. Yeni veri geldiğinde eski ve yeni uygun ölçümleri içeren **kümülatif CSV** ile yeniden çalıştır. Sadece yeni satırları verirsen fit yalnız o satırları kullanır; önceki ölçümler hafızadan eklenmez.
6. Her fit ayrı klasöre ve ZIP'e kaydedilir. Colab oturumu silinmeden sonuçları indir veya kalıcı depoya kopyala. ZIP içindeki `active_scenario.json` sonraki hesap için seçilmiş senaryodur; `candidate_scenario.json` inceleme gerektirse bile uydurulan adayı saklar.

## Veri biçimi

CSV sütunları tam olarak şu sırada olmalı:

```text
measurement_id,experiment_id,source_id,condition_id,split,observable,concentration_M,value,sd
```

| `observable` | Ölçülen nicelik | `value` / `sd` birimi |
|---|---|---|
| `kd_1_M`, `kd_2_M`, `kd_3_M` | Doğru hedef sırasındaki monovalent ayrışma sabiti | M |
| `J12_M`, `J13_M`, `J23_M` | Aynı geometri/model için bağımsız belirlenmiş etkin kapanma faktörü | M |
| `J123_M2` | Üçlü kapanma faktörü | M² |
| `mono_1_fraction`, `mono_2_fraction`, `mono_3_fraction` | Tek kol–tek hedef için Langmuir denge bağlanma fraksiyonu | 0–1 fraksiyon |
| `p_any_ligand_bound` | Sabit birer R1/R2/R3 kümesinde herhangi bir kaset işgali olasılığı | 0–1 fraksiyon |
| `p_one_cassette_bridges_all_three` | Aynı kasetin kümedeki üç reseptörü köprüleme olasılığı | 0–1 fraksiyon |
| `receptor_1_occupancy`, `receptor_2_occupancy`, `receptor_3_occupancy` | Kümedeki belirli reseptörün işgal olasılığı | 0–1 fraksiyon |
| `mean_cassettes_bound` | Küme başına ortalama bağlı kaset molekül sayısı | 0–3 molekül/küme |

Derişim eğrilerinde `concentration_M` **serbest** ligand derişimidir; doğrudan Kd/J ölçümlerinde bu alan boş bırakılır. `sd`, sağlanan değerin standart hatasıdır. Ortalama veriyorsan ham tekil ölçümlerin standart sapmasını doğrudan ortalamanın hatası yerine koyma. Belirsiz bir ölçüme otomatik sıfır hata atanmaz.

`measurement_id` benzersiz olmalı. `experiment_id` bağımsız deney/çalışma grubunu belirtir; aynı deneyin satırları hem train hem validation olamaz. `source_id` metadata içindeki `sources` sözlüğüne bağlanır: DOI, yayın tablosu veya izlenebilir laboratuvar kaydı yaz. `condition_id` bütün bu fit boyunca aynıdır.

Metadata'da `conditions` alanı sıcaklık, pH, iyonik güç, konstrükt/PTM açıklaması ve gerekiyorsa ortak geometri kimliğini içerir. Başlangıç senaryosunun `calibration_context` alanı aynı koşulları açıkça tanımlamalı. Ayrıca bağımsızlık açıklaması, monovalent afiniteyi füzyona taşıma varsayımı, dengeye ulaşıldığı beyanı ve serbest derişim kullanımı gerekir. Şablonun boş alanları bilinçli olarak doldurulmamıştır.

**Ham SPR/BLI/RFU, EC50, görünür avidite Kd'si, koff veya genel hücre bağlanma fraksiyonu bu niceliklerle özdeş değildir.** Böyle veriler için kütle taşınımı, yüzey yoğunluğu, yeniden bağlanma, sinyal normalizasyonu veya kinetik gözlem modeli gerekebilir. Hücre bunları sessizce eşitlemez.

## Uyum ve otomatik güncelleme

- Pozitif serbest parametreler log10 uzayında, bilinen standart hatalarla ağırlıklandırılmış en küçük karelerle uydurulur. Diğer parametreler sabit tutulur. Önceki fit bir önsel değildir; parametre başlangıcıdır.
- Ayrılmış `validation` verileri optimizasyona girmez. Birbirinden bağımsız yeterli doğrulama yoksa fit kaydedilir fakat otomatik etkinleştirilmez. Otomatik kullanım istemiyorsan `AUTO_USE_CALIBRATION=False` seç.
- Yerel Jacobian rankı, çoklu başlangıçlardan farklı çözümler, parametre sınırları, yerel belirsizlik ve artıklar değerlendirilir. Yalnız toplam işgal eğrisi, farklı J bileşimlerini ayırmaya yetmeyebilir.
- Etkinleştirme kuralları raporda saklanır: tam yerel rank, sınıra takılmama, yaklaşık %95 aralık yarı genişliği en çok 1 log10 birim, aralıkların sınırları aşmaması, koşullu artık p-değeri en az 0.01, en az max(3, serbest parametre sayısı) bağımsız doğrulama gözlemi, doğrulama duyarlılığında tam yerel rank ve başlangıca göre doğrulama χ²'sinde kötüleşmeme. Bunlar evrensel biyolojik kabul eşikleri değildir.
- Güven aralıkları yerel log-parametre kovaryansından hesaplanır. Parametreler ayrı ayrı belirlenemiyorsa sahte hassasiyet vermek için pseudoinverse kullanılmaz; aralıklar üretilmez. Bu yöntem profil olabilirlik, bootstrap veya Bayesian posterior değildir; sabit Kd belirsizliği ve model hatası kapsanmaz.
- Grafikler ölçüm ±1 standart hata, başlangıç modeli, aday fit ve standartlaştırılmış artıkları gösterir. Parametre aralıkları tabloda yer alır; çizgilerin çevresinde tahmin belirsizlik bandı hesaplanmış değildir.

Bağımsız hata varsayımı teknik tekrarları, korelasyonlu zaman noktalarını veya aynı ham deneyden hem eğriyi hem türetilmiş Kd'yi birlikte bağımsız veri saymayı haklı kılmaz. Metadata açıklaması bu uygunluğu otomatik doğrulamaz. Tekrar tekrar kontrol edilen doğrulama grubu sonunda nihai bağımsız test olmaktan çıkar; yeni deneylerle dış doğrulama gerekir.

## Kayıt ve sınırlar

Her sürüm tam CSV/metadata kopyasını, dosya hash'lerini, başlangıç senaryosunu, serbest/sabit parametreleri, sınırları, uydurulan değerleri, tanıları, parametre aralıklarını, yazılım sürümlerini ve kalibrasyon kaynak hash'ini saklar. Önceki kayıtlar korunur.

Bu model sabit birer reseptör içeren kümenin denge modelidir. Sonradan eklenen bilimsel veriler onu otomatik bir membran, doku seçiciliği, aktivasyon veya kinetik modeline dönüştürmez. Sonuç tek evrensel bir “avidite sabiti” değildir; derişime bağlı işgal ve üçlü köprüleme senaryosudur. İyi fit, mekanizmanın biyolojik olarak doğru olduğunu tek başına kanıtlamaz.

Kaynaklar: [SciPy least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html), [SciPy kovaryans yaklaşımının sınırları](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.curve_fit.html), [Raue ve arkadaşları: parametre belirlenebilirliği](https://pubmed.ncbi.nlm.nih.gov/19505944/).
