# Üç reseptör / üç binder pipeline

Güncel Colab giriş dosyası: `diffusion_trivalent_adaptive_colab_2026-09-29.ipynb`.
Notebook gerekli yerel kaynakları kendi içinde taşır. Bu klasör aynı kodun okunabilir sürümüdür.

Yeni **6B** hücresi gelecekteki uyumlu deneysel verilerle Kd ve/veya J parametrelerini yeniden uydurur, bağımsız doğrulama ve belirsizlik kontrollerinden geçen modeli sonraki hesapta kullanabilir. Veri biçimi, tekrar kullanım ve bilimsel sınırlar: [CALIBRATION.md](CALIBRATION.md). Eski, kalibrasyonsuz `diffusion_trivalent_colab_2026-09-29.ipynb` dosyası korunmuştur.

## Kullanım

1. Notebook'u Colab'e yükle, tasarım/tahmin çalıştıracaksan GPU seç.
2. Hedefler hücresinde üç farklı protein reseptör konstrüktünün dosyasını, zincirini ve **tam konstrükt dizisini** tanımla. ECD kullanılıyorsa yalnız ECD dizisini yaz. Otomatik hedef seçimi veya örnek protein ikamesi yoktur.
3. Yeni tasarım için `mode="design"`, binder uzunluğu ve konstrükt dizisine göre 1 tabanlı hotspot konumları ver. Akış RFdiffusion → ProteinMPNN → AlphaFold incelemesidir. Üç hedef ayrı çalışır; eşikleri geçen geometri adayı yoksa durur. Varsayılan iki omurga × sekiz dizi keşif açısından küçük bir örneklemedir.
4. Elindeki ikili kompleksler için `mode="import"`, `pair_path`, `binder_chain`, `binder_sequence` ve hedefin zincir/dizisini ver. Karışık design/import kullanımı desteklenir.
5. `CONNECTIONS` hem GS20 linker'lı hem doğrudan füzyon üretir. Linker dizilerini değiştirebilir, `ALL_SIX_DOMAIN_ORDERS=True` ile altı domain sırasını deneyebilirsin. Her kaset bir zincirdir ve her hedef için bir kol taşır: **toplam valans 3**.
6. Boltz bütün kaseti tek başına ve üç hedefle yeniden tahmin eder. `RUN_BOLTZ=False` ile dış AF3/AF3-ReD çalışmasına uygun girdiler üret. Tam kaset tahminlerini `EXTERNAL_PREDICTIONS` ile açık zincir eşlemesi vererek içeri al. Dış çıktılar varsa ilk çalıştırmada kaset kimliklerini görüp eşlemeleri doldurmak gerekir; dışarıda tahmin yapıldıktan sonra yeni bir import çalışması başlatılabilir.
7. ZIP'i indir. PyMOL'da kaset klasörünün `view_results.py` betiğini çalıştır veya `predictions/*.cif` dosyalarını aç. AlphaFold Server için `alphafold_server_jobs.json`; yerel AF3 için `prediction_inputs/*.af3.json` kullan. Server'ın iş/kaynak sınırları nedeniyle işleri parçalara ayırmak gerekebilir.

AF3-ReD mevcut çıktı envanteri için `AF3RED_OUTPUT_ROOT` isteğe bağlıdır. Envanter bir çalıştırma veya biyolojik kabul değildir. Zincir/dizi kimliği açıkça sağlanır. Notebook'un hazırlanmasında Rosalind Workbench kullanılamadı: oturumun araçlarında ve eklenti aramasında bulunmadı.

## Düzeltmeler ve bilimsel kapsam

