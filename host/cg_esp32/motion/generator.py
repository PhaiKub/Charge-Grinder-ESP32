"""Generate synthetic mouse speed and curve profiles using pca model.

Output semantics
----------------
speed        : px/s.
curve_series : θ(s) the heading angle on uniform arc-length.

Needs model.npz
If you want to see trainer implementation, you can check:
https://github.com/Walpth/ideal-mouse-movements
"""

import json
import math
from functools import lru_cache
import numpy as np

def _savgol_coeffs(window_length: int, polyorder: int, deriv: int = 0, delta: float = 1.0) -> np.ndarray:
    if window_length < 3: raise ValueError("window_length must be >= 3")
    if window_length % 2 == 0: raise ValueError("window_length must be odd")
    if polyorder < 0 or polyorder >= window_length: raise ValueError("Invalid polyorder")
    if deriv < 0: raise ValueError("deriv must be nonnegative")
    if deriv > polyorder: return np.zeros(window_length, dtype=np.float64)

    half = window_length // 2
    x = np.arange(half, -half - 1, -1, dtype=np.float64)
    order = np.arange(polyorder + 1, dtype=np.float64)[:, None]
    A = x ** order

    y = np.zeros(polyorder + 1, dtype=np.float64)
    y[deriv] = math.factorial(deriv) / (delta ** deriv)

    coeffs, *_ = np.linalg.lstsq(A, y, rcond=None)
    return coeffs.astype(np.float64, copy=False)

def _fit_edge_interpolation(x: np.ndarray, y: np.ndarray, *, window_length: int, polyorder: int, deriv: int, delta: float) -> None:
    half = window_length // 2
    idx = np.arange(window_length, dtype=np.float64)

    left_coeffs = np.polyfit(idx, x[:window_length], polyorder)
    if deriv > 0: left_coeffs = np.polyder(left_coeffs, m=deriv)
    left_x = np.arange(0, half, dtype=np.float64)
    y[:half] = np.polyval(left_coeffs, left_x) / (delta ** deriv)

    right_coeffs = np.polyfit(idx, x[-window_length:], polyorder)
    if deriv > 0: right_coeffs = np.polyder(right_coeffs, m=deriv)
    right_x = np.arange(window_length - half, window_length, dtype=np.float64)
    y[-half:] = np.polyval(right_coeffs, right_x) / (delta ** deriv)

def savgol_filter(x, window_length: int, polyorder: int, deriv: int = 0, delta: float = 1.0, axis: int = -1, mode: str = "interp", cval: float = 0.0):
    if mode != "interp": raise NotImplementedError("Only mode='interp' is implemented")
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim != 1: raise NotImplementedError("This local savgol_filter supports only 1D input")
    if arr.size < 3: return arr.copy()
    if window_length > arr.size: window_length = arr.size if arr.size % 2 != 0 else arr.size - 1
    if polyorder >= window_length: polyorder = window_length - 1
    if polyorder < 0: return arr.copy()

    coeffs = _savgol_coeffs(window_length, polyorder, deriv=deriv, delta=delta)
    y = np.convolve(arr, coeffs, mode="same")
    _fit_edge_interpolation(arr, y, window_length=window_length, polyorder=polyorder, deriv=deriv, delta=delta)
    return y


# Core generation

@lru_cache(maxsize=4)
def _load_model(model_path: str) -> dict:
    with np.load(model_path, allow_pickle=True) as data:
        d = {key: data[key] for key in data.files}
    # Dequantize int8 tables
    for key in [k for k in d if k.endswith("_q")]:
        base = key[:-2]
        d[base] = d[key].astype(np.float32) * d[base + "_scale"]
        del d[key]
    return d

