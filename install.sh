#!/usr/bin/env bash
# Instalador / atualizador do painel do servidor AssaultCube (CubeForge).
# Uso (como root):
#   bash <(curl -fsSL https://raw.githubusercontent.com/kayquedeleonai-droid/dark-painel/main/install.sh)
set -euo pipefail

REPO="${REPO:-https://github.com/kayquedeleonai-droid/dark-painel.git}"
ACUSER="${ACUSER:-ac}"
PORT=8080

say()  { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31mERRO: %s\033[0m\n' "$*"; exit 1; }

[ "$(id -u)" = 0 ] || fail "Rode como root (a linha deve terminar em #). Se estiver como '$ACUSER', digite: exit"
id "$ACUSER" >/dev/null 2>&1 || fail "O usuário '$ACUSER' não existe."
ACHOME="$(getent passwd "$ACUSER" | cut -d: -f6)"
ACUID="$(id -u "$ACUSER")"
[ -f "$ACHOME/server.sh" ] || fail "Não achei $ACHOME/server.sh. O AssaultCube está instalado nesse usuário?"
DEST="$ACHOME/painel"
asuser() { sudo -u "$ACUSER" "$@"; }
asac()   { sudo -u "$ACUSER" XDG_RUNTIME_DIR="/run/user/$ACUID" "$@"; }

say "Instalando dependências (git, Python, Flask, Waitress)"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git python3 python3-flask python3-waitress >/dev/null

say "Baixando o painel do GitHub"
if [ -d "$DEST/.git" ]; then
  asuser git -C "$DEST" pull --ff-only
else
  # instalação antiga (sem git): guarda o login e troca pela versão do GitHub
  KEEP=""
  if [ -f "$DEST/config.json" ]; then KEEP="$(mktemp)"; cp "$DEST/config.json" "$KEEP"; fi
  rm -rf "$DEST"
  asuser git clone -q "$REPO" "$DEST"
  if [ -n "$KEEP" ]; then cp "$KEEP" "$DEST/config.json"; rm -f "$KEEP"; fi
fi
mkdir -p "$ACHOME/logs"
chown -R "$ACUSER:$ACUSER" "$DEST" "$ACHOME/logs"

if [ ! -f "$DEST/config.json" ]; then
  say "Criando o login do painel"
  read -rp "Nome de usuário do painel: " PUSER
  while :; do
    read -rsp "Senha do painel (mínimo 10 caracteres, não aparece na tela): " PPASS; echo
    read -rsp "Repita a senha: " PPASS2; echo
    if [ "${#PPASS}" -lt 10 ]; then echo "Senha muito curta."; continue; fi
    if [ "$PPASS" != "$PPASS2" ]; then echo "As senhas não conferem."; continue; fi
    break
  done
  PUSER="$PUSER" PPASS="$PPASS" CFG="$DEST/config.json" python3 - <<'PY'
import json, os, secrets
from werkzeug.security import generate_password_hash
cfg = {"username": os.environ["PUSER"],
       "password_hash": generate_password_hash(os.environ["PPASS"]),
       "secret_key": secrets.token_hex(32)}
with open(os.environ["CFG"], "w") as f:
    json.dump(cfg, f)
PY
  unset PPASS PPASS2
  chown "$ACUSER:$ACUSER" "$DEST/config.json"
else
  say "Login do painel já existe, mantendo (para trocar: apague $DEST/config.json e rode de novo)"
fi
chmod 600 "$DEST/config.json"

if [ ! -f "$DEST/site.json" ]; then
  printf '{"host": "%s", "discord": ""}\n' "$(hostname -I | awk '{print $1}')" > "$DEST/site.json"
  chown "$ACUSER:$ACUSER" "$DEST/site.json"
fi

PRO="$ACHOME/pro"
PRO_PORT=28767
AC_TARBALL="https://github.com/assaultcube/AC/releases/download/v1.3.0.2/AssaultCube_v1.3.0.2_LockdownEdition_RC1.tar.bz2"
if [ ! -f "$PRO/server.sh" ]; then
  say "Criando o segundo servidor (CubeForge | Inter Pro) em $PRO"
  mkdir -p "$PRO"
  TMPF="$(mktemp --suffix=.tar.bz2)"
  curl -fsSL -o "$TMPF" "$AC_TARBALL"
  tar -xjf "$TMPF" -C "$PRO"
  rm -f "$TMPF"
  mkdir -p "$PRO/logs"
  cat > "$PRO/config/servercmdline.txt" <<EOF
// CubeForge | Inter Pro: configurado pelo painel
-n\\f5Cube\\f9Forge \\f4| \\f3Inter Pro \\f4NY
-oWelcome to CubeForge Inter Pro! Competitive matches. Respect everyone and play fair. No racism, discrimination or harassment - violators will be banned. GG!
-c12
-f$PRO_PORT
-mms.cubers.net
-MCURD
-kA300
EOF
  cat > "$PRO/config/maprot.cfg" <<'EOF'
ac_complex tdm|tosok time:15
ac_desert tdm|tosok time:15
ac_douze tdm|tosok time:15
ac_aqueous tdm|tosok time:15
ac_arctic tdm|tosok time:15
ac_depot tdm|tosok time:15
ac_mines tdm|tosok time:15
ac_shine tdm|tosok time:15
EOF
  if [ -f "$ACHOME/config/serverpwd.cfg" ]; then cp "$ACHOME/config/serverpwd.cfg" "$PRO/config/serverpwd.cfg"; fi
  chown -R "$ACUSER:$ACUSER" "$PRO"
  echo "Servidor PRO criado. Falta a chave dele: cole em Configurações no painel (selecione Inter Pro)."
fi

if asuser screen -ls 2>/dev/null | grep -q '\.ac'; then
  say "Parando o servidor antigo que estava no screen"
  asuser screen -S ac -X quit || true
  sleep 2
fi

say "Configurando o servidor e o painel para ligarem sozinhos"
UNITDIR="$ACHOME/.config/systemd/user"
mkdir -p "$UNITDIR"
cp "$DEST"/systemd/*.service "$UNITDIR/"
chown -R "$ACUSER:$ACUSER" "$ACHOME/.config"

loginctl enable-linger "$ACUSER"
for _ in $(seq 1 20); do [ -S "/run/user/$ACUID/bus" ] && break; sleep 0.5; done
asac systemctl --user daemon-reload
asac systemctl --user enable ac-server.service ac-pro.service ac-painel.service ac-site.service >/dev/null 2>&1
asac systemctl --user restart ac-server.service ac-pro.service ac-painel.service ac-site.service

say "Liberando as portas no firewall"
ufw allow "$PORT/tcp" >/dev/null || true
ufw allow 8081/tcp >/dev/null || true
ufw allow "$PRO_PORT:$((PRO_PORT + 1))/udp" >/dev/null || true

sleep 3
IP="$(hostname -I | awk '{print $1}')"
echo
if asac systemctl --user is-active --quiet ac-painel.service; then
  printf '\033[1;32mPronto! Abra no navegador:  http://%s:%s\033[0m\n' "$IP" "$PORT"
  printf '\033[1;32mSite público CubeForge:    http://%s:8081\033[0m\n' "$IP"
  echo "Próximas atualizações: pelo botão em Atualizações, dentro do painel."
else
  echo "O painel não ligou. Veja o erro com:"
  echo "  sudo -u $ACUSER XDG_RUNTIME_DIR=/run/user/$ACUID journalctl --user -u ac-painel -n 30"
fi
for S in ac-server:Public ac-pro:"Inter Pro"; do
  UNIT="${S%%:*}"; NAME="${S#*:}"
  if asac systemctl --user is-active --quiet "$UNIT.service"; then
    echo "Servidor $NAME: ligado."
  else
    echo "Servidor $NAME: NÃO ligou. Ligue pelo painel e veja a aba Log."
  fi
done
