"""Tether istatistiği: Fourier uzayında zincir kompozisyonu.

Matematiksel çekirdek
---------------------
İdeal (etkileşimsiz) bir zincirde ardışık segmentlerin uç-uca vektörleri
bağımsızdır, dolayısıyla toplam uç-uca vektörün olasılık yoğunluğu
segmentlerinkilerin *konvolüsyonu*, karakteristik fonksiyonu ise
*çarpımı*dır:

    Phi(k) = prod_s phi_s(k),      phi_s(k) = <exp(i k . r_s)>

İzotropik segmentler için phi yalnızca |k|'ya bağlıdır. Üç temel segment:

    serbest-eklemli çubuk (Kuhn), uzunluk b :  phi = sinc(kb) = sin(kb)/(kb)
    rijit çubuk, uzunluk L                  :  phi = sinc(kL)
    Gauss yayı, <r^2> = m                   :  phi = exp(-k^2 m / 6)

Bize iki türev nicelik lazım:

1) Radyal yoğunluk (sabit-geometri modu; reseptör konumu bilinen hâl)

       P(r) = 1/(2 pi^2 r) * int_0^inf k sin(kr) Phi(k) dk        [nm^-3]

2) Düzlemsel erişim  A(dz) (düzensiz yüzey modu; reseptörler bir düzlemde
   sürekli dağılmış)

       A(dz) = int_R^2 dx dy  P(sqrt(x^2 + y^2 + dz^2))           [nm^-1]

   Kapalı bir özdeşlik işi çok kolaylaştırır: izotropik bir 3B yoğunluğun
   bir düzlem üzerindeki integrali, tek bir Kartezyen bileşenin marjinal
   yoğunluğuna eşittir:

       A(dz) = p_z(dz) = (1/pi) int_0^inf Phi(k) cos(k dz) dk

   ve ayrıca      P(r) = -(1/(2 pi r)) * dp_z/dr .

Yani tek bir kosinüs dönüşümü her iki niceliği de verir. Sayısal yol
budur: Phi(k) düzgün bir k-ızgarasında örneklenir, DCT-I ile p_z(z)
elde edilir, P(r) türevden gelir.

Düzenleyici (regularizer)
-------------------------
Rijit çubuk gibi segmentlerin P(r)'si bir delta dağılımıdır ve Phi(k)
sönmez. Bu yüzden her dönüşümde bir çözünürlük parametresi eps ile
    Phi(k) -> Phi(k) * exp(-(k eps)^2 / 6)
uygulanır; bu, P'yi <r^2>=eps^2 olan bir Gauss ile konvolve etmeye
denktir. eps fiziksel bir "bağlanma cebi toleransı" gibi okunabilir ve
raporlanır -- gizli bir kesme (truncation) hilesi değildir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from scipy.fft import dct


# --------------------------------------------------------------------------
# Segmentler
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    """Zincir segmenti için soyut arayüz."""

    def phi(self, k: np.ndarray) -> np.ndarray:  # pragma: no cover - arayüz
        raise NotImplementedError

    @property
    def contour(self) -> float:
        """Maksimum uzayabileceği mesafe [nm]. Gauss için sonsuz."""
        raise NotImplementedError

    @property
    def msq(self) -> float:
        """Ortalama kare uç-uca uzunluk <r^2> [nm^2]."""
        raise NotImplementedError

    def sample(self, rng: np.random.Generator, size: int) -> np.ndarray:
        """Uç-uca vektörlerden (size, 3) örnek. Fourier yolundan bağımsız."""
        raise NotImplementedError


def _unit_vectors(rng: np.random.Generator, size: int) -> np.ndarray:
    """Küre yüzeyinde düzgün dağılmış birim vektörler, (size, 3)."""
    z = rng.uniform(-1.0, 1.0, size)
    phi = rng.uniform(0.0, 2.0 * np.pi, size)
    s = np.sqrt(np.maximum(1.0 - z**2, 0.0))
    return np.column_stack([s * np.cos(phi), s * np.sin(phi), z])


def _sinc(x: np.ndarray) -> np.ndarray:
    """sin(x)/x, x=0'da 1 (numpy.sinc pi ölçekli olduğu için kendi sürümümüz)."""
    out = np.ones_like(x)
    nz = x != 0.0
    out[nz] = np.sin(x[nz]) / x[nz]
    return out


