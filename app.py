"""Painel web do servidor AssaultCube (DARK PUBLIC SERVER).

Roda como o usuário `ac` e controla o servidor do jogo por systemd (--user).
"""
import glob
import hmac
import json
import os
import re
import secrets
import subprocess
import time
from functools import wraps

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash

AC_DIR = os.environ.get("AC_DIR", os.path.expanduser("~"))
PANEL_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.environ.get("PAINEL_CONFIG", os.path.join(PANEL_DIR, "config.json"))
SERVICE = os.environ.get("AC_SERVICE", "ac-server")
DEMO = os.environ.get("PAINEL_DEMO") == "1"  # só para testes: não chama systemctl

CMDLINE = os.path.join(AC_DIR, "config", "servercmdline.txt")
MAPROT = os.path.join(AC_DIR, "config", "maprot.cfg")
PWDFILE = os.path.join(AC_DIR, "config", "serverpwd.cfg")
BLACKLIST = os.path.join(AC_DIR, "config", "serverblacklist.cfg")
LOGDIR = os.path.join(AC_DIR, "logs")

MODES = [
    ("tdm", "Team Deathmatch"), ("dm", "Deathmatch"), ("ctf", "Capture the Flag"),
    ("tktf", "Team Keep the Flag"), ("ktf", "Keep the Flag"), ("htf", "Hunt the Flag"),
    ("tlss", "Team Last Swiss Standing"), ("lss", "Last Swiss Standing"),
    ("tosok", "Team One Shot One Kill"), ("osok", "One Shot One Kill"),
    ("tpf", "Team Pistol Frenzy"), ("pf", "Pistol Frenzy"),
    ("tsurv", "Team Survivor"), ("surv", "Survivor"),
]
MODE_KEYS = [m for m, _ in MODES]
MAP_RE = re.compile(r"^(\*|[a-z0-9_.\-]+\*?)$")

with open(CFG_PATH) as f:
    CFG = json.load(f)

app = Flask(__name__)
app.secret_key = CFG["secret_key"]
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=12 * 3600,
)

# ---------------------------------------------------------------- utilidades

