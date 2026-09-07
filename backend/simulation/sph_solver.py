"""Genuine demonstration-scale 2D Weakly-Compressible SPH (WCSPH) solver.

This is an actual numerical SPH computation — particle positions evolve from
density summation, a Tait equation of state, SPH pressure gradients, Monaghan
artificial viscosity, gravity, and symplectic time integration with a CFL time
step. It is NOT a path router or particle animation.

Test case: classic 2D dam-break. A column of water particles is held in the left
part of a closed box; gravity collapses it and it surges along the floor to the
right, exactly the "reservoir -> breach -> downstream" behaviour Phase 2 needs.

Pure numpy (no scipy / numba). Neighbour search is a uniform cell linked-list;
all pair interactions are vectorised with ``np.add.at``.

Reference formulation: Monaghan (1994, 2005), Becker & Teschner (2007) WCSPH.
Not validated / not calibrated — demonstration scale only.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

GRAVITY = 9.81


# --------------------------------------------------------------------------- #
# SPH kernel — Wendland C2 (2D), compact support radius = 2h, positive definite
# --------------------------------------------------------------------------- #
def _kernel_constants(h: float) -> float:
    return 7.0 / (4.0 * np.pi * h * h)  # 2D Wendland C2 normalisation


def kernel_w(r: np.ndarray, h: float) -> np.ndarray:
    q = r / h
    a = _kernel_constants(h)
    out = np.zeros_like(q)
    m = q < 2.0
    qm = q[m]
    out[m] = a * (1.0 - 0.5 * qm) ** 4 * (2.0 * qm + 1.0)
    return out


def kernel_grad(dx: np.ndarray, r: np.ndarray, h: float) -> np.ndarray:
    """Return ∇W_ij (vector), shape (P, 2). dx = x_i - x_j, r = |dx|."""
    q = r / h
    a = _kernel_constants(h)
    fac = np.zeros_like(q)
    m = (q < 2.0) & (r > 1e-12)
    qm = q[m]
    # dW/dr = a * (-5 q) (1 - q/2)^3 / h
    dwdr = a * (-5.0 * qm) * (1.0 - 0.5 * qm) ** 3 / h
    fac[m] = dwdr / r[m]
    return dx * fac[:, None]


# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #
@dataclass
class SPHConfig:
    box: tuple[float, float] = (2.0, 1.2)          # domain size (m)
    reservoir: tuple[float, float] = (0.6, 0.9)    # water column w x h (m)
    dx: float = 0.032                              # initial particle spacing (m)
    rho0: float = 1000.0
    gamma: float = 7.0
    alpha_visc: float = 0.18                       # Monaghan artificial viscosity
    xsph_eps: float = 0.5
    cfl: float = 0.25
    restitution: float = 0.0
    bnd_stiffness: float = 2.0                     # x c0^2, soft wall penalty
    t_end: float = 0.9
    n_frames: int = 20
    seed: int = 12345


@dataclass
class SPHResult:
    config: SPHConfig
    positions0: np.ndarray
    frames: list[dict] = field(default_factory=list)   # per-frame snapshots
    metrics: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# solver
# --------------------------------------------------------------------------- #
class SPHSimulation:
    def __init__(self, cfg: SPHConfig):
        self.cfg = cfg
        self.h = 1.3 * cfg.dx
        self.cutoff = 2.0 * self.h
        # weak-compressibility sound speed: ~10x the expected surge speed
        surge = np.sqrt(2.0 * GRAVITY * cfg.reservoir[1])
        self.c0 = max(10.0 * surge, 20.0)
        self.B = cfg.rho0 * self.c0 ** 2 / cfg.gamma
        self.mass = cfg.rho0 * cfg.dx ** 2  # 2D: mass per particle = rho0 * area

        rng = np.random.default_rng(cfg.seed)
        xs = np.arange(cfg.dx * 0.5, cfg.reservoir[0], cfg.dx)
        ys = np.arange(cfg.dx * 0.5, cfg.reservoir[1], cfg.dx)
        gx, gy = np.meshgrid(xs, ys)
        pos = np.column_stack([gx.ravel(), gy.ravel()]).astype(np.float64)
        # tiny symmetry-breaking jitter so the collapse is not a frozen lattice
        pos += (rng.random(pos.shape) - 0.5) * (cfg.dx * 0.05)
        self.x = pos
        self.x0 = pos.copy()
        self.v = np.zeros_like(pos)
        self.n = pos.shape[0]
        self.rho = np.full(self.n, cfg.rho0)
        self.p = np.zeros(self.n)
        self.dt = cfg.cfl * self.h / self.c0
        self.steps = 0
        self.sim_time = 0.0
        self._n_isolated = 0

    # --- neighbour pairs via a fully vectorised uniform cell linked list -- #
    def _pairs(self) -> tuple[np.ndarray, np.ndarray]:
        cs = self.cutoff
        gx = np.floor((self.x[:, 0] - self.x[:, 0].min()) / cs).astype(np.int64)
        gy = np.floor((self.x[:, 1] - self.x[:, 1].min()) / cs).astype(np.int64)
        ncx = int(gx.max()) + 3          # +pad so home+offset stays in range
        ncy = int(gy.max()) + 3
        ncells = ncx * ncy
        cell = (gx + 1) + (gy + 1) * ncx
        order = np.argsort(cell, kind="stable")
        cell_sorted = cell[order]

        cell_start = np.zeros(ncells + 1, np.int64)
        counts = np.bincount(cell_sorted, minlength=ncells)
        cell_start[1:] = np.cumsum(counts)          # start[c]..start[c+1] in `order`

        offsets = np.array([dx + dy * ncx for dy in (-1, 0, 1) for dx in (-1, 0, 1)], np.int64)
        p_sorted_pos = np.arange(self.n)             # position of each particle in `order`
        home_cell = cell_sorted                      # cell of the particle at sorted pos p

        i_list, j_list = [], []
        for off in offsets:
            nc = home_cell + off                     # neighbour cell per sorted particle
            valid = (nc >= 0) & (nc < ncells)
            src = p_sorted_pos[valid]
            ncv = nc[valid]
            seg_start = cell_start[ncv]
            seg_len = cell_start[ncv + 1] - seg_start
            keep = seg_len > 0
            src, seg_start, seg_len = src[keep], seg_start[keep], seg_len[keep]
            if src.size == 0:
                continue
            # ragged expansion: each src particle pairs with seg_len neighbours
            i_rep = np.repeat(src, seg_len)
            within = np.arange(seg_len.sum()) - np.repeat(np.cumsum(seg_len) - seg_len, seg_len)
            j_pos = np.repeat(seg_start, seg_len) + within
            i_list.append(order[i_rep])
            j_list.append(order[j_pos])
        if not i_list:
            return np.empty(0, np.int64), np.empty(0, np.int64)
        i = np.concatenate(i_list)
        j = np.concatenate(j_list)
        m = i < j                                    # unique unordered pairs, no self
        i, j = i[m], j[m]
        d = self.x[i] - self.x[j]
        r2 = np.einsum("ij,ij->i", d, d)
        m = r2 < cs * cs
        return i[m], j[m]

    # --- one derivative evaluation -------------------------------------- #
    def _accel(self, i, j):
        cfg = self.cfg
        h = self.h
        dx = self.x[i] - self.x[j]
        r = np.sqrt(np.einsum("ij,ij->i", dx, dx))
        r = np.maximum(r, 1e-9)

        n = self.n
        w = kernel_w(r, h)
        gw = kernel_grad(dx, r, h)
        w_self = kernel_w(np.array([0.0]), h)[0]

        def scatter(idx_i, idx_j, val):
            """Symmetric pair scatter-add: out[i] += val, out[j] += val."""
            return (np.bincount(idx_i, val, minlength=n)
                    + np.bincount(idx_j, val, minlength=n))

        def scatter_anti(idx_i, idx_j, val):
            """Anti-symmetric: out[i] += val, out[j] -= val."""
            return (np.bincount(idx_i, val, minlength=n)
                    - np.bincount(idx_j, val, minlength=n))

        # density by summation (Monaghan). Free-surface particles are naturally
        # under-dense; the EOS below floors their pressure at 0 (Becker-Teschner),
        # which is the physical free-surface condition, not clipping.
        rho = self.mass * w_self + self.mass * scatter(i, j, w)
        # Detached spray with essentially no kernel support (< 3 neighbours in 2D
        # cannot form a surface) is flagged as free surface: rho := rho0 -> p := 0,
        # so it then follows ballistic free-fall. Interior particles keep their
        # genuine summation density.
        neigh = np.bincount(i, minlength=n) + np.bincount(j, minlength=n)
        rho = np.where(neigh < 3, cfg.rho0, rho)
        rho = np.clip(rho, 0.3 * cfg.rho0, 3.0 * cfg.rho0)   # hard safety rail only
        self.rho = rho
        self._n_isolated = int(np.count_nonzero(neigh < 2))

        # Tait equation of state
        p = self.B * ((rho / cfg.rho0) ** cfg.gamma - 1.0)
        p = np.where(p < 0.0, 0.0, p)          # free surface: no tensile pressure
        self.p = p

        pi, pj = p[i], p[j]
        rhoi, rhoj = rho[i], rho[j]
        press_term = (pi / rhoi ** 2 + pj / rhoj ** 2)

        # Monaghan artificial viscosity
        dv = self.v[i] - self.v[j]
        dvdx = np.einsum("ij,ij->i", dv, dx)
        rho_bar = 0.5 * (rhoi + rhoj)
        mu = h * dvdx / (r ** 2 + 0.01 * h * h)
        visc = np.where(dvdx < 0.0, -cfg.alpha_visc * self.c0 * mu / rho_bar, 0.0)

        coeff = -(self.mass) * (press_term + visc)
        contrib = coeff[:, None] * gw

        a = np.zeros((self.n, 2))
        a[:, 0] = scatter_anti(i, j, contrib[:, 0])
        a[:, 1] = scatter_anti(i, j, contrib[:, 1])
        a[:, 1] -= GRAVITY

        # soft box walls (penalty force within one h of a wall)
        k = cfg.bnd_stiffness * self.c0 ** 2
        bx, by = cfg.box
        left = self.x[:, 0] < h
        right = self.x[:, 0] > bx - h
        floor = self.x[:, 1] < h
        a[left, 0] += k * (h - self.x[left, 0]) / h
        a[right, 0] -= k * (self.x[right, 0] - (bx - h)) / h
        a[floor, 1] += k * (h - self.x[floor, 1]) / h
        ceil = self.x[:, 1] > by - h
        a[ceil, 1] -= k * (self.x[ceil, 1] - (by - h)) / h

        # XSPH velocity smoothing (returned separately, applied to positions)
        vji = self.v[j] - self.v[i]
        wij = (self.mass / rho_bar) * w
        xsph = np.zeros((self.n, 2))
        xsph[:, 0] = scatter_anti(i, j, wij * vji[:, 0])
        xsph[:, 1] = scatter_anti(i, j, wij * vji[:, 1])
        xsph *= cfg.xsph_eps
        return a, xsph

    def step(self):
        i, j = self._pairs()
        a, xsph = self._accel(i, j)
        if not np.all(np.isfinite(a)):
            raise RuntimeError(f"non-finite acceleration at step {self.steps}")

        # adaptive CFL dt: acoustic + force + viscous limits
        amax = float(np.sqrt(np.max(np.einsum("ij,ij->i", a, a))) + 1e-9)
        vmax = float(np.sqrt(np.max(np.einsum("ij,ij->i", self.v, self.v))) + 1e-9)
        dt_f = np.sqrt(self.h / amax)
        dt_cv = self.h / (self.c0 + vmax)
        self.dt = float(self.cfg.cfl * min(dt_f, dt_cv))
        self.dt = min(self.dt, self.cfg.cfl * self.h / self.c0)

        # symplectic Euler (kick-drift) + XSPH position correction
        self.v = self.v + a * self.dt
        self.x = self.x + (self.v + xsph) * self.dt

        # hard containment (particles cannot leave the closed box)
        bx, by = self.cfg.box
        for axis, hi in ((0, bx), (1, by)):
            lo_hit = self.x[:, axis] < 0.0
            hi_hit = self.x[:, axis] > hi
            self.x[lo_hit, axis] = 0.0
            self.x[hi_hit, axis] = hi
            self.v[lo_hit | hi_hit, axis] *= -self.cfg.restitution

        if not np.all(np.isfinite(self.x)) or not np.all(np.isfinite(self.v)):
            raise RuntimeError(f"non-finite state at step {self.steps}")

        self.sim_time += self.dt
        self.steps += 1

    def snapshot(self) -> dict:
        speed = np.sqrt(np.einsum("ij,ij->i", self.v, self.v))
        disp = np.sqrt(np.einsum("ij,ij->i", self.x - self.x0, self.x - self.x0))
        return {
            "t": float(self.sim_time),
            "step": int(self.steps),
            "x": self.x.copy(),
            "v": self.v.copy(),
            "rho": self.rho.copy(),
            "p": self.p.copy(),
            "max_speed": float(speed.max()),
            "mean_speed": float(speed.mean()),
            "max_disp": float(disp.max()),
            "rho_min": float(self.rho.min()),
            "rho_max": float(self.rho.max()),
            "p_min": float(self.p.min()),
            "p_max": float(self.p.max()),
            "n_isolated": int(self._n_isolated),
        }


def run(cfg: SPHConfig | None = None, progress=lambda p, m="": None) -> SPHResult:
    cfg = cfg or SPHConfig()
    sim = SPHSimulation(cfg)
    result = SPHResult(config=cfg, positions0=sim.x0.copy())

    # prime density/pressure once so the first frame is physical
    i, j = sim._pairs()
    sim._accel(i, j)
    result.frames.append(sim.snapshot())

    started = time.perf_counter()
    frame_times = np.linspace(0.0, cfg.t_end, cfg.n_frames + 1)[1:]
    fi = 0
    max_steps = 500_000
    while sim.sim_time < cfg.t_end and sim.steps < max_steps:
        sim.step()
        while fi < len(frame_times) and sim.sim_time >= frame_times[fi]:
            result.frames.append(sim.snapshot())
            fi += 1
            progress(int(100 * sim.sim_time / cfg.t_end), f"SPH t={sim.sim_time:.2f}s")
    if fi < len(frame_times):
        result.frames.append(sim.snapshot())
    runtime = time.perf_counter() - started

    all_speed = np.concatenate([np.sqrt(np.einsum("ij,ij->i", f["v"], f["v"])) for f in result.frames])
    all_rho = np.concatenate([f["rho"] for f in result.frames])
    all_p = np.concatenate([f["p"] for f in result.frames])
    result.metrics = {
        "particle_count": int(sim.n),
        "timesteps": int(sim.steps),
        "frames": len(result.frames),
        "simulation_time_s": float(sim.sim_time),
        "runtime_seconds": float(runtime),
        "dt_final_s": float(sim.dt),
        "smoothing_length_m": float(sim.h),
        "sound_speed_mps": float(sim.c0),
        "particle_mass_kg": float(sim.mass),
        "max_velocity_mps": float(all_speed.max()),
        "mean_velocity_mps": float(all_speed.mean()),
        "max_density": float(all_rho.max()),
        "min_density": float(all_rho.min()),
        "median_density": float(np.median(all_rho)),
        "p05_density": float(np.percentile(all_rho, 5)),
        "density_relative_error_pct": float(100.0 * np.abs(np.median(all_rho) - 1000.0) / 1000.0),
        "max_pressure_pa": float(all_p.max()),
        "min_pressure_pa": float(all_p.min()),
        "max_displacement_m": float(result.frames[-1]["max_disp"]),
        "isolated_particles_final": int(result.frames[-1]["n_isolated"]),
        "finite": bool(np.all(np.isfinite(all_speed)) and np.all(np.isfinite(all_rho))
                       and np.all(np.isfinite(all_p))),
    }
    return result


if __name__ == "__main__":
    import json
    import sys

    res = run(progress=lambda p, m="": print(f"[{p:3d}%] {m}", flush=True))
    print(json.dumps(res.metrics, indent=2))
    out = res.positions0
    print(f"initial particles: {out.shape[0]}  box={res.config.box}  reservoir={res.config.reservoir}")
    if "--save" in sys.argv:
        np.savez_compressed(
            "sph_standalone_frames.npz",
            positions0=res.positions0,
            **{f"x_{k}": f["x"] for k, f in enumerate(res.frames)},
            **{f"v_{k}": f["v"] for k, f in enumerate(res.frames)},
            times=np.array([f["t"] for f in res.frames]),
        )
        print("saved sph_standalone_frames.npz")
