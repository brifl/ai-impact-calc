
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, Tuple, Dict
from enum import Enum

# =============================================================================
# Factor groups: meta + detailed
# Each group returns:
# - additive_component: in [-1, 1]
# - gates: dict[str, multiplier_0_1]
# - multipliers: dict[str, multiplier_0_1] (non-gate compounding)
# - risk: separate risk contribution (0..1 or -1..1 as desired)
# =============================================================================

@dataclass
class FactorOutput:
    additive: float  # [-1, +1]
    gates: Dict[str, float] = field(default_factory=dict)         # [0,1]
    multipliers: Dict[str, float] = field(default_factory=dict)   # [0,1] or >1 if you choose
    risk: Dict[str, float] = field(default_factory=dict)          # risk channels, usually [0,1]
    debug: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Rubric configuration (rough draft)
# =============================================================================

@dataclass(frozen=True)
class RubricWeights:
    """
    High-level weights. Keep simple initially; refine later.
    additive weights should sum to ~1 across included groups.
    """
    # Meta factor weights (additive baseline)
    w_macro: float = 0.12
    w_constraint: float = 0.18
    w_trust: float = 0.18
    w_control_points: float = 0.18
    w_adaptation: float = 0.14
    w_georeg: float = 0.10
    w_capital_alloc: float = 0.10

    # Risk integration
    # risk_weight controls how much risk reduces final score
    risk_weight: float = 0.35

    # Hard caps
    score_min: float = -100.0
    score_max: float = 100.0


# =============================================================================
# Scorer
# =============================================================================

@dataclass
class ScoreBreakdown:
    company: str
    horizon: TimeHorizon
    as_of: Optional[str]
    regime_mixture: RegimeMixture
    group_outputs: Dict[str, FactorOutput]
    base_additive: float
    gate_multiplier: float
    multiplier_product: float
    risk_index: float
    final_score: float


# =============================================================================
# Time/Horizon + Regime selection
# =============================================================================
class TimeHorizon(str, Enum):
    SHORT = "0-2y"
    MID = "2-5y"
    LONG = "5-12y"

@dataclass
class Signal:
    """
    value: numeric value or score (provider-defined)
    scale: describes the range/meaning of value, e.g. "raw", "score_-1_1", "percent", etc.
    confidence: 0..1, provider's quality estimate
    freshness_days: age of the underlying data
    """
    value: float
    scale: str = "raw"
    confidence: float = 0.8
    freshness_days: int = 30
    details: Mapping[str, Any] = field(default_factory=dict)

class Regime(str, Enum):
    POWER_CONSTRAINED_BOOM = "power_constrained_boom"
    POWER_CONSTRAINED_STAGFLATION = "power_constrained_stagflation"
    TRUST_COLLAPSE = "trust_collapse"
    REGULATORY_CLAMPDOWN = "regulatory_clampdown"
    HYPER_COMPETITION = "hyper_competition"
    CAPITAL_CONCENTRATION = "capital_concentration"
    GEOPOLITICAL_BIFURCATION = "geopolitical_bifurcation"
    SECURITY_ARMS_RACE = "security_arms_race"

@dataclass(frozen=True)
class RegimeMixture:
    """
    A probability-like mixture. We do not forecast here;
    magic_data_provider can provide weights if desired, otherwise caller sets.
    """
    weights: Mapping[Regime, float]

    def normalized(self) -> "RegimeMixture":
        s = sum(max(0.0, float(v)) for v in self.weights.values())
        if s <= 0:
            # default: base-ish mixture
            default = {
                Regime.POWER_CONSTRAINED_BOOM: 0.35,
                Regime.SECURITY_ARMS_RACE: 0.35,
                Regime.TRUST_COLLAPSE: 0.15,
                Regime.HYPER_COMPETITION: 0.15,
            }
            return RegimeMixture(default).normalized()
        return RegimeMixture({k: max(0.0, float(v)) / s for k, v in self.weights.items()})
