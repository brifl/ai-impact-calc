"""
Mega Rubric Scorer (rough draft)

Goals
- Input: company_name (str), horizon (TimeHorizon)
- Output: single score in [-100, 100] plus rich breakdown
- No built-in data. All signals come from magic_data_provider.
- Keep volatility/risk separate until final aggregation.
- Support "regime sheet": gates, multipliers, additive contributors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional
from magic_data_provider import MagicDataProvider
from models import TimeHorizon, RegimeMixture, Regime, RubricWeights, ScoreBreakdown, FactorOutput
import math
from util import clamp, to_minus1_plus1_from_0_1, gate, sat_log, exp_downside_penalty, logistic


class MegaRubricScorer:
    def __init__(self, provider: MagicDataProvider, *, weights: Optional[RubricWeights] = None):
        self.p = provider
        self.w = weights or RubricWeights()

    def score_company(
        self,
        company: str,
        horizon: TimeHorizon,
        *,
        as_of: Optional[str] = None,
        regime_mixture: Optional[RegimeMixture] = None,
    ) -> ScoreBreakdown:
        mix = (regime_mixture or self.p.get_regime_mixture(horizon=horizon, as_of=as_of)).normalized()

        # Compute meta factor groups
        out_macro = self._macro_and_liquidity(company, horizon, as_of, mix)
        out_constraint = self._constraint_regime(company, horizon, as_of, mix)
        out_trust = self._trust_and_legitimacy(company, horizon, as_of, mix)
        out_control = self._control_point_concentration(company, horizon, as_of, mix)
        out_adapt = self._adaptation_speed(company, horizon, as_of, mix)
        out_georeg = self._geopolitical_and_regulatory(company, horizon, as_of, mix)
        out_capalloc = self._capital_allocation(company, horizon, as_of, mix)

        group_outputs = {
            "macro": out_macro,
            "constraint": out_constraint,
            "trust": out_trust,
            "control_points": out_control,
            "adaptation": out_adapt,
            "georeg": out_georeg,
            "capital_alloc": out_capalloc,
        }

        # Additive base (weighted sum in [-1,1] roughly)
        base = (
            self.w.w_macro * out_macro.additive
            + self.w.w_constraint * out_constraint.additive
            + self.w.w_trust * out_trust.additive
            + self.w.w_control_points * out_control.additive
            + self.w.w_adaptation * out_adapt.additive
            + self.w.w_georeg * out_georeg.additive
            + self.w.w_capital_alloc * out_capalloc.additive
        )
        base = clamp(base, -1.0, 1.0)

        # Gates and multipliers
        gate_mult = 1.0
        mult_prod = 1.0
        for g in group_outputs.values():
            for _, m in g.gates.items():
                gate_mult *= clamp(m, 0.0, 1.0)
            for _, m in g.multipliers.items():
                # multipliers can be modeled as [0,1] discounts or >1 boosts.
                # In this rough draft, treat them as [0,1] discounts/boosts capped.
                mult_prod *= clamp(m, 0.0, 1.25)

        # Risk index (0..1), aggregated, then applied as a discount
        risk_index = self._aggregate_risk(group_outputs)

        # Final mapping to [-100,100]
        # - base is the "intrinsic" advantage signal
        # - gate_mult and mult_prod are feasibility/compounding modifiers
        # - risk reduces the score via a convex discount
        raw = base * gate_mult * mult_prod
        risk_discount = clamp(1.0 - self.w.risk_weight * (risk_index ** 1.2), 0.0, 1.0)
        raw *= risk_discount

        final = 100.0 * clamp(raw, -1.0, 1.0)
        final = clamp(final, self.w.score_min, self.w.score_max)

        return ScoreBreakdown(
            company=company,
            horizon=horizon,
            as_of=as_of,
            regime_mixture=mix,
            group_outputs=group_outputs,
            base_additive=base,
            gate_multiplier=gate_mult,
            multiplier_product=mult_prod,
            risk_index=risk_index,
            final_score=final,
        )

    # -------------------------------------------------------------------------
    # Risk aggregation
    # -------------------------------------------------------------------------

    def _aggregate_risk(self, group_outputs: Mapping[str, FactorOutput]) -> float:
        """
        Aggregate risk channels into [0,1].
        Each group can emit risk["channel"]=0..1. Weighting can be refined later.
        """
        # rough draft weights
        channel_weights = {
            "macro_tail": 0.18,
            "power_constraint": 0.18,
            "security_incident": 0.22,
            "regulatory": 0.16,
            "geopolitical": 0.16,
            "execution": 0.10,
        }
        accum = 0.0
        wsum = 0.0
        for g in group_outputs.values():
            for ch, v in g.risk.items():
                if ch in channel_weights:
                    w = channel_weights[ch]
                    accum += w * clamp(float(v), 0.0, 1.0)
                    wsum += w
        if wsum <= 0:
            return 0.25  # default moderate
        return clamp(accum / wsum, 0.0, 1.0)

    # -------------------------------------------------------------------------
    # Factor group implementations (rough)
    # NOTE: We assume provider returns normalized scores for many metric_ids.
    # - Use get_score(..., score_range=(0,1)) for convenience.
    # - Each group chooses shape: linear vs sigmoid vs threshold gates.
    # -------------------------------------------------------------------------

    def _macro_and_liquidity(self, company: str, horizon: TimeHorizon, as_of: Optional[str], mix: RegimeMixture) -> FactorOutput:
        # Company sensitivity to macro regime (0=defensive, 1=fragile)
        macro_fragile = self.p.get_score("macro.company_sensitivity", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        # Current macro tightness (0=loose, 1=tight)
        macro_tight = self.p.get_score("macro.tightness_index", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value

        # Additive: defensive is good when tight, neutral when loose
        # Invert fragility; scale by tightness
        defensive = 1.0 - clamp(macro_fragile, 0.0, 1.0)
        additive01 = 0.5 * defensive + 0.5 * defensive * clamp(macro_tight, 0.0, 1.0)
        additive = to_minus1_plus1_from_0_1(additive01)

        # Risk channel: macro tails
        risk_tail = clamp(macro_fragile * macro_tight, 0.0, 1.0)

        return FactorOutput(additive=additive, risk={"macro_tail": risk_tail},
                           debug={"macro_fragile": macro_fragile, "macro_tight": macro_tight})

    def _constraint_regime(self, company: str, horizon: TimeHorizon, as_of: Optional[str], mix: RegimeMixture) -> FactorOutput:
        # Power / compute access (0..1 good)
        power_access = self.p.get_score("constraint.power_access_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        compute_access = self.p.get_score("constraint.compute_access_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value

        # Gate: must have minimum to scale in power constrained regimes
        # Thresholds can be horizon-dependent; keep simple for now.
        g_power = gate(power_access, threshold=0.55, softness=0.08)
        g_compute = gate(compute_access, threshold=0.50, softness=0.10)

        # Additive: above threshold, diminishing returns
        additive01 = 0.55 * sat_log(power_access, k=3.0) + 0.45 * sat_log(compute_access, k=2.0)
        additive = to_minus1_plus1_from_0_1(clamp(additive01, 0.0, 1.0))

        # Risk: constraint risk increases when access is low
        risk = clamp((1.0 - power_access) * 0.6 + (1.0 - compute_access) * 0.4, 0.0, 1.0)

        return FactorOutput(additive=additive, gates={"power_gate": g_power, "compute_gate": g_compute},
                           risk={"power_constraint": risk},
                           debug={"power_access": power_access, "compute_access": compute_access})

    def _trust_and_legitimacy(self, company: str, horizon: TimeHorizon, as_of: Optional[str], mix: RegimeMixture) -> FactorOutput:
        # Goodness scores (0..1 good)
        security_maturity = self.p.get_score("trust.security_maturity_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        auditability = self.p.get_score("trust.auditability_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        provenance_support = self.p.get_score("trust.provenance_support_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value

        # Badness: incident pressure (0..1 bad)
        incident_bad = self.p.get_score("trust.security_incident_bad", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value

        # Gate: if incidents are severe/repeated, adoption ceiling collapses
        # Convert "bad" into gate via exponential penalty.
        incident_penalty = exp_downside_penalty(incident_bad, strength=3.5)  # 1 good, -> 0 bad
        g_trust = clamp(incident_penalty, 0.0, 1.0)

        # Additive: sigmoid because trust adoption often S-curves
        quality01 = 0.45 * security_maturity + 0.35 * auditability + 0.20 * provenance_support
        additive01 = logistic(quality01, k=4.0, x0=0.55)
        additive = to_minus1_plus1_from_0_1(additive01)

        # Multiplier: trust interacts with distribution; emitted here as "trust_multiplier"
        # Keep it near [0.6, 1.1] but we cap globally later.
        trust_mult = 0.6 + 0.5 * clamp(quality01, 0.0, 1.0)  # 0.6..1.1
        trust_mult *= g_trust  # incidents shrink it

        risk = clamp(incident_bad * (1.0 - security_maturity), 0.0, 1.0)

        return FactorOutput(
            additive=additive,
            gates={"trust_gate": g_trust},
            multipliers={"trust_multiplier": clamp(trust_mult, 0.0, 1.25)},
            risk={"security_incident": risk},
            debug={
                "security_maturity": security_maturity,
                "auditability": auditability,
                "provenance_support": provenance_support,
                "incident_bad": incident_bad,
                "quality01": quality01,
            },
        )

    def _control_point_concentration(self, company: str, horizon: TimeHorizon, as_of: Optional[str], mix: RegimeMixture) -> FactorOutput:
        # (0..1 good)
        distribution_lock = self.p.get_score("platform.distribution_lock_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        switching_cost = self.p.get_score("platform.switching_cost_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        data_advantage = self.p.get_score("platform.data_advantage_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        network_effects = self.p.get_score("platform.network_effects_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value

        # Additive: saturating (log-ish)
        additive01 = (
            0.35 * sat_log(distribution_lock, k=4.0)
            + 0.25 * sat_log(switching_cost, k=3.0)
            + 0.20 * sat_log(data_advantage, k=2.0)
            + 0.20 * sat_log(network_effects, k=3.0)
        )
        additive = to_minus1_plus1_from_0_1(clamp(additive01, 0.0, 1.0))

        # Multiplier: concentration flywheel under hyper-competition and concentration regimes
        regime_boost = (
            mix.weights.get(Regime.HYPER_COMPETITION, 0.0) * 0.10
            + mix.weights.get(Regime.CAPITAL_CONCENTRATION, 0.0) * 0.12
        )
        flywheel = 0.95 + regime_boost + 0.15 * clamp(distribution_lock, 0.0, 1.0)  # ~0.95..1.22
        flywheel = clamp(flywheel, 0.0, 1.25)

        return FactorOutput(
            additive=additive,
            multipliers={"control_flywheel": flywheel},
            debug={
                "distribution_lock": distribution_lock,
                "switching_cost": switching_cost,
                "data_advantage": data_advantage,
                "network_effects": network_effects,
                "flywheel": flywheel,
            },
        )

    def _adaptation_speed(self, company: str, horizon: TimeHorizon, as_of: Optional[str], mix: RegimeMixture) -> FactorOutput:
        # (0..1 good)
        ship_velocity = self.p.get_score("org.ship_velocity_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        talent_density = self.p.get_score("org.talent_density_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        internal_agent_use = self.p.get_score("org.internal_agent_adoption_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        cost_restructure = self.p.get_score("org.restructure_velocity_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value

        # Additive: fairly linear, but becomes multiplicative under discontinuity
        additive01 = 0.30 * ship_velocity + 0.30 * talent_density + 0.20 * internal_agent_use + 0.20 * cost_restructure
        additive = to_minus1_plus1_from_0_1(clamp(additive01, 0.0, 1.0))

        # Multiplier: in high disruption regimes, slow movers get lapped
        disruption = mix.weights.get(Regime.HYPER_COMPETITION, 0.0) + mix.weights.get(Regime.SECURITY_ARMS_RACE, 0.0)
        adapt_mult = 0.90 + 0.25 * clamp(additive01, 0.0, 1.0) + 0.10 * clamp(disruption, 0.0, 1.0)
        adapt_mult = clamp(adapt_mult, 0.0, 1.25)

        # Risk: execution risk rises when velocity is low
        risk_exec = clamp((1.0 - ship_velocity) * 0.6 + (1.0 - cost_restructure) * 0.4, 0.0, 1.0)

        return FactorOutput(
            additive=additive,
            multipliers={"adaptation_multiplier": adapt_mult},
            risk={"execution": risk_exec},
            debug={
                "ship_velocity": ship_velocity,
                "talent_density": talent_density,
                "internal_agent_use": internal_agent_use,
                "cost_restructure": cost_restructure,
                "adapt_mult": adapt_mult,
            },
        )

    def _geopolitical_and_regulatory(self, company: str, horizon: TimeHorizon, as_of: Optional[str], mix: RegimeMixture) -> FactorOutput:
        # (0..1 good)
        compliance_readiness = self.p.get_score("reg.compliance_readiness_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        liability_ready = self.p.get_score("reg.liability_readiness_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        # bad exposures (0..1 bad)
        export_controls_bad = self.p.get_score("geo.export_control_exposure_bad", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        sanctions_bad = self.p.get_score("geo.sanctions_exposure_bad", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        antitrust_bad = self.p.get_score("reg.antitrust_risk_bad", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value

        # Additive: readiness helps, exposures hurt
        readiness01 = 0.55 * compliance_readiness + 0.45 * liability_ready
        exposure01 = 0.45 * export_controls_bad + 0.25 * sanctions_bad + 0.30 * antitrust_bad
        additive01 = clamp(readiness01 * (1.0 - 0.7 * exposure01), 0.0, 1.0)
        additive = to_minus1_plus1_from_0_1(additive01)

        # Gate: regulatory exclusion risk in clampdown regimes
        clampdown_weight = mix.weights.get(Regime.REGULATORY_CLAMPDOWN, 0.0)
        # If clampdown is likely and readiness is low, gate hits.
        reg_gate = gate(readiness01, threshold=0.55, softness=0.10) ** (1.0 + 2.0 * clampdown_weight)

        # Risk channels
        risk_reg = clamp((1.0 - readiness01) * 0.6 + antitrust_bad * 0.4, 0.0, 1.0)
        risk_geo = clamp(export_controls_bad * 0.7 + sanctions_bad * 0.3, 0.0, 1.0)

        return FactorOutput(
            additive=additive,
            gates={"regulatory_gate": reg_gate},
            risk={"regulatory": risk_reg, "geopolitical": risk_geo},
            debug={
                "compliance_readiness": compliance_readiness,
                "liability_ready": liability_ready,
                "export_controls_bad": export_controls_bad,
                "sanctions_bad": sanctions_bad,
                "antitrust_bad": antitrust_bad,
                "readiness01": readiness01,
                "exposure01": exposure01,
                "reg_gate": reg_gate,
            },
        )

    def _capital_allocation(self, company: str, horizon: TimeHorizon, as_of: Optional[str], mix: RegimeMixture) -> FactorOutput:
        # (0..1 good)
        fcf_strength = self.p.get_score("capital.free_cash_flow_strength_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        balance_sheet = self.p.get_score("capital.balance_sheet_strength_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        mna_skill = self.p.get_score("capital.mna_integration_skill_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value
        discipline = self.p.get_score("capital.allocation_discipline_good", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value

        # bad: moonshot tendency (0..1 bad)
        moonshot_bad = self.p.get_score("capital.moonshot_propensity_bad", company=company, horizon=horizon, as_of=as_of, score_range=(0, 1)).value

        additive01 = clamp(
            0.30 * fcf_strength
            + 0.25 * balance_sheet
            + 0.20 * mna_skill
            + 0.25 * discipline
            - 0.25 * moonshot_bad,
            0.0, 1.0
        )
        additive = to_minus1_plus1_from_0_1(additive01)

        # Multiplier: in concentration regime, cash + M&A skill compounds
        conc = mix.weights.get(Regime.CAPITAL_CONCENTRATION, 0.0)
        mna_mult = 0.95 + 0.20 * conc * clamp(mna_skill, 0.0, 1.0) + 0.10 * conc * clamp(balance_sheet, 0.0, 1.0)
        mna_mult = clamp(mna_mult, 0.0, 1.20)

        # Risk: moonshot + weak discipline yields convex downside
        risk_moon = clamp(moonshot_bad * (1.0 - discipline), 0.0, 1.0)

        return FactorOutput(
            additive=additive,
            multipliers={"mna_multiplier": mna_mult},
            risk={"execution": risk_moon},
            debug={
                "fcf_strength": fcf_strength,
                "balance_sheet": balance_sheet,
                "mna_skill": mna_skill,
                "discipline": discipline,
                "moonshot_bad": moonshot_bad,
                "mna_mult": mna_mult,
            },
        )
