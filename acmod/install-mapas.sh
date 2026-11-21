#!/usr/bin/env bash
# Cria o terceiro servidor: CubeForge | Map Lab (edição cooperativa de mapas, até 8 jogadores).
# Usa o servidor ORIGINAL do AssaultCube 1.3.0.2, sem modificação, para não ter problema com o masterserver.
# Uso (como root):
#   bash /home/ac/painel/acmod/install-mapas.sh           # cria (ou reconfigura) o Map Lab
#   bash /home/ac/painel/acmod/install-mapas.sh remover   # desliga e apaga o Map Lab
set -euo pipefail

ACUSER="${ACUSER:-ac}"
PORT=28771
AC_TARBALL="https://github.com/assaultcube/AC/releases/download/v1.3.0.2/AssaultCube_v1.3.0.2_LockdownEdition_RC1.tar.bz2"

say()  { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31mERRO: %s\033[0m\n' "$*"; exit 1; }

[ "$(id -u)" = 0 ] || fail "Rode como root (a linha deve terminar em #)."
id "$ACUSER" >/dev/null 2>&1 || fail "O usuário '$ACUSER' não existe."
ACHOME="$(getent passwd "$ACUSER" | cut -d: -f6)"
ACUID="$(id -u "$ACUSER")"
DEST="$ACHOME/mapas"
UNITDIR="$ACHOME/.config/systemd/user"
asac() { sudo -u "$ACUSER" XDG_RUNTIME_DIR="/run/user/$ACUID" "$@"; }

if [ "${1:-}" = remover ]; then
  say "Desligando e removendo o Map Lab"
  asac systemctl --user disable --now ac-mapas.service >/dev/null 2>&1 || true
  rm -f "$UNITDIR/ac-mapas.service"
  asac systemctl --user daemon-reload
  rm -rf "$DEST"
  ufw delete allow "$PORT:$((PORT + 1))/udp" >/dev/null 2>&1 || true
  echo "Map Lab removido. Os servidores Public e Inter Pro não foram mexidos."
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
# garantia: nunca usar binário modificado neste servidor
rm -f "$DEST/bin_unix/native_server"

say "Preparando os mapas editáveis"
# No AssaultCube, o coop só é liberado para todos em mapas da pasta servermaps/incoming.
# Mapas oficiais (e os de servermaps/) são somente leitura: no coop exigem admin.
INC="$DEST/packages/maps/servermaps/incoming"
mkdir -p "$INC"
# mapas da comunidade do Public
for d in "$ACHOME/packages/maps/servermaps" "$ACHOME/packages/maps/servermaps/incoming"; do
  if [ -d "$d" ]; then
    find "$d" -maxdepth 1 -type f \( -name '*.cgz' -o -name '*.cfg' \) -exec cp -n {} "$INC/" \; || true
  fi
done
# cópias editáveis dos mapas oficiais: ac_complex vira lab_complex, e assim por diante
OFF="$DEST/packages/maps/official"
for f in "$OFF"/ac_*.cgz; do
  [ -f "$f" ] || continue
  b="$(basename "$f" .cgz)"; n="lab_${b#ac_}"
  cp -n "$f" "$INC/$n.cgz" || true
  if [ -f "$OFF/$b.cfg" ]; then cp -n "$OFF/$b.cfg" "$INC/$n.cfg" || true; fi
done
# versões antigas deste script copiavam para servermaps/ (somente leitura): move para incoming
find "$DEST/packages/maps/servermaps" -maxdepth 1 -type f \( -name '*.cgz' -o -name '*.cfg' \) -exec mv -n {} "$INC/" \; || true

say "Escrevendo a configuração"
KEYLINE=""
if [ -f "$DEST/config/servercmdline.txt" ]; then
  KEYLINE="$(grep -E '^-Y' "$DEST/config/servercmdline.txt" | grep -v 'AAAAAAAA' | head -1 || true)"
fi
{
  echo "// CubeForge | Map Lab: configurado pelo painel"
  echo "-n\\f5Cube\\f1Forge \\f4| \\f0Map Lab \\f4NY"
  echo "-oWelcome to CubeForge Map Lab! Build maps together.\\n\\f2Edit: \\f0/coop lab_complex \\f2- blank map: \\f0/newmap 6 \\f2- edit mode: \\f0E\\n\\f2Save: \\f0/savemap name \\f2then \\f0/sendmap\\n\\f3Respect other people's work."
  echo "-c8"
  echo "-f$PORT"
  echo "-mms.cubers.net"
  echo "-McruD"
  echo "-PfkbpmasrcDeptwx"
  echo "-Z200"
  echo "-kA0"
  [ -n "$KEYLINE" ] && echo "$KEYLINE"
} > "$DEST/config/servercmdline.txt"

# O servidor dedicado não deixa o modo coop na rotação: ele começa num mapa normal
# e os jogadores entram no coop com /coop nome_do_mapa (o voto passa na hora se estiver sozinho).
cat > "$DEST/config/maprot.cfg" <<'EOF'
ac_complex tdm time:60
ac_desert tdm time:60
ac_depot tdm time:60
EOF
if [ -f "$ACHOME/config/serverpwd.cfg" ] && [ ! -f "$DEST/config/serverpwd.cfg.cubeforge" ]; then
  cp "$ACHOME/config/serverpwd.cfg" "$DEST/config/serverpwd.cfg"
  touch "$DEST/config/serverpwd.cfg.cubeforge"
fi
chown -R "$ACUSER:$ACUSER" "$DEST"

say "Criando o serviço ac-mapas"
mkdir -p "$UNITDIR"
cat > "$UNITDIR/ac-mapas.service" <<'EOF'
[Unit]
Description=Servidor AssaultCube (CubeForge Map Lab)

[Service]
WorkingDirectory=%h/mapas
ExecStart=/usr/bin/stdbuf -oL -eL %h/mapas/server.sh
StandardOutput=truncate:%h/mapas/logs/console.log
StandardError=inherit
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
chown -R "$ACUSER:$ACUSER" "$ACHOME/.config"
asac systemctl --user daemon-reload
asac systemctl --user enable ac-mapas.service >/dev/null 2>&1
asac systemctl --user restart ac-mapas.service

say "Liberando a porta no firewall"
ufw allow "$PORT:$((PORT + 1))/udp" >/dev/null || true

sleep 3
if asac systemctl --user is-active --quiet ac-mapas.service; then
  printf '\033[1;32mMap Lab ligado na porta %s.\033[0m\n' "$PORT"
else
  echo "O Map Lab não ligou. Veja: tail -30 $DEST/logs/console.log"
fi
if [ -z "$KEYLINE" ]; then
  echo "Falta a chave própria dele: no jogo digite /authkey new maplab, copie a chave e cole no painel"
  echo "(selecione Map Lab > Configurações). Não use a mesma chave do Public ou do Inter Pro."
fi
