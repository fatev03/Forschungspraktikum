# Trivalent joint geometry — teknik ve biyolojik inceleme

29 Eylül 2026. İncelenen kaynak: `trijoint_submitted.py`, kullanıcının eklediği hücrenin değiştirilmemiş kopyası. Gerçek Boltz kompleksleri sağlanmadı. `check_synthetic.py` kendi geometrik oyuncak PDB dosyalarını geçici dizinde oluşturur; bu dosyalar fiziksel protein modelleri değildir. Kullanıcının mesajındaki kaçış/HTML işaretleri içeren test metni doğrudan çalıştırılmadı; belirtilen geometrik özellikler ve dört hata yolu bağımsız bir test düzeneğinde yeniden kontrol edildi.

**Sonuç:** Hücre, ikili kompleksleri ayrı ayrı inceleyen yararlı bir kaba geometri taramasıdır. Mevcut haliyle ortak üçlü bağlanmayı, biyolojik avidite büyüklüğünü veya hücre seçiciliğini doğrulamaz. Çıktıların biyolojik anlamını bozan gerçek uygulama hataları da vardır.

## Yeniden üretilen bulgular

| Kontrol | Sonuç |
|---|---|
| 10 binder CA, 4 arayüz CA; n_off=3 Å, c_off=sqrt(421) Å; uç yönü işaretleri | Geçti |
| optimal_linker / coil_span tersliği ve mevcut polimer sabitleri | Geçti |
| 25 aa linker: 5 nm'de kötü yönelim erişir, 10 nm'de erişmez | Geçti |
| Yanlış linker/Kd sayısı, eksik zincir ve bozuk spec kontrolleri | Geçti |
| Tek kolun çökmeden dönmesi | Geçti; satırlardaki üçlü bağlanma etiketleri tek kola uygun değil |
| 5 nm için aktarılan Ceff | 5921.782 µM; aynı hesabın kötü yönelim değeri 7.002 µM |
| Aktarılan / kötü yönelim Ceff | 845.77 kat |
| İlk Kd'yi 1000 kat zayıflatma | Bütün kazanç satırları aynı kaldı |
| 12 nm'de en iyi uç mesafesi 96.5 Å, linker sınırı 87.5 Å | Yine pozitif Ceff aktarıldı: 2.605e-8 M |
| Hiçbir binder arayüz teması yok | Yine yaklaşık 2.70 milyon kazanç raporlandı |
| Aynı yapının iki MODEL kaydı | 10 yerine 20 binder CA sayıldı |
| Linker uzunluğu 25.9 | Sessizce 25'e indirildi |
| Negatif reseptör aralığı | Kabul edildi |

Sayısal kayıt: `results.json`.

## Öncelikli düzeltmeler

### 1. P1 — Konservatif diye aktarılan Ceff iyimser yönelimden geliyor

272. satır Ceff'i “floor” olarak tanımlıyor. 290–295. satırlar ise `gaps_best` kullanıyor. En geniş erişilebilir aralığı seçmek, o aralıktaki en iyi yönelimi en kötü yönelim yapmaz. Sentetik örnekte bu fark Ceff için 846 kat, iki-linker kazancı için yaklaşık 715 bin kattır.

Düzeltme: en iyi ve en kötü yönelim değerlerini açıkça ayrı döndür. Seçicilik hücresine hangisinin taşındığını etiketle. Fiziksel doğrulama olmadan hiçbirine biyolojik alt/üst sınır deme.

### 2. P1 — Kontur uzunluğu sınırı yalnızca kötü yönelimde uygulanıyor

215. satır `ce_best` değerini erişim kontrolü olmadan hesaplıyor; 290–295. satırdaki aktarım da öyle. Gaussian dağılım sonsuz desteklidir; dolayısıyla fiziksel kontur uzunluğunun ötesinde de pozitif değer verir. 12 nm örneği bunu gösteriyor.

Düzeltme: bütün değerlendirme ve aktarım yollarında kontur sınırını uygula. Bu, Gaussian modeli tam bir sonlu-zincir modeli yapmaz; özellikle kontur sınırına yakın bölge için FJC/WLC veya uygun bir konformasyon örneklemesi gerekir. Erişilemeyen bir kolun sıfır Ceff'ini `1e-30` tabanı ile sonradan pozitife çevirmemek gerekir.

### 3. P1 — Arayüz bulunmayınca bir bağlanma merkezi varmış gibi devam ediliyor

135. satırda `iface_res == 0` olduğunda tüm binder'ın merkezi kullanılıyor. Böylece uzaktaki iki protein, bağlanma kompleksiymiş gibi değerlendirmeye giriyor. Temas ve çakışma değerleri yalnızca yazdırılıyor; üçlü skorun üretilmesini engellemiyor.

Düzeltme: arayüz yoksa geometriyi “değerlendirilemez” olarak döndür. Çakışma ve yapı güveni için ayrıca açık kabul koşulları belirle; temas bulunmasını bağlanma kanıtı sayma.

