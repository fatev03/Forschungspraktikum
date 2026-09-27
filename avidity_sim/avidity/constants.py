"""Birim dönüşümleri ve fiziksel sabitler.

Paket genelinde kullanılan birim sistemi:
    uzunluk   nm
    hacim     nm^3
    yüzey     nm^-2  (reseptör yoğunluğu)
    derişim   M      (mol/L)
    zaman     s
    enerji    kT     (boyutsuz, log-ağırlık olarak)
"""

AVOGADRO = 6.02214076e23  # 1/mol

# 1 L = (1e8 nm)^3 = 1e24 nm^3  =>  1 parçacık/nm^3 = 1e24 / N_A  M
NM3_TO_MOLAR = 1e24 / AVOGADRO  # ~1.6605 M per (1/nm^3)

MOLAR_TO_NM3 = 1.0 / NM3_TO_MOLAR  # ~0.6022 (1/nm^3) per M

# kolaylık
UM2_PER_NM2 = 1e-6  # 1 nm^-2 = 1e6 um^-2  -> ters yönde dikkat
NM2_PER_UM2 = 1e6
