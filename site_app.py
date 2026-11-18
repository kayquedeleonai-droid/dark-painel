"""Site público CubeForge: servidores ao vivo, ranking e downloads.

Só leitura. Não usa o login nem a chave secreta do painel e não mostra IP nem a
identidade completa dos jogadores.
"""
import json
import os
import re
import time

from flask import Flask, abort, jsonify, render_template
from markupsafe import Markup, escape

import acquery
import ranking as R

AC_DIR = os.environ.get("AC_DIR", os.path.expanduser("~"))
HERE = os.path.dirname(os.path.abspath(__file__))
SITE_CFG = os.environ.get("SITE_CONFIG", os.path.join(HERE, "site.json"))

SERVERS = [
    {"id": "public", "label": "Public", "dir": AC_DIR},
    {"id": "pro", "label": "Inter Pro", "dir": os.path.join(AC_DIR, "pro")},
]

app = Flask(__name__, template_folder="site_templates", static_folder="site_static", static_url_path="/s")


def cfg():
    try:
        with open(SITE_CFG) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def cmdline(sdir):
    vals = {}
    try:
        with open(os.path.join(sdir, "config", "servercmdline.txt"), encoding="utf-8", errors="replace") as f:
            for line in f:
                s = line.strip()
                if s.startswith("-") and len(s) > 1:
                    vals.setdefault(s[1], s[2:])
    except OSError:
        pass
    return vals


def installed():
    return [s for s in SERVERS if os.path.exists(os.path.join(s["dir"], "server.sh"))]


_status = {"t": 0, "data": []}


def server_status():
    """Consulta cada servidor pela porta de informações (com cache de 5 s)."""
    if time.time() - _status["t"] < 5:
        return _status["data"]
    host = cfg().get("host", "")
    out = []
    for s in installed():
        cl = cmdline(s["dir"])
        try:
            port = int(cl.get("f", "28763"))
        except ValueError:
            port = 28763
        q = acquery.query("127.0.0.1", port)
        out.append({
            "id": s["id"], "label": s["label"], "port": port,
            "online": q is not None,
            "name": (q or {}).get("description") or cl.get("n", s["label"]).replace("\\f", "\f"),
            "players": (q or {}).get("players", 0),
            "max": (q or {}).get("maxclients") or int(cl.get("c", "16") or 16),
            "map": (q or {}).get("map", ""),
            "mode": (q or {}).get("mode_name", ""),
            "mode_short": (q or {}).get("mode_short", ""),
            "minremain": (q or {}).get("minremain", 0),
            "names": (q or {}).get("names", []),
            "modded": (q or {}).get("modded", False),
            "connect": (f"/{'modconnect' if (q or {}).get('modded') else 'connect'} {host}"
                        + ("" if port == 28763 else f" {port}")) if host else "",
        })
    _status.update(t=time.time(), data=out)
    return out


def hidden():
    try:
        with open(os.path.join(HERE, "ranking_hidden.json")) as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def players(scope="all"):
    srvs = installed() if scope == "all" else [s for s in installed() if s["id"] == scope]
    links = R.load_links(os.path.join(HERE, "ranking_links.json"))
    ps = R.combine([R.parse_vita(os.path.join(s["dir"], "config", "servervita.cfg")) for s in srvs], links)
    hid = hidden()
    return {k: v for k, v in ps.items() if not (set(v["ids"]) & hid)}


def public_id(p):
    return p["id"][:10]


# ---------------------------------------------------------------- filtros

AC_COLORS = {"0": "#3cdc3c", "1": "#4f8fff", "2": "#ffdc32", "3": "#ff4040", "4": "#9a9a9a",
             "5": "#ffffff", "6": "#8b5a2b", "7": "#b01818", "8": "#c05cff", "9": "#ff9a1f"}


@app.template_filter("acname")
def acname(text):
    """Converte os códigos de cor do jogo (\\f0..\\f9) em HTML seguro."""
    parts = re.split(r"\f([0-9])", text or "")
    html, color = [], None
    for i, part in enumerate(parts):
        if i % 2 == 1:
            color = AC_COLORS.get(part)
            continue
        part = re.sub(r"\f.?", "", part)
        if part:
            html.append(f'<span style="color:{color}">{escape(part)}</span>' if color else str(escape(part)))
    return Markup("".join(html))


@app.template_filter("quando")
def _quando(m):
    return R.fmt_when(m)


@app.template_filter("duracao")
def _duracao(m):
    return R.fmt_minutes(m)


@app.context_processor
def inject():
    c = cfg()
    return {"site": {"host": c.get("host", ""), "discord": c.get("discord", "")}, "pid": public_id}


@app.after_request
def headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resp


# ---------------------------------------------------------------- páginas

def feed(servers, top):
    """Linhas do "kill feed" do topo: fatos reais, não partidas inventadas."""
    lines = []
    online = [s for s in servers if s["online"]]
    for s in online:
        if s["players"]:
            lines.append(("live", f"{s['players']} jogando agora em {s['label']}", s["map"] or ""))
        elif s["map"]:
            lines.append(("map", f"{s['label']} está em {s['map']}", s["mode_short"]))
    if top:
        lines.append(("top", f"{top[0]['name']} lidera o ranking", f"{top[0]['skill']} de skill"))
    if len(top) > 1:
        best_kd = max(top[:10], key=lambda p: p["kd"])
        lines.append(("kd", f"{best_kd['name']} tem o melhor K/D do top 10", str(best_kd["kd"])))
    if not online:
        lines.append(("off", "Servidores em manutenção", "volte em instantes"))
    return lines[:4]


@app.route("/")
def index():
    servers = server_status()
    ps = players()
    top = R.ranked(ps, "skill", 10)
    return render_template("index.html", servers=servers, top=top[:10], feed=feed(servers, top),
                           online=sum(s["players"] for s in servers),
                           slots=sum(s["max"] for s in servers if s["online"]),
                           total_players=len(ps))


@app.route("/ranking")
@app.route("/ranking/<scope>")
def ranking(scope="all"):
    if scope != "all" and not any(s["id"] == scope for s in installed()):
        abort(404)
    rows = R.ranked(players(scope), "skill", 10)
    return render_template("ranking.html", rows=rows[:100], scope=scope, servers=installed())


@app.route("/jogador/<sid>")
def jogador(sid):
    sid = sid.lower()
    if not re.fullmatch(r"[0-9a-f]{10}", sid):
        abort(404)
    ps = players()
    p = next((p for p in ps.values() if p["id"].startswith(sid)), None)
    if not p:
        abort(404)
    pos = next((r["pos"] for r in R.ranked(ps, "skill", 10) if r["id"] == p["id"]), None)
    return render_template("jogador.html", p=p, pos=pos)


@app.route("/downloads")
def downloads():
    return render_template("downloads.html")


@app.route("/api/status")
def api_status():
    return jsonify([{k: s[k] for k in ("id", "label", "online", "players", "max", "map", "mode", "mode_short",
                                       "minremain", "connect")} for s in server_status()])


@app.errorhandler(404)
def nao_encontrado(e):
    return render_template("404.html"), 404
