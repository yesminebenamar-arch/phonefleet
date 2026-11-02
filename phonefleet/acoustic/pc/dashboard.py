"""Génération du dashboard HTML à partir des enregistrements collectés.

Mode statique : regénère une fois le HTML/CSV.
Mode live    : sert le dashboard sur http://localhost:PORT et le rafraîchit.

Classes du modèle : petit/moyen/grand bateau + bruit de fond (la classe
biologique a été retirée, faute de données).

Usage :
    python -m pc.dashboard --data recordings/
    python -m pc.dashboard --data recordings/ --live
"""

import argparse
import csv
import http.server
import socketserver
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import metadata
from core.logging_utils import get_logger

log = get_logger("dashboard")

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / "templates" / "dashboard.html"


def collect_records(data_dir: Path) -> list[dict]:
    records = []
    for txt_path in sorted(data_dir.rglob("log_*.txt"), reverse=True):
        wav_path = txt_path.with_suffix(".wav")
        meta = metadata.read(txt_path)
        wav_mb = round(wav_path.stat().st_size / 1_048_576, 2) if wav_path.exists() else 0.0
        ts = meta.get("timestamp", txt_path.stem.replace("log_", ""))
        # Année/date : depuis les métadonnées, sinon déduites du timestamp
        # (format YYYY-MM-DD_HH-MM-SS) pour rester compatible avec les anciens fichiers.
        year = meta.get("year", ts[:4] if len(ts) >= 4 else "????")
        date = meta.get("date", ts[:10] if len(ts) >= 10 else "?")
        site = meta.get("site", "inconnu").upper()
        if site == "INCONNU":
            # Anciens tests sans site renseigné, on les exclut du dashboard.
            continue
        records.append({
            "site": site,
            "year": year,
            "date": date,
            "piezo_model": meta.get("piezo_model", "N/A"),
            "piezo_serial": meta.get("piezo_serial", "N/A"),
            "timestamp": ts,
            "wav_ok": meta.get("wav_ok", "?"),
            "wav_size_mb": wav_mb,
            "detection_class": meta.get("detection_class", "N/A"),
            "detection_conf": meta.get("detection_conf", "N/A"),
            "detection_ratio": meta.get("detection_ratio", "N/A"),
            "alert_sent": meta.get("alert_sent", "non"),
            "battery_pct": meta.get("battery_pct", "N/A"),
            "battery_temp": meta.get("battery_temp", "N/A"),
            "battery_voltage": meta.get("battery_voltage", "N/A"),
            "gps_lat": meta.get("gps_lat", "N/A"),
            "gps_lon": meta.get("gps_lon", "N/A"),
            "gps_accuracy": meta.get("gps_accuracy", "N/A"),
            "frequency_hz": meta.get("frequency_hz", "N/A"),
        })
    # Classement hiérarchique : année la plus récente d'abord, puis site (A→Z),
    # puis horodatage décroissant. Tris successifs du critère le moins au plus
    # significatif (le tri Python est stable).
    records.sort(key=lambda r: r["timestamp"], reverse=True)
    records.sort(key=lambda r: r["site"])
    records.sort(key=lambda r: r["year"], reverse=True)
    return records


def detection_color(class_name: str) -> str:
    c = class_name.lower()
    if "bateau" in c or "ship" in c: return "#f59e0b"
    if "fond" in c or "background" in c: return "#6b7280"
    return "#334155"  # pas de détection : bordure discrète


def battery_color(pct_str: str) -> str:
    try:
        pct = float(pct_str)
    except (TypeError, ValueError):
        return "#6b7280"
    if pct >= 50: return "#22c55e"
    if pct >= 20: return "#f59e0b"
    return "#ef4444"


def confidence_color(conf_str: str) -> str:
    try:
        c = float(conf_str)
    except (TypeError, ValueError):
        return "#6b7280"
    if c >= 0.75: return "#22c55e"
    if c >= 0.50: return "#f59e0b"
    return "#ef4444"