| Konu | Uygulanan davranış |
|---|---|
| Kimlik | Üç ayrı hedef; tam dizi eşleşmesi, eksik ağır atomlar, farklı MODEL kayıtları ve açık zincir eşlemesi denetlenir. RFdiffusion'ın binder/reseptör sırası AlphaFold girdisi için kimlik kontrolüyle yeniden düzenlenir. |
| Arayüz | Her binder kendi hedefine karşı incelenir. Arayüz yoksa, eksik atom varsa veya ciddi atom yakınlığı bulunursa kaset oluşturma adayı kabul edilmez. Temas bulunması bağlanma kanıtı değildir. |
| Füzyon | Gerçek linker rezidüleri nihai dizide yer alır. Doğrudan füzyon polimer yayı olarak modellenmez. İkili komplekslerden sahte bir ortak koordinat yapısı birleştirilmez. |
| Tam yapı | Peptit C–N bağlantıları, eksik atomlar, domain şekil değişimi, domain–hedef temasları, linker dahil bütün kaset–reseptör ve reseptör–reseptör yakınlıkları raporlanır. Bunlar kaba kontrollerdir; tam stereokimyasal validasyon, protonasyon veya kuvvet alanı minimizasyonu değildir. |
| Biyokimya | Tam füzyon için kütle, teorik pI, pH 7.4 yükü, GRAVY, sisteinler, N-glikozilasyon motifleri ve hidrofobik diziler raporlanır. Ekspresyon, disülfit eşleşmesi, gerçek glikozilasyon ve agregasyon sonucu çıkarılmaz. |
| Membran / glikan | Verilmiş heteroatomlar korunur ve yakınlıkları denetlenir. Aynı koordinat sisteminde kaynaklı bir membran düzlemi verilirse kasetin yarı uzay ihlali ölçülür. Bilinmeyen glikan, kofaktör veya membran yerleşimi yok sayılıp biyolojik uygunluk ilan edilmez. |
| Linker fiziği | Kaba mesafe zarfından Ceff üretilmez. İsteğe bağlı ortak-yapı modeli sonlu konturlu ideal zincir kullanır; düzenlenmiş dağılım konturda kesilip normalize edilir. J13 aradaki serbest domaini de içerir. Yönelim, dışlanan hacim ve membran etkileri entegre edilmediğinden deneysel veya biyolojik alt/üst sınır değildir. |
| Termodinamik | Kd'ler ve kapanma faktörleri verilirse sabit R1/R2/R3 kümesinin 15 işgal düzeni normalize edilir. İlk Kd, serbest ligand derişimi ve farklı kasetlerin rekabeti hesaba katılır. J12/J13/J23 M, J123 M² birimindedir. ΔG° yalnız verilen Kd'nin standart-durum dönüşümüdür; katlanma serbest enerjisi, ΔH/ΔS veya kinetik tahmini değildir. |
| Özgüllük / işlev | Üç amaçlanan ve altı çapraz domain–hedef tahmini için girdiler üretilir. Bunlar off-target deneylerinin yerine geçmez. Agonizm, antagonizm, internalizasyon veya üç hedef gerektiren biyolojik AND kapısı iddia edilmez. |

Reseptör isimleri genel girdilerdir; akış GIPR/GLP-1R/GCGR'ye özgü değildir. Bununla birlikte otomatik tasarım kapsamı standart 20 aminoasitli tek zincir protein konstrüktleridir. Çok alt birimli, glikan bağımlı veya protein dışı hedeflerin kimyası ayrıca modellenmelidir. Üç yapının aynı hücrede ve erişilebilir konumlarda bulunması, doku seçiciliği veya deneysel avidite burada kurulmuş değildir.

## Doğrulama ve yeniden üretim

CPU testleri: `python -m unittest discover -s tests/trivalent -v`.
Notebook üretimi: `python tools/build_trivalent_colab.py`.
Gerçek Jupyter çekirdeğinde boş girdi ve sentetik import çalışmaları: `python tools/validate_trivalent_colab.py`.
Son komut `numpy scipy pandas biopython matplotlib nbformat nbclient ipykernel` ister; yerel Jupyter bağlantıları açar. Sentetik geometriler test amacıyla oluşturulur; biyolojik protein veya başarılı tasarım örneği değildir.

GPU kurulum/kestirim kodu ayrı Python ortamları ve sabit Git revizyonları kullanır. Çalışma anındaki paket listeleri, model dosyası hash'leri ve çıktı hash'leri kaydedilir. **Gerçek GPU çalışması ve gerçek hedeflerde tasarım başarısı bu teslim sırasında doğrulanmadı.** Colab donanımı, CUDA ve bağımlılık uygunluğu ayrıca çalıştırılarak doğrulanmalıdır. PyMOL betiği sahte komut arayüzüyle yükleme akışı bakımından sınandı; uygulamada görsel inceleme yapılmış sayılmaz.

Yöntem/API kaynakları: [RFdiffusion](https://github.com/RosettaCommons/RFdiffusion), [ColabDesign](https://github.com/sokrypton/ColabDesign), [Boltz](https://github.com/jwohlwend/boltz/blob/main/docs/prediction.md), [yerel AF3](https://github.com/google-deepmind/alphafold3/blob/main/docs/input.md), [AlphaFold Server](https://github.com/google-deepmind/alphafold/tree/main/server), [linker–Ceff deneysel çalışması](https://pubmed.ncbi.nlm.nih.gov/31659043/).