@dataclass(frozen=True)
class Rod(Segment):
    """Uçlarından serbestçe eklemli rijit çubuk, uzunluk L."""

    length: float

    def phi(self, k: np.ndarray) -> np.ndarray:
        return _sinc(k * self.length)

    @property
    def contour(self) -> float:
        return self.length

    @property
    def msq(self) -> float:
        return self.length**2

    def sample(self, rng: np.random.Generator, size: int) -> np.ndarray:
        return _unit_vectors(rng, size) * self.length


@dataclass(frozen=True)
class FJC(Segment):
    """Serbest-eklemli zincir: n adet b uzunluklu Kuhn segmenti."""

    b: float
    n: int

    def phi(self, k: np.ndarray) -> np.ndarray:
        return _sinc(k * self.b) ** self.n

    @property
    def contour(self) -> float:
        return self.b * self.n

    @property
    def msq(self) -> float:
        return self.n * self.b**2

    def sample(self, rng: np.random.Generator, size: int) -> np.ndarray:
        out = np.zeros((size, 3))
        for _ in range(self.n):
            out += _unit_vectors(rng, size) * self.b
        return out


@dataclass(frozen=True)
class Gaussian(Segment):
    """İdeal Gauss yayı; sonlu uzayabilirlik sınırı YOKTUR."""

    msq_value: float

    def phi(self, k: np.ndarray) -> np.ndarray:
        return np.exp(-(k**2) * self.msq_value / 6.0)

    @property
    def contour(self) -> float:
        return float("inf")

    @property
    def msq(self) -> float:
        return self.msq_value

    def sample(self, rng: np.random.Generator, size: int) -> np.ndarray:
        return rng.normal(scale=np.sqrt(self.msq_value / 3.0), size=(size, 3))


def wlc(contour_length: float, persistence_length: float) -> "Chain":
    """Kurtçuk-benzeri zinciri (WLC) eşdeğer serbest-eklemli zincire eşler.

    Eşleme, WLC'nin uç-uca dağılımının ilk iki momentini *tam* tutturur:

        kontur  = L_c
        <r^2>   = 2 l_p L_c  -  2 l_p^2 (1 - exp(-L_c/l_p))   (Kratky-Porod)

    Bunun için n adet b uzunluklu Kuhn çubuğu + 1 adet c uzunluklu artık
    çubuk kullanılır (n b + c = L_c, n b^2 + c^2 = <r^2>). İki bilinmeyen,
    iki denklem: b ikinci derece denklemden çözülür. Yuvarlama artığı yok.

    L_c <~ l_p (rijit rejim) hâlinde tek bir rijit çubuk döndürülür.

    Not: yalnızca ilk iki moment eşlenir; dağılımın tam şekli gerçek WLC
    değildir. Bu, avidite hesabında baskın olan büyüklükleri (erişim ve
    kontur sınırı) doğru verir, kuyruk şeklini yaklaşık verir.
    """
    if contour_length <= 0 or persistence_length <= 0:
        raise ValueError("contour_length ve persistence_length pozitif olmalı")

    L = float(contour_length)
    lp = float(persistence_length)
    # Kratky-Porod tam ifadesi
    msq_target = 2.0 * lp * L - 2.0 * lp**2 * (1.0 - np.exp(-L / lp))

    # Rijit limit: <r^2> -> L^2, tek çubuk yeterli
    if msq_target >= L**2 * (1.0 - 1e-9):
        return Chain.of(Rod(L))

    n_phys = max(1, int(round(L / (2.0 * lp))))
    for n in _candidate_counts(n_phys):
        disc = n**2 * L**2 - n * (n + 1) * (L**2 - msq_target)
        if disc < 0:
            continue
        root = np.sqrt(disc)
        for b in ((n * L + root) / (n * (n + 1)), (n * L - root) / (n * (n + 1))):
            if b <= 0:
                continue
            c = L - n * b
            if -1e-12 <= c <= b + 1e-12:
                c = max(c, 0.0)
                segs: list[Segment] = [FJC(b=b, n=n)]
                if c > 1e-9 * L:
                    segs.append(Rod(c))
                return Chain(tuple(segs))

    # Hiçbir geçerli çözüm yoksa (beklenmez): momentleri koruyan Gauss+çubuk
    return Chain.of(Rod(L * 1e-9), Gaussian(msq_target))


