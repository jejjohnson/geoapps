"""Mask overlap and label carry-over (sub-decision E1).

IoU(M_a, M_b) = |M_a ∧ M_b| / |M_a ∨ M_b|
a label ℓ carries over to a new detection d  ⇔  IoU(G_ℓ, M_d) ≥ τ
"""

import numpy as np
from numpy.typing import ArrayLike


def iou(mask_a: ArrayLike, mask_b: ArrayLike) -> float:
    a = np.asarray(mask_a, dtype=bool)  # (H, W)
    b = np.asarray(mask_b, dtype=bool)  # (H, W)
    union = np.logical_or(a, b).sum()
    if union == 0:
        return 0.0
    return float(np.logical_and(a, b).sum() / union)  # (H, W) × 2 → ()


def label_carries_over(label_mask: ArrayLike, detection_mask: ArrayLike, tau: float = 0.5) -> bool:
    return iou(label_mask, detection_mask) >= tau