def _knn_query_features(data, duration, distance, start=None, end=None,
                        submove_index=0, n_submoves=1, parent_distance=None) -> np.ndarray:
    if start is not None and end is not None:
        angle = math.atan2(float(end[1]) - float(start[1]), float(end[0]) - float(start[0]))
        ctx = [math.cos(angle), math.sin(angle), float(start[0]), float(start[1])]
    else:
        # no coordinates: neutral context
        ctx = list(data["knn_feat_mean"][2:6])
    parent = float(parent_distance) if parent_distance is not None else float(distance)
    raw = np.array([
        math.log(max(float(duration), 1e-3)), math.log(max(float(distance), 1.0)),
        *ctx,
        float(int(n_submoves) > 1), float(int(submove_index) > 0),
        math.log(max(parent, 1.0)),
    ])
    return (raw - data["knn_feat_mean"]) / data["knn_feat_std"]

# Importance weights on the z-scored context features
# [log_dur, log_dist, cos, sin, x0, y0, is_multi, is_later, log_parent_dist]:
# direction, screen position and the substroke's role within its parent move
# carry the personal patterns, so they get priority over dur/dist in the
# metric.
_KNN_FEATURE_WEIGHTS = np.array([0.8, 0.8, 1.5, 1.5, 1.2, 1.2, 1.5, 1.5, 0.6])

def _ess_weights(d2k: np.ndarray, target_ess: float):
    """Softmax weights over squared distances with bandwidth bisected until the
    effective sample size hits target_ess. Distances concentrate in this
    feature space, so a fixed bandwidth is either flat or a near-argmax; the
    ESS target keeps the density genuinely local while guaranteeing no single
    training stroke dominates (repeat queries sample a distribution, never
    replay one stroke)."""
    d2k = d2k - d2k.min()

    def weights(h2):
        w = np.exp(-0.5 * d2k / h2)
        w /= w.sum()
        return w, 1.0 / float(np.sum(w ** 2))

    lo, hi = 1e-6, max(float(d2k.max()), 1e-5) * 50.0
    w, ess = weights(hi)
    if ess > target_ess:
        for _ in range(24):
            mid = math.sqrt(lo * hi)
            w, ess = weights(mid)
            if abs(ess - target_ess) < 1.0:
                break
            if ess > target_ess:
                hi = mid
            else:
                lo = mid
    return w, ess

def _knn_neighborhood(data, feat_norm: np.ndarray, k: int = 96, target_ess: float = 16.0,
                      feature_weights=None):
    """Softmax-weighted substroke neighbors of the query context."""
    fw = _KNN_FEATURE_WEIGHTS if feature_weights is None else feature_weights
    table = data["knn_features_norm"].astype(float) * fw
    d2 = np.sum((table - feat_norm * fw) ** 2, axis=1)
    k = min(k, len(d2))
    idx = np.argpartition(d2, k - 1)[:k]
    w, ess = _ess_weights(d2[idx], target_ess)
    return idx, w, ess

def move_neighborhood(model_path, duration, distance, start, end, k: int = 96, target_ess: float = 16.0):
    """Shared move-level neighborhood over whole training strokes (episodes).

    One query here drives the layout AND every leg's profile, so a generated
    move's composition and kinematics come from the same behavioral episodes.
    Returns (rows, weights, ess) into the layout_* arrays.
    """
    data = _load_model(model_path)
    angle = math.atan2(float(end[1]) - float(start[1]), float(end[0]) - float(start[0]))
    raw = np.array([
        math.log(max(float(duration), 1e-3)), math.log(max(float(distance), 1.0)),
        math.cos(angle), math.sin(angle),
        float(start[0]), float(start[1]),
    ])
    feat = (raw - data["layout_ctx_mean"]) / data["layout_ctx_std"]
    fw = _KNN_FEATURE_WEIGHTS[:6]
    table = data["layout_context_norm"].astype(float) * fw
    d2 = np.sum((table - feat * fw) ** 2, axis=1)
    k = min(k, len(d2))
    rows = np.argpartition(d2, k - 1)[:k]
    w, ess = _ess_weights(d2[rows], target_ess)
    return rows, w, ess

_GLOBAL_DUR_SLOPE: dict = {}
DURATION_FLOOR_FRAC = 0.18


