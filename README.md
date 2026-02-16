# Mega Rubric Scorer (README)

A regime-aware rubric for scoring companies in an AGI/agent-disruption world.

This project provides **calculation logic only**. It deliberately contains **no embedded market data** and **no forecasting**. All signals are retrieved from a pluggable `magic_data_provider` interface.

The scorer outputs a single **company score in the range -100 to 100**, plus a rich breakdown of factor-group contributions, gates, multipliers, and risk.

---

## Why this exists

In a world where:
- AI agents can perform high-quality cognitive work at low cost,
- synthetic media and automated persuasion are easy and scalable,
- compute and electricity become major bottlenecks,
- security and trust failures can cause sudden repricing,
- geopolitical partitioning and regulation can change markets abruptly,

traditional linear scoring models tend to break. They average everything together and miss:
- **hard feasibility constraints** (power, regulatory eligibility),
- **nonlinear trust collapse** from repeated incidents,
- **compounding advantages** from distribution + workflow control points,
- **regime shifts** where different factors dominate.

This rubric is built around those realities.

---

## Design principles

### 1) No embedded data
The scorer has **no built-in datasets** or "facts about companies."  
It only contains:
- factor-group definitions
- weighting
- nonlinear transforms (sigmoid, log saturation, gates)
- aggregation logic

All inputs come from a provider module.

### 2) No forecasting
`magic_data_provider` may compute:
- current values
- trailing-window metrics
- normalized scores derived from observed data

But the scorer does not attempt to predict the future.

### 3) Regime-aware, not one-size-fits-all
Different conditions change which factors matter most:
- Power scarcity makes power access a gate.
- Trust crises make security and provenance dominate.
- Tight liquidity penalizes leverage and long-duration bets.
- Hyper-competition penalizes feature-only moats.

The scorer supports a **regime mixture** (weights across named regimes) to tune which gates and multipliers matter most.

### 4) Separate risk from advantage until the end
The scorer keeps:
- **advantage** (base additive score)
- **feasibility** (gates and multipliers)
- **risk** (tail risk channels)

separate until final aggregation. This makes it possible to:
- rank by advantage alone,
- compare risk-adjusted vs non-adjusted outcomes,
- analyze why a company scored high but carries high blow-up risk.

### 5) Nonlinear where reality is nonlinear
Many real-world dynamics are not linear:
- You cannot "average out" catastrophic security posture.
- Power and regulatory access behave like thresholds.
- Adoption and workflow embedment often follow S-curves.
- Distribution and market power show diminishing returns once dominant.

The scorer uses nonlinear transforms intentionally.

---

## Inputs and outputs

### Inputs
- `company: str` — human-readable company name
- `horizon: TimeHorizon` — one of:
  - `SHORT` = 0-2 years
  - `MID` = 2-5 years
  - `LONG` = 5-12 years
- `as_of: Optional[str]` — ISO date string for "current as of"
- `regime_mixture: Optional[RegimeMixture]`
  - if omitted, the provider can return a recommended mixture

### Output
A `ScoreBreakdown` containing:
- `final_score: float` in **[-100, 100]**
- `base_additive: float` in roughly **[-1, 1]**
- `gate_multiplier: float` in **[0, 1]**
- `multiplier_product: float` typically in **[0, ~1.25]**
- `risk_index: float` in **[0, 1]**
- per-group `FactorOutput`:
  - `additive` [-1,1]
  - `gates` (0..1 multipliers)
  - `multipliers` (usually 0..1.25)
  - `risk` channels (0..1)
  - debug metadata

---

## Architectural overview

At a high level:

1) **Get or accept a regime mixture**
2) Compute **seven factor groups** (meta factors)
3) Combine them into:
   - a **weighted additive base**
   - a **product of gates**
   - a **product of multipliers**
4) Compute a separate **risk index**
5) Convert to a final score in **[-100, 100]**

### Final score formula (conceptual)
Let:
- `B` = base additive score in [-1, 1]
- `G` = product of gates in [0, 1]
- `M` = product of multipliers (bounded)
- `R` = risk index in [0, 1]
- `risk_discount = 1 - risk_weight * R^p` (clamped 0..1)

Then:

`raw = B * G * M * risk_discount`

`final_score = clamp(100 * raw, -100, 100)`

This structure forces:
- hard constraints (gates) to cap upside
- compounding effects (multipliers) to amplify winners
- risk to reduce score in a convex way without distorting the base advantage signal

---

## Regimes and why they matter

The scorer supports these regimes:

- `POWER_CONSTRAINED_BOOM`
- `POWER_CONSTRAINED_STAGFLATION`
- `TRUST_COLLAPSE`
- `REGULATORY_CLAMPDOWN`
- `HYPER_COMPETITION`
- `CAPITAL_CONCENTRATION`
- `GEOPOLITICAL_BIFURCATION`
- `SECURITY_ARMS_RACE`