def _candidate_counts(n_phys: int) -> list[int]:
    """Fiziksel Kuhn sayısından başlayıp dışa doğru aday n değerleri."""
    out = [n_phys]
    for d in range(1, 6):
        if n_phys - d >= 1:
            out.append(n_phys - d)
        out.append(n_phys + d)
    return out


def wlc_report(contour_length: float, persistence_length: float) -> dict:
    """WLC -> FJC eşlemesinin moment uyumunu raporlar."""
    ch = wlc(contour_length, persistence_length)
    L, lp = float(contour_length), float(persistence_length)
    target = 2.0 * lp * L - 2.0 * lp**2 * (1.0 - np.exp(-L / lp))
    return {
        "n_segments": len(ch.segments),
        "contour_nm": ch.contour,
        "contour_target_nm": L,
        "msq_model_nm2": ch.msq,
        "msq_target_nm2": target,
        "rel_error_msq": (ch.msq - target) / target,
        "rel_error_contour": (ch.contour - L) / L,
    }


def peptide_linker(
    n_residues: int,
    rise_per_residue: float = 0.365,
    persistence_length: float = 0.5,
) -> "Chain":
    """Esnek peptid bağlayıcı için pratik yapıcı.

    Varsayılan sabitler (residü başına kontur artışı, persistans uzunluğu)
    açık parametrelerdir; modelin matematiği bunlardan bağımsızdır ve her
    ikisi de duyarlılık taramasına sokulabilir.
    """
    return wlc(n_residues * rise_per_residue, persistence_length)


# --------------------------------------------------------------------------
# Zincir = segment dizisi
# --------------------------------------------------------------------------


