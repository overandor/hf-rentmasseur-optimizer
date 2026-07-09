"""
Real ML training pipeline for bio performance prediction.

Includes:
- k-fold cross-validation
- backpropagation with Adam-like optimizer
- walk-forward validation
- online training loop
- metrics: MAE, RMSE, R^2
"""

import json
import logging
import pickle
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

from .bio_features import feature_vector
from .bio_generator import _score_variant
from .bio_appraiser import load_bios

log = logging.getLogger("profileops.ml_trainer")

MODEL_PATH = Path(__file__).parent / "data" / "models" / "bio_ml_model.pkl"


class MLP:
    """MLP with Adam optimizer and dropout."""

    def __init__(self, input_size: int, hidden_size: int = 32, output_size: int = 3,
                 seed: int = 42, dropout: float = 0.2):
        rng = np.random.default_rng(seed)
        self.W1 = rng.normal(0, np.sqrt(2.0 / input_size), (input_size, hidden_size))
        self.b1 = np.zeros((1, hidden_size))
        self.W2 = rng.normal(0, np.sqrt(2.0 / hidden_size), (hidden_size, output_size))
        self.b2 = np.zeros((1, output_size))
        self.dropout = dropout

        # Adam moments
        self.mW1 = np.zeros_like(self.W1)
        self.vW1 = np.zeros_like(self.W1)
        self.mb1 = np.zeros_like(self.b1)
        self.vb1 = np.zeros_like(self.b1)
        self.mW2 = np.zeros_like(self.W2)
        self.vW2 = np.zeros_like(self.W2)
        self.mb2 = np.zeros_like(self.b2)
        self.vb2 = np.zeros_like(self.b2)
        self.t = 0

    def _relu(self, x):
        return np.maximum(0, x)

    def _sigmoid(self, x):
        return 1 / (1 + np.exp(-np.clip(x, -500, 500)))

    def forward(self, X, training=False):
        self.z1 = X @ self.W1 + self.b1
        self.a1 = self._relu(self.z1)
        if training and self.dropout > 0:
            self.mask = (np.random.rand(*self.a1.shape) > self.dropout).astype(float)
            self.a1 *= self.mask / (1 - self.dropout)
        self.z2 = self.a1 @ self.W2 + self.b2
        self.a2 = self._sigmoid(self.z2)
        return self.a2

    def backward(self, X, y, y_pred, lr=0.01, beta1=0.9, beta2=0.999, eps=1e-8):
        self.t += 1
        m = X.shape[0]

        dz2 = (y_pred - y) / m
        dW2 = self.a1.T @ dz2
        db2 = np.sum(dz2, axis=0, keepdims=True)

        da1 = dz2 @ self.W2.T
        if self.dropout > 0:
            da1 *= self.mask
        dz1 = da1 * (self.z1 > 0)
        dW1 = X.T @ dz1
        db1 = np.sum(dz1, axis=0, keepdims=True)

        # Adam update
        for dW, mW, vW, W in [(dW1, self.mW1, self.vW1, self.W1),
                                (db1, self.mb1, self.vb1, self.b1),
                                (dW2, self.mW2, self.vW2, self.W2),
                                (db2, self.mb2, self.vb2, self.b2)]:
            mW[:] = beta1 * mW + (1 - beta1) * dW
            vW[:] = beta2 * vW + (1 - beta2) * (dW ** 2)
            m_hat = mW / (1 - beta1 ** self.t)
            v_hat = vW / (1 - beta2 ** self.t)
            W -= lr * m_hat / (np.sqrt(v_hat) + eps)

    def train_epoch(self, X, y, lr=0.01, batch_size=64):
        n = X.shape[0]
        indices = np.random.permutation(n)
        total_loss = 0
        for i in range(0, n, batch_size):
            idx = indices[i:i+batch_size]
            Xb = X[idx]
            yb = y[idx]
            y_pred = self.forward(Xb, training=True)
            loss = np.mean((y_pred - yb) ** 2)
            total_loss += loss * len(idx)
            self.backward(Xb, yb, y_pred, lr=lr)
        return total_loss / n

    def predict(self, X):
        return self.forward(X, training=False)

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: Path):
        with open(path, "rb") as f:
            return pickle.load(f)


