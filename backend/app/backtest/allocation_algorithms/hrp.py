"""Hierarchical Risk Parity (López de Prado, 2016) — Change 16 scipy second pass.

Three stages: (1) tree clustering of the correlation-distance matrix, (2) quasi-diagonal
leaf ordering, (3) recursive bisection allocating inverse-variance between clusters. HRP is
long-only and sums to 1 by construction, and it needs no matrix inversion — robust for
ill-conditioned covariances where min-variance struggles.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform


def _quasi_diag(link: np.ndarray) -> list[int]:
    """Return leaf order by unrolling the linkage tree (original-item indices)."""
    link = link.astype(int)
    n = link[-1, 3]  # total number of original items
    order = [link[-1, 0], link[-1, 1]]
    while max(order) >= n:
        expanded: list[int] = []
        for item in order:
            if item < n:
                expanded.append(item)
            else:  # a merged cluster — replace with its two children
                left, right = link[item - n, 0], link[item - n, 1]
                expanded.extend([left, right])
        order = expanded
    return order


def _cluster_var(cov: pd.DataFrame, items: list) -> float:
    sub = cov.loc[items, items].to_numpy()
    ivp = 1.0 / np.diag(sub)
    ivp /= ivp.sum()  # inverse-variance weights within the cluster
    return float(ivp @ sub @ ivp)


def hrp_weights(returns: pd.DataFrame) -> pd.Series:
    cols = list(returns.columns)
    n = len(cols)
    if n == 1:
        return pd.Series([1.0], index=cols)

    cov = returns.cov().fillna(0.0)
    corr = returns.corr().fillna(0.0)
    np.fill_diagonal(corr.values, 1.0)

    # Correlation distance, clustered with single linkage.
    dist = np.sqrt(np.clip((1.0 - corr.to_numpy()) / 2.0, 0.0, None))
    np.fill_diagonal(dist, 0.0)
    link = linkage(squareform(dist, checks=False), method="single")

    ordered = [cols[i] for i in _quasi_diag(link)]

    # Recursive bisection: split the ordered list, allocate inverse to cluster variance.
    weights = pd.Series(1.0, index=ordered)
    clusters = [ordered]
    while clusters:
        clusters = [
            half
            for cluster in clusters
            for half in (cluster[: len(cluster) // 2], cluster[len(cluster) // 2 :])
            if len(cluster) > 1
        ]
        for i in range(0, len(clusters), 2):
            left, right = clusters[i], clusters[i + 1]
            var_l, var_r = _cluster_var(cov, left), _cluster_var(cov, right)
            alpha = 1.0 - var_l / (var_l + var_r) if (var_l + var_r) > 0 else 0.5
            weights[left] *= alpha
            weights[right] *= 1.0 - alpha

    return weights.reindex(cols).fillna(0.0)