@dataclass
class Chain:
    """Sıralı segmentlerden oluşan ideal zincir."""

    segments: tuple[Segment, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self.segments = tuple(self.segments)

    @classmethod
    def of(cls, *parts: "Segment | Chain") -> "Chain":
        """Segment ve/veya Chain parçalarını tek bir zincire düzleştirir."""
        segs: list[Segment] = []
        for p in parts:
            if isinstance(p, Chain):
                segs.extend(p.segments)
            else:
                segs.append(p)
        return cls(tuple(segs))

    def __add__(self, other: "Chain") -> "Chain":
        return Chain(self.segments + other.segments)

    @property
    def contour(self) -> float:
        return float(sum(s.contour for s in self.segments))

    @property
    def msq(self) -> float:
        return float(sum(s.msq for s in self.segments))

    @property
    def rms(self) -> float:
        return float(np.sqrt(self.msq))

    def phi(self, k: np.ndarray) -> np.ndarray:
        out = np.ones_like(k)
        for s in self.segments:
            out = out * s.phi(k)
        return out

    def is_empty(self) -> bool:
        return len(self.segments) == 0

    def sample(self, rng: np.random.Generator, size: int) -> np.ndarray:
        """Toplam uç-uca vektörlerden (size, 3) örnek."""
        out = np.zeros((size, 3))
        for seg in self.segments:
            out += seg.sample(rng, size)
        return out


# --------------------------------------------------------------------------
# Sayısal dönüşüm
# --------------------------------------------------------------------------


@dataclass
class TetherGrid:
    """Bir zincir için önceden hesaplanmış p_z(z) ve P(r) tabloları.

    Parameters
    ----------
    chain : Chain
    eps : float
        Çözünürlük / yumuşatma uzunluğu [nm]. Delta-benzeri yoğunlukları
        <r^2> = eps^2 olan bir Gauss ile konvolve eder.
    z_max : float
        Tablo üst sınırı [nm]. Varsayılan: konturun 1.15 katı (sonluysa),
        aksi hâlde 6 x rms.
    n_grid : int
        k ve z ızgara noktası sayısı (2^m + 1 tercih edilir).
    """

    chain: Chain
    eps: float = 0.25
    z_max: float | None = None
    n_grid: int = 2**14 + 1

    def __post_init__(self) -> None:
        if self.z_max is None:
            c = self.chain.contour
            self.z_max = 1.15 * c if np.isfinite(c) else 6.0 * max(self.chain.rms, self.eps)
            self.z_max = max(self.z_max, 4.0 * self.eps)

        n = self.n_grid
        dz = self.z_max / (n - 1)
        dk = np.pi / self.z_max
        self._z = np.arange(n) * dz
        self._k = np.arange(n) * dk

        phi = self.chain.phi(self._k)
        phi = phi * np.exp(-(self._k**2) * self.eps**2 / 6.0)

        # DCT-I  <->  trapez kuralı ile kosinüs dönüşümü
        # y_m = phi_0 + (-1)^m phi_{n-1} + 2 sum_{j=1}^{n-2} phi_j cos(pi j m/(n-1))
        # int_0^inf phi cos(k z_m) dk ~= dk/2 * y_m
        y = dct(phi, type=1)
        self._pz = (dk / 2.0) * y / np.pi  # [nm^-1]
        self._dz = dz

        # P(r) = -(1/(2 pi r)) dp_z/dr
        dpz = np.gradient(self._pz, dz)
        with np.errstate(divide="ignore", invalid="ignore"):
            pr = -dpz / (2.0 * np.pi * self._z)
        # r -> 0 limiti: P(0) sonlu; kübik ekstrapolasyon yerine ikinci
        # noktadan lineer geri-alım yeterli (tablo zaten yumuşatılmış).
        pr[0] = pr[1] + (pr[1] - pr[2])
        self._pr = np.maximum(pr, 0.0)  # sayısal salınımdan negatif sızmayı kes

    # --- erişimciler -----------------------------------------------------

    @property
    def z(self) -> np.ndarray:
        return self._z

    def areal_reach(self, dz: float | np.ndarray) -> np.ndarray:
        """A(dz) = int_plane P  [nm^-1]; düzlem, zincir kökünden dz yükseklikte."""
        a = np.interp(np.abs(np.asarray(dz, dtype=float)), self._z, self._pz, right=0.0)
        return np.maximum(a, 0.0)

    def radial_density(self, r: float | np.ndarray) -> np.ndarray:
        """P(r)  [nm^-3]; uç-uca mesafenin radyal olasılık yoğunluğu."""
        p = np.interp(np.asarray(r, dtype=float), self._z, self._pr, right=0.0)
        return np.maximum(p, 0.0)

    # --- doğrulama -------------------------------------------------------

    def check_normalization(self) -> dict:
        """int 4 pi r^2 P(r) dr = 1 ve int p_z dz (tam eksende) = 1 kontrolü."""
        r = self._z
        norm_3d = np.trapezoid(4.0 * np.pi * r**2 * self._pr, r)
        norm_1d = 2.0 * np.trapezoid(self._pz, r)  # tam eksen = 2 x yarım eksen
        msq = np.trapezoid(4.0 * np.pi * r**4 * self._pr, r)
        return {
            "norm_3d": float(norm_3d),
            "norm_1d": float(norm_1d),
            "msq_numeric": float(msq),
            "msq_analytic": self.chain.msq + self.eps**2,
        }