def read_lines(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except FileNotFoundError:
        return []


def write_lines(path, lines):
    """Grava de forma segura e guarda uma cópia .bak da versão anterior."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        with open(path, "rb") as src, open(path + ".bak", "wb") as dst:
            dst.write(src.read())
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    os.replace(tmp, path)


def svc(action):
    if DEMO:
        return subprocess.CompletedProcess([], 0, "active\n", "")
    return subprocess.run(["systemctl", "--user", action, SERVICE],
                          capture_output=True, text=True, timeout=30)


def service_active():
    return svc("is-active").stdout.strip() == "active"


def service_since():
    if DEMO:
        return ""
    r = subprocess.run(["systemctl", "--user", "show", "-p", "ActiveEnterTimestamp", "--value", SERVICE],
                       capture_output=True, text=True, timeout=10)
    return r.stdout.strip()


def latest_log():
    """Log mais recente: o console capturado pelo systemd ou os arquivos do próprio jogo."""
    files = glob.glob(os.path.join(LOGDIR, "serverlog_*.txt"))
    console = os.path.join(LOGDIR, "console.log")
    if os.path.exists(console) and os.path.getsize(console) > 0:
        files.append(console)
    return max(files, key=os.path.getmtime) if files else None


def tail(path, n):
    if not path:
        return []
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - 200_000))
        data = f.read().decode("utf-8", errors="replace")
    return data.splitlines()[-n:]

# ------------------------------------------------- servercmdline.txt (-n, -o ...)

def read_cmdline():
    values = {}
    for line in read_lines(CMDLINE):
        s = line.strip()
        if s.startswith("-") and len(s) >= 2:
            values.setdefault(s[1], s[2:])
    return values


def write_cmdline(updates):
    """updates: {letra: valor ou None (remove)}; preserva o resto do arquivo."""
    out, done = [], set()
    for line in read_lines(CMDLINE):
        s = line.strip()
        if s.startswith("-") and len(s) >= 2 and s[1] in updates:
            k = s[1]
            if k in done:
                continue
            done.add(k)
            if updates[k] not in (None, ""):
                out.append(f"-{k}{updates[k]}")
            continue
        out.append(line)
    for k, v in updates.items():
        if k not in done and v not in (None, ""):
            out.append(f"-{k}{v}")
    write_lines(CMDLINE, out)

# ------------------------------------------------------------------ maprot.cfg

def parse_maprot():
    entries, other = [], []
    for line in read_lines(MAPROT):
        body = line.split("//", 1)[0].strip()
        toks = body.split()
        if len(toks) >= 2 and MAP_RE.match(toks[0]):
            modes = toks[1].split("|")
            if all(m in MODE_KEYS for m in modes):
                time_v, extra = "", []
                for t in toks[2:]:
                    if t.startswith("time:"):
                        time_v = t[5:]
                    else:
                        extra.append(t)
                entries.append({"map": toks[0], "modes": modes, "time": time_v, "extra": " ".join(extra)})
                continue
        other.append(line)
    return entries, other


def available_maps():
    names = set()
    for f in glob.glob(os.path.join(AC_DIR, "packages", "maps", "**", "*.cgz"), recursive=True):
        names.add(os.path.splitext(os.path.basename(f))[0])
    return sorted(names)

# --------------------------------------------------------------------- status

def log_status():
    lines = tail(latest_log(), 2000)
    info = {"master": None, "maprot": None, "map": None, "mode": None}
    for l in lines:
        if "master server registration succeeded" in l:
            info["master"] = True
        elif "LAN-only" in l or "KEY FAILURE" in l:
            info["master"] = False
        m = re.search(r"read (\d+) map rotation entries", l)
        if m:
            info["maprot"] = int(m.group(1))
        m = re.search(r"Game start: (.+?) on ([a-z0-9_.\-]+)", l)
        if m:
            info["mode"], info["map"] = m.group(1), m.group(2)
    return info

# ----------------------------------------------------------- login e segurança

FAILS = {}  # ip -> [tentativas, bloqueado_ate]
MAX_FAILS, BLOCK_SECS = 5, 15 * 60


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not session.get("auth"):
            return redirect(url_for("login"))
        return view(*a, **kw)
    return wrapped


@app.before_request
def csrf_protect():
    session.setdefault("csrf", secrets.token_hex(16))
    if request.method == "POST":
        token = request.form.get("csrf") or request.headers.get("X-CSRF")
        if not token or not hmac.compare_digest(token, session["csrf"]):
            abort(400, "Sessão expirada. Recarregue a página.")


@app.after_request
def security_headers(resp):
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.context_processor
def inject():
    return {"csrf": session.get("csrf", ""), "pending": session.get("pending", False)}


@app.route("/login", methods=["GET", "POST"])
def login():
    ip = request.remote_addr or "?"
    count, until = FAILS.get(ip, [0, 0])
    if until > time.time():
        mins = int((until - time.time()) // 60) + 1
        return render_template("login.html", error=f"Muitas tentativas. Tente de novo em {mins} min."), 429
    if request.method == "POST":
        user = request.form.get("user", "")
        pwd = request.form.get("password", "")
        ok_user = hmac.compare_digest(user, CFG["username"])
        ok_pwd = check_password_hash(CFG["password_hash"], pwd)
        if ok_user and ok_pwd:
            FAILS.pop(ip, None)
            session.clear()
            session.permanent = True
            session["auth"] = True
            session["csrf"] = secrets.token_hex(16)
            return redirect(url_for("index"))
        count += 1
        FAILS[ip] = [count, time.time() + BLOCK_SECS if count >= MAX_FAILS else 0]
        time.sleep(1)
        return render_template("login.html", error="Usuário ou senha incorretos."), 401
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------------------------------------------------------------- páginas

@app.route("/")
@login_required
def index():
    return render_template("index.html", page="index", cmd=read_cmdline())


@app.route("/api/status")
@login_required
def api_status():
    info = log_status()
    info["online"] = service_active()
    info["since"] = service_since()
    return jsonify(info)


@app.route("/api/log")
@login_required
def api_log():
    n = min(int(request.args.get("n", 300)), 2000)
    path = latest_log()
    return jsonify({"file": os.path.basename(path) if path else None, "lines": tail(path, n)})


@app.route("/acao/<acao>", methods=["POST"])
@login_required
def acao(acao):
    if acao not in ("start", "stop", "restart"):
        abort(404)
    r = svc(acao)
    if r.returncode == 0:
        msgs = {"start": "Servidor ligado.", "stop": "Servidor desligado.", "restart": "Servidor reiniciado."}
        flash(msgs[acao], "ok")
        if acao in ("start", "restart"):
            session["pending"] = False
    else:
        flash("Erro: " + (r.stderr or r.stdout).strip()[:300], "erro")
    return redirect(request.form.get("next") or url_for("index"))


@app.route("/config", methods=["GET", "POST"])
@login_required
def config():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        motd = request.form.get("motd", "").strip()
        serverpass = request.form.get("serverpass", "").strip()
        try:
            maxc = int(request.form.get("maxclients", "16"))
        except ValueError:
            maxc = 16
        errors = []
        if not name:
            errors.append("O nome não pode ficar vazio.")
        if len(name) > 100:
            errors.append("Nome muito longo.")
        if len(motd) > 250:
            errors.append("Mensagem de boas-vindas muito longa.")
        if not 1 <= maxc <= 16:
            errors.append("Jogadores: de 1 a 16 (acima de 16 o servidor sai da lista pública).")
        if " " in serverpass:
            errors.append("A senha para entrar não pode ter espaços.")
        if any("\n" in v or "\r" in v for v in (name, motd, serverpass)):
            errors.append("Texto inválido.")
        if errors:
            for e in errors:
                flash(e, "erro")
        else:
            write_cmdline({"n": name, "o": motd, "c": str(maxc), "p": serverpass or None})
            session["pending"] = True
            flash("Configurações salvas. Reinicie o servidor para aplicar.", "ok")
            return redirect(url_for("config"))
    cmd = read_cmdline()
    return render_template("config.html", page="config", cmd=cmd,
                           has_key=bool(cmd.get("Y")), master=cmd.get("m", ""))


@app.route("/mapas", methods=["GET", "POST"])
@login_required
def mapas():
    if request.method == "POST":
        if "raw" in request.form:
            raw = request.form["raw"].replace("\r", "").split("\n")
            write_lines(MAPROT, raw)
        else:
            idx = sorted({int(k.split("-")[1]) for k in request.form if re.match(r"^row-\d+-map$", k)})
            lines, errors = [], []
            for i in idx:
                mp = request.form.get(f"row-{i}-map", "").strip().lower()
                if not mp:
                    continue
                modes = [m for m in request.form.getlist(f"row-{i}-modes") if m in MODE_KEYS]
                t = request.form.get(f"row-{i}-time", "").strip()
                extra = request.form.get(f"row-{i}-extra", "").strip()
                if not MAP_RE.match(mp):
                    errors.append(f"Nome de mapa inválido: {mp}")
                    continue
                if not modes:
                    errors.append(f"Escolha pelo menos um modo para {mp}.")
                    continue
                parts = [mp, "|".join(modes)]
                if t:
                    if not t.isdigit() or not 1 <= int(t) <= 60:
                        errors.append(f"Tempo inválido em {mp} (1 a 60 minutos).")
                        continue
                    parts.append(f"time:{t}")
                if extra:
                    if not re.match(r"^([a-z]+:-?\d+\s*)+$", extra):
                        errors.append(f"Opções extras inválidas em {mp}.")
                        continue
                    parts.append(extra)
                lines.append(" ".join(parts))
            if errors:
                for e in errors:
                    flash(e, "erro")
                return redirect(url_for("mapas"))
            _, other = parse_maprot()
            other = [l for l in other if l.strip()]
            write_lines(MAPROT, other + lines)
        session["pending"] = True
        flash("Rotação de mapas salva. Reinicie o servidor para aplicar.", "ok")
        return redirect(url_for("mapas"))
    entries, _ = parse_maprot()
    return render_template("mapas.html", page="mapas", entries=entries, modes=MODES,
                           maps=available_maps(), raw="\n".join(read_lines(MAPROT)))


def read_pwds():
    out = []
    for i, line in enumerate(read_lines(PWDFILE)):
        s = line.strip()
        if s and not s.startswith("//"):
            toks = s.split()
            out.append({"line": i, "pwd": toks[0], "deny": len(toks) > 1 and toks[1] == "1"})
    return out


@app.route("/admins", methods=["GET", "POST"])
@login_required
def admins():
    if request.method == "POST":
        lines = read_lines(PWDFILE)
        if request.form.get("op") == "add":
            pwd = request.form.get("pwd", "").strip()
            deny = request.form.get("deny") == "1"
            if len(pwd) < 6 or re.search(r"\s", pwd) or "//" in pwd:
                flash("A senha precisa ter pelo menos 6 caracteres, sem espaços.", "erro")
            elif any(p["pwd"] == pwd for p in read_pwds()):
                flash("Essa senha já existe.", "erro")
            else:
                lines.append(pwd + (" 1" if deny else ""))
                write_lines(PWDFILE, lines)
                session["pending"] = True
                flash("Senha adicionada. Reinicie o servidor para aplicar.", "ok")
        elif request.form.get("op") == "del":
            try:
                n = int(request.form.get("line", "-1"))
            except ValueError:
                n = -1
            valid = {p["line"] for p in read_pwds()}
            if n in valid:
                del lines[n]
                write_lines(PWDFILE, lines)
                session["pending"] = True
                flash("Senha removida. Reinicie o servidor para aplicar.", "ok")
        return redirect(url_for("admins"))
    pwds = [{**p, "masked": p["pwd"][:2] + "•" * max(4, len(p["pwd"]) - 2)} for p in read_pwds()]
    return render_template("admins.html", page="admins", pwds=pwds)


@app.route("/bans", methods=["GET", "POST"])
@login_required
def bans():
    if request.method == "POST":
        raw = request.form.get("raw", "").replace("\r", "").split("\n")
        write_lines(BLACKLIST, raw)
        session["pending"] = True
        flash("Lista de banidos salva. Reinicie o servidor para aplicar.", "ok")
        return redirect(url_for("bans"))
    return render_template("bans.html", page="bans", raw="\n".join(read_lines(BLACKLIST)))


@app.route("/log")
@login_required
def log():
    return render_template("log.html", page="log")

# ------------------------------------------------------------------ atualizações

UNIT_SRC = os.path.join(PANEL_DIR, "systemd")
UNIT_DST = os.path.expanduser("~/.config/systemd/user")


def git(*args, timeout=60):
    return subprocess.run(["git", "-C", PANEL_DIR, *args], capture_output=True, text=True, timeout=timeout)


def version_info():
    r = git("log", "-1", "--format=%h|%cs|%s")
    if r.returncode != 0 or "|" not in r.stdout:
        return None
    h, d, s = r.stdout.strip().split("|", 2)
    return {"hash": h, "date": d, "subject": s}


def sync_units():
    """Copia os serviços do repositório para o systemd. Retorna os que mudaram."""
    changed = []
    for src in glob.glob(os.path.join(UNIT_SRC, "*.service")):
        dst = os.path.join(UNIT_DST, os.path.basename(src))
        new = open(src).read()
        old = open(dst).read() if os.path.exists(dst) else None
        if new != old:
            os.makedirs(UNIT_DST, exist_ok=True)
            with open(dst, "w") as f:
                f.write(new)
            changed.append(os.path.basename(src))
    if changed and not DEMO:
        subprocess.run(["systemctl", "--user", "daemon-reload"], timeout=30)
    return changed


@app.route("/atualizacoes")
@login_required
def atualizacoes():
    return render_template("atualizacoes.html", page="atualizacoes", ver=version_info())


@app.route("/api/verificar")
@login_required
def api_verificar():
    f = git("fetch", "-q", "origin")
    if f.returncode != 0:
        return jsonify({"ok": False, "erro": (f.stderr or "falha ao falar com o GitHub").strip()[:300]})
    r = git("log", "--format=%h|%cs|%s", "HEAD..@{u}")
    novas = [dict(zip(("hash", "date", "subject"), l.split("|", 2))) for l in r.stdout.splitlines() if "|" in l]
    return jsonify({"ok": True, "novas": novas})


@app.route("/atualizar", methods=["POST"])
@login_required
def atualizar():
    r = git("pull", "--ff-only", timeout=120)
    if r.returncode != 0:
        flash("Não foi possível atualizar: " + (r.stderr or r.stdout).strip()[:300], "erro")
        return redirect(url_for("atualizacoes"))
    changed = sync_units()
    if "ac-server.service" in changed:
        session["pending"] = True
    flash("Painel atualizado! Ele vai reiniciar em alguns segundos; recarregue a página.", "ok")
    if not DEMO:
        # reinicia o painel por fora deste processo, depois de responder
        subprocess.Popen(["systemd-run", "--user", "--on-active=2", "--quiet",
                          "systemctl", "--user", "restart", "ac-painel.service"])
    return redirect(url_for("atualizacoes"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=False)
