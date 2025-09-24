"""
backend/main.py
CNC Laser Time Study API (Expanded Version)
"""

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Tuple
import math
import re

# =============================================================================
# Application Setup
# =============================================================================

FRONTEND_ORIGINS = [
    "http://192.168.254.135:3009",
    "http://localhost:3009",
]

app = FastAPI(title="CNC Time Study API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Helpers
# =============================================================================

TOKEN_RE = re.compile(r"([A-Za-z][+\-0-9.]+)")

def strip_semicolon_comments(line: str) -> str:
    if ";" in line:
        return line.split(";", 1)[0]
    return line

def strip_parenthetical_comments(line: str) -> str:
    while True:
        s = line.find("(")
        if s == -1:
            return line
        e = line.find(")", s + 1)
        if e == -1:
            return line[:s]
        line = line[:s] + line[e + 1:]

def normalize_mcode(code: str) -> str:
    code = code.strip().upper()
    if not code:
        return code
    if code[0] == "M":
        num = code[1:].lstrip("0")
        return "M" + (num if num else "0")
    return code

def move_time_trap(distance_mm: float, feed_mm_min: float, accel_g: float) -> float:
    if distance_mm <= 0.0 or feed_mm_min <= 0.0 or accel_g <= 0.0:
        return 0.0
    vmax = feed_mm_min / 60.0
    a = accel_g * 9.81 * 1000.0
    d_acc = (vmax * vmax) / (2.0 * a)
    if 2.0 * d_acc < distance_mm:
        t_acc = vmax / a
        d_cruise = distance_mm - 2.0 * d_acc
        t_cruise = d_cruise / vmax
        return 2.0 * t_acc + t_cruise
    v_peak = math.sqrt(distance_mm * a)
    t_acc = v_peak / a
    return 2.0 * t_acc

def add_segment(segments: List[dict], kind: str, p0: Tuple[float, float], p1: Tuple[float, float]):
    segments.append({"type": kind, "points": [[p0[0], p0[1]], [p1[0], p1[1]]]})

def normalize_toolpath(tp: List[dict], box: float = 400.0) -> List[dict]:
    if not tp:
        return tp
    xs, ys = [], []
    for seg in tp:
        for px, py in seg["points"]:
            xs.append(px); ys.append(py)
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    dx = maxx - minx if maxx > minx else 1.0
    dy = maxy - miny if maxy > miny else 1.0
    scale = box / max(dx, dy)
    out = []
    for seg in tp:
        pts = []
        for px, py in seg["points"]:
            pts.append([(px - minx) * scale, (py - miny) * scale])
        out.append({"type": seg["type"], "points": pts})
    return out

# =============================================================================
# API
# =============================================================================

@app.get("/")
async def root():
    return {"message": "CNC Time Study API running"}

@app.post("/analyze")
async def analyze(
    file: UploadFile = File(...),

    rapid_accel_g: float       = Form(1.0),
    cut_accel_g: float         = Form(0.5),
    pierce_time: float         = Form(1.0),
    lifter_time: float         = Form(0.5),
    default_rapid_ipm: float   = Form(500.0),
    default_cut_ipm: float     = Form(100.0),

    beam_on_code: str          = Form("M07"),
    beam_off_code: str         = Form("M08"),

    inch_mode_code: str        = Form("G70"),
    metric_mode_code: str      = Form("G71"),
    abs_mode_code: str         = Form("G90"),
    rel_mode_code: str         = Form("G91"),
):

    # -------------------------------------------------------------------------
    # Defaults
    # -------------------------------------------------------------------------
    default_rapid_mm_min = default_rapid_ipm * 25.4
    default_cut_mm_min   = default_cut_ipm * 25.4

    x = y = 0.0
    beam_on = False
    feed_mm_min = 0.0
    unit_factor = 1.0
    absolute_mode = True

    cut_time_s = travel_time_s = pierce_time_s = dwell_time_s = lifter_time_s = 0.0
    pierce_count = beam_cycles = 0
    toolpath: List[dict] = []

    target_on  = normalize_mcode(beam_on_code)
    target_off = normalize_mcode(beam_off_code)

    inch_mode   = inch_mode_code.strip().upper()
    metric_mode = metric_mode_code.strip().upper()
    abs_mode    = abs_mode_code.strip().upper()
    rel_mode    = rel_mode_code.strip().upper()

    raw_bytes = await file.read()
    lines = raw_bytes.decode(errors="ignore").splitlines()

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        line = strip_semicolon_comments(line)
        line = strip_parenthetical_comments(line)
        line = line.strip()
        if not line:
            continue

        parts = TOKEN_RE.findall(line.upper())
        if not parts:
            continue
        cmd = parts[0]

        # Modes
        if cmd in (inch_mode, "G20"):
            unit_factor = 25.4
            continue
        if cmd in (metric_mode, "G21"):
            unit_factor = 1.0
            continue
        if cmd == abs_mode:
            absolute_mode = True
            continue
        if cmd == rel_mode:
            absolute_mode = False
            continue

        # Beam
        cmd_norm = normalize_mcode(cmd)
        if cmd_norm == target_on:
            if not beam_on:
                beam_on = True
                pierce_time_s += float(pierce_time)
                lifter_time_s += float(lifter_time)
                pierce_count += 1
                beam_cycles += 1
            continue
        if cmd_norm == target_off:
            if beam_on:
                beam_on = False
                lifter_time_s += float(lifter_time)
                beam_cycles += 1
            continue

        # Dwell
        if cmd in ("G4", "G04"):
            dwell_s = 0.0
            for t in parts[1:]:
                if t.startswith("S"):
                    dwell_s = float(t[1:])
                elif t.startswith("P"):
                    val = float(t[1:])
                    dwell_s = (val / 1000.0) if val > 50 else val
            dwell_time_s += dwell_s
            continue

        # Feed update
        for t in parts[1:]:
            if t.startswith("F"):
                feed_mm_min = float(t[1:]) * unit_factor

        # Rapids
        if cmd in ("G0", "G00"):
            nx, ny = x, y
            for t in parts[1:]:
                if t.startswith("X"):
                    val = float(t[1:]) * unit_factor
                    nx = val if absolute_mode else (x + val)
                elif t.startswith("Y"):
                    val = float(t[1:]) * unit_factor
                    ny = val if absolute_mode else (y + val)
            dist = math.hypot(nx - x, ny - y)
            travel_time_s += move_time_trap(dist, default_rapid_mm_min, rapid_accel_g)
            add_segment(toolpath, "travel", (x, y), (nx, ny))
            x, y = nx, ny
            continue

        # Linear
        if cmd in ("G1", "G01"):
            nx, ny = x, y
            local_feed = feed_mm_min
            for t in parts[1:]:
                if t.startswith("X"):
                    val = float(t[1:]) * unit_factor
                    nx = val if absolute_mode else (x + val)
                elif t.startswith("Y"):
                    val = float(t[1:]) * unit_factor
                    ny = val if absolute_mode else (y + val)
                elif t.startswith("F"):
                    local_feed = float(t[1:]) * unit_factor
            dist = math.hypot(nx - x, ny - y)
            if beam_on:
                fr = local_feed if local_feed > 0 else default_cut_mm_min
                cut_time_s += move_time_trap(dist, fr, cut_accel_g)
                add_segment(toolpath, "cut", (x, y), (nx, ny))
            else:
                travel_time_s += move_time_trap(dist, default_rapid_mm_min, rapid_accel_g)
                add_segment(toolpath, "travel", (x, y), (nx, ny))
            x, y = nx, ny
            continue

        # Arcs
        if cmd in ("G2", "G02", "G3", "G03"):
            nx, ny = x, y
            i_off = j_off = 0.0
            local_feed = feed_mm_min
            for t in parts[1:]:
                if t.startswith("X"):
                    val = float(t[1:]) * unit_factor
                    nx = val if absolute_mode else (x + val)
                elif t.startswith("Y"):
                    val = float(t[1:]) * unit_factor
                    ny = val if absolute_mode else (y + val)
                elif t.startswith("I"):
                    i_off = float(t[1:]) * unit_factor
                elif t.startswith("J"):
                    j_off = float(t[1:]) * unit_factor
                elif t.startswith("F"):
                    local_feed = float(t[1:]) * unit_factor
            # Arc center handling
                cx = x + i_off
                cy = y + j_off
            r = math.hypot(x - cx, y - cy)
            if r <= 0.0:
                x, y = nx, ny
                continue
            a1 = math.atan2(y - cy, x - cx)
            a2 = math.atan2(ny - cy, nx - cx)
            if (abs(nx - x) < 1e-9 and abs(ny - y) < 1e-9 and (abs(i_off) > 1e-12 or abs(j_off) > 1e-12)):
                delta = -2.0 * math.pi if cmd.startswith("G2") else 2.0 * math.pi
            else:
                delta = a2 - a1
                if cmd.startswith("G2") and delta > 0:
                    delta -= 2.0 * math.pi
                if cmd.startswith("G3") and delta < 0:
                    delta += 2.0 * math.pi
            arc_len = abs(delta) * r
            if beam_on:
                fr = local_feed if local_feed > 0 else default_cut_mm_min
                cut_time_s += move_time_trap(arc_len, fr, cut_accel_g)
                seg_kind = "cut"
            else:
                travel_time_s += move_time_trap(arc_len, default_rapid_mm_min, rapid_accel_g)
                seg_kind = "travel"
            steps = max(40, int(abs(delta) * 80))
            px_prev, py_prev = x, y
            for s in range(1, steps + 1):
                ang = a1 + delta * (s / steps)
                px = cx + r * math.cos(ang)
                py = cy + r * math.sin(ang)
                add_segment(toolpath, seg_kind, (px_prev, py_prev), (px, py))
                px_prev, py_prev = px, py
            x, y = nx, ny
            continue

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    total_time_s = cut_time_s + travel_time_s + pierce_time_s + dwell_time_s + lifter_time_s
    norm_toolpath = normalize_toolpath(toolpath, box=400.0)
    final_modes = {
        "units": "inch" if unit_factor > 1.0 else "metric",
        "positioning": "absolute" if absolute_mode else "relative",
    }
    return {
        "filename": file.filename,
        "cut_time_sec": round(cut_time_s, 3),
        "travel_time_sec": round(travel_time_s, 3),
        "pierce_time_sec": round(pierce_time_s, 3),
        "dwell_time_sec": round(dwell_time_s, 3),
        "lifter_time_sec": round(lifter_time_s, 3),
        "total_time_sec": round(total_time_s, 3),
        "pierce_count": pierce_count,
        "beam_cycles": beam_cycles,
        "toolpath": norm_toolpath,
        "final_modes": final_modes,
    }