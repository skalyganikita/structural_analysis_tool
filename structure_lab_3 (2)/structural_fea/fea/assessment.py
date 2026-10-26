"""Linear screening checks. First yield and Euler screening are NOT collapse."""

import numpy as np


def assess(result):
    """Return per-member maxima and the smallest proportional limit multiplier.

    Stress = N/A - M*y/I (tension positive). Deflection limit is the absolute
    translation magnitude, including joint sway, not chord-relative deflection.
    A user-enabled Euler check uses in-plane I and an explicit physical length.
    """
    # Keep each check separate: stress, displacement and Euler buckling
    # answer different questions and none is a complete collapse prediction.
    rows = []
    limits = []
    limit = result.model.get("deflection_limit", 0.025)
    raw_by_id = {e["id"]: e for e in result.model["elements"]}
    for e in result.elements:
        raw = raw_by_id[e.id]
        top, bottom = raw.get("c_top"), raw.get("c_bottom")
        fibres = [top, -bottom] if top and bottom else None
        x = e.critical_points(fibres)
        u, v, N, V, M = e.fields(x)
        # Pythagoras gives total translation from the two local components.
        translation = np.hypot(u, v)
        di = int(np.argmax(translation))
        disp = float(translation[di])
        row = dict(
            element=e.id,
            mass_kg=raw.get("density", 0) * e.A * e.L if raw.get("density") else None,
            max_translation_m=disp,
            translation_x_m=float(x[di]),
            translation_ratio=disp / limit,
            peak_normal_stress_Pa=None,
            stress_x_m=None,
            stress_fibre=None,
            yield_ratio=None,
            first_yield_multiplier=None,
            compression_N=float(max(0, -np.min(N))),
            euler_load_N=None,
            euler_ratio=None,
            euler_multiplier=None,
            euler_status="Not enabled",
        )
        if disp > 0:
            limits.append((limit / disp, "Translation limit", e.id))
        if fibres and result.model["type"] == "frame":
            stress = np.array([N / e.A - M * y / e.I for y in fibres])
            where = np.unravel_index(np.argmax(abs(stress)), stress.shape)
            peak = float(abs(stress[where]))
            row.update(
                peak_normal_stress_Pa=peak,
                stress_x_m=float(x[where[1]]),
                stress_fibre=("top", "bottom")[where[0]],
            )
            if raw.get("material") == "Steel" and raw.get("fy"):
                ratio = peak / raw["fy"]
                row.update(
                    yield_ratio=ratio,
                    first_yield_multiplier=(1 / ratio if ratio > 0 else None),
                )
                if ratio > 0:
                    limits.append((1 / ratio, "First normal-stress yield", e.id))
        if raw.get("buckling_enabled"):
            K = raw.get("effective_length_factor")
            L = raw.get("buckling_length")
            if (
                result.model["type"] != "frame"
                or raw.get("material") != "Steel"
                or not (K and L and raw.get("fy"))
            ):
                row["euler_status"] = (
                    "Specify steel fy, effective-length factor and physical buckling length"
                )
            elif row["compression_N"] <= 1e-8:
                row["euler_status"] = "No compression in this load case"
            else:
                Pcr = float(np.pi**2 * e.E * e.I / (K * L) ** 2)
                row["euler_load_N"] = Pcr
                if Pcr / e.A > raw["fy"]:
                    row["euler_status"] = (
                        "Outside elastic Euler range: Pcr/A exceeds fy; use an inelastic design method"
                    )
                else:
                    ratio = row["compression_N"] / Pcr
                    row.update(
                        euler_ratio=ratio,
                        euler_multiplier=1 / ratio,
                        euler_status="In-plane Euler screening; peak compression envelope",
                    )
                    limits.append(
                        (1 / ratio, "Simplified in-plane Euler buckling", e.id)
                    )
        rows.append(row)
    governing = min(limits, key=lambda item: item[0]) if limits else None
    return rows, governing