A `RegimeMixture` is a mapping `{Regime: weight}` which is normalized.

Regimes influence:
- which factors behave like gates
- how strong certain multipliers become
- how quickly penalties apply in discontinuities

The scorer itself is not predictive: the mixture is either:
- supplied externally by the caller, or
- returned by the provider as a "current-state regime profile"

---

## Factor groups (meta factors)

The model uses seven groups, each representing a broad "meta factor."
Each group is built from multiple signals queried from the provider.

### 1) Macro and liquidity
**What it captures**
- How the cost of capital and liquidity conditions affect survivability and valuations.

**Why it matters**
- In tight liquidity, leveraged or long-duration business models can fail rapidly regardless of product quality.

**Typical signals**
- Company sensitivity to macro tightening
- Current macro tightness index

**Model behavior**
- Mostly additive, but contributes to a **macro tail risk** channel.

---

### 2) Constraint regime (power/compute access)
**What it captures**
- Whether the firm can scale deployment when electricity and compute are the bottleneck.

**Why it matters**
- In a power-constrained world, the best agent product cannot scale without MW and interconnect.
- This is a **feasibility constraint**, not a preference.

**Typical signals**
- `constraint.power_access_good` (0..1)
- `constraint.compute_access_good` (0..1)

**Model behavior**
- Includes explicit **gates**:
  - power gate
  - compute gate
- Additive portion uses diminishing returns (saturating log).

---

### 3) Trust and legitimacy
**What it captures**
- Security maturity, auditability, provenance readiness, and incident history.

**Why it matters**
- Synthetic media and agent misuse can collapse trust.
- Repeat security failures create compounding downside.

**Typical signals**
- Security maturity (good)
- Auditability (good)
- Provenance support (good)
- Incident pressure (bad)

**Model behavior**
- Trust quality feeds additive via a sigmoid (adoption S-curve)
- Incident pressure generates a **gate** via exponential downside
- Emits a multiplier that can compound with distribution in downstream logic

---

### 4) Control point concentration
**What it captures**
- Strength of unavoidable bottlenecks like distribution, switching costs, data advantage, network effects.

**Why it matters**
- When code is cheap, value concentrates in:
  - distribution
  - systems of record
  - proprietary data
  - network effects
- These create persistence of margins and winner-take-most outcomes.

**Typical signals**
- Distribution lock
- Switching costs
- Data advantage
- Network effects

**Model behavior**
- Saturating (log-like) additive score
- Emits a compounding multiplier in hyper-competition / concentration regimes

---

### 5) Adaptation speed
**What it captures**
- Organizational ability to ship, retool, adopt agents internally, and restructure costs.

**Why it matters**
- In discontinuities, slow movers can be functionally dead even if they "should" win long-term.

**Typical signals**
- Shipping velocity
- Talent density
- Internal agent adoption
- Restructure velocity

**Model behavior**
- Additive linear blend
- Multiplier increases in disruptive regimes (hyper-competition, security arms race)
- Emits execution risk

---

### 6) Geopolitical and regulatory partitioning
**What it captures**
- Compliance readiness, liability posture, and exposure to export controls, sanctions, and antitrust.

**Why it matters**
- Rules can change abruptly and exclude firms from markets.
- Export controls can remove access to critical supply chain nodes.
- Compliance becomes a moat and a gate.

**Typical signals**
- Compliance readiness (good)
- Liability readiness (good)
- Export control exposure (bad)
- Sanctions exposure (bad)
- Antitrust risk (bad)

**Model behavior**
- Adds a **regulatory gate**, strengthened under clampdown regime weight
- Emits separate risk channels: regulatory and geopolitical

---

### 7) Capital allocation and M&A posture
**What it captures**
- Free cash flow, balance sheet strength, M&A integration skill, discipline, and moonshot propensity.

**Why it matters**
- Cash-rich firms can buy capabilities and consolidate control points.
- Poor discipline can destroy advantage via desperate capex or unfocused bets.

**Typical signals**
- Free cash flow strength (good)
- Balance sheet strength (good)
- M&A integration skill (good)
- Allocation discipline (good)
- Moonshot propensity (bad)

**Model behavior**
- Additive blend
- M&A multiplier increases under capital concentration regime
- Emits execution risk from moonshot × low discipline

---

## Gates vs multipliers vs additive contributions

### Additive contributions (linear-ish)
Used when performance differences matter continuously:
- execution velocity
- capital discipline
- baseline trust quality
- macro defensiveness

### Gates (hard feasibility)
Used when falling below a threshold caps upside:
- power access
- compute access
- severe/repeated incidents
- regulatory eligibility

