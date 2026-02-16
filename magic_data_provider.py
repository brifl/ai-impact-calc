# =============================================================================
# magic_data_provider interface (rough draft)
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, Tuple, Dict
from models import Signal, TimeHorizon, RegimeMixture


class MagicDataProvider(Protocol):
    """
    Provider can answer any signal query with a normalized score or raw value.

    Design philosophy
    - All queries should be explicit and self-describing (metric_id + context dict).
    - Provider is responsible for:
        * mapping to underlying data sources
        * normalizing to requested scales
        * handling as_of dates, time windows, and confidence/quality
    - Provider does NOT forecast; it can compute historical/current scores.
    """

    # --- core query: returns a numeric score/value plus metadata ---
    def get_value(
        self,
        metric_id: str,
        *,
        company: str,
        horizon: TimeHorizon,
        as_of: Optional[str] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> "Signal":
        """
        metric_id examples:
          - "company.sector.primary"
          - "market.share.core_category"
          - "finance.net_debt_to_ebitda"
          - "trust.security_incident_rate"
          - "constraint.power_access_index"
          - "geo.export_control_exposure"
          - "platform.distribution_lock_index"
          - "agents.agentization_depth_index"

        Returns Signal(value=..., scale=..., confidence=..., freshness_days=...)
        """
        ...

    # --- convenience: provider can return a normalized score directly ---
    def get_score(
        self,
        metric_id: str,
        *,
        company: str,
        horizon: TimeHorizon,
        as_of: Optional[str] = None,
        context: Optional[Mapping[str, Any]] = None,
        score_range: Tuple[float, float] = (-1.0, 1.0),
    ) -> "Signal":
        """
        Returns a normalized score in score_range, e.g. [-1,1] or [0,1].
        Use for rubric-ready signals (retention quality, moat durability, etc.).
        """
        ...

    # --- optional: provide a recommended regime mixture (still non-forecast, but can be current-state based) ---
    def get_regime_mixture(
        self,
        *,
        horizon: TimeHorizon,
        as_of: Optional[str] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> RegimeMixture:
        """
        Example: weights based on current macro, power constraints, incident rates, etc.
        """
        ...

# =============================================================================
# Example: metric catalog (OPTIONAL, for documentation only)
# =============================================================================

METRICS_DOC: Dict[str, str] = {
    # Macro
    "macro.tightness_index": "0..1, 1=tight liquidity and high cost of capital.",
    "macro.company_sensitivity": "0..1, 1=high sensitivity to macro tightening (levered, long-duration, cyclical).",

    # Constraints
    "constraint.power_access_good": "0..1, 1=excellent secured power/interconnect path for scaling compute.",
    "constraint.compute_access_good": "0..1, 1=excellent GPU/network/memory supply access and ability to procure/operate.",

    # Trust
    "trust.security_maturity_good": "0..1, controls, secure-by-default, response automation.",
    "trust.auditability_good": "0..1, logs, replay, approvals, compliance-grade tooling.",
    "trust.provenance_support_good": "0..1, content credentials/provenance strategy integration.",
    "trust.security_incident_bad": "0..1, incident frequency/severity/repeat-ness; 1 is very bad.",

    # Control points
    "platform.distribution_lock_good": "0..1, default placement in workflows/devices/platforms.",
    "platform.switching_cost_good": "0..1, stickiness and lock-in from integrations/data/process.",
    "platform.data_advantage_good": "0..1, proprietary data access that improves outcomes.",
    "platform.network_effects_good": "0..1, marketplace/community/network effects strength.",

    # Org
    "org.ship_velocity_good": "0..1, cadence and quality of shipping meaningful features.",
    "org.talent_density_good": "0..1, ability to attract/retain top builders.",
    "org.internal_agent_adoption_good": "0..1, uses agents internally to compound productivity.",
    "org.restructure_velocity_good": "0..1, ability to change cost structure quickly.",

    # Reg/Geo
    "reg.compliance_readiness_good": "0..1, certs, audits, enterprise readiness.",
    "reg.liability_readiness_good": "0..1, contracts/insurance posture and governance controls.",
    "geo.export_control_exposure_bad": "0..1 bad, dependence on restricted components/markets.",
    "geo.sanctions_exposure_bad": "0..1 bad, sanction risk for markets/supply chain.",
    "reg.antitrust_risk_bad": "0..1 bad, constraint on M&A / bundling.",

    # Capital alloc
    "capital.free_cash_flow_strength_good": "0..1 good, resilient cash generation.",
    "capital.balance_sheet_strength_good": "0..1 good, low leverage / high liquidity.",
    "capital.mna_integration_skill_good": "0..1 good, track record of successful integrations.",
    "capital.allocation_discipline_good": "0..1 good, kills bad projects, avoids capex traps.",
    "capital.moonshot_propensity_bad": "0..1 bad, tendency for desperate capex or unfocused bets.",
}
