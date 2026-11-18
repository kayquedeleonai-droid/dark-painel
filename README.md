# CubeForge · Painel dos servidores

Painel web para administrar um servidor **AssaultCube 1.3** rodando em Linux (Ubuntu), com login.

Funções: status do servidor, ligar/reiniciar/desligar, nome com cores, boas-vindas, máximo de jogadores,
rotação de mapas, senhas de admin, banidos permanentes, log ao vivo e atualização pelo próprio painel.

## Instalar ou atualizar pelo terminal

Como **root** no servidor (o AssaultCube precisa estar instalado no usuário `ac`):

```
bash <(curl -fsSL https://raw.githubusercontent.com/kayquedeleonai-droid/dark-painel/main/install.sh)
```

Depois abra `http://IP_DO_SERVIDOR:8080`.

Senhas, chave do servidor e configurações ficam só no servidor e **nunca** vão para este repositório.

## Comandos de emergência (como root)

```
sudo -u ac XDG_RUNTIME_DIR=/run/user/$(id -u ac) systemctl --user restart ac-server   # reinicia o jogo
sudo -u ac XDG_RUNTIME_DIR=/run/user/$(id -u ac) systemctl --user restart ac-painel   # reinicia o painel
```

Para trocar a senha do painel: apague `/home/ac/painel/config.json` e rode o instalador de novo.