def _global_duration_slope(data, model_path) -> float:
    """Population log(duration) ~ log(distance) slope, cached per model. Floors
    the noisy local slope in sample_move_duration (which collapses to ~0 when the
    neighborhood has little distance spread, copying a mismatched-distance
    neighbor's absolute duration through uncorrected)."""
    if model_path not in _GLOBAL_DUR_SLOPE:
        feats = data["layout_features"].astype(float)
        ld = np.log(np.maximum(feats[:, 1], 1.0))
        lu = np.log(np.maximum(feats[:, 0], 1e-3))
        b = float(np.polyfit(ld, lu, 1)[0]) if len(ld) > 2 else 0.2
        _GLOBAL_DUR_SLOPE[model_path] = float(np.clip(b, 0.05, 1.0))
    return _GLOBAL_DUR_SLOPE[model_path]


def sample_move_context(model_path, distance, start, end, k: int = 96,
                        target_ess: float = 16.0, n_submovements: int | None = None,
                        curvature_pref: tuple[float, float] | None = None, seed=None):
    """One coherent move-level draw: (duration, donor_row, n_submoves).

    Queries the move-level context table WITHOUT the duration dimension
    (distance, direction, start position), then:
      1. draws n_submoves from the plain neighbor weights (preserves the real
         composition marginal exactly),
      2. picks a DONOR stroke among the n-matched neighbors, optionally
         re-weighted toward a curvature target (arc/chord),
      3. takes the donor's duration with a local Fitts-slope correction for
         the residual distance mismatch.

    The same donor drives the layout and every leg's episode downstream, so a
    sampled duration is always consistent with the composition it is budgeted
    into. Previously duration and layout came from INDEPENDENT neighbor picks:
    a 1.4s duration (real only for multi-submove moves) could land on a solo
    layout, creating single submoves slower than anything in training — and the
    reverse compressed legs too fast (Fitts sigma 0.170 vs real 0.141).
    """
    data = _load_model(model_path)
    rng = np.random.default_rng(seed)
    angle = math.atan2(float(end[1]) - float(start[1]), float(end[0]) - float(start[0]))
    raw = np.array([
        math.log(max(float(distance), 1.0)),
        math.cos(angle), math.sin(angle),
        float(start[0]), float(start[1]),
    ])
    feat = (raw - data["layout_ctx_mean"][1:]) / data["layout_ctx_std"][1:]
    fw = _KNN_FEATURE_WEIGHTS[1:6]
    table = data["layout_context_norm"][:, 1:].astype(float) * fw
    d2 = np.sum((table - feat * fw) ** 2, axis=1)
    k = min(k, len(d2))
    rows = np.argpartition(d2, k - 1)[:k]
    w, _ = _ess_weights(d2[rows], target_ess)

    feats = data["layout_features"][rows].astype(float)
    log_dur = np.log(np.maximum(feats[:, 0], 1e-3))
    log_dist = np.log(np.maximum(feats[:, 1], 1.0))
    mx, my = w @ log_dist, w @ log_dur
    var = w @ (log_dist - mx) ** 2
    slope = float(w @ ((log_dist - mx) * (log_dur - my)) / var) if var > 1e-9 else 0.0
    # Floor the local slope at the population distance->duration scaling. When the
    # neighborhood has little distance spread the local estimate collapses to ~0,
    # and a neighbor's absolute duration then gets copied onto a query at a very
    # different distance with no correction (e.g. a 0.45s/397px duration onto a
    # 31px move => eff 68px/s) — the source of the extreme slow-short outliers.
    slope = float(np.clip(max(slope, _global_duration_slope(data, model_path)), 0.0, 1.0))

    # 1. composition from the plain weights
    n_choices = data["layout_n_submoves"][rows].astype(int)
    if n_submovements is None:
        n_sub = int(rng.choice(n_choices, p=w))
    else:
        available = data["layout_n_submoves"].astype(int)
        n_sub = int(np.clip(int(n_submovements), 1, int(np.nanmax(available))))
        if not np.any(available == n_sub):
            n_sub = int(available[np.argmin(np.abs(available - n_sub))])
    n_sub = max(1, n_sub)

    # 2. donor among the n-matched neighbors (curvature preference within-n only,
    #    so a curvature target reshapes geometry without shifting the n marginal)
    mask = n_choices == n_sub
    if mask.any():
        cand_local = np.flatnonzero(mask)
        cw = w[cand_local].astype(float)
    else:
        global_match = np.flatnonzero(data["layout_n_submoves"].astype(int) == n_sub)
        cand_local = None
        cw = np.ones(len(global_match), dtype=float)
    if curvature_pref is not None and "layout_curvature" in data:
        target, bandwidth = curvature_pref
        rows_for_curv = rows[cand_local] if cand_local is not None else global_match
        curv = data["layout_curvature"][rows_for_curv].astype(float)
        cw = cw * np.exp(-np.abs(curv - float(target)) / max(float(bandwidth), 1e-6))
    if cw.sum() <= 0:
        cw = np.ones(len(cw), dtype=float)
    cw = cw / cw.sum()
    if cand_local is not None:
        j_local = int(rng.choice(len(cand_local), p=cw))
        j = int(cand_local[j_local])
        donor = int(rows[j])
        donor_log_dur, donor_log_dist = log_dur[j], log_dist[j]
    else:
        donor = int(global_match[int(rng.choice(len(global_match), p=cw))])
        dfeat = data["layout_features"][donor].astype(float)
        donor_log_dur = math.log(max(dfeat[0], 1e-3))
        donor_log_dist = math.log(max(dfeat[1], 1.0))

    # 3. donor duration, Fitts-corrected to the query distance
    log_query = math.log(max(float(distance), 1.0))
    log_d = donor_log_dur + slope * (log_query - donor_log_dist) + rng.normal(0.0, 0.03)
    # Bound slowness relative to the locally-typical duration at this distance, so
    # a sampled duration can't be much slower-for-distance than similar real moves.
    typical = my + slope * (log_query - mx)
    log_d = min(log_d, typical - math.log(DURATION_FLOOR_FRAC))
    duration = float(np.clip(math.exp(log_d), 0.04, 3.0))
    return duration, donor, n_sub


