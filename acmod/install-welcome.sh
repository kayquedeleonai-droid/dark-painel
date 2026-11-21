#!/usr/bin/env bash
# CubeForge: boas-vindas com estatísticas e rank (K, D, K/D, tempo jogado, flags, posição no ranking).
# Só isso: sem comandos de Inter e sem votação de mapa. Compila o servidor oficial 1.3.0.2 com essa mudança
# e o coloca como bin_unix/native_server. Depois confere o registro no masterserver: se falhar, volta sozinho
# para o servidor original.
#
# Uso, como root na VPS:
#   bash /home/ac/painel/acmod/install-welcome.sh            -> instala no Public (/home/ac)
#   bash /home/ac/painel/acmod/install-welcome.sh pro        -> instala no Inter Pro (/home/ac/pro)
#   bash /home/ac/painel/acmod/install-welcome.sh remover    -> volta o Public ao servidor original
#   bash /home/ac/painel/acmod/install-welcome.sh remover-pro
set -euo pipefail

ACUSER=ac
ACHOME=/home/ac
AC_REPO="https://github.com/assaultcube/AC.git"
AC_TAG="v1.3.0.2"
HERE="$(cd "$(dirname "$0")" && pwd)"

say()  { printf '\033[1;33m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m%s\033[0m\n' "$*"; }
fail() { printf '\033[1;31mERRO: %s\033[0m\n' "$*"; exit 1; }
[ "$(id -u)" = 0 ] || fail "Rode como root (ou com sudo)."

DEST="$ACHOME"; SERVICE=ac-server; NAME="Public"; ACTION=instalar
case "${1:-}" in
  ""|public) ;;
  pro) DEST="$ACHOME/pro"; SERVICE=ac-pro; NAME="Inter Pro" ;;
  remover|remover-public) ACTION=remover ;;
  remover-pro) ACTION=remover; DEST="$ACHOME/pro"; SERVICE=ac-pro; NAME="Inter Pro" ;;
  *) fail "Opção desconhecida: $1 (use: public, pro, remover ou remover-pro)" ;;
esac
[ -f "$DEST/server.sh" ] || fail "Não achei $DEST/server.sh"
LOG="$DEST/logs/console.log"

restart() {
  local uid; uid="$(id -u "$ACUSER")"
  sudo -u "$ACUSER" XDG_RUNTIME_DIR="/run/user/$uid" systemctl --user restart "$SERVICE.service"
}
remover() {
  rm -f "$DEST/bin_unix/native_server"
  restart
}

if [ "$ACTION" = remover ]; then
  remover
  ok "Pronto: o $NAME voltou ao servidor original do AssaultCube."
  exit 0
fi

say "Instalando ferramentas de compilação"
apt-get update -q >/dev/null
DEBIAN_FRONTEND=noninteractive apt-get install -y -q build-essential clang zlib1g-dev python3 git >/dev/null

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
say "Baixando o código oficial do AssaultCube 1.3.0.2"
git -c advice.detachedHead=false clone -q --depth 1 --branch "$AC_TAG" "$AC_REPO" "$WORK/ac"
SRC="$WORK/ac/source/src"
[ -d "$SRC" ] || fail "Não achei a pasta source/src no código baixado."

say "Aplicando as boas-vindas com rank"
python3 "$HERE/apply-welcome.py" "$SRC"

say "Compilando o servidor (leva de 2 a 5 minutos)"
if ! make -C "$SRC" server -j"$(nproc)" >"$WORK/build.log" 2>&1; then
  tail -40 "$WORK/build.log"
  fail "A compilação falhou. Nada foi trocado no servidor."
fi

install -o "$ACUSER" -g "$ACUSER" -m 755 "$SRC/ac_server" "$DEST/bin_unix/native_server"
restart
say "$NAME reiniciado com as boas-vindas. Conferindo o registro no masterserver (até 2 minutos)..."

for _ in $(seq 1 24); do
  sleep 5
  if grep -q "master server registration succeeded" "$LOG" 2>/dev/null; then
    ok "Registro no masterserver: OK. O $NAME continua na lista, com as boas-vindas ligadas."
    exit 0
  fi
  if grep -q -E "could not connect|registration failed|could not open socket" "$LOG" 2>/dev/null; then
    grep -E "could not connect|registration failed|could not open socket" "$LOG" | tail -2
    say "O masterserver recusou. Voltando o $NAME para o servidor original..."
    remover
    sleep 20
    if grep -q "master server registration succeeded" "$LOG" 2>/dev/null; then
      ok "O servidor original registrou normal. Então o problema é a versão modificada: me avise."
    else
      echo "O original também ainda não registrou: pode ser o masterserver fora do ar agora. Veja a aba Log do painel."
    fi
    exit 1
  fi
done
echo "Nenhuma resposta do masterserver em 2 minutos (nem sucesso nem erro)."
echo "O servidor ficou com as boas-vindas. Confira na lista do jogo; se não aparecer, rode:"
echo "  bash $HERE/install-welcome.sh remover"
