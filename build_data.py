#!/usr/bin/env python3
"""
RAA Extreme 2026 — Datenaufbereitung (Fokus Sebastian Trimborn)

Holt die aktuellen Renndaten vom Tracking-Server und schreibt site/data.json,
das vom Dashboard (site/index.html) gelesen wird. Wird von GitHub Actions
alle paar Minuten ausgeführt.

    python3 build_data.py

Benötigt nur Python 3, keine zusätzlichen Pakete.
"""

import json
import os
import re
import shutil
import time
import urllib.request

API = "https://race.perfect-tracking.com/api"
RACE_ID = 43            # RaceAroundAustria 2026
GROUP = 197             # RAA Extreme Solo
FOCUS = 2563            # Sebastian Trimborn
RIVALS = [2565, 2559]   # Rainer Steinberger, Lukas Kaufmann
TRACKED = [FOCUS] + RIVALS
HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
HTML = os.path.join(HERE, "index.html")
OUT = os.path.join(SITE, "data.json")
CACHE = os.path.join(HERE, ".raa_cache")
os.makedirs(CACHE, exist_ok=True)
os.makedirs(SITE, exist_ok=True)


def get(path, cache_name=None, max_age=None):
    """GET auf die Tracking-API, optional mit Datei-Cache."""
    cp = os.path.join(CACHE, cache_name) if cache_name else None
    if cp and os.path.exists(cp) and (max_age is None or time.time() - os.path.getmtime(cp) < max_age):
        with open(cp, encoding="utf-8") as fh:
            return json.load(fh)
    # Der Tracking-Server steht hinter Cloudflare und weist Anfragen ab, die nicht
    # wie ein echter Browser aussehen — deshalb der vollstaendige Header-Satz.
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Referer": "https://race.perfect-tracking.com/race/raa2026/ergebnisse",
        "Origin": "https://race.perfect-tracking.com",
        "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Connection": "keep-alive",
    }
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(f"{API}/{path}", headers=headers)
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.loads(r.read().decode("utf-8"))
            break
        except Exception as e:                       # 403/429 sind meist voruebergehend
            last = e
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
    if cp:
        with open(cp, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    return data


def sec(t):
    m = re.match(r"(?:(\d+)d )?(\d+):(\d+)(?::(\d+))?$", t.strip())
    return None if not m else int(m.group(1) or 0) * 86400 + int(m.group(2)) * 3600 \
        + int(m.group(3)) * 60 + int(m.group(4) or 0)


def km(x):
    return float(x.replace(".", "").replace(",", "."))


def elapsed_at(track, k):
    if k < track[0][0] - 0.001 or k > track[-1][0] + 0.001:
        return None
    for i in range(1, len(track)):
        k0, e0 = track[i - 1]
        k1, e1 = track[i]
        if k <= k1:
            return e1 if k1 == k0 else e0 + (e1 - e0) * (k - k0) / (k1 - k0)
    return track[-1][1]


def build():
    """Holt alles Nötige und schreibt dash.json."""
    # Route und Streckenprofil ändern sich nicht — einen Tag cachen.
    route = get(f"Race/DataRouteAll/{RACE_ID}", "route.json", 86400)["data"]["routes"]
    r71 = [r for r in route if r["id"] == 71][0]["data"]
    total = r71[-1][2]

    raw = get(f"Live/DataLiveAll/{RACE_ID}")
    live = raw["data"]
    upd = {x["id"]: x for x in live["update"]}
    group_ids = [p["id"] for p in live["teilnehmer"] if p["gruppe"] == GROUP]

    riders = {}
    for rid in group_ids:
        # Zwischenzeiten ändern sich nur an den Zeitnahmestellen — 3 Minuten cachen.
        d = get(f"Race/DataPageTeilnehmer/{rid}", f"t{rid}.json", 180)["data"]
        st = []
        for r in d["stationen"]:
            e = sec(r[5])
            if r[0] != 0 and e == 0:
                continue
            st.append({"idx": r[0], "name": r[1][0], "km": km(r[2]), "alt": r[3],
                       "rank": r[4], "elapsed": e, "speed": float(r[7].replace(",", ".")),
                       "clock": r[8]})
        u = upd[rid]
        now_km = r71[u["point"]][2]
        riders[rid] = {
            "id": rid, "name": d["name"], "num": d["startnummer"], "stations": st,
            "track": [(s["km"], s["elapsed"]) for s in st] + [(now_km, u["runtimesec"])],
            "now_km": now_km, "now_alt": r71[u["point"]][3], "elapsed": u["runtimesec"],
            "speed": u["speed"], "geo": u["geo"], "status": u["status"],
            "eta": u.get("finishest"), "etatol": u.get("finishesttol"),
            "start": st[0]["clock"], "runtime": u["runtime"],
            "avg": round(now_km / (u["runtimesec"] / 3600), 2),
        }

    def recent_kmh(r):
        st = r["stations"]
        seg = None
        if st and r["now_km"] > st[-1]["km"] and r["elapsed"] > st[-1]["elapsed"]:
            seg = (r["now_km"] - st[-1]["km"]) / ((r["elapsed"] - st[-1]["elapsed"]) / 3600)
        v = r["speed"] if r["speed"] and r["speed"] >= 12 else (seg or r["avg"])
        return max(10.0, min(45.0, v))

    f = riders[FOCUS]

    def gap_to_focus(rid):
        """Minuten, die der Fokusfahrer HINTER Fahrer rid liegt (+ = dahinter)."""
        if rid == FOCUS:
            return 0.0
        r = riders[rid]
        road = r["now_km"] - f["now_km"]
        if abs(road) <= 20 and r["status"] == 1 and f["status"] == 1:
            v = (recent_kmh(f) + recent_kmh(r)) / 2
            return round((road / v * 3600 - (r["elapsed"] - f["elapsed"])) / 60, 1)
        ref = min(f["now_km"], r["now_km"])
        ef, er = elapsed_at(f["track"], ref), elapsed_at(r["track"], ref)
        return None if ef is None or er is None else round((ef - er) / 60, 1)

    gapcurve = []
    for s in f["stations"]:
        gapcurve.append({"km": round(s["km"], 2), "name": s["name"], "gaps": {
            str(rid): (lambda e: None if e is None else round((s["elapsed"] - e) / 60, 1))(
                elapsed_at(riders[rid]["track"], s["km"])) for rid in RIVALS}})
    gapcurve.append({"km": round(f["now_km"], 2), "name": "jetzt", "now": True,
                     "gaps": {str(rid): gap_to_focus(rid) for rid in RIVALS}})

    for rid in TRACKED:
        r = riders[rid]
        pts = [(s["km"], s["elapsed"], s["name"]) for s in r["stations"]] + \
              [(r["now_km"], r["elapsed"], "jetzt")]
        r["segments"] = [{"to": pts[i][2], "km": round(pts[i][0] - pts[i - 1][0], 1),
                          "kmh": round((pts[i][0] - pts[i - 1][0]) /
                                       ((pts[i][1] - pts[i - 1][1]) / 3600), 1),
                          "endkm": round(pts[i][0], 1)}
                         for i in range(1, len(pts))
                         if pts[i][1] > pts[i - 1][1] and pts[i][0] > pts[i - 1][0]]
        e0 = elapsed_at(r["track"], r["now_km"] - 50)
        r["v50"] = None if e0 is None else round(50 / ((r["elapsed"] - e0) / 3600), 1)

    speedrows = []
    for s in [x for x in f["segments"] if x["to"] != "jetzt"][-7:]:
        row = {"to": s["to"], "km": s["endkm"], "v": {}}
        for rid in TRACKED:
            m = [x for x in riders[rid]["segments"]
                 if x["to"] == s["to"] and abs(x["endkm"] - s["endkm"]) < 0.5]
            row["v"][str(rid)] = m[0]["kmh"] if m else None
        speedrows.append(row)
    speedrows.append({"to": "laufender Abschnitt", "km": round(f["now_km"], 1),
                      "v": {str(rid): riders[rid]["segments"][-1]["kmh"] for rid in TRACKED}})

    stat_rows = []
    for s in f["stations"]:
        row = {"name": s["name"], "km": round(s["km"], 1), "alt": s["alt"], "e": {}, "g": {}}
        for rid in TRACKED:
            m = [x for x in riders[rid]["stations"]
                 if x["name"] == s["name"] and abs(x["km"] - s["km"]) < 0.5]
            row["e"][str(rid)] = m[0]["elapsed"] if m else None
            if rid != FOCUS:
                e = elapsed_at(riders[rid]["track"], s["km"])
                row["g"][str(rid)] = None if e is None else round((s["elapsed"] - e) / 60, 1)
        stat_rows.append(row)

    field = [{"id": rid, "name": riders[rid]["name"], "num": riders[rid]["num"],
              "km": round(riders[rid]["now_km"], 1), "status": riders[rid]["status"],
              "speed": riders[rid]["speed"], "geo": riders[rid]["geo"],
              "eta": riders[rid]["eta"], "gap": gap_to_focus(rid), "avg": riders[rid]["avg"],
              "runtime": riders[rid]["runtime"], "tracked": rid in TRACKED}
             for rid in group_ids]
    field.sort(key=lambda z: (z["status"] == 3, -999999 if z["gap"] is None else -z["gap"]))

    out = {
        "snapshot": raw["time"], "total_km": total, "focus": str(FOCUS),
        "order": [str(x) for x in TRACKED],
        "riders": {str(rid): {k: v for k, v in riders[rid].items() if k != "track"}
                   for rid in TRACKED},
        "nowgaps": {str(rid): gap_to_focus(rid) for rid in RIVALS},
        "gapcurve": gapcurve, "speedrows": speedrows, "stat_rows": stat_rows, "field": field,
        "profile": [[round(r71[i][2], 1), round(r71[i][3])] for i in range(0, len(r71), 40)],
    }
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    os.replace(tmp, OUT)
    return out


if __name__ == "__main__":
    d = build()
    shutil.copyfile(HTML, os.path.join(SITE, "index.html"))
    print(f"site/data.json geschrieben — Trimborn km "
          f"{d['riders'][str(FOCUS)]['now_km']:.1f}, "
          f"Steinberger {-d['nowgaps'][str(RIVALS[0])]:+.0f} min, "
          f"Kaufmann {-d['nowgaps'][str(RIVALS[1])] / 60:+.1f} h")