def sample_move_duration(model_path, distance, start, end, k: int = 96,
                         target_ess: float = 16.0, seed=None):
    """Duration-only wrapper around sample_move_context (kept for callers that
    do not need the coupled donor/layout row)."""
    duration, _donor, _n = sample_move_context(
        model_path, distance, start, end, k=k, target_ess=target_ess, seed=seed)
    return duration

def episode_for_legs(model_path, ref_layout_row: int, n_submoves: int, rows, w,
                     curvature_target: float | None = None):
    """Per-leg episode sampling spec for a chosen reference stroke.

    Each leg gets the reference stroke's own leg as the sample center plus
    role-matched legs from the whole neighborhood for the jitter covariance.
    Entries are None where the reference leg is missing from the score table
    (legs shorter than the training cutoff); those fall back to leg-level kNN.

    When curvature_target is set, the net-heading (theta_lin) jitter is
    suppressed so the selected straight reference is reproduced faithfully
    instead of being pulled back toward a curvy neighborhood.
    """
    data = _load_model(model_path)
    if ref_layout_row < 0:
        return [None] * n_submoves
    lin_jitter = CURV_TARGET_LIN_JITTER if curvature_target is not None else 1.0
    parent = data["knn_parent_row"]
    sidx = data["knn_sub_index"].astype(int)
    scnt = data["knn_sub_count"].astype(int)

    ref_leg_row = {int(sidx[r]): int(r) for r in np.flatnonzero(parent == ref_layout_row)}
    parent_w = np.zeros(int(parent.max()) + 2, dtype=float)
    parent_w[np.asarray(rows, dtype=int)] = np.asarray(w, dtype=float)
    in_nbr = (parent >= 0) & (parent_w[np.maximum(parent, 0)] > 0)

    episodes = []
    for i in range(n_submoves):
        if n_submoves == 1:
            role = (scnt == 1)
        elif i == 0:
            role = (sidx == 0) & (scnt > 1)
        else:
            role = (sidx > 0) & (scnt > 1)
        cand = np.flatnonzero(in_nbr & role)
        ref = ref_leg_row.get(i)
        if ref is None or len(cand) < 8:
            episodes.append(None)
            continue
        cw = parent_w[parent[cand]]
        cw = cw / cw.sum()
        episodes.append({
            "ref": ref,
            "cand": cand,
            "w": cw,
            "ess": 1.0 / float(np.sum(cw ** 2)),
            "lin_jitter": lin_jitter,
        })
    return episodes