def build_row(r: dict) -> str:
    det_c = detection_color(r["detection_class"])
    bat_c = battery_color(r["battery_pct"])
    conf_c = confidence_color(r["detection_conf"])

    try:
        conf_pct = f"{float(r['detection_conf']) * 100:.0f}%"
    except (TypeError, ValueError):
        conf_pct = r["detection_conf"]

    try:
        lat, lon = float(r["gps_lat"]), float(r["gps_lon"])
        gps = (f'<a href="https://maps.google.com/?q={lat},{lon}" '
               f'target="_blank" style="color:#3b82f6;font-size:12px">'
               f'{lat:.4f}, {lon:.4f}</a>')
    except (TypeError, ValueError):
        gps = "N/A"

    alert = ('<span class="badge-alert">OUI</span>' if r["alert_sent"] == "oui"
             else '<span style="color:#9ca3af">—</span>')
    wav = ('<span style="color:#22c55e">✓</span>' if r["wav_ok"] == "True"
           else '<span style="color:#ef4444">✗</span>')

    piezo = r["piezo_model"]
    if r["piezo_serial"] not in ("N/A", "", "inconnu"):
        piezo += f' · SN {r["piezo_serial"]}'

    # Batterie + température fusionnées dans une seule cellule.
    battery_combo = f'{r["battery_pct"]}% · {r["battery_temp"]}°C'

    # Flag utilisé par le filtre "🎯 Avec détection" côté HTML/JS.
    has_detection = "1" if r["detection_class"] not in ("N/A", "", None) else "0"

    # Fréquence : affichage brut, "N/A" si absent
    freq = r.get("frequency_hz", "N/A")
    if freq not in ("N/A", "", None):
        try:
            freq_display = f"{float(freq):.0f} Hz"
        except (TypeError, ValueError):
            freq_display = str(freq)
    else:
        freq_display = "N/A"

    return (
        f'<tr data-site="{r["site"]}" data-alert="{r["alert_sent"]}" '
        f'data-class="{r["detection_class"].lower()}" data-has-detection="{has_detection}" '
        f'style="border-left:3px solid {det_c}">'
        f'<td style="font-weight:500;color:#e2e8f0">{r["site"]}</td>'
        f'<td style="text-align:center;color:#94a3b8">{r["year"]}</td>'
        f'<td style="font-size:12px;color:#94a3b8">{piezo}</td>'
        f'<td style="font-family:monospace;font-size:12px;color:#94a3b8">{r["timestamp"]}</td>'
        f'<td style="text-align:center">{wav} {r["wav_size_mb"]} MB</td>'
        f'<td style="font-weight:500;color:{det_c}">{r["detection_class"]}</td>'
        f'<td style="text-align:center;color:{conf_c}">{conf_pct}</td>'
        f'<td style="text-align:center">{alert}</td>'
        f'<td style="text-align:center;color:{bat_c}">{battery_combo}</td>'
        f'<td style="font-size:12px">{gps}</td>'
        f'<td style="font-size:12px;color:#94a3b8">{freq_display}</td>'
        f'</tr>'
    )


def render_html(records: list[dict], live: bool) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    total = len(records)
    wav_ok = sum(1 for r in records if r["wav_ok"] == "True")
    alerts = sum(1 for r in records if r["alert_sent"] == "oui")
    sites = sorted({r["site"] for r in records})
    piezos = sorted({r["piezo_model"] for r in records
                     if r["piezo_model"] not in ("N/A", "", "inconnu")})
    boat_count = sum(1 for r in records if any(s in r["detection_class"].lower()
                                                for s in ("bateau", "ship")))
    bg_count = sum(1 for r in records if any(s in r["detection_class"].lower()
                                              for s in ("fond", "background")))

    site_buttons = "".join(
        f'<button class="chip" onclick="filterSite(\'{s}\')">{s}</button>'
        for s in sites
    )

    return (template
            .replace("{{META_REFRESH}}", '<meta http-equiv="refresh" content="30">' if live else "")
            .replace("{{LIVE_BADGE}}", '<span class="badge-live">🔴 LIVE</span>' if live else "")
            .replace("{{GENERATED}}", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
            .replace("{{SITES}}", ", ".join(sites) if sites else "aucun")
            .replace("{{PIEZOS}}", ", ".join(piezos) if piezos else "non renseigné")
            .replace("{{TOTAL}}", str(total))
            .replace("{{WAV_OK}}", str(wav_ok))
            .replace("{{BOAT_COUNT}}", str(boat_count))
            .replace("{{BG_COUNT}}", str(bg_count))
            .replace("{{ALERTS}}", str(alerts))
            .replace("{{SITE_BUTTONS}}", site_buttons)
            .replace("{{ROWS}}", "".join(build_row(r) for r in records)))


def export_csv(records: list[dict], out_path: Path) -> None:
    if not records:
        return
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)


def generate_once(data_dir: Path, out_dir: Path, live: bool) -> int:
    records = collect_records(data_dir)
    if not records:
        log.warning("Aucun enregistrement trouvé dans %s", data_dir)
        return 0
    (out_dir / "dashboard.html").write_text(render_html(records, live), encoding="utf-8")
    export_csv(records, out_dir / "dashboard.csv")
    return len(records)


def live_loop(data_dir: Path, out_dir: Path, interval: int = 30) -> None:
    while True:
        try:
            n = generate_once(data_dir, out_dir, live=True)
            log.info("Dashboard mis à jour — %d enregistrement(s)", n)
        except Exception as e:
            log.error("Erreur mise à jour : %s", e)
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dashboard bioacoustique")
    parser.add_argument("--data", default="recordings")
    parser.add_argument("--out", default=".")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    data_dir = Path(args.data)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not data_dir.exists():
        raise SystemExit(f"Dossier introuvable : {data_dir}")
    if not TEMPLATE_PATH.exists():
        raise SystemExit(f"Template absent : {TEMPLATE_PATH}")

    n = generate_once(data_dir, out_dir, live=args.live)
    log.info("Généré dashboard.html (%d enregistrements)", n)

    if not args.live:
        log.info("Ouvrir %s/dashboard.html", out_dir.resolve())
        return

    threading.Thread(target=live_loop, args=(data_dir, out_dir),
                     daemon=True).start()
    url = f"http://localhost:{args.port}/dashboard.html"
    log.info("Dashboard LIVE → %s", url)
    webbrowser.open(url)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(out_dir.resolve()), **kw)
        def log_message(self, *a, **kw): pass
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", args.port), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            log.info("Arrêt du serveur")


if __name__ == "__main__":
    main()