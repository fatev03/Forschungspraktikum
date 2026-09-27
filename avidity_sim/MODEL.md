# Çok-değerlikli avidite ve durum-doluluğu modeli

Doğrusal bir kaset üzerinde taşınan $n$ bağlayıcı domain'in, $n$ tür
reseptör taşıyan bir yüzeyle etkileşiminin istatistiksel-mekanik modeli.

---

## 0. Model ne verir, ne vermez

**Verir.** Belirli varsayımlar altında, bir tasarımın *göreli* avantajını:
durum dağılımı, koşullu bağlanma olasılıkları, ikamet süresi, ve bunların
$K_D$, reseptör yoğunluğu, linker uzunluğu ve epitop yüksekliğine
duyarlılığı. Tasarım karşılaştırması için kalibre edilebilir bir çerçeve.

**Vermez.** Mutlak bir bağlanma serbest enerjisi. Monovalent $K_{D,i}$
değerleri **girdidir**, çıktı değil. Model bunları tahmin etmez; onları
alıp çok-değerlikli sonuçlarına çevirir. Girdi $K_D$'ler yanlışsa çıktı da
yanlıştır — ve avidite üstel yükselttiği için hata da yükselir.

---

## 1. Notasyon

| Simge | Anlam | Birim |
|---|---|---|
| $n$ | domain / reseptör türü sayısı | — |
| $S \subseteq \{0,\dots,n-1\}$ | bağlı domain kümesi (durum) | — |
| $K_i$ | domain $i$'nin monovalent ayrışma sabiti | M |
| $k_{\mathrm{on},i}$, $k_{\mathrm{off},i}=K_i k_{\mathrm{on},i}$ | hız sabitleri | M⁻¹s⁻¹, s⁻¹ |
| $\sigma_i$, $\sigma_i^{\text{tot}}$ | serbest / toplam reseptör yoğunluğu | nm⁻² |
| $z_i$ | epitop yüksekliği | nm |
| $[L]$ | serbest ligand derişimi | M |
| $\kappa = 10^{24}/N_A \approx 1.6605$ | nm⁻³ → M | M·nm³ |

---

## 2. Tether istatistiği

### 2.1 Fourier uzayında kompozisyon

İdeal zincirde segmentlerin uç-uca vektörleri bağımsızdır, dolayısıyla
karakteristik fonksiyonlar çarpılır:

$$\Phi(k) = \prod_s \varphi_s(k)$$

| segment | $\varphi(k)$ | kontur | $\langle r^2\rangle$ |
|---|---|---|---|
| Kuhn çubuğu, $n$ adet, uzunluk $b$ | $\operatorname{sinc}^n(kb)$ | $nb$ | $nb^2$ |
| rijit çubuk, uzunluk $L$ | $\operatorname{sinc}(kL)$ | $L$ | $L^2$ |
| Gauss yayı | $e^{-k^2m/6}$ | $\infty$ | $m$ |

### 2.2 İki türev nicelik

**Radyal yoğunluk** (reseptör konumu bilinen hâl):

$$P(r) = \frac{1}{2\pi^2 r}\int_0^\infty k\sin(kr)\,\Phi(k)\,dk$$

**Düzlemsel erişim** (reseptörler bir düzlemde sürekli dağılmış):

$$A(\Delta z) = \int_{\mathbb{R}^2} dx\,dy\; P\!\left(\sqrt{x^2+y^2+\Delta z^2}\right)$$

Kilit özdeşlik — izotropik bir 3B yoğunluğun düzlem integrali, tek bir
Kartezyen bileşenin marjinal yoğunluğuna eşittir:

$$\boxed{\;A(\Delta z) \;=\; p_z(\Delta z) \;=\; \frac{1}{\pi}\int_0^\infty \Phi(k)\cos(k\,\Delta z)\,dk\;}$$

ve ters yönde $P(r) = -\dfrac{1}{2\pi r}\dfrac{dp_z}{dr}$.

Yani **tek bir kosinüs dönüşümü** (DCT-I) her iki niceliği birden verir.
Salınımlı integrallerle boğuşmaya gerek yok.

*Gauss kontrolü:* $\Phi = e^{-k^2m/6}$ için kapalı form
$A(\Delta z) = \sqrt{\alpha/\pi}\,e^{-\alpha \Delta z^2}$, $\alpha = 3/2m$.
Sayısal yol buna $\sim10^{-6}$ bağıl hatayla oturur.

