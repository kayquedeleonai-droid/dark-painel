#!/usr/bin/env bash
# Cria os servidores CubeForge 2VS2 e 1VS1 (CTF, mesma rotação e mapas do Public, servidor ORIGINAL).
# Uso, como root na VPS:
#   bash /home/ac/painel/acmod/install-duelo.sh 2v2           # cria (ou reconfigura) o 2VS2, porta 28775, 4 jogadores
#   bash /home/ac/painel/acmod/install-duelo.sh 1v1           # cria (ou reconfigura) o 1VS1, porta 28779, 2 jogadores
#   bash /home/ac/painel/acmod/install-duelo.sh remover-2v2   # desliga e apaga o 2VS2
#   bash /home/ac/painel/acmod/install-duelo.sh remover-1v1   # desliga e apaga o 1VS1
set -euo pipefail

ACUSER="${ACUSER:-ac}"
AC_TARBALL="https://github.com/assaultcube/AC/releases/download/v1.3.0.2/AssaultCube_v1.3.0.2_LockdownEdition_RC1.tar.bz2"

say()  { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31mERRO: %s\033[0m\n' "$*"; exit 1; }

[ "$(id -u)" = 0 ] || fail "Rode como root (a linha deve terminar em #)."
id "$ACUSER" >/dev/null 2>&1 || fail "O usuário '$ACUSER' não existe."
ACHOME="$(getent passwd "$ACUSER" | cut -d: -f6)"
ACUID="$(id -u "$ACUSER")"
UNITDIR="$ACHOME/.config/systemd/user"
asac() { sudo -u "$ACUSER" XDG_RUNTIME_DIR="/run/user/$ACUID" "$@"; }

ACTION=instalar
case "${1:-}" in
  2v2|2vs2) ID=2v2 ;;
  1v1|1vs1) ID=1v1 ;;
  remover-2v2) ID=2v2; ACTION=remover ;;
  remover-1v1) ID=1v1; ACTION=remover ;;
  *) fail "Diga qual: 2v2, 1v1, remover-2v2 ou remover-1v1" ;;
esac
if [ "$ID" = 2v2 ]; then
  PORT=28775; MAX=4; TAG=2VS2; TXT="2 vs 2"
else
  PORT=28779; MAX=2; TAG=1VS1; TXT="1 vs 1"
fi
DEST="$ACHOME/$ID"
SERVICE="ac-$ID"

if [ "$ACTION" = remover ]; then
  say "Desligando e removendo o $TAG"
  asac systemctl --user disable --now "$SERVICE.service" >/dev/null 2>&1 || true
  rm -f "$UNITDIR/$SERVICE.service"
  asac systemctl --user daemon-reload
  rm -rf "$DEST"
  ufw delete allow "$PORT:$((PORT + 1))/udp" >/dev/null 2>&1 || true
  echo "$TAG removido. Os outros servidores não foram mexidos."
  exit 0
fi

if [ ! -f "$DEST/server.sh" ]; then
  say "Baixando o AssaultCube original para $DEST"
  mkdir -p "$DEST"
  TMPF="$(mktemp --suffix=.tar.bz2)"
  curl -fsSL -o "$TMPF" "$AC_TARBALL"
  tar -xjf "$TMPF" -C "$DEST"
  rm -f "$TMPF"
fi
mkdir -p "$DEST/logs"
rm -f "$DEST/bin_unix/native_server"   # servidor original, sem modificação

say "Copiando os mapas e a rotação do Public (CTF, favoritos)"
if [ -d "$ACHOME/packages/maps/servermaps" ]; then
  mkdir -p "$DEST/packages/maps/servermaps"
  cp -rn "$ACHOME/packages/maps/servermaps/." "$DEST/packages/maps/servermaps/" || true
fi
[ -f "$ACHOME/config/maprot.cfg" ] && cp -f "$ACHOME/config/maprot.cfg" "$DEST/config/maprot.cfg"
if [ -f "$ACHOME/config/serverpwd.cfg" ] && [ ! -f "$DEST/config/serverpwd.cfg.cubeforge" ]; then
  cp "$ACHOME/config/serverpwd.cfg" "$DEST/config/serverpwd.cfg"
  touch "$DEST/config/serverpwd.cfg.cubeforge"
fi

say "Escrevendo a configuração"
KEYLINE=""
if [ -f "$DEST/config/servercmdline.txt" ]; then
  KEYLINE="$(grep -E '^-Y' "$DEST/config/servercmdline.txt" | grep -v 'AAAAAAAA' | head -1 || true)"
fi
{
  echo "// CubeForge $TAG: configurado pelo painel"
  printf '%s\n' "-n\\f3CUBE\\f5FORGE \\f3$TAG\\f2 \\f5| \\f2CTF \\f5| \\f324\\f2/\\f37"
  printf '%s\n' "-oWelcome to \\f3CUBE\\f5FORGE \\f3$TAG\\f2! CTF, $TXT. Teams are balanced automatically.\\n\\f2Good luck and have fun!"
  echo "-c$MAX"
  echo "-f$PORT"
  echo "-mms.cubers.net"
  [ -n "$KEYLINE" ] && echo "$KEYLINE"
} > "$DEST/config/servercmdline.txt"
chown -R "$ACUSER:$ACUSER" "$DEST"

say "Criando o serviço $SERVICE"
mkdir -p "$UNITDIR"
cat > "$UNITDIR/$SERVICE.service" <<EOF
[Unit]
Description=Servidor AssaultCube (CubeForge $TAG)

[Service]
WorkingDirectory=%h/$ID
ExecStart=/usr/bin/stdbuf -oL -eL %h/$ID/server.sh
StandardOutput=truncate:%h/$ID/logs/console.log
StandardError=inherit
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
chown -R "$ACUSER:$ACUSER" "$ACHOME/.config"
asac systemctl --user daemon-reload
asac systemctl --user enable "$SERVICE.service" >/dev/null 2>&1
asac systemctl --user restart "$SERVICE.service"

say "Liberando a porta no firewall"
ufw allow "$PORT:$((PORT + 1))/udp" >/dev/null || true

sleep 3
if asac systemctl --user is-active --quiet "$SERVICE.service"; then
  printf '\033[1;32m%s ligado na porta %s (máximo %s jogadores).\033[0m\n' "$TAG" "$PORT" "$MAX"
else
  echo "O $TAG não ligou. Veja: tail -30 $DEST/logs/console.log"
fi
if [ -z "$KEYLINE" ]; then
  echo "Falta a chave própria dele: no jogo digite /authkey new cf$ID, pegue a linha priv no authkeys.cfg"
  echo "e cole no painel (selecione $TAG > Configurações). Não repita a chave de outro servidor."
fi
