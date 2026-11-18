"""Ranking dos jogadores a partir do banco de "vitas" do próprio servidor AssaultCube.

O servidor 1.3 identifica cada jogador por uma chave pública (não pelo nome) e
salva as estatísticas dele em config/servervita.cfg. Formato de cada registro:

    PUBKEY <64 hex>
        NAME <nome mais antigo> ... <nome atual>
        IP ...            (ignorado aqui, por privacidade)
        CLAN <tag>
        CC <país antigo> ... <país atual>
        STAT first:<min> last:<min> frags:<n> deaths:<n> ...

Datas (first/last) são minutos desde 1970 (unixtime / 60).
"""
import json
import os
import re
import time
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # pragma: no cover
    TZ = timezone.utc

STAT_KEYS = ["first", "last", "ban", "whitelist", "admin", "owner", "minconn", "minact",
             "flags", "antiflags", "frags", "deaths", "tks", "suicides", "damage", "ff"]
COUNTERS = ["minconn", "minact", "flags", "antiflags", "frags", "deaths", "tks", "suicides", "damage", "ff"]
HEX64 = re.compile(r"^[0-9a-f]{64}$")

_cache = {}  # caminho -> (mtime, registros)


def unescape(s):
    """Desfaz o escape que o servidor usa ao gravar textos (ex.: \\_ = espaço)."""
    out, i = [], 0
    simple = {"_": " ", "f": "\f", "n": "\n", "t": "\t", "a": "\a", '"': '"', "\\": "\\", "i": "\1"}
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n in simple:
                out.append(simple[n]); i += 2; continue
            if n == "x":
                m = re.match(r"[0-9a-fA-F]{1,2}", s[i + 2:])
                if m:
                    out.append(chr(int(m.group(0), 16))); i += 2 + len(m.group(0)); continue
            if n.isdigit():
                m = re.match(r"\d{1,3}", s[i + 1:])
                out.append(chr(int(m.group(0)) & 0x7F)); i += 1 + len(m.group(0)); continue
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def clean_name(s):
    """Nome para exibir: sem códigos de cor nem caracteres de controle."""
    s = re.sub(r"\f.", "", s)
    return "".join(ch for ch in s if ch.isprintable()).strip()


def parse_vita(path):
    """Lê o arquivo de vitas. Retorna {pubkey: registro}. Usa cache por data de modificação."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    hit = _cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    players, cur = {}, None
    with open(path, encoding="latin-1", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("//"):
                continue
            toks = line.split()
            key, vals = toks[0], toks[1:]
            if key == "PUBKEY":
                pk = vals[0].lower() if vals else ""
                if HEX64.match(pk):
                    cur = players.setdefault(pk, {"id": pk, "names": [], "cc": "", "clan": "",
                                                  "stats": {k: 0 for k in STAT_KEYS}})
                else:
                    cur = None
            elif cur is None:
                continue
            elif key == "NAME":
                for v in vals:  # do mais antigo para o atual
                    n = clean_name(unescape(v))
                    if n:
                        if n in cur["names"]:
                            cur["names"].remove(n)
                        cur["names"].append(n)
            elif key == "CC" and vals:
                cur["cc"] = vals[-1][:2].upper()
            elif key == "CLAN" and vals:
                cur["clan"] = clean_name(unescape(" ".join(vals)))
            elif key == "STAT":
                for v in vals:
                    k, _, num = v.partition(":")
                    if k in cur["stats"]:
                        try:
                            cur["stats"][k] = int(num)
                        except ValueError:
                            pass
    _cache[path] = (mtime, players)
    return players


def skill(s):
    """Mesma fórmula que o servidor usa para equilibrar os times (pontos por minuto jogado)."""
    if s["minact"] <= 0:
        return 0
    pos = s["frags"] * 100 + s["damage"] * 2 + s["flags"] * 10
    neg = s["deaths"] * 50 + s["ff"] * 3 + s["antiflags"] * 15 + s["tks"] * 100 + s["suicides"] * 100
    return round((pos - neg) / s["minact"])


def kd(s):
    return round(s["frags"] / s["deaths"], 2) if s["deaths"] else float(s["frags"])


def fmt_when(minutes):
    if not minutes:
        return "—"
    ago = time.time() / 60 - minutes
    if ago < 2:
        return "agora"
    if ago < 60:
        return f"há {int(ago)} min"
    if ago < 24 * 60:
        return f"há {int(ago // 60)} h"
    if ago < 30 * 24 * 60:
        return f"há {int(ago // 1440)} dias"
    return datetime.fromtimestamp(minutes * 60, TZ).strftime("%d/%m/%Y")


def fmt_minutes(m):
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} min"


# ------------------------------------------------- juntar identidades (merge)

def load_links(path):
    try:
        with open(path) as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if HEX64.match(k) and HEX64.match(v)}
    except (OSError, ValueError):
        return {}


def save_links(path, links):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(links, f, indent=1)
    os.replace(tmp, path)


def resolve(pk, links):
    seen = set()
    while pk in links and pk not in seen:
        seen.add(pk)
        pk = links[pk]
    return pk


def combine(sources, links):
    """Junta os jogadores de vários servidores e as identidades ligadas manualmente."""
    out = {}
    for players in sources:
        for pk, p in players.items():
            main = resolve(pk, links)
            agg = out.get(main)
            if agg is None:
                agg = out[main] = {"id": main, "names": [], "cc": "", "clan": "", "ids": [],
                                   "stats": {k: 0 for k in STAT_KEYS}}
            if pk not in agg["ids"]:
                agg["ids"].append(pk)
            s, a = p["stats"], agg["stats"]
            for k in COUNTERS:
                a[k] += s[k]
            if s["first"] and (not a["first"] or s["first"] < a["first"]):
                a["first"] = s["first"]
            if s["last"] >= a["last"]:
                a["last"] = s["last"]
                # nome, país e clã mais recentes vêm de quem jogou por último
                agg["cc"] = p["cc"] or agg["cc"]
                agg["clan"] = p["clan"] or agg["clan"]
                names = [n for n in agg["names"] if n not in p["names"]] + p["names"]
            else:
                names = p["names"] + [n for n in agg["names"] if n not in p["names"]]
            agg["names"] = names
    for p in out.values():
        s = p["stats"]
        p["name"] = p["names"][-1] if p["names"] else "(sem nome)"
        p["aka"] = list(reversed(p["names"][:-1]))
        p["skill"], p["kd"] = skill(s), kd(s)
        p["short"] = p["id"][:8]
    return out


SORTS = {
    "skill": lambda p: (p["skill"], p["stats"]["frags"]),
    "frags": lambda p: (p["stats"]["frags"], p["skill"]),
    "kd": lambda p: (p["kd"], p["stats"]["frags"]),
    "flags": lambda p: (p["stats"]["flags"], p["skill"]),
    "tempo": lambda p: (p["stats"]["minact"], p["skill"]),
    "recentes": lambda p: (p["stats"]["last"],),
}


def ranked(players, sort="skill", min_minutes=10, query=""):
    """Lista ordenada. Quem jogou menos que min_minutes fica fora (evita ranking distorcido)."""
    q = query.strip().lower()
    rows = [p for p in players.values()
            if p["stats"]["minact"] >= min_minutes or sort == "recentes"]
    rows.sort(key=SORTS.get(sort, SORTS["skill"]), reverse=True)
    for i, p in enumerate(rows, 1):
        p["pos"] = i
    if q:
        rows = [p for p in rows if any(q in n.lower() for n in p["names"]) or p["id"].startswith(q)]
    return rows
