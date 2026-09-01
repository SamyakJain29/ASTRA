"""Small, label-free statistical baselines for irregular telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np


class DetectorNotFittedError(RuntimeError):
    """Raised when a fitted detector is used before fitting."""


class BaselineDetector(Protocol):
    """Minimal interface shared by ASTRA baseline detectors."""

    name: str

    def fit(self, values: np.ndarray) -> BaselineDetector: ...

    def predict(self, values: np.ndarray) -> np.ndarray: ...

    def parameters(self) -> dict[str, float | str | None]: ...


def _finite_training_values(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64).reshape(-1)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        raise ValueError("A detector requires at least one finite training value.")
    return finite


@dataclass
class NoAlarmDetector:
    """Sanity-check detector that always emits zero alarms."""

    name: str = "no_alarm"

    def fit(self, values: np.ndarray) -> NoAlarmDetector:
        del values
        return self

    def predict(self, values: np.ndarray) -> np.ndarray:
        return np.zeros(np.asarray(values).shape, dtype=bool)

    def parameters(self) -> dict[str, float | str | None]:
        return {}


@dataclass
class GlobalStdDetector:
    """Flag values farther than a fixed number of training standard deviations."""

    threshold: float = 3.0
    center_: float | None = None
    scale_: float | None = None
    training_count_: int = 0
    name: str = "global_std"

    def fit(self, values: np.ndarray) -> GlobalStdDetector:
        training = _finite_training_values(values)
        self.center_ = float(np.mean(training, dtype=np.float64))
        self.scale_ = float(np.std(training, dtype=np.float64, ddof=0))
        self.training_count_ = int(training.size)
        return self

    def score(self, values: np.ndarray) -> np.ndarray:
        if self.center_ is None or self.scale_ is None:
            raise DetectorNotFittedError("GlobalStdDetector has not been fitted.")
        array = np.asarray(values, dtype=np.float64)
        if self.scale_ == 0.0:
            return np.where(np.isfinite(array) & (array != self.center_), 10.0, 0.0)
        scores = np.abs(array - self.center_) / self.scale_
        return np.where(np.isfinite(array), scores, 0.0)

    def predict(self, values: np.ndarray) -> np.ndarray:
        return self.score(values) > self.threshold

    def parameters(self) -> dict[str, float | str | None]:
        return {
            "threshold_std": float(self.threshold),
            "center": self.center_,
            "population_std": self.scale_,
            "training_count": self.training_count_,
        }


@dataclass
class MedianMadDetector:
    """Flag values using a training median and scaled median absolute deviation."""

    threshold: float = 5.0
    consistency_scale: float = 1.4826
    center_: float | None = None
    scale_: float | None = None
    raw_mad_: float | None = None
    training_count_: int = 0
    name: str = "median_mad"

    def fit(self, values: np.ndarray) -> MedianMadDetector:
        training = _finite_training_values(values)
        self.center_ = float(np.median(training))
        self.raw_mad_ = float(np.median(np.abs(training - self.center_)))
        self.scale_ = self.consistency_scale * self.raw_mad_
        self.training_count_ = int(training.size)
        return self

    def score(self, values: np.ndarray) -> np.ndarray:
        if self.center_ is None or self.scale_ is None:
            raise DetectorNotFittedError("MedianMadDetector has not been fitted.")
        array = np.asarray(values, dtype=np.float64)
        if self.scale_ == 0.0:
            return np.where(np.isfinite(array) & (array != self.center_), 10.0, 0.0)
        scores = np.abs(array - self.center_) / self.scale_
        return np.where(np.isfinite(array), scores, 0.0)

    def predict(self, values: np.ndarray) -> np.ndarray:
        return self.score(values) > self.threshold

    def parameters(self) -> dict[str, float | str | None]:
        return {
            "threshold_mad": float(self.threshold),
            "consistency_scale": float(self.consistency_scale),
            "center": self.center_,
            "raw_mad": self.raw_mad_,
            "scaled_mad": self.scale_,
            "training_count": self.training_count_,
        }


class IsolationForestDetector:
    """Multivariate Isolation Forest baseline detector."""

    def __init__(self, contamination: float = 0.01, random_state: int = 42) -> None:
        from sklearn.ensemble import IsolationForest
        self.contamination = contamination
        self.random_state = random_state
        self.model = IsolationForest(contamination=contamination, random_state=random_state)
        self.fitted_ = False
        self.name = "isolation_forest"

    def fit(self, values: np.ndarray) -> IsolationForestDetector:
        array = np.asarray(values, dtype=np.float64)
        if array.ndim == 1:
            array = array.reshape(-1, 1)
        self.model.fit(array)
        self.fitted_ = True
        return self

    def score(self, values: np.ndarray) -> np.ndarray:
        if not self.fitted_:
            raise DetectorNotFittedError("IsolationForestDetector has not been fitted.")
        array = np.asarray(values, dtype=np.float64)
        if array.ndim == 1:
            array = array.reshape(-1, 1)
        # IsolationForest decision_function: lower means more anomalous. Convert to positive score.
        raw_scores = -self.model.decision_function(array)
        return raw_scores

    def predict(self, values: np.ndarray) -> np.ndarray:
        if not self.fitted_:
            raise DetectorNotFittedError("IsolationForestDetector has not been fitted.")
        array = np.asarray(values, dtype=np.float64)
        if array.ndim == 1:
            array = array.reshape(-1, 1)
        # IsolationForest predict returns -1 for anomaly, 1 for normal
        return self.model.predict(array) == -1

    def parameters(self) -> dict[str, float | str | None]:
        return {
            "contamination": float(self.contamination),
            "random_state": int(self.random_state),
        }


class MultiChannelSpacecraftDetector:
    """Wrapper that manages per-channel detectors and computes aggregate spacecraft unusualness."""

    def __init__(self, channel_names: list[str], detector_cls: type = GlobalStdDetector, **kwargs: Any) -> None:
        self.channel_names = channel_names
        self.detector_cls = detector_cls
        self.kwargs = kwargs
        self.detectors: dict[str, Any] = {ch: detector_cls(**kwargs) for ch in channel_names}

    def fit(self, channel_data: dict[str, np.ndarray]) -> MultiChannelSpacecraftDetector:
        for ch, vals in channel_data.items():
            if ch in self.detectors:
                self.detectors[ch].fit(vals)
        return self

    def predict_channels(self, channel_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        return {ch: self.detectors[ch].predict(vals) for ch, vals in channel_data.items() if ch in self.detectors}

    def score_channels(self, channel_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        return {ch: self.detectors[ch].score(vals) for ch, vals in channel_data.items() if ch in self.detectors}

    def aggregate_unusualness(self, channel_data: dict[str, np.ndarray]) -> np.ndarray:
        scores = self.score_channels(channel_data)
        if not scores:
            return np.array([])
        stacked = np.column_stack(list(scores.values()))
        # Root mean square deviation across channels as aggregate spacecraft unusualness score
        return np.sqrt(np.mean(stacked**2, axis=1))

    def predict_spacecraft(self, channel_data: dict[str, np.ndarray]) -> np.ndarray:
        predictions = self.predict_channels(channel_data)
        if not predictions:
            return np.array([], dtype=bool)
        stacked = np.column_stack(list(predictions.values()))
        return np.any(stacked, axis=1)

