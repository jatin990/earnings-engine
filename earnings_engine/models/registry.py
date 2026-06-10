"""Single place to look up models by name (CLI, reports, Phase 5 predict)."""

from earnings_engine.models.base import DirectionModel
from earnings_engine.models.baseline import AlwaysUp, PastUpRate
from earnings_engine.models.classifier import GBClassifier

MODELS: dict[str, type[DirectionModel]] = {
    AlwaysUp.name: AlwaysUp,
    PastUpRate.name: PastUpRate,
    GBClassifier.name: GBClassifier,
}


def make_model(name: str) -> DirectionModel:
    try:
        return MODELS[name]()
    except KeyError:
        raise ValueError(f"Unknown model {name!r}; choose from {list(MODELS)}")
