"""Aplica só as boas-vindas com estatísticas e rank do CubeForge no server.cpp do AssaultCube 1.3.0.2.
Uso: python3 apply-welcome.py <pasta source/src>
Mudança mínima: uma função nova e uma chamada quando o jogador termina de entrar."""
import os
import sys

src = sys.argv[1]
here = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(src, "server.cpp")
s = open(p, encoding="latin-1").read()
if "CubeForge: boas-vindas" in s:
    print("já aplicado")
    sys.exit(0)
inc = open(os.path.join(here, "welcome.inc"), encoding="utf-8").read()


def rep(old, new):
    global s
    if s.count(old) != 1:
        sys.exit("trecho não encontrado (ou repetido): " + old[:70])
    s = s.replace(old, new)


rep("void sendiplist(int receiver, int cn)\n", inc + "\nvoid sendiplist(int receiver, int cn)\n")
rep("        sendinitclient(*cl);\n        if(clientrole != CR_DEFAULT) changeclientrole(sender, clientrole, NULL, true);\n",
    "        sendinitclient(*cl);\n        if(clientrole != CR_DEFAULT) changeclientrole(sender, clientrole, NULL, true);\n        cfwelcome(sender);\n")
open(p, "w", encoding="latin-1").write(s)
print("ok")