def build_dataset(bios: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
    """Build feature matrix X and label matrix y from bios."""
    X, y = [], []
    for bio in bios:
        X.append(feature_vector(bio["headline"], bio["description"]))
        scores = _score_variant(bio["headline"], bio["description"])
        # Synthetic labels: realistic CTR/email/phone
        ctr = min(0.08, scores["composite"] * 0.08 + 0.01)
        email = min(0.05, scores["composite"] * 0.05 + 0.005)
        phone = min(0.03, scores["composite"] * 0.03 + 0.003)
        y.append([ctr, email, phone])
    return np.array(X), np.array(y)


def k_fold_cv(bios: List[Dict], k: int = 5, epochs: int = 100, lr: float = 0.01) -> Dict:
    """Run k-fold cross-validation."""
    X, y = build_dataset(bios)
    n = X.shape[0]
    fold_size = n // k
    metrics = []

    for fold in range(k):
        val_start = fold * fold_size
        val_end = val_start + fold_size
        val_idx = np.arange(val_start, val_end)
        train_idx = np.concatenate([np.arange(0, val_start), np.arange(val_end, n)])

        X_train, y_train = X[train_idx], y[train_idx]
        X_val, y_val = X[val_idx], y[val_idx]

        model = MLP(input_size=X.shape[1], hidden_size=32, output_size=3)
        for epoch in range(epochs):
            model.train_epoch(X_train, y_train, lr=lr)

        y_pred = model.predict(X_val)
        mae = np.mean(np.abs(y_pred - y_val))
        rmse = np.sqrt(np.mean((y_pred - y_val) ** 2))
        r2 = 1 - np.sum((y_val - y_pred) ** 2) / np.sum((y_val - np.mean(y_val)) ** 2)
        metrics.append({"mae": mae, "rmse": rmse, "r2": r2})
        log.info("Fold %d: MAE=%.4f RMSE=%.4f R2=%.4f", fold, mae, rmse, r2)

    return {
        "folds": metrics,
        "mean_mae": np.mean([m["mae"] for m in metrics]),
        "mean_rmse": np.mean([m["rmse"] for m in metrics]),
        "mean_r2": np.mean([m["r2"] for m in metrics]),
    }


def walk_forward_validation(bios: List[Dict], train_ratio: float = 0.8,
                            epochs: int = 100, lr: float = 0.01) -> Dict:
    """Train on first N% of data, validate on last (100-N)%."""
    X, y = build_dataset(bios)
    split = int(train_ratio * X.shape[0])
    X_train, y_train = X[:split], y[:split]
    X_val, y_val = X[split:], y[split:]

    model = MLP(input_size=X.shape[1], hidden_size=32, output_size=3)
    for epoch in range(epochs):
        loss = model.train_epoch(X_train, y_train, lr=lr)
        if epoch % 20 == 0:
            log.info("Epoch %d: train_loss=%.4f", epoch, loss)

    y_pred = model.predict(X_val)
    mae = np.mean(np.abs(y_pred - y_val))
    rmse = np.sqrt(np.mean((y_pred - y_val) ** 2))
    r2 = 1 - np.sum((y_val - y_pred) ** 2) / np.sum((y_val - np.mean(y_val)) ** 2)

    return {
        "train_size": split,
        "val_size": X.shape[0] - split,
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
    }


def online_train(bios_stream: List[Dict], model: MLP = None, epochs: int = 10,
                 lr: float = 0.01, save_path: Path = MODEL_PATH) -> MLP:
    """Online training: update model with new bios as they arrive."""
    X, y = build_dataset(bios_stream)
    if model is None:
        model = MLP(input_size=X.shape[1], hidden_size=32, output_size=3)
    for epoch in range(epochs):
        loss = model.train_epoch(X, y, lr=lr)
        log.info("Online epoch %d: loss=%.4f", epoch, loss)
    model.save(save_path)
    return model


def full_training_pipeline(bios_path: Path, cv_folds: int = 5, epochs: int = 100,
                           lr: float = 0.01) -> Dict:
    """Run CV + walk-forward + final model training."""
    bios = load_bios(bios_path, limit=50000)
    log.info("Training pipeline on %d bios", len(bios))

    cv_results = k_fold_cv(bios, k=cv_folds, epochs=epochs, lr=lr)
    wf_results = walk_forward_validation(bios, train_ratio=0.8, epochs=epochs, lr=lr)

    # Final model
    X, y = build_dataset(bios)
    model = MLP(input_size=X.shape[1], hidden_size=32, output_size=3)
    for epoch in range(epochs):
        model.train_epoch(X, y, lr=lr)
    model.save(MODEL_PATH)

    return {
        "cv": cv_results,
        "walk_forward": wf_results,
        "model_path": str(MODEL_PATH),
    }