### 4. P1 — “Trivalent gain” tam avidite veya üçlü bağlanma olasılığı değil

218. satırda yalnızca `kds[i+1]` kullanılır; üç kollu durumda ilk Kd hesaba girmez. Çıktının “üç ayrı Kd'yi kullanır” açıklaması bu nedenle doğru değildir.

İfade, uygun ideal varsayımlarda **ilk kol zaten bağlıyken tam bağlı durumun o tekli bağlı duruma göre ağırlık oranı** olarak okunabilir:

`w123 / w1 = (Ceff12 / Kd2) × (Ceff23 / Kd3)`.

Bu koşullu yorumda Kd1'in iptal olması doğrudur. Tam sistem bağlanması veya üçlü durum olasılığı için ilk bağlanma, ligand konsantrasyonu, diğer tekli ve ikili durumlar ve normalizasyon gerekir. Bu yüzden düzeltme, rastgele Kd1 çarpanı eklemek değil, niceliği doğru tanımlamak veya tam durum modeline geçmektir.

### 5. P2 — En iyi mesafe formülü her durumda erişilebilir bir minimum değil

210. satır `max(s-a-b,0)` kullanıyor. Serbest dönme altında üç sabit uzunluk için tam minimum:

`max(0, s-a-b, a-s-b, b-s-a)`.

Örnek: s=5 Å, a=30 Å, b=2 Å için kod 0 Å verir; minimum 23 Å'dır. Mevcut formül güvenli ama gevşek bir alt zarf olarak adlandırılabilir; “gerçek en iyi yönelim” olarak okunmamalıdır.

Ayrıca ortadaki binder'ın N ve C uçları aynı rijit cisme bağlıdır. İki linker için ayrı ayrı optimize edilen yönelimler birlikte gerçekleşmeyebilir. `gap_worst <= contour` koşulu, varsayılan merkezler ve uç yarıçapları altında bir uzunluk kontrolüdür; reseptörlerin, binder'ların ve membranın çakışmadan ortak bir yapı kurabildiğini göstermez.

### 6. P2 — PDB ve girdi kontrolleri eksik

Okuyucu MODEL/ENDMDL sınırlarını ayırmıyor, residue kimliklerini saklamıyor; ilk/son CA'yı gerçek biyolojik uç varsayıyor. Eksik terminal rezidüler veya birden fazla model uç mesafelerini bozabilir. ATOM dışındaki glikanlar okunmuyor. Aynı hedef/binder zinciri de reddedilmiyor.

Girdiler için sonlu ve pozitif Kd, pozitif tam sayı linker, negatif olmayan fiziksel aralık ve boş olmayan grid kontrolü eklenmeli. `clash_atoms`, çakışan atom çifti sayısı değil, en az bir hedef atomuna eşikten yakın binder atomlarının sayısıdır; etiket bu ayrımı korumalıdır.

## Biyolojik değerlendirme

### Üç ikili kompleks, ortak hücre yüzeyi geometrisini belirlemez

Her binder'ı kendi reseptörüne göre ölçmek doğru bir iyileştirmedir. Bununla birlikte hücre, üç boyutlu uç vektörlerini sadece merkezden uzaklıklara indirger. Membran normali, ECD yüksekliği ve eğimi, reseptör gövdeleri, glikanlar, reseptörler arası ve binder'lar arası çakışmalar değerlendirilmez. “outward” işareti de gerçek peptit bağının çıkış yönü değil, CA-merkez vektörlerine dayalı bir göstergedir.

GIPR/GLP-1R/GCGR için yalnızca ECD komplekslerine bağlanmak, tam reseptöre erişimi veya agonizmi göstermez. GLP-1R'nin ECD konumu ligand durumuna göre değişir; doğal peptit aktivasyonunda transmembran bölgeyle etkileşim önemlidir. N-glikozilasyon da GIPR ve GLP-1R'nin yüzeyde bulunmasını ve işlevini etkiler. Bu nedenle ortak membran yerleşimi ve glikan/sterik değerlendirme biyolojik yorum için gereklidir.

