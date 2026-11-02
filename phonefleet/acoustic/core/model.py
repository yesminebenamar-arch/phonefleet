"""MLP léger en numpy pur (baseline IARA, ~67% acc en publication).
"""

import numpy as np


CLASSES = {
    0: "Petit bateau (< 50 m)",
    1: "Bateau moyen (50–100 m)",
    2: "Grand bateau (> 100 m)",
    3: "Bruit de fond",
}

# Bruit de fond (3) exclu des alertes SMS : seules les 3 classes de bateaux
# déclenchent une alerte.
ALERT_CLASSES = {0, 1, 2}


class MLP:
    """MLP 3 couches : input → 128 → 64 → n_classes."""

    def __init__(self, input_dim: int, n_classes: int = 4, seed: int = 42):
        rng = np.random.default_rng(seed)
        self.W1 = rng.standard_normal((input_dim, 128)).astype(np.float32) * np.sqrt(2 / input_dim)
        self.b1 = np.zeros(128, dtype=np.float32)
        self.W2 = rng.standard_normal((128, 64)).astype(np.float32) * np.sqrt(2 / 128)
        self.b2 = np.zeros(64, dtype=np.float32)
        self.W3 = rng.standard_normal((64, n_classes)).astype(np.float32) * np.sqrt(2 / 64)
        self.b3 = np.zeros(n_classes, dtype=np.float32)
        self.n_classes = n_classes

    @staticmethod
    def _relu(x):
        return np.maximum(0, x)

    @staticmethod
    def _softmax_row(x):
        e = np.exp(x - x.max(axis=-1, keepdims=True))
        return e / e.sum(axis=-1, keepdims=True)

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Forward sur un batch (n, input_dim) ou un vecteur (input_dim,)."""
        if x.ndim == 1:
            x = x[None, :]
        h1 = self._relu(x @ self.W1 + self.b1)
        h2 = self._relu(h1 @ self.W2 + self.b2)
        return self._softmax_row(h2 @ self.W3 + self.b3)

    def predict_proba(self, mel_spec: np.ndarray) -> np.ndarray:
        """Prédit sur chaque colonne (fenêtre temporelle) du spectrogramme MEL."""
        return self.forward(mel_spec.T)

    def save(self, path: str):
        np.savez(path, W1=self.W1, b1=self.b1,
                 W2=self.W2, b2=self.b2,
                 W3=self.W3, b3=self.b3)

    def load(self, path: str):
        d = np.load(path, allow_pickle=False)
        self.W1, self.b1 = d["W1"], d["b1"]
        self.W2, self.b2 = d["W2"], d["b2"]
        self.W3, self.b3 = d["W3"], d["b3"]
        # Sécurité : vérifie que le .npz chargé correspond bien au nombre de
        # classes attendu par CLASSES (évite un mismatch silencieux si un
        # ancien .npz à 5 classes est chargé par erreur).
        loaded_classes = self.W3.shape[1]
        if loaded_classes != len(CLASSES):
            raise ValueError(
                f"Le fichier {path} a {loaded_classes} classes en sortie, "
                f"mais CLASSES en définit {len(CLASSES)}. "
                f"Vérifie que le modèle a bien été entraîné avec le bon dataset."
            )
        self.n_classes = loaded_classes


def train(model: MLP, X: np.ndarray, y: np.ndarray,
          epochs: int = 50, lr: float = 1e-3, batch_size: int = 32,
          on_epoch=None, should_stop=None, seed: int = 42):
    """SGD mini-batch avec cross-entropy. Modifie le modèle en place.
    `seed` : graine du générateur aléatoire utilisé pour mélanger les
    exemples à chaque epoch. AVANT cette correction, le mélange utilisait
    np.random.shuffle (générateur global, non seedé) : deux exécutions sur
    exactement les mêmes données donnaient des résultats légèrement
    différents (ex. balanced_accuracy 61.3% un jour, 61.5% un autre, avec
    un "meilleur epoch" différent), car l'ordre de présentation des
    mini-batches changeait à chaque run. Avec un générateur seedé local,
    deux exécutions avec les mêmes données/hyperparamètres donnent
    maintenant EXACTEMENT le même résultat — important pour pouvoir
    affirmer en soutenance que vos résultats sont reproductibles.

    `should_stop` : callable optionnel, sans argument, renvoyant un bool.
    Vérifié après chaque epoch (donc après l'appel à `on_epoch`) — permet à
    l'appelant (ex. pc/train.py) d'implémenter un early stopping basé sur
    une métrique externe (ex. accuracy sur un jeu de test).
    """
    rng = np.random.default_rng(seed)
    n_samples = len(X)
    indices = np.arange(n_samples)
    n_classes = model.n_classes

    for epoch in range(epochs):
        rng.shuffle(indices)
        total_loss = 0.0
        n_batches = 0

        for start in range(0, n_samples, batch_size):
            idx = indices[start:start + batch_size]
            Xb, yb = X[idx], y[idx]

            h1 = MLP._relu(Xb @ model.W1 + model.b1)
            h2 = MLP._relu(h1 @ model.W2 + model.b2)
            probs = MLP._softmax_row(h2 @ model.W3 + model.b3)

            one_hot = np.zeros_like(probs)
            one_hot[np.arange(len(yb)), yb] = 1.0
            total_loss += float(-np.mean(np.sum(one_hot * np.log(probs + 1e-9), axis=1)))
            n_batches += 1

            dout = (probs - one_hot) / len(yb)
            dW3 = h2.T @ dout
            db3 = dout.sum(axis=0)
            dh2 = (dout @ model.W3.T) * (h2 > 0)
            dW2 = h1.T @ dh2
            db2 = dh2.sum(axis=0)
            dh1 = (dh2 @ model.W2.T) * (h1 > 0)
            dW1 = Xb.T @ dh1
            db1 = dh1.sum(axis=0)

            model.W3 -= lr * dW3; model.b3 -= lr * db3
            model.W2 -= lr * dW2; model.b2 -= lr * db2
            model.W1 -= lr * dW1; model.b1 -= lr * db1

        avg_loss = total_loss / max(n_batches, 1)
        if on_epoch is not None:
            preds = np.argmax(model.forward(X), axis=1)
            acc = float((preds == y).mean())
            on_epoch(epoch + 1, avg_loss, acc)

        if should_stop is not None and should_stop():
            break