def _weighted_gaussian_sample(values: np.ndarray, w, ess, rng) -> np.ndarray:
    """Sample from the weighted local Gaussian of the neighborhood's values."""
    mu = w @ values
    centered = values - mu
    cov = (centered * w[:, None]).T @ centered
    # Sharper neighborhoods estimate covariance from fewer effective samples,
    # so shrink toward the diagonal proportionally.
    shrink = min(0.5, 0.1 + 3.0 / max(ess, 1.0))
    cov = (1.0 - shrink) * cov + shrink * np.diag(np.diag(cov)) + np.eye(values.shape[1]) * 1e-6
    return rng.multivariate_normal(mu, cov)

def _sample_local_gaussian_scores(data, level: int, idx, w, ess, rng) -> np.ndarray:
    return _weighted_gaussian_sample(data[f"l{level}_knn_scores"][idx].astype(float), w, ess, rng)

# Scale of the deviation added around an episode's reference leg. Calibrated
# against the real peak-speed distribution: symmetric jitter in asinh space
# inflates peaks through sinh convexity, and 0.6 left vmax p50/p90 ~5-7% hot on
# mid/long moves; 0.4 matches real within ~2% with no measurable loss of
# curvature or profile-shape diversity (donor selection carries most variety).
_EPISODE_JITTER = 0.4
# Net-heading jitter multiplier when a curvature target is requested: shrink the
# theta_lin spread so the selected straight reference is not re-curved.
CURV_TARGET_LIN_JITTER = 0.15

