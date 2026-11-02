"""Dashboard HTML embarqué — tourne DIRECTEMENT sur le Fairphone (Termux),
le template HTML est ici EMBARQUÉ dans ce fichier.
Dépendances : stdlib uniquement (argparse, csv, http.server, socketserver,
threading, time, webbrowser, datetime, pathlib) + core.metadata /
core.logging_utils.
Usage (sur le Fairphone, dans Termux) :
    cd ~/pfe
    python -m android.dashboard --live
    # puis ouvrir http://localhost:8080/dashboard.html dans Chrome (même téléphone)

Par défaut, lit les enregistrements dans config.TERMUX_DATA (là où
android/receiver.py écrit les .wav/.txt).

Classes du modèle : petit/moyen/grand bateau + bruit de fond (la classe
biologique a été retirée, faute de données).
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

from core import config
from core import metadata
from core.logging_utils import get_logger

log = get_logger("dashboard")


DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
{{META_REFRESH}}
<title>BIOFISH — Dashboard</title>
<style>
  body { background:#0f172a; color:#e2e8f0; font-family: system-ui, sans-serif; margin:0; padding:16px; }
  h1 { font-size:20px; margin:0 0 4px; }
  .meta { color:#94a3b8; font-size:13px; margin-bottom:16px; }
  .stats { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:16px; }
  .stat { background:#1e293b; border-radius:8px; padding:10px 16px; min-width:100px; }
  .stat b { display:block; font-size:22px; }
  .stat span { color:#94a3b8; font-size:12px; }
  .chips { margin-bottom:12px; }
  .chip { background:#1e293b; color:#e2e8f0; border:1px solid #334155; border-radius:999px;
          padding:6px 14px; margin-right:6px; margin-bottom:6px; cursor:pointer; font-size:13px; }
  .chip.active { background:#3b82f6; border-color:#3b82f6; }
  table { width:100%; border-collapse: collapse; font-size:13px; }
  th { text-align:left; padding:8px 6px; border-bottom:1px solid #334155; color:#94a3b8;
       position:sticky; top:0; background:#0f172a; }
  td { padding:6px; border-bottom:1px solid #1e293b; }
  .badge-live { background:#ef4444; padding:2px 8px; border-radius:6px; font-size:12px; }
  .badge-alert { background:#ef4444; color:white; padding:2px 8px; border-radius:6px; font-size:11px; }
</style>
</head>
<body>
<h1>BIOFISH — Dashboard {{LIVE_BADGE}}</h1>
<div class="meta">Généré le {{GENERATED}} — Sites : {{SITES}} — Piézo(s) : {{PIEZOS}}</div>
<div class="stats">
  <div class="stat"><b>{{TOTAL}}</b><span>Enregistrements</span></div>
  <div class="stat"><b>{{WAV_OK}}</b><span>WAV OK</span></div>
  <div class="stat"><b>{{BOAT_COUNT}}</b><span>Détections bateau</span></div>
  <div class="stat"><b>{{BG_COUNT}}</b><span>Bruit de fond</span></div>
  <div class="stat"><b>{{ALERTS}}</b><span>Alertes SMS</span></div>
</div>
<div class="chips">
  <button class="chip active" onclick="filterSite('', this)">Tous</button>
  {{SITE_BUTTONS}}
</div>
<table>
<thead><tr>
  <th>Site</th><th>Année</th><th>Piézo</th><th>Horodatage</th><th>WAV</th>
  <th>Classe</th><th>Confiance</th><th>Alerte</th><th>Batterie</th><th>Temp</th><th>GPS</th><th>Fréq.</th>
</tr></thead>
<tbody>{{ROWS}}</tbody>
</table>
<script>
function filterSite(site, btn) {
  document.querySelectorAll('tr[data-site]').forEach(function(row) {
    row.style.display = (!site || row.dataset.site === site) ? '' : 'none';
  });
  document.querySelectorAll('.chip').forEach(function(c) { c.classList.remove('active'); });
  btn.classList.add('active');
}
</script>
</body>
</html>"""


