# avidity_sim

Çok-değerlikli bağlanmanın **avidite ve durum-doluluğu simülatörü**.
Doğrusal bir kaset üzerindeki $n$ domain ile $n$ tür reseptör taşıyan bir
yüzey arasındaki etkileşimi, $2^n$ bağlanma durumu üzerinde çözer.

Matematiksel türetim, varsayımlar ve doğrulama listesi: **[MODEL.md](MODEL.md)**

> Bu bir *affinity predictor* değildir. Monovalent $K_D$ değerleri
> **girdidir**. Çıktı, aynı varsayımlar altında tasarımların **göreli**
> karşılaştırmasıdır.

---

## Kurulum

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python numpy scipy matplotlib pytest
```

## Çalıştırma

```bash
.venv/bin/python demo.py
```

```bash
.venv/bin/python -m pytest tests/ -q
```

---

## Katmanlar

| Modül | İçerik |
|---|---|
| `avidity/tether.py` | Zincir istatistiği. Fourier uzayında segment kompozisyonu; tek bir DCT-I'den hem düzlemsel erişim $A(\Delta z)$ hem radyal yoğunluk $P(r)$. |
| `avidity/model.py` | Durum ağırlıkları, öz-uyumlu reseptör tükenmesi (log-uzayı Newton), denge gözlenebilirleri. |
| `avidity/kinetics.py` | Tek-ligand CTMC (ikamet süresi, etkin $k_{\text{off}}$, gevşeme spektrumu) ve nonlineer popülasyon ODE'si. |
| `avidity/sweep.py` | Parametre tutamakları, yerel log-log duyarlılık, LHS + sıra-regresyonu ile küresel duyarlılık. |

## En küçük örnek

```python
from avidity import (Cassette, Domain, Receptor, Surface, System,
                     peptide_linker, residence_analysis)

sysm = System(
    Cassette(
        domains=[Domain("D1", kd=1e-6), Domain("D2", kd=3e-7), Domain("D3", kd=2e-6)],
        linkers=[peptide_linker(40), peptide_linker(40)],
    ),
    Surface([
        Receptor("R1", density=2e-3, height=4.0),   # nm^-2, nm
        Receptor("R2", density=1e-3, height=6.0),
        Receptor("R3", density=5e-4, height=3.0),
    ]),
)

eq = sysm.solve(1e-10)                  # M
print(eq.table())                       # durum dağılımı
print(eq.p_at_least(2))                 # P(>=2 bağ)
print(eq.p_conditional(2, [0, 1]))      # P(D3 | D1,D2)
print(residence_analysis(eq).tau_entry) # yüzeyde ortalama kalma süresi (s)
```

Sabit geometri (bilinen reseptör konumları) için
`Surface(..., mode="fixed")` ve `Receptor(..., position=(x, y, z))`.

---

## Demo çıktısından üç sonuç

Üç domain, $K_D = 1\,/\,0.3\,/\,2$ µM, reseptör yoğunlukları
$2000\,/\,1000\,/\,500$ µm⁻², 40-residü linkerler:

**1. Avidite kazancı büyük ama denge ve kinetikte farklı.**
Toplam bağlanmada en iyi monovalente göre **1339×**, ikamet süresinde
**602×** ($\tau$: 33 s → 20 000 s). Gevşeme spektrumu bir yavaş modu
($5\times10^{-5}$ s⁻¹) diğerlerinden (1–36 s⁻¹) ayırıyor.

**2. EC50 avidite ölçmez.**
Görünür EC50 $=1.6$ µM — en güçlü monovalent $K_D$'den (0.3 µM) *zayıf*.
Plato reseptör kapasitesiyle belirlenir ve yüksek $[L]$'de her reseptöre
ayrı bir ligand monovalent bağlanır.

**3. Üçlü bağlanma derişimde monoton değil (prozone).**
Üçlü-bağlı yoğunluk $4\times10^{-9}$ M'de tepe yapıp $10^{-3}$ M'de
tepenin %2'sine iniyor. Optimum bir doz vardır.

Ayrıca her linkerin optimum uzunluğu, yalnızca köprülediği epitop
yüksekliği farkıyla belirleniyor ($L_c^* = 3\Delta z^2/2\ell_p$); 2B
tarama analitik tahmini tutturuyor.

---

## Şekiller

| Dosya | İçerik |
|---|---|
| `figures/01_titrasyon.png` | Bağlanma izotermi (üçlü vs monovalent), prozone tepesi, valans dağılımı |
| `figures/02_linker_taramasi.png` | $L_{12} \times L_{23}$ taraması; sayısal vs analitik optimum |
| `figures/03_dissosiyasyon.png` | CTMC kaçış eğrileri ve ODE yıkama kinetiği |
| `figures/04_secicilik.png` | Reseptör yoğunluğu senaryolarında üçlü yoğunluk ve seçicilik |
| `figures/05_duyarlilik.png` | Yerel log-log duyarlılık |

---

## Doğrulama

`tests/test_core.py` — 29 test. Model yalnızca kendi kendiyle tutarlı
olduğunu değil, iddia ettiği özdeşlikleri **bağımsız yollarla** sınar:
Gauss kapalı formu, 2·10⁶ örnekli Monte Carlo, tam Langmuir limiti,
yol bağımsızlığı, ayrıntılı denge, Kolmogorov döngü kriteri, ODE sabit
noktasının denge çözücüsüyle örtüşmesi. Ayrıntılı liste MODEL.md §8.
