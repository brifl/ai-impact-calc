import math

# =============================================================================
# Utility transforms (linear/logistic/log/saturating + gates + multipliers)
# =============================================================================

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def sat_log(x: float, k: float = 1.0) -> float:
    """
    Saturating log-like transform for positive x.
    Returns ~0 for x near 0, grows quickly then slows.
    """
    x = max(0.0, x)
    return math.log1p(k * x) / math.log1p(k * 1.0)  # normalized at x=1


def logistic(x: float, k: float = 3.0, x0: float = 0.0) -> float:
    """Sigmoid centered at x0; output in (0,1)."""
    return 1.0 / (1.0 + math.exp(-k * (x - x0)))


def to_minus1_plus1_from_0_1(x01: float) -> float:
    return 2.0 * clamp(x01, 0.0, 1.0) - 1.0


def gate(value01: float, threshold: float, softness: float = 0.05) -> float:
    """
    Gate multiplier in [0,1]. Below threshold it drops fast.
    softness controls how gradual the transition is.
    """
    v = clamp(value01, 0.0, 1.0)
    if softness <= 0:
        return 1.0 if v >= threshold else 0.0
    # smooth step around threshold
    x = (v - threshold) / softness
    return clamp(logistic(x, k=3.0, x0=0.0), 0.0, 1.0)


def exp_downside_penalty(incident_score01: float, strength: float = 3.0) -> float:
    """
    Exponential downside in [0,1]. Higher incident_score01 => lower multiplier.
    incident_score01 should mean "badness"; 0=good, 1=bad.
    """
    b = clamp(incident_score01, 0.0, 1.0)
    return math.exp(-strength * b)

