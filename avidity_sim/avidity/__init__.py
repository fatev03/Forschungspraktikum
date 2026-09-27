"""Çok-değerlikli avidite ve durum-doluluğu simülatörü.

Katmanlar
---------
``tether``    zincir istatistiği: Fourier kompozisyonu, A(dz), P(r)
``model``     durum ağırlıkları, doygunluk, denge gözlenebilirleri
``kinetics``  tek-ligand CTMC (ikamet süresi) + popülasyon ODE'si
``sweep``     parametre tutamakları, yerel/küresel duyarlılık

Matematiksel ayrıntılar için MODEL.md.
"""

from .constants import NM3_TO_MOLAR
from .kinetics import (
    ResidenceAnalysis,
    Trajectory,
    kinetic_avidity,
    residence_analysis,
    simulate,
    washout,
)
from .model import (
    Cassette,
    Domain,
    Equilibrium,
    Receptor,
    Surface,
    System,
    all_states,
    apparent_kd,
    avidity_enhancement,
    monovalent_reference,
    state_density_profile,
    titration,
)
from .tether import (
    FJC,
    Chain,
    Gaussian,
    Rod,
    Segment,
    TetherGrid,
    peptide_linker,
    wlc,
    wlc_report,
)

__all__ = [
    "NM3_TO_MOLAR",
    "Segment", "Rod", "FJC", "Gaussian", "Chain", "TetherGrid",
    "wlc", "wlc_report", "peptide_linker",
    "Domain", "Receptor", "Cassette", "Surface", "System", "Equilibrium",
    "all_states", "titration", "apparent_kd", "avidity_enhancement",
    "monovalent_reference", "state_density_profile",
    "ResidenceAnalysis", "residence_analysis", "kinetic_avidity",
    "Trajectory", "simulate", "washout",
]