def collect_records(data_dir: Path) -> list[dict]:
    records = []
    for txt_path in sorted(data_dir.rglob("log_*.txt"), reverse=True):
        wav_path = txt_path.with_suffix(".wav")
        meta = metadata.read(txt_path)
        wav_mb = round(wav_path.stat().st_size / 1_048_576, 2) if wav_path.exists() else 0.0
        ts = meta.get("timestamp", txt_path.stem.replace("log_", ""))
        year = meta.get("year", ts[:4] if len(ts) >= 4 else "????")
        records.append({
            "site": meta.get("site", "inconnu").upper(),
            "year": year,
            "piezo_model": meta.get("piezo_model", "N/A"),
            "piezo_serial": meta.get("piezo_serial", "N/A"),
            "timestamp": ts,
            "wav_ok": meta.get("wav_ok", "?"),
            "wav_size_mb": wav_mb,
            "detection_class": meta.get("detection_class", "N/A"),
            "detection_conf": meta.get("detection_conf", "N/A"),
            "alert_sent": meta.get("alert_sent", "non"),
            "call_sent": meta.get("call_sent", "non"),
            "battery_pct": meta.get("battery_pct", "N/A"),
            "battery_temp": meta.get("battery_temp", "N/A"),
            "gps_lat": meta.get("gps_lat", "N/A"),
            "gps_lon": meta.get("gps_lon", "N/A"),
            "frequency_hz": meta.get("frequency_hz", "N/A"),
        })
    records.sort(key=lambda r: r["timestamp"], reverse=True)
    records.sort(key=lambda r: r["site"])
    records.sort(key=lambda r: r["year"], reverse=True)
    return records


def detection_color(class_name: str) -> str:
    c = class_name.lower()
    if "bateau" in c or "ship" in c: return "#f59e0b"
    if "fond" in c or "background" in c: return "#6b7280"
    return "#94a3b8"


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
        gps = f'{lat:.4f}, {lon:.4f}'
    except (TypeError, ValueError):
        gps = "N/A"

    alert_bits = []
    if r["alert_sent"] == "oui":
        alert_bits.append('<span class="badge-alert">SMS</span>')
    if r["call_sent"] == "oui":
        alert_bits.append('<span class="badge-alert">APPEL</span>')
    alert = " ".join(alert_bits) if alert_bits else '<span style="color:#9ca3af">—</span>'

    wav = ('<span style="color:#22c55e">✓</span>' if r["wav_ok"] == "True"
           else '<span style="color:#ef4444">✗</span>')

    piezo = r["piezo_model"]
    if r["piezo_serial"] not in ("N/A", "", "inconnu"):
        piezo += f' · SN {r["piezo_serial"]}'

    return (
        f'<tr data-site="{r["site"]}" data-class="{r["detection_class"].lower()}">'
        f'<td style="font-weight:500;color:#e2e8f0">{r["site"]}</td>'
        f'<td style="text-align:center;color:#94a3b8">{r["year"]}</td>'
        f'<td style="font-size:12px;color:#94a3b8">{piezo}</td>'
        f'<td style="font-family:monospace;font-size:12px;color:#94a3b8">{r["timestamp"]}</td>'
        f'<td style="text-align:center">{wav} {r["wav_size_mb"]} MB</td>'
        f'<td style="font-weight:500;color:{det_c}">{r["detection_class"]}</td>'
        f'<td style="text-align:center;color:{conf_c}">{conf_pct}</td>'
        f'<td style="text-align:center">{alert}</td>'
        f'<td style="text-align:center;color:{bat_c}">{r["battery_pct"]}%</td>'
        f'<td style="font-size:12px;color:#94a3b8">{r["battery_temp"]}°C</td>'
        f'<td style="font-size:12px">{gps}</td>'
        f'<td style="font-size:11px;color:#6b7280">{r["frequency_hz"]} Hz</td>'
        f'</tr>'
    )


def render_html(records: list[dict], live: bool) -> str:
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
        f'<button class="chip" onclick="filterSite(\'{s}\', this)">{s}</button>'
        for s in sites
    )

    return (DASHBOARD_TEMPLATE
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
    parser = argparse.ArgumentParser(description="Dashboard bioacoustique (embarqué Fairphone)")
    parser.add_argument("--data", default=config.TERMUX_DATA,
                        help="Dossier des enregistrements (défaut : config.TERMUX_DATA)")
    parser.add_argument("--out", default=f"{config.TERMUX_HOME}/dashboard",
                        help="Dossier de sortie du dashboard.html")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    data_dir = Path(args.data)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not data_dir.exists():
        raise SystemExit(f"Dossier introuvable : {data_dir}")

    n = generate_once(data_dir, out_dir, live=args.live)
    log.info("Généré %s/dashboard.html (%d enregistrements)", out_dir, n)

    if not args.live:
        log.info("Ouvre %s/dashboard.html dans un navigateur (Chrome) sur le téléphone.", out_dir)
        return

    threading.Thread(target=live_loop, args=(data_dir, out_dir), daemon=True).start()
    url = f"http://localhost:{args.port}/dashboard.html"
    log.info("Dashboard LIVE → %s", url)
    log.info("Ouvre cette adresse dans Chrome, sur ce même téléphone.")
    try:
        webbrowser.open(url)
    except Exception:
        pass  # pas de navigateur par défaut sous Termux — ouverture manuelle nécessaire

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