### 2.3 Kontur sınırı fizikten gelir

FJC ve çubuk segmentlerinin $\Phi$'si, kontur uzunluğundan uzak
mesafelerde $P$ ve $A$'yı **tam olarak sıfıra** götürür. "Erişilemeyen
reseptör" bir veto kuralı değil, dağılımın kendi sonucudur. Gauss
segmentleri bu sınıra sahip değildir; o yüzden uzayabilirlik önemliyse
FJC/WLC kullanılmalıdır.

### 2.4 Düzenleyici

Rijit çubuğun $P$'si bir deltadır. Her dönüşümde
$\Phi \to \Phi\, e^{-(k\varepsilon)^2/6}$ uygulanır: bu, $P$'yi
$\langle r^2\rangle = \varepsilon^2$ olan bir Gauss'la konvolve etmektir.
$\varepsilon$ raporlanan, fiziksel olarak "bağlanma cebi toleransı" diye
okunabilen bir çözünürlük parametresidir — gizli bir kesme değildir.

### 2.5 WLC eşlemesi

WLC, ilk iki momenti **tam** tutturan bir FJC'ye eşlenir:
$n$ adet $b$ uzunluklu Kuhn çubuğu + 1 adet $c$ artık çubuğu,

$$nb + c = L_c, \qquad nb^2 + c^2 = 2\ell_p L_c - 2\ell_p^2\!\left(1 - e^{-L_c/\ell_p}\right)$$

İkinci denklemin sağ tarafı Kratky–Porod'un tam ifadesidir. İki bilinmeyen,
iki denklem; $b$ ikinci dereceden çözülür. Dağılımın *şekli* gerçek WLC
değildir, ama erişim ve kontur sınırı doğrudur.

---

## 3. Durum ağırlıkları

### 3.1 Formül

$S = (s_0 < s_1 < \dots < s_{m-1})$ için

$$w(S) \;=\; \underbrace{\frac{[L]}{K_{s_0}}\,\sigma_{s_0}}_{\text{çapa (3B)}}\;\times\; \prod_{k=0}^{m-2}\underbrace{\frac{c_{\text{eff}}(s_k, s_{k+1})}{K_{s_{k+1}}}}_{\text{kapanış (tether)}}$$

Birim: nm⁻². Etkin yerel derişim:

$$c_{\text{eff}}(i,j) = \begin{cases}
\kappa\,\sigma_j\,A_{ij}(|z_i - z_j|)\,\chi_{ij} & \text{düzensiz yüzey} \\[4pt]
\kappa\,P_{ij}(d_{ij})\,\chi_{ij} & \text{sabit geometri}
\end{cases}$$

$\chi_{ij}$: sterik erişim faktörü (glikokaliks, kalabalıklık). Varsayılan 1;
modelin bu etkileri *açıkça* dışarıda bıraktığı ve kullanıcının girmesi
gereken yer burasıdır.

### 3.2 Neden yalnızca ardışık çiftler?

İdeal zincirde domain konumları kontur boyunca bir **Markov zinciri**
oluşturur. Bu yüzden $S$'deki domain'lerin ortak konum yoğunluğu, $S$
içindeki *ardışık* çiftlerin geçiş çekirdeklerine ayrışır. Bağlı olmayan
ara domain'ler marjinalleştirilir — $\{0,2\}$ durumunda 0–2 tether'ı
linker₀ + domain₁ + linker₁'dir.

Üç sonuç:

1. **Yol bağımsızlığı.** $w(S)$, hangi bağın önce kurulduğuna bağlı
   değildir. Termodinamiğin gerektirdiği bu özellik modelde kimliksel
   olarak sağlanır, elle dayatılmaz.

2. **İlmek-kapanışı bedeli doğru çıkar.** Zaten bağlı iki domain'in
   *arasına* üçüncüsünü yerleştirmek, tek bir komşuya erişmekten pahalıdır:
   $$K_1\frac{w(\{0,1,2\})}{w(\{0,2\})} = \frac{c_{\text{eff}}(0,1)\,c_{\text{eff}}(1,2)}{c_{\text{eff}}(0,2)}$$
   Bu, "en yakın komşuya eriş" kestirmesinin vereceği $c_{\text{eff}}(0,1)$
   değerinden farklıdır. (Bu kestirme kodun ilk sürümünde vardı ve
   ayrıntılı dengeyi bozuyordu.)

3. **Çok-doğrusallık.** Her bağlı domain'in $\sigma$'sı ağırlıkta tam bir
   kez geçer:
   $$w(S) = C_S \prod_{i\in S}\sigma_i$$
   Bu, doygunluk denklemini çözülebilir kılar (§4).

---

## 4. Doygunluk

Serbest reseptör yoğunlukları şunu sağlamalı:

$$\sigma_i + \sum_{S \ni i} w(S) = \sigma_i^{\text{tot}}$$

$w$ çok-doğrusal olduğundan, $x = \ln\sigma$ değişkeninde sol taraf bir
**log-sum-exp**'tir:

$$r_i(x) = \log\!\Big(e^{x_i} + \sum_{S\ni i} C_S\, e^{\sum_{j\in S}x_j}\Big) - \log\sigma_i^{\text{tot}} = 0$$

Her $r_i$, $x$'in her bileşeninde kesin artan ve konvekstir. Bu, kimyasal
denge kodlarının standart formudur; analitik Jacobian'lı Newton ile
güvenilir çözülür.

> **Not.** Doğrudan $\sigma$ uzayında sönümlü sabit-nokta iterasyonu güçlü
> avidite rejiminde (bağlanmanın $\sigma$'da kübik büyüdüğü yerde)
> **yakınsamaz**. İlk uygulamada 500 iterasyonda bağıl artık $10^{-1}$
> düzeyinde kalıyordu. Log uzayı bu sorunu yapısal olarak çözer.

Ligand ayak izi dışlaması (isteğe bağlı), öz-uyumlu Langmuir formunda:
$\rho_{\text{tot}} = W/(1 + a_L W)$.

---

## 5. Kinetik

### 5.1 Tek-ligand CTMC

Bağlı durumlar üzerinde üreteç $Q$; boş küme yutucu:

$$S \to S\cup\{j\}:\; k_{\mathrm{on},j}\,c_{\text{eff}}(j\,|\,S), \qquad
S \to S\setminus\{j\}:\; k_{\mathrm{off},j}$$

Koşullu etkin derişim **denge ağırlıklarından türetilir**:

$$c_{\text{eff}}(j\,|\,S) = K_j\,\frac{w(S\cup\{j\})}{w(S)}$$

Bu tanım ayrıntılı dengeyi kimliksel olarak sağlar:

$$w(S)\,k_{S\to S+j} = k_{\mathrm{on},j}K_j\,w(S{+}j) = k_{\mathrm{off},j}\,w(S{+}j)$$

Dolayısıyla Kolmogorov döngü kriteri de otomatik sağlanır — hiper-küpteki
her döngüde ileri ve geri hız çarpımları eşittir.

**Ortalama ilk-geçiş süresi:** $\tau = -Q^{-1}\mathbf{1}$.
**Hayatta kalma:** $\mathrm{Sv}(t) = \mathbf{1}^\top e^{Q^\top t} p_0$
(satır = kaynak konvansiyonu; $\int_0^\infty \mathrm{Sv} = p_0\cdot\tau$).
**Gevşeme spektrumu:** $-\mathrm{Re}\,\lambda(Q)$ — avidite imzası, bir yavaş
modun diğerlerinden kopmasıdır.

Erişilemez durumlar ($w = 0$: veto, $K_D=\infty$, $\sigma=0$) üretece
alınmaz; alınırlarsa tanımsız hız üretirler.

### 5.2 Popülasyon ODE'si

Reseptör tükenmesi yüzünden nonlineer:

$$\dot\rho_S = \sum_{S'}\rho_{S'}q_{S'\to S} - \rho_S\sum q_{S\to\cdot} + \delta_{|S|,1}\,k_{\mathrm{on},i}[L]\sigma_i$$

Varış hız sabiti ayrıntılı dengeden $k_{\mathrm{on},i}$ olarak sabitlenir;
böylece ODE'nin sabit noktası denge çözücüsüyle **aynıdır** (test edilir).

---

## 6. Gözlenebilirler ve tuzakları

| Nicelik | Tanım | Uyarı |
|---|---|---|
| $\rho(S)$ | durum yoğunluğu | — |
| $P(\geq k)$ | bağlılar içinde $k$+ bağ payı | güçlü avidite'de 1'e doyar, duyarlılığı sıfırlanır |
| $P(j \mid S)$ | koşullu bağlanma | — |
| $\tau_{\text{entry}}$ | varıştan itibaren ikamet | avidite'nin en temiz ölçüsü |
| avidite kazancı | çok-değerlikli / en iyi monovalent | denge ve kinetik sürümleri farklıdır |
| EC50 | yarı-plato derişimi | **avidite ölçmez** — aşağıya bakınız |

### 6.1 EC50 neden avidite ölçmez

Plato, reseptör kapasitesiyle belirlenir. Yüksek $[L]$'de her reseptöre
ayrı bir ligand monovalent bağlanır, dolayısıyla yarı-plato noktası
monovalent $K_D$ tarafından yönetilir. Demo sisteminde EC50 $= 1.6\times10^{-6}$ M,
en güçlü monovalent $K_D = 3\times10^{-7}$ M — oysa denge avidite kazancı
1339×, kinetik kazanç 602×.

### 6.2 Prozone (hook) etkisi

Çok-değerlikli durumların yoğunluğu derişimde **monoton değildir**. Ligand
fazlası reseptörleri tek tek işgal eder ve ortak bağlanma için reseptör
bırakmaz. Demo sisteminde üçlü-bağlı yoğunluk $4\times10^{-9}$ M'de tepe
yapar; $10^{-3}$ M'de tepenin %2'sine iner.

*"Daha çok ligand her zaman daha çok üçlü bağlanma" yanlıştır.*

### 6.3 Linker optimumu

Gauss rejiminde $A(\Delta z) = \sqrt{3/2\pi m}\,e^{-3\Delta z^2/2m}$ ve
$m \approx 2\ell_p L_c$, dolayısıyla

$$\frac{\partial A}{\partial m} = 0 \;\Longrightarrow\; m^* = 3\Delta z^2 \;\Longrightarrow\; L_c^* = \frac{3\Delta z^2}{2\ell_p}$$

Kısa linker yükseklik farkını köprüleyemez, uzun linker entropik olarak
seyrelir. Her linkerin optimumu **yalnızca kendi köprülediği** $\Delta z$
ile belirlenir — bu, ardışık-çift ayrışmasının bağımsız bir sınamasıdır ve
2B tarama analitik tahmini tutturur (demo: sayısal (11, 26) nm, analitik
(12, 27) nm).

**İki mod farklı optimum verir.** Sabit geometride $c_{\text{eff}}$'e giren
3B yoğunluktur, düzensiz yüzeyde düzlemsel marjinal — $m$ üsleri farklıdır:

| mod | $c_{\text{eff}} \propto$ | optimum |
|---|---|---|
| sabit geometri | $P(d) \sim m^{-3/2} e^{-3d^2/2m}$ | $m^* = d^2$ |
| düzensiz yüzey | $A(\Delta z) \sim m^{-1/2} e^{-3\Delta z^2/2m}$ | $m^* = 3\Delta z^2$ |

Üs farkı optimumu **3 kat** kaydırır. Tasarlanmış bir yüzey deseni için
optimize edilen linker, hücre yüzeyinde optimal değildir.

Ayrıca sabit geometride $P(d)$, $d$'de **monoton azalır** — burada iç
optimum yoktur. (Radyal dağılım $4\pi d^2 P(d)$ ile karıştırmamak gerekir;
$c_{\text{eff}}$'e giren yoğunluğun kendisidir.)

---

## 7. Duyarlılık

**Yerel:** $S = \partial\ln y / \partial\ln\theta$, merkezi farkla. Ölçekten
bağımsız olduğu için farklı birimlerdeki parametreler kıyaslanabilir.

**Küresel:** Latin hiperküp + sıra-dönüşümlü regresyon (SRRC). Birlikte
raporlanan $R^2$ düşükse ($\lesssim 0.7$) model o bölgede güçlü
etkileşimlidir ve SRRC tek başına yanıltır.

---

## 8. Doğrulama

`tests/test_core.py` — 25 test. Her biri modelin *iddia ettiği* bir
özdeşliği bağımsız bir yolla sınar.

| Ne | Nasıl |
|---|---|
| $A(\Delta z)$, $P(r)$ | Gauss kapalı formu (bağıl hata $10^{-6}$) |
| $A(\Delta z)$ | 2·10⁶ örnekli Monte Carlo |
| zincir kompozisyonu | MC konvolüsyonu |
| normalizasyon, 2. moment | sayısal integral |
| WLC eşlemesi | Kratky–Porod momentleri (hata $<10^{-9}$) |
| kontur sınırı | $P(r > L_c) = 0$ |
| monovalent limit | tam Langmuir izotermi |
| iki-değerlikli ağırlıklar | elle yazılmış kapalı form |
| **yol bağımsızlığı** | her çapa seçimi için ayrı açılım |
| çok-doğrusallık | rastgele $\sigma$'larda $w = C_S\prod\sigma$ |
| reseptör korunumu | $\sigma_{\text{free}} + \text{bağlı} = \sigma_{\text{tot}}$ |
| **ayrıntılı denge** | her kenarda $w q = w' q'$ |
| **Kolmogorov döngüsü** | hiper-küp döngüsünde ileri = geri |
| monovalent MFPT | $\tau = 1/k_{\text{off}}$ |
| $\int \mathrm{Sv}\,dt$ | $= \tau$ |
| **ODE sabit noktası** | $=$ denge çözücüsü |
| çözücü kararlılığı | 12 onluk mertebe boyunca |
| linker optimumu | analitik $3\Delta z^2/2\ell_p$ |
| prozone tepesi | iç maksimum + monoton toplam |

---

## 9. Varsayımlar

Modelin açıkça **dışarıda bıraktıkları**:

1. **İdeal zincir.** Dışlanan hacim, domain–domain ve domain–yüzey
   etkileşimleri yok. Kalabalık yüzeylerde $A$ abartılı olur.
2. **Rijit domain'ler, izotropik eklemler.** Bağlanma yönelimi (epitopun
   hangi açıdan yaklaşılması gerektiği) modellenmiyor; $\chi_{ij}$ bunun
   için kaba bir tutamak.
3. **Düzensiz yüzey ortalama-alan.** Reseptörler bağımsız ve düzgün
   dağılmış varsayılır; kümelenme (clustering) yok.
4. **Sabit reseptör konumları** (`fixed` modu) ya da **tam hareketlilik**
   (`disordered` modu) — aradaki kısmi difüzyon rejimi yok.
5. **Membran dışlaması yok.** Tether'ın membranın içinden geçmesi
   engellenmiyor; bu $A$'yı en fazla ~2× abartır.
6. **Tek kaset.** Aynı taşıyıcı üzerinde birden çok kaset varsa, kaset-içi
   ve kasetler-arası avidite ayrılmalıdır — modelde yok.
7. **Rekabet yok.** Çözeltide yarışan ligandlar modellenmiyor.
8. **$K_D$'ler girdidir.** Tahmin edilmezler.

---

## 10. Genişletme noktaları

| İstenen | Nereye dokunulur |
|---|---|
| yeni segment tipi | `tether.Segment` alt sınıfı + `phi`, `contour`, `msq`, `sample` |
| dallanmış kaset | `Cassette.tether` ve §3.2'deki ardışık-çift kuralı (Markov ağacına genelleşir) |
| reseptör kümelenmesi | `c_eff` içinde $\sigma_j \to$ çift-korelasyon fonksiyonu ile ağırlıklı yoğunluk |
| yönelim kısıtı | $\chi_{ij}$ yerine yönelime bağlı faktör, ya da $\Phi$'ye yönelim çekirdeği |
| kuvvet altında bağlanma | `kinetics` içinde $k_{\text{off}}$'a Bell terimi; ayrıntılı denge bozulur, akı dengesi gerekir |
| deneysel kalibrasyon | ikili kaset kontrolleriyle $\chi_{ij}$ ve $\ell_p$ uydurma |

---

## 11. İsimlendirme

Bu bir **avidite ve durum-doluluğu simülatörüdür**, bir *affinity
predictor* değil. İkinci isim, modelin taşıyamayacağı bir iddiadır:
monovalent $K_D$'ler girdi olduğu sürece çıktı, senaryo bazlı **göreli**
sıralamadır.
