"""
Neural network predictor for bio performance.

Predicts: click-through rate, email likelihood, phone-call likelihood.

Uses a small MLP with numpy. Trainable on synthetic or real A/B data.
"""

import json
import logging
import pickle
from pathlib import Path
from typing import Dict, List

import numpy as np

from .bio_features import feature_vector, FEATURE_NAMES
from .bio_generator import _score_variant

log = logging.getLogger("profileops.predictor")

MODEL_PATH = Path(__file__).parent / "data" / "models" / "bio_predictor.pkl"


class MLP:
    """Tiny 2-layer MLP with sigmoid activations."""

    def __init__(self, input_size: int, hidden_size: int = 16, output_size: int = 3, seed: int = 42):
        rng = np.random.default_rng(seed)
        self.W1 = rng.normal(0, 0.1, (input_size, hidden_size))
        self.b1 = np.zeros((1, hidden_size))
        self.W2 = rng.normal(0, 0.1, (hidden_size, output_size))
        self.b2 = np.zeros((1, output_size))
        self.losses = []

    def _relu(self, x):
        return np.maximum(0, x)

    def _sigmoid(self, x):
        return 1 / (1 + np.exp(-np.clip(x, -500, 500)))

    def forward(self, X):
        self.z1 = X @ self.W1 + self.b1
        self.a1 = self._relu(self.z1)
        self.z2 = self.a1 @ self.W2 + self.b2
        self.a2 = self._sigmoid(self.z2)
        return self.a2

    def predict(self, X):
        return self.forward(X)

    def train(self, X, y, epochs: int = 500, lr: float = 0.01, verbose: bool = False):
        for epoch in range(epochs):
            y_pred = self.forward(X)
            loss = np.mean((y_pred - y) ** 2)
            self.losses.append(loss)

            # Backprop
            dz2 = 2 * (y_pred - y) * y_pred * (1 - y_pred)
            dW2 = self.a1.T @ dz2 / len(X)
            db2 = np.mean(dz2, axis=0, keepdims=True)

            da1 = dz2 @ self.W2.T
            dz1 = da1 * (self.z1 > 0)
            dW1 = X.T @ dz1 / len(X)
            db1 = np.mean(dz1, axis=0, keepdims=True)

            self.W2 -= lr * dW2
            self.b2 -= lr * db2
            self.W1 -= lr * dW1
            self.b1 -= lr * db1

            if verbose and epoch % 100 == 0:
                log.info("Epoch %d, loss: %.4f", epoch, loss)

    def save(self, path: Path = MODEL_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: Path = MODEL_PATH):
        with open(path, "rb") as f:
            return pickle.load(f)


def _synthetic_score(headline: str, description: str) -> List[float]:
    """Generate synthetic training labels from heuristic scores."""
    scores = _score_variant(headline, description)
    # Map to [0,1] targets
    ctr = min(0.15, scores["composite"] * 0.15 + 0.02)
    email = min(0.10, scores["composite"] * 0.10 + 0.01)
    phone = min(0.08, scores["composite"] * 0.08 + 0.005)
    return [ctr, email, phone]


def build_synthetic_training_data(bios: List[Dict], noise: float = 0.02) -> (np.ndarray, np.ndarray):
    """Build training data from generated bios."""
    X = []
    y = []
    for bio in bios:
        X.append(feature_vector(bio["headline"], bio["description"]))
        label = _synthetic_score(bio["headline"], bio["description"])
        label = [max(0, min(1, v + np.random.normal(0, noise))) for v in label]
        y.append(label)
    return np.array(X), np.array(y)


def train_predictor(bios: List[Dict], epochs: int = 500, save: bool = True) -> MLP:
    """Train the MLP on synthetic data."""
    X, y = build_synthetic_training_data(bios)
    model = MLP(input_size=X.shape[1], hidden_size=24, output_size=3)
    log.info("Training predictor on %d samples...", len(X))
    model.train(X, y, epochs=epochs, verbose=True)
    if save:
        model.save()
    return model


def predict_performance(headline: str, description: str, model: MLP = None) -> Dict:
    """Predict CTR, email, phone likelihood for a bio."""
    if model is None:
        try:
            model = MLP.load()
        except Exception:
            log.warning("No trained model found. Using heuristic fallback.")
            scores = _score_variant(headline, description)
            return {
                "ctr": round(scores["composite"] * 0.15 + 0.02, 4),
                "email": round(scores["composite"] * 0.10 + 0.01, 4),
                "phone": round(scores["composite"] * 0.08 + 0.005, 4),
            }
    X = np.array([feature_vector(headline, description)])
    pred = model.predict(X)[0]
    return {
        "ctr": round(float(pred[0]), 4),
        "email": round(float(pred[1]), 4),
        "phone": round(float(pred[2]), 4),
    }


def explain_features(headline: str, description: str) -> Dict:
    """Return feature values for explainability."""
    features = extract_features(headline, description)
    return {name: features[name] for name in FEATURE_NAMES}
