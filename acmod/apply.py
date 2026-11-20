"""Aplica os comandos de Inter do CubeForge no server.cpp do AssaultCube 1.3.0.2.
Uso: python3 apply.py <pasta source/src>
Não mexe no jogo dos jogadores: só no programa do servidor."""
import os
import sys

src = sys.argv[1]
here = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(src, "server.cpp")
s = open(p, encoding="latin-1").read()
if "CubeForge: comandos de Inter" in s:
    print("já aplicado")
    sys.exit(0)
inc = open(os.path.join(here, "intercmds.inc"), encoding="utf-8").read()


def rep(old, new):
    global s
    if s.count(old) != 1:
        sys.exit("trecho não encontrado (ou repetido): " + old[:70])
    s = s.replace(old, new)


# 1) código dos comandos logo antes de sendiplist (depois de disconnect_client)
rep("void sendiplist(int receiver, int cn)\n", inc + "\nvoid sendiplist(int receiver, int cn)\n")
# 2) pausa automática: avisa a saída em disconnect_client (antes de apagar o cliente)
rep("void disconnect_client(int n, int reason)\n{",
    "static void interplayerleft(int cn);\nvoid disconnect_client(int n, int reason)\n{")
rep("    if(reason>=0) enet_peer_disconnect(c.peer, reason);\n    clients[n]->zap();",
    "    if(reason>=0) enet_peer_disconnect(c.peer, reason);\n    interplayerleft(n);\n    clients[n]->zap();")
# 3) comandos no chat normal e no chat do time (a mensagem com ! não vai para o chat)
rep("            case SV_TEXTME:\n            case SV_TEXT:\n            {\n"
    "                int mid1 = curmsg, mid2 = p.length();\n"
    "                getstring(text, p);\n"
    "                filtertext(text, text, FTXT__CHAT);\n",
    "            case SV_TEXTME:\n            case SV_TEXT:\n            {\n"
    "                int mid1 = curmsg, mid2 = p.length();\n"
    "                getstring(text, p);\n"
    "                filtertext(text, text, FTXT__CHAT);\n"
    "                if(type == SV_TEXT && intercommand(sender, text)) break;\n")
rep("            case SV_TEAMTEXTME:\n            case SV_TEAMTEXT:\n"
    "                getstring(text, p);\n"
    "                filtertext(text, text, FTXT__CHAT);\n",
    "            case SV_TEAMTEXTME:\n            case SV_TEAMTEXT:\n"
    "                getstring(text, p);\n"
    "                filtertext(text, text, FTXT__CHAT);\n"
    "                if(type == SV_TEAMTEXT && intercommand(sender, text)) break;\n")
# 4) contagem regressiva e mapa novo, a cada volta do servidor
rep("    if(!sg->sispaused) sg->gamemillis += diff;\n    servmillis = nextmillis;\n",
    "    if(!sg->sispaused) sg->gamemillis += diff;\n    servmillis = nextmillis;\n    intertick();\n")
open(p, "w", encoding="latin-1").write(s)
print("ok")
