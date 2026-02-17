from mega_rubric_scorer import MegaRubricScorer
from magic_data_provider import MagicDataProvider
from models import TimeHorizon

# Create provider with data file
provider = MagicDataProvider(data_file="data.json")

# Create scorer
scorer = MegaRubricScorer(provider)

# Score Microsoft
print("=" * 70)
print("Scoring Microsoft (Medium horizon)")
print("=" * 70)
result = scorer.score_company("Microsoft", TimeHorizon.MID, as_of="2026-02-16")
print(f"Final Score: {result.final_score:.2f}")
print(f"Risk Index: {result.risk_index:.3f}")
print(f"Base Additive: {result.base_additive:.3f}")
print(f"Gate Multiplier: {result.gate_multiplier:.3f}")
print(f"Multiplier Product: {result.multiplier_product:.3f}")
print()

print("Factor Groups:")
for k, v in result.group_outputs.items():
    print(f"  {k}:")
    print(f"    additive: {v.additive:.3f}")
    if v.gates:
        print(f"    gates: {v.gates}")
    if v.multipliers:
        print(f"    multipliers: {v.multipliers}")
    if v.risk:
        print(f"    risk: {v.risk}")
print()

# Score Google
print("=" * 70)
print("Scoring Google (Medium horizon)")
print("=" * 70)
result2 = scorer.score_company("Google", TimeHorizon.MID, as_of="2026-02-16")
print(f"Final Score: {result2.final_score:.2f}")
print(f"Risk Index: {result2.risk_index:.3f}")
print()
