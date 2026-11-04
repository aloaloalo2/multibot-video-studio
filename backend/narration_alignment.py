"""Joint phrase timing on the original audio's clock, without synthesis.

The quadratic program has only neighbouring constraints. Its interior-point
Newton system is tridiagonal, so even a long packed narration needs O(n) work
per iteration and no optional solver dependency.
"""
from __future__ import annotations

import numpy as np


def _tridiagonal(diagonal, off, rhs):
    """Solve a symmetric positive-definite tridiagonal Newton system."""
    d, b = diagonal.copy(), rhs.copy()
    for i in range(1, len(d)):
        ratio = off[i-1] / d[i-1]
        d[i] -= ratio * off[i-1]
        b[i] -= ratio * b[i-1]
    x = b / d
    for i in range(len(d)-2, -1, -1):
        x[i] -= off[i] * x[i+1] / d[i]
    return x


def propose(items: list[dict], total: float, gaps: list[float], *,
            min_speed: float, max_speed: float, max_shift: float) -> list[float] | None:
    """Minimize both boundary errors and unnecessary stretching for the full chain.

    Start/end displacements are the variables. Tempo, source windows, order and
    film boundaries are constraints. A small natural-duration penalty resolves
    negligible timing benefits gently. The caller must render from raw takes and
    validate actual decoded durations before accepting the proposal.
    """
    if not items:
        return None
    try:
        anchors = np.array([(x['original_start'], x['original_end']) for x in items], dtype=float)
        measured = np.array([x['fitted_length'] for x in items], dtype=float)
        speeds = np.array([x['speed'] for x in items], dtype=float)
        gaps = np.asarray(gaps, dtype=float)
    except (KeyError, TypeError, ValueError):
        return None
    n = len(items)
    if (not 0 < min_speed <= max_speed or not np.isfinite(max_shift) or max_shift <= 0
            or gaps.shape != (n-1,) or not np.isfinite(anchors).all()
            or not np.isfinite(measured).all() or not np.isfinite(speeds).all()
            or not np.isfinite(gaps).all() or np.any(gaps < 0)
            or np.any(measured <= 0) or np.any(speeds < min_speed)
            or np.any(speeds > max_speed) or np.any(anchors[:, 0] < 0)
            or np.any(anchors[:, 1] <= anchors[:, 0]) or not np.isfinite(total) or total <= 0):
        return None
    raw = measured * speeds
    shortest, longest = raw/max_speed, raw/min_speed
    lower = np.maximum(0., anchors-max_shift)-anchors
    upper = np.minimum(total, anchors+max_shift)-anchors
    if np.any(lower > upper) or shortest.sum()+gaps.sum() > total+1e-6:
        return None
    # Check local feasibility as well as the film's total space. This also keeps
    # an impossible chain away from a diverging primal/dual Newton iteration.
    previous_end = 0.
    for i in range(n):
        start = max(anchors[i, 0]+lower[i, 0], previous_end+(gaps[i-1] if i else 0.))
        end = max(anchors[i, 1]+lower[i, 1], start+shortest[i])
        start = max(start, end-longest[i])
        if start > anchors[i, 0]+upper[i, 0]+1e-6 or end > anchors[i, 1]+upper[i, 1]+1e-6:
            return None
        previous_end = end

    # .5*sum(start_shift^2+end_shift^2)
    # + .5*weight*sum((duration-natural_duration)^2).
    weight = .25
    span = anchors[:, 1]-anchors[:, 0]
    size = n*2
    hd = np.full(size, 1+weight)
    ho = np.zeros(size-1)
    ho[::2] = -weight
    linear = np.column_stack((-weight*(span-raw), weight*(span-raw))).ravel()

    # G*x <= bound. Each row has one coefficient or two adjacent coefficients.
    # Displacements keep long episodes well conditioned at their final phrases.
    all_vars = np.arange(size)
    starts = np.arange(0, size, 2)
    ends = starts+1
    left = np.concatenate((all_vars, all_vars, starts, starts, ends[:-1]))
    right = np.concatenate((all_vars, all_vars, ends, ends, starts[1:]))
    a = np.concatenate((np.ones(size), -np.ones(size), -np.ones(n), np.ones(n), np.ones(n-1)))
    b = np.concatenate((np.zeros(size*2), np.ones(n), -np.ones(n), -np.ones(n-1)))
    bound = np.concatenate((upper.ravel(), -lower.ravel(), longest-span,
                            span-shortest, anchors[1:, 0]-anchors[:-1, 1]-gaps))
    def multiply(x):
        return a*x[left]+b*x[right]
    def transpose(x):
        return (np.bincount(left, weights=a*x, minlength=size)
                + np.bincount(right, weights=b*x, minlength=size))
    def hessian(x):
        y = hd*x
        y[:-1] += ho*x[1:]
        y[1:] += ho*x[:-1]
        return y
    def positive_step(value, delta):
        falling = delta < 0
        return min(1., float(np.min(-value[falling]/delta[falling], initial=np.inf)))

    x = _tridiagonal(hd, ho, -linear)
    slack = np.maximum(1., bound-multiply(x))
    dual = np.ones(len(bound))
    for _ in range(100):
        primal = multiply(x)+slack-bound
        stationarity = hessian(x)+linear+transpose(dual)
        mu = float(np.mean(slack * dual))
        if max(np.max(np.abs(primal)), np.max(np.abs(stationarity)), mu) < 1e-7:
            duration = span+x[1::2]-x[::2]
            if np.max(multiply(x)-bound) <= 1e-6 and np.all(duration > 0):
                return np.clip(raw/duration, min_speed, max_speed).tolist()
            return None
        ratio = dual/slack
        diagonal = hd + np.bincount(left, weights=a*a*ratio, minlength=size)
        diagonal += np.bincount(right, weights=b*b*ratio, minlength=size)
        off = ho + np.bincount(left[b != 0], weights=(a*b*ratio)[b != 0], minlength=size)[:-1]
        def direction(complementarity):
            dx = _tridiagonal(diagonal, off,
                -stationarity+transpose((complementarity-dual*primal)/slack))
            ds = -primal-multiply(dx)
            dz = (-complementarity-dual*ds)/slack
            return dx, ds, dz
        # A long narration must not fall back to every phrase at the cap merely
        # because neighbour-by-neighbour relaxation cannot converge in time.
        _, ds, dz = direction(slack*dual)
        predicted = np.mean((slack+positive_step(slack, ds)*ds)
                            * (dual+positive_step(dual, dz)*dz))
        sigma = min(1., max(0., float(predicted/mu)))**3
        dx, ds, dz = direction(slack*dual+ds*dz-sigma*mu)
        primal_step = .995*positive_step(slack, ds)
        dual_step = .995*positive_step(dual, dz)
        x += primal_step*dx
        slack += primal_step*ds
        dual += dual_step*dz
        if not np.isfinite(x).all() or not np.isfinite(slack).all() or not np.isfinite(dual).all():
            return None
    return None  # Keep the previously measured, valid audio on non-convergence.