Kaynaklar: [GLP-1R tam uzunluk yapısı ve ECD hareketi](https://www.nature.com/articles/s41467-020-14934-5), [GIPR/GLP-1R glikozilasyon çalışması](https://pubmed.ncbi.nlm.nih.gov/22412906/).

### Polimer hesabı bir yaklaşım; sabitleri kopyalamak doğrulama değildir

Birim dönüşümü ve `optimal_linker` tersliği doğru. Ancak Kohn çalışmasının ölçeklemesi kimyasal olarak açılmış proteinlerden gelir. 0.598 üssüyle elde edilen zincir boyutunu ideal Gaussian dağılım ve `<r²>=6Rg²` bağıntısıyla birleştirmek yaklaşık bir modeldir. Gerçek GS, yüklü, prolinli veya yapısal linker'ların eşdeğerliği gösterilmiş değildir. Sørensen–Kjaergaard deneyleri linker dizisinin Ceff'i değiştirdiğini gösterir.

Gaussian konum olasılığı zaten konformasyon entropisini içerir; kodun “entropy loss omitted” ifadesi bu yüzden fazla geneldir. Eksik olan yönelim, sterik engeller, membran ve modelin kapsamadığı konformasyon etkileridir. “UPPER BOUND” bütün bu sistemler için kanıtlanmış bir biyolojik sınır değildir.

Kaynaklar: [Kohn 2004](https://pmc.ncbi.nlm.nih.gov/articles/PMC515087/), [Sørensen ve Kjaergaard 2019](https://pubmed.ncbi.nlm.nih.gov/31659043/).

### Valans 4, gerçek yapının dört kopya taşımasına bağlıdır

Her reseptör için bir binder taşıyan tek doğrusal kaset `1,1,1` valanslıdır. `4,4,4`, her özgüllükten dört erişilebilir kopya ve toplam 12 bağlanma bölgesi gerektirir. İki linker'lı üç-domain modeli bu 12-kollu yapının geometrisini hesaplamaz. Valansı grafiği daha seçici yapmak için artırmak fiziksel bir gerekçe değildir.

Mevcut analitik seçicilik formülünde bütün yoğunluklar aynı katsayıyla ölçeklenirken alfa için toplam valans bir matematiksel üst sınırdır. Bu sınır biyolojik AND-kapısı kanıtı değildir. Reseptörlerden biri yokken diğerleri hâlâ bağlanma sağlayabilir; üç reseptörün zorunlu olduğu bir mantık kurulmamıştır.

### Yoğunluk ve Ceff aynı fiziksel modele bağlanmalı

“Yüzlerce reseptör/µm²” notebook varsayılanıdır; ilgili hücrelerde ölçülmüş değer değildir. Aynı hücrede, erişilebilir yüzeyde, aynı anda bu üç reseptörün bulunması ayrıca gösterilmelidir. 15 nm yarıçap ve 500 reseptör/µm² için diskte beklenen reseptör sayısı yalnızca 0.353'tür. Sabit ve bağımsız Poisson dağılımı varsayılırsa 300 ve 200 reseptör/µm² olan iki diğer türün bu diskte en az birer kopyasının birlikte bulunma olasılığı yaklaşık %2.52'dir. Bu hesap da senaryodur; reseptör hareketi ve kümelenme sonucu değiştirebilir.

`(1+N_i*Ceff/Kd_i)^v_i` formülü reseptör kimliğini, yerel reseptör tükenmesini veya aynı reseptörün iki kolla işgal edilememesini açıkça takip etmez. Sabit mesafedeki Ceff'i doğrudan bir erişim diski içindeki tüm reseptörlere uygulamak da onların mesafe dağılımını çözmez. Yüzey üzerinde konum dağılımının integrali veya konumları açıkça örnekleyen model gerekir.

İki farklı Ceff'in geometrik ortalaması sadece iki sayının çarpımını korur. En zayıf kolu, farklı tekli/ikili durumları veya 12-valanslı seçicilik polinomunu korumaz. Linker RMS uzunluğuna ortalama binder boyunu eklemek de fiziksel olarak doğrulanmış bir erişim yarıçapı değildir.

Seçicilik hücresinin `z0=exp(-attach_cost)` ifadesi ligand konsantrasyonunu açıkça parametreleştirmediğinden theta'yı deneysel mutlak bağlı fraksiyon olarak okumamak gerekir. Süperseçicilik literatüründe valans, bağ gücü ve çözeltideki konuk konsantrasyonu birlikte etkilidir: [Martinez-Veracoechea ve Frenkel 2011](https://pmc.ncbi.nlm.nih.gov/articles/PMC3131366/).

## Uygun kullanım ve sonraki adım

Bu hücreyi **belirtilen ideal geometri altında linker erişim taraması** olarak kullan. İlk olarak yanlış Ceff aktarımını, bütün kollarda kontur sınırını ve eksik-arayüz kabulünü düzelt; kazancı ilk kola koşullu ağırlık oranı olarak adlandır. Sonra gerçek yapının valansını belirle ve mümkünse tam reseptörleri aynı membran referansına yerleştirerek ortak sterik/yönelim değerlendirmesi yap. Tam avidite ve durum olasılıkları için mevcut `avidity_sim` durum modeli bir başlangıç olabilir, fakat onun da yönelim/membran varsayımları ayrıca ele alınmalıdır.

İnceleme sırasında üretim notebook'ları ve eklenen hücrenin algoritması değiştirilmedi. Önceki Colab ihracında `pdb_override` boş olmasına rağmen 4. bölümün açıklamasında 1BRS yazması bir metin tutarsızlığıdır; tek binder için linker kontrolü gerçekten atlanır.