def generate_mouse_profile(model_path, duration, distance, seed=None, start=None, end=None,
                           submove_index=0, n_submoves=1, parent_distance=None, episode=None):
    data = _load_model(model_path)
    config = json.loads(str(data["config_json"]))
    level_sizes = config["level_sizes"]
    rng = np.random.default_rng(seed)

    if "knn_features_norm" not in data:
        raise RuntimeError("Model predates the kNN score tables (v15+); retrain with main_pipeline/train.py")

    # Conditioning ladder
    use_episode = episode is not None
    if not use_episode:
        fw = None
        if start is None or end is None:
            fw = _KNN_FEATURE_WEIGHTS.copy()
            fw[2:6] = 0.0
        neighbor_idx, neighbor_w, neighbor_ess = _knn_neighborhood(
            data, _knn_query_features(data, duration, distance, start, end,
                                      submove_index, n_submoves, parent_distance),
            feature_weights=fw)

    joint_coeffs = []
    for i in range(len(config["level_sizes"])):
        if use_episode:
            scores = data[f"l{i}_knn_scores"]
            spread = _weighted_gaussian_sample(
                scores[episode["cand"]].astype(float), episode["w"], episode["ess"], rng)
            mu = episode["w"] @ scores[episode["cand"]].astype(float)
            z = scores[episode["ref"]].astype(float) + _EPISODE_JITTER * (spread - mu)
        else:
            z = _sample_local_gaussian_scores(data, i, neighbor_idx, neighbor_w, neighbor_ess, rng)
        z = np.clip(z, -3.5 * data[f"l{i}_score_std"], 3.5 * data[f"l{i}_score_std"])
        joint_coeffs.append(data[f"l{i}_m"] + z @ data[f"l{i}_c"])

    def _inverse(coeffs):
        v = coeffs[0]
        for i in range(1, len(level_sizes)):
            up = np.interp(
                np.linspace(0, 1, level_sizes[i]),
                np.linspace(0, 1, level_sizes[i-1]), v)
            up[1::2] += coeffs[i]
            v = up
        return v

    speed_coeffs = [jc[:len(jc)//2] * data[f"l{i}_scale"][0] for i, jc in enumerate(joint_coeffs)]
    theta_coeffs = [jc[len(jc)//2:] * data[f"l{i}_scale"][1] for i, jc in enumerate(joint_coeffs)]
    
    v_norm = np.sinh(_inverse(speed_coeffs))
    v_norm = np.clip(v_norm, 0.01, 15.0)

    v_s = v_norm * (distance / duration)
    theta = _inverse(theta_coeffs)

    # Re-inject the linear heading component
    if use_episode:
        lin_table = data["knn_theta_lin"][episode["cand"]].astype(float)
        lin_mu = episode["w"] @ lin_table
        spread = _weighted_gaussian_sample(lin_table, episode["w"], episode["ess"], rng)
        lin_jit = float(episode.get("lin_jitter", 1.0)) * _EPISODE_JITTER
        lin = data["knn_theta_lin"][episode["ref"]].astype(float) + lin_jit * (spread - lin_mu)
        lin = np.clip(lin, -3.5 * data["knn_theta_lin_std"], 3.5 * data["knn_theta_lin_std"])
        theta = theta + lin[0] + lin[1] * np.linspace(0.0, 1.0, len(theta))
    else:
        lin_table = data["knn_theta_lin"][neighbor_idx].astype(float)
        lin_mu = neighbor_w @ lin_table
        lin_sd = np.sqrt(np.maximum(neighbor_w @ (lin_table - lin_mu) ** 2, 1e-8))
        lin = _weighted_gaussian_sample(lin_table, neighbor_w, neighbor_ess, rng)
        lin = np.clip(lin, lin_mu - 2.5 * lin_sd, lin_mu + 2.5 * lin_sd)
        lin = np.clip(lin, -3.5 * data["knn_theta_lin_std"], 3.5 * data["knn_theta_lin_std"])
        theta = theta + lin[0] + lin[1] * np.linspace(0.0, 1.0, len(theta))

    return v_s, theta

def sample_theta_residual(model_path, n: int, speed_profile=None, seed=None) -> np.ndarray:
    data = _load_model(model_path)
    if "theta_residual_std" not in data or n <= 0:
        return np.zeros(max(n, 0), dtype=np.float32)

    rng = np.random.default_rng(seed)
    src_std = np.asarray(data["theta_residual_std"], dtype=float)
    std = np.interp(
        np.linspace(0.0, 1.0, n),
        np.linspace(0.0, 1.0, len(src_std)),
        src_std,
    )

    if speed_profile is not None:
        speed = np.asarray(speed_profile, dtype=float)
        if len(speed) == n and np.nanmedian(speed) > 1e-9:
            speed_gain = np.sqrt(np.clip(speed / np.nanmedian(speed), 0.25, 2.25))
            std *= speed_gain

    u = np.linspace(0.0, 1.0, n)
    n_knots = int(rng.integers(5, 11))
    interior = np.sort(rng.uniform(0.08, 0.92, max(0, n_knots - 2)))
    knot_u = np.concatenate([[0.0], interior, [1.0]])
    knot_y = rng.normal(0.0, 1.0, len(knot_u))
    knot_y[0] = 0.0
    knot_y[-1] = 0.0
    residual = np.interp(u, knot_u, knot_y)

    window = max(5, int(round(n * rng.uniform(0.055, 0.12))) | 1)
    if window < n:
        kernel = np.hanning(window)
        kernel /= max(float(kernel.sum()), 1e-9)
        pad = window // 2
        residual = np.convolve(np.pad(residual, pad, mode="edge"), kernel, mode="valid")

    residual -= residual.mean()
    rms = math.sqrt(float(np.mean(residual ** 2)))
    if rms > 1e-9:
        residual /= rms

    taper = np.sin(np.pi * u) ** 0.5
    residual = residual * std * taper
    residual -= np.linspace(residual[0], residual[-1], n)
    residual -= residual[0]
    return residual.astype(np.float32)
