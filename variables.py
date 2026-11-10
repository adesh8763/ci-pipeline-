"""Variable catalogue: the single place where every predictor is defined, grouped and documented.
(Answers the supervisor's "Variables?" comment: `python variables.py` writes variable_catalogue.csv / .md
for pasting into the paper's data section.)

Dataset column naming:  <source>_<variable>[_<stat>]   source in {seviri, radar, era5, imerg, ctx}
"""
import re
import sys

# --- primary groups used by the models M1..M7
SAT, RADAR, ATM, PRECIP, CTX = "seviri_", "radar_", "era5_", "imerg_", "ctx_"

# --- ERA5 sub-groups (physical mechanism). Regex on the variable name after "era5_".
ATM_SUBGROUPS = {
    "thermo":   r"^(CAPE|CIN|LAPSE_850_500|T_925|T2M|SST)$",        # instability / buoyancy
    "moisture": r"^(TCWV|RH_700|RH_850|RH_700_850_mean|Q_925|D2M)$", # moisture availability
    "shear":    r"^(SHEAR_\d+_\d+)$",                                  # organisation / updraught tilt
    "dynamics": r"^(OMEGA_700)$",                                      # large-scale ascent
    "pbl":      r"^(BLH|PS)$",                                         # boundary-layer depth / pressure
}

CATALOGUE = [
    # source, variable, units, description, role
    ("SEVIRI L1.5", "BT_IR039 / IR087 / IR108 / IR120 / IR134", "K", "Brightness temperature, window & CO2 channels", "cloud-top temperature & phase"),
    ("SEVIRI L1.5", "BT_WV062 / WV073", "K", "Brightness temperature, water-vapour channels", "upper/mid-level moisture, cloud-top height"),
    ("SEVIRI derived", "d_BT108_15min / 30min", "K per 15/30 min", "10.8 um cooling rate", "updraught growth (key CI signal)"),
    ("SEVIRI derived", "BTD_62_73, BTD_87_108, BTD_108_120, BTD_39_108", "K", "Channel differences", "cloud-top height, phase, glaciation, particle size"),
    ("NPOL radar", "radar_cmax_{max,mean}, radar_frac_gt10, radar_frac_gt0", "dBZ / fraction", "Column-max reflectivity statistics within RADAR_WIN_KM of the event BEFORE first echo", "pre-existing weak echoes / developing cell"),
    ("ERA5 thermo", "CAPE, CIN, LAPSE_850_500, T_925, T2M, SST", "J/kg, K, K/km", "Instability & buoyancy", "environment: energy"),
    ("ERA5 moisture", "TCWV, RH_700, RH_850, RH_700_850_mean, Q_925, D2M", "kg/m2, %, g/kg, K", "Moisture availability", "environment: moisture"),
    ("ERA5 shear", "SHEAR_925_600, SHEAR_925_500", "m/s", "Bulk wind shear", "environment: organisation"),
    ("ERA5 dynamics", "OMEGA_700", "Pa/s", "Large-scale vertical motion", "environment: forcing"),
    ("ERA5 pbl", "BLH, PS", "m, Pa", "Boundary-layer height, surface pressure", "environment: mixing"),
    ("IMERG V07", "imerg_p_last, imerg_p_accum, imerg_frac_wet, imerg_p_max", "mm/h, mm, fraction", "Satellite precipitation in the 0.1-deg box around the event, ONLY half-hours ending before t_ref", "pre-existing rainfall / wet-surface state"),
    ("Context", "ctx_hour_sin, ctx_hour_cos, ctx_range_km", "-, km", "Time of day of the forecast issue time, radar range of the event", "confounder control (diurnal cycle, detection sensitivity)"),
]


def group_of(col: str) -> str:
    for g, p in (("sat", SAT), ("radar", RADAR), ("atm", ATM), ("precip", PRECIP), ("ctx", CTX)):
        if col.startswith(p):
            return g
    return "other"


def atm_subgroup(col: str):
    if not col.startswith(ATM):
        return None
    name = col[len(ATM):]
    for g, pat in ATM_SUBGROUPS.items():
        if re.match(pat, name):
            return g
    return "other_atm"


def columns(df, group):
    if group == "sat":
        return [c for c in df.columns if c.startswith(SAT)]
    pref = {"radar": RADAR, "atm": ATM, "precip": PRECIP, "ctx": CTX}[group]
    return [c for c in df.columns if c.startswith(pref)]


def atm_columns(df, subgroups):
    return [c for c in columns(df, "atm") if atm_subgroup(c) in subgroups]


if __name__ == "__main__":
    import csv
    from config import PROCESSED
    with open(PROCESSED / "variable_catalogue.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["source", "variables", "units", "description", "physical_role"]); w.writerows(CATALOGUE)
    with open(PROCESSED / "variable_catalogue.md", "w") as f:
        f.write("| Source | Variables | Units | Description | Role |\n|---|---|---|---|---|\n")
        for r in CATALOGUE:
            f.write("| " + " | ".join(r) + " |\n")
    print("wrote", PROCESSED / "variable_catalogue.csv", "and .md")
