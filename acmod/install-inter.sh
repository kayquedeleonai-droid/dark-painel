#!/usr/bin/env bash
# CubeForge: instala os comandos de Inter (!inter, !ready, !go, pausa automática...) num servidor AssaultCube 1.3.0.2.
# Baixa o código oficial do AssaultCube (tag v1.3.0.2 no GitHub), aplica as mudanças do CubeForge, compila só o programa do servidor
# e o coloca como bin_unix/native_server (o server.sh usa esse arquivo quando ele existe).
# O jogo dos jogadores não muda: eles continuam usando o AssaultCube normal.
#
# Uso, como root na VPS:
#   bash /home/ac/painel/acmod/install-inter.sh            -> instala no Inter Pro (/home/ac/pro)
#   bash /home/ac/painel/acmod/install-inter.sh public     -> instala no Public (/home/ac)
#   bash /home/ac/painel/acmod/install-inter.sh remover    -> volta o Inter Pro ao servidor original
set -euo pipefail

ACUSER=ac
ACHOME=/home/ac
AC_REPO="https://github.com/assaultcube/AC.git"
AC_TAG="v1.3.0.2"
HERE="$(cd "$(dirname "$0")" && pwd)"

say()  { printf '\033[1;33m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31mERRO: %s\033[0m\n' "$*"; exit 1; }
[ "$(id -u)" = 0 ] || fail "Rode como root (ou com sudo)."

DEST="$ACHOME/pro"; SERVICE=ac-pro; NAME="Inter Pro"; ACTION=instalar
case "${1:-}" in
  ""|pro) ;;
  public) DEST="$ACHOME"; SERVICE=ac-server; NAME="Public" ;;
  remover) ACTION=remover ;;
  remover-public) ACTION=remover; DEST="$ACHOME"; SERVICE=ac-server; NAME="Public" ;;
  *) fail "Opção desconhecida: $1 (use: pro, public, remover ou remover-public)" ;;
esac
[ -f "$DEST/server.sh" ] || fail "Não achei $DEST/server.sh"

restart() {
  local uid; uid="$(id -u "$ACUSER")"
  sudo -u "$ACUSER" XDG_RUNTIME_DIR="/run/user/$uid" systemctl --user restart "$SERVICE.service"
}

if [ "$ACTION" = remover ]; then
  rm -f "$DEST/bin_unix/native_server"
  restart
  say "Pronto: o $NAME voltou ao servidor original do AssaultCube."
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

say "Aplicando os comandos de Inter do CubeForge"
python3 "$HERE/apply.py" "$SRC"

say "Compilando o servidor (leva de 2 a 5 minutos)"
if ! make -C "$SRC" server -j"$(nproc)" >"$WORK/build.log" 2>&1; then
  tail -40 "$WORK/build.log"
  fail "A compilação falhou. Nada foi trocado no servidor."
fi

# Inter Pro: comandos de partida liberados para todos os jogadores (inter_open:1).
# No Public ficam só para admins. Dá para mudar depois em config/serverparameters.cfg (vale em até 1 minuto).
PARAMS="$DEST/config/serverparameters.cfg"
OPEN=0; [ "$SERVICE" = ac-pro ] && OPEN=1
if grep -q '^inter_open:' "$PARAMS" 2>/dev/null; then
  sed -i "s/^inter_open:.*/inter_open:$OPEN/" "$PARAMS"
else
  printf '\n// CubeForge: 1 = todos podem usar !inter, !go, !pause, !private...; 0 = só admins\ninter_open:%s\n' "$OPEN" >> "$PARAMS"
fi
chown "$ACUSER:$ACUSER" "$PARAMS"

install -o "$ACUSER" -g "$ACUSER" -m 755 "$SRC/ac_server" "$DEST/bin_unix/native_server.new"
mv -f "$DEST/bin_unix/native_server.new" "$DEST/bin_unix/native_server"
restart
say "Pronto! Os comandos de Inter estão ativos no $NAME."
if [ "$OPEN" = 1 ]; then
  echo "  No jogo: qualquer jogador pode digitar !inter, !ready, !go, !private... (!help mostra tudo)."
else
  echo "  No jogo: entre como admin (/setadmin 1 SENHA) e digite !help."
fi
echo "  Para voltar ao original: bash $HERE/install-inter.sh remover"
