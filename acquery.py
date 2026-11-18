"""Consulta ao vivo de um servidor AssaultCube 1.3 pela porta de informações (porta do jogo + 1).

É o mesmo "ping" que o navegador de servidores do jogo usa: devolve modo, mapa,
jogadores, minutos restantes, descrição e a lista de nomes conectados.
"""
import socket

MODES = [  # índice = número do modo + 1 (igual ao jogo)
    ("DEMO", "demo playback"),
    ("TDM", "team deathmatch"), ("coop", "coopedit"), ("DM", "deathmatch"), ("SURV", "survivor"),
    ("TSURV", "team survivor"), ("CTF", "capture the flag"), ("PF", "pistol frenzy"),
    ("BTDM", "bot team deathmatch"), ("BDM", "bot deathmatch"), ("LSS", "last swiss standing"),
    ("OSOK", "one shot, one kill"), ("TOSOK", "team one shot, one kill"), ("BOSOK", "bot one shot, one kill"),
    ("HTF", "hunt the flag"), ("TKTF", "team keep the flag"), ("KTF", "keep the flag"),
    ("TPF", "team pistol frenzy"), ("TLSS", "team last swiss standing"), ("BPF", "bot pistol frenzy"),
    ("BLSS", "bot last swiss standing"), ("BTSURV", "bot team survivor"), ("BTOSOK", "bot team one shot, one kill"),
]
EXTPING_NAMELIST = 1


def putint(n):
    if -127 < n < 128:
        return bytes([n & 0xFF])
    if -0x8000 <= n < 0x8000:
        return bytes([0x80, n & 0xFF, (n >> 8) & 0xFF])
    return bytes([0x81]) + (n & 0xFFFFFFFF).to_bytes(4, "little")


class Reader:
    def __init__(self, data):
        self.d, self.i = data, 0

    def byte(self):
        if self.i >= len(self.d):
            raise ValueError("resposta curta")
        b = self.d[self.i]
        self.i += 1
        return b

    def getint(self):
        c = self.byte()
        c = c - 256 if c > 127 else c
        if c == -128:
            lo, hi = self.byte(), self.byte()
            n = lo | (hi << 8)
            return n - 0x10000 if n & 0x8000 else n
        if c == -127:
            n = int.from_bytes(bytes(self.byte() for _ in range(4)), "little")
            return n - (1 << 32) if n & 0x80000000 else n
        return c

    def getstring(self):
        out = []
        while True:
            c = self.getint()
            if c == 0:
                return "".join(out)
            out.append(chr(c & 0xFF))


def mode_name(n, short=False):
    i = n + 1
    if 0 <= i < len(MODES):
        return MODES[i][0 if short else 1]
    return "?"


def query(host, game_port, timeout=1.5):
    """Retorna um dicionário com o estado do servidor, ou None se ele não respondeu."""
    req = putint(1) + putint(EXTPING_NAMELIST)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        try:
            s.sendto(req, (host, game_port + 1))
            data, _ = s.recvfrom(4096)
        except OSError:
            return None
    try:
        r = Reader(data)
        r.i = len(req)  # o servidor devolve a pergunta antes da resposta
        info = {"protocol": r.getint(), "mode": r.getint(), "players": r.getint(),
                "minremain": r.getint(), "map": r.getstring(), "description": r.getstring(),
                "maxclients": r.getint(), "flags": r.getint(), "names": []}
        if r.i < len(data) and r.getint() == EXTPING_NAMELIST:
            while True:
                n = r.getstring()
                if not n:
                    break
                info["names"].append(n)
    except ValueError:
        return None
    info["mode_short"] = mode_name(info["mode"], True)
    info["mode_name"] = mode_name(info["mode"])
    info["modded"] = info["protocol"] < 0
    return info