### Multipliers (compounding)
Used when advantages amplify each other:
- distribution × trust
- concentration flywheels in hyper-competition
- M&A flywheel in capital concentration
- adaptation multiplier in discontinuity regimes

This structure avoids a common scoring failure: "averaging out" fatal constraints.

---

## Risk model

### What risk represents
Risk is not "badness." It is the probability-weighted severity of outcomes that can crater value:
- macro tails
- power scarcity
- security incidents
- regulatory exclusion
- geopolitical shocks
- execution/moonshot failures

### Where risk appears
Each factor group emits risk channels like:
- `macro_tail`
- `power_constraint`
- `security_incident`
- `regulatory`
- `geopolitical`
- `execution`

They are combined into a `risk_index` in [0,1], then applied as a convex discount.

---

## The `magic_data_provider` interface

### Purpose
The provider is responsible for:
- fetching raw metrics
- normalizing them into the ranges required by the rubric
- reporting confidence and freshness
- optionally providing a regime mixture based on current conditions

The scorer never uses external APIs directly.

### Core methods

#### `get_value(metric_id, company, horizon, as_of, context) -> Signal`
Returns raw numeric values or values in arbitrary units.

#### `get_score(metric_id, ..., score_range=(-1,1)) -> Signal`
Returns a normalized score in a target range, typically:
- 0..1 for "goodness" or "badness"
- -1..1 when a symmetric scale is natural

#### `get_regime_mixture(horizon, as_of, context) -> RegimeMixture`
Optional helper that returns a normalized mixture.

### The `Signal` type
Each signal includes metadata:
- `value: float`
- `scale: str` (e.g. `raw`, `score_0_1`, `percent`)
- `confidence: 0..1`
- `freshness_days: int`
- optional `details` map for debugging or attribution

---

## Metric IDs (conventions)

Metric IDs are **namespaced strings** so you can expand them over time without changing the scoring API.

Examples:
- `macro.tightness_index`
- `constraint.power_access_good`
- `trust.security_incident_bad`
- `platform.distribution_lock_good`
- `org.ship_velocity_good`
- `geo.export_control_exposure_bad`
- `capital.moonshot_propensity_bad`

A full metric dictionary can be maintained in the provider or in a shared catalog.
The scorer treats them as opaque keys.

---

## Intended usage

```python
provider = magic_data_provider.Provider(...)
scorer = MegaRubricScorer(provider)

result = scorer.score_company(
    company="Microsoft",
    horizon=TimeHorizon.MID,
    as_of="2026-02-16",
)

print("Final:", result.final_score)
print("Risk:", result.risk_index)
for group_name, out in result.group_outputs.items():
    print(group_name, out.additive, out.gates, out.multipliers, out.risk)
```

---

## Extension points

### Add more factor groups

You can add sector-specific groups (optional) such as:

* defense exposure and procurement advantage
* advertising exposure and trust sensitivity
* regulated vertical eligibility
* supply chain and physical bottlenecks (water, cooling, transformers)

### Improve regime logic

Right now the regime mixture influences only a few multipliers/gates.
Future versions can:

* adjust weights per regime
* add regime-specific gates (e.g. bifurcation gating supply chain access)
* compute scenario scores and probability-weighted totals

### Improve risk modeling

Enhancements can include:

* separate short-term vs long-term risk indices
* asymmetric penalties (left-tail vs right-tail)
* correlation modeling (systemic risk vs idiosyncratic risk)

---

## Constraints and limitations (by design)

* **Not a trading system**

  * This is a qualitative-to-quantitative scoring skeleton.
* **No embedded truth**

  * All truth comes from the provider.
* **No forecasting**

  * The score represents a structured view of current signals under a horizon framing.
* **Nonlinear design**

  * The rubric is intentionally non-linear because the underlying dynamics are non-linear.

---

## FAQ

### Why -100 to 100?

A bounded range forces comparability and discourages false precision.
It also makes it easy to map:

* 0 ≈ neutral
* positive ≈ structural advantage
* negative ≈ structural disadvantage
  with headroom for extreme winners/losers.

### Why gates instead of weights?

Some constraints are binary in practice:

* no power → no scale
* repeated security failures → no trust → no adoption
* regulatory exclusion → no market access

Averaging these into a weight hides the real-world feasibility boundary.

### Why a provider interface instead of direct data pulls?

Separation improves:

* testability
* reproducibility (as_of snapshots)
* portability across data vendors
* the ability to swap in expert judgment scores where hard metrics do not exist

---

## Glossary

* **Gate**: a multiplier in [0,1] that sharply reduces upside when below a threshold.
* **Multiplier**: compounding factor capturing flywheels and interactions.
* **Additive score**: continuous contribution roughly in [-1,1].
* **Regime mixture**: weighted blend of macro conditions that changes which factors dominate.
* **Risk index**: separate 0..1 measure of tail/blow-up risk used only at the end.

---

```
