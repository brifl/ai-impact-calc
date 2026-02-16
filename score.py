from mega_rubric_scorer import MegaRubricScorer
from magic_data_provider import MagicDataProvider
from models import TimeHorizon

provider = MagicDataProvider()
scorer = MegaRubricScorer(provider)
result = scorer.score_company("Microsoft", TimeHorizon.MID, as_of="2026-02-16")
print(result.final_score, result.risk_index)
for k, v in result.group_outputs.items():
    print(k, v.additive, v.gates, v.multipliers, v.risk)