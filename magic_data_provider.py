# =============================================================================
# magic_data_provider implementation
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, Tuple, Dict
import json
import logging
import os
from models import Signal, TimeHorizon, RegimeMixture, Regime

logger = logging.getLogger(__name__)


class MagicDataProvider:
    """
    Provider loads signal data from a JSON file.
    
    JSON structure:
    {
      "CompanyName": {
        "metric.id": {
          "value": <float>,
          "scale": <str>,
          "confidence": <float>,
          "freshness_days": <int>,
          "details": <dict optional>
        },
        ...
      },
      ...
    }
    """

    def __init__(self, data_file: str = "data.json"):
        """Load data from JSON file."""
        if not os.path.exists(data_file):
            raise FileNotFoundError(f"Data file not found: {data_file}")
        
        with open(data_file, 'r') as f:
            self.data = json.load(f)

    # --- core query: returns a numeric score/value plus metadata ---
    def get_value(
        self,
        metric_id: str,
        *,
        company: str,
        horizon: TimeHorizon,
        as_of: Optional[str] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> Signal:
        """
        Fetches a signal value from the data file for the given company and metric.
        
        metric_id examples:
          - "constraint.power_access_good"
          - "trust.security_incident_bad"
          - "platform.distribution_lock_good"
          - etc.

        Returns Signal(value=..., scale=..., confidence=..., freshness_days=...)
        """
        logger.info("get_value called: metric_id=%s, company=%s, horizon=%s, as_of=%s, context=%s",
                    metric_id, company, horizon, as_of, context)
        # Look up company and metric in the data
        if company not in self.data:
            raise ValueError(f"Company not found in data: {company}")
        
        company_data = self.data[company]
        
        if metric_id not in company_data:
            raise ValueError(f"Metric not found for company {company}: {metric_id}")
        
        metric_data = company_data[metric_id]
        
        # Construct Signal from the matched data
        return Signal(
            value=metric_data.get("value", 0.0),
            scale=metric_data.get("scale", "raw"),
            confidence=metric_data.get("confidence", 0.8),
            freshness_days=metric_data.get("freshness_days", 30),
            details=metric_data.get("details", {}),
        )

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
    ) -> Signal:
        """
        Returns a normalized score in score_range, e.g. [-1,1] or [0,1].
        Use for rubric-ready signals (retention quality, moat durability, etc.).
        """
        logger.info("get_score called: metric_id=%s, company=%s, horizon=%s, as_of=%s, context=%s, score_range=%s",
                    metric_id, company, horizon, as_of, context, score_range)
        signal = self.get_value(metric_id, company=company, horizon=horizon, as_of=as_of, context=context)
        
        # If already in the requested range, just return it
        if score_range == (-1.0, 1.0):
            # Convert from [0,1] to [-1,1]
            signal.value = 2.0 * signal.value - 1.0
        
        return signal

    # --- optional: provide a recommended regime mixture ---
    def get_regime_mixture(
        self,
        *,
        horizon: TimeHorizon,
        as_of: Optional[str] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> RegimeMixture:
        """
        Returns a default regime mixture.
        In a real implementation, this could compute based on macro data, etc.
        For now, return a balanced mixture suitable for 2026 conditions.
        """
        logger.info("get_regime_mixture called: horizon=%s, as_of=%s, context=%s",
                    horizon, as_of, context)
        return RegimeMixture({
            Regime.POWER_CONSTRAINED_BOOM: 0.25,
            Regime.SECURITY_ARMS_RACE: 0.30,
            Regime.TRUST_COLLAPSE: 0.15,
            Regime.HYPER_COMPETITION: 0.20,
            Regime.REGULATORY_CLAMPDOWN: 0.10,
        })

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
