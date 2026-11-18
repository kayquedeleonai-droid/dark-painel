# CubeForge · Painel dos servidores

Painel web para administrar um servidor **AssaultCube 1.3** rodando em Linux (Ubuntu), com login.

Funções: status do servidor, ligar/reiniciar/desligar, nome com cores, boas-vindas, máximo de jogadores,
rotação de mapas, senhas de admin, banidos permanentes, log ao vivo e atualização pelo próprio painel.

## Instalar ou atualizar pelo terminal

Como **root** no servidor (o AssaultCube precisa estar instalado no usuário `ac`):

```
bash <(curl -fsSL https://raw.githubusercontent.com/kayquedeleonai-droid/dark-painel/main/install.sh)
```

Depois abra o painel em `http://IP_DO_SERVIDOR:8080` e o site público em `http://IP_DO_SERVIDOR:8081`.

Senhas, chave do servidor e configurações ficam só no servidor e **nunca** vão para este repositório.

## Comandos de emergência (como root)

```
sudo -u ac XDG_RUNTIME_DIR=/run/user/$(id -u ac) systemctl --user restart ac-server   # reinicia o jogo
sudo -u ac XDG_RUNTIME_DIR=/run/user/$(id -u ac) systemctl --user restart ac-painel   # reinicia o painel
```

Para trocar a senha do painel: apague `/home/ac/painel/config.json` e rode o instalador de novo.

## Site público

`site_app.py` (serviço `ac-site`, porta 8081): servidores ao vivo (consulta a porta de informações de cada
servidor, como a lista do jogo), ranking público e downloads. Só leitura; não mostra IP nem a identidade
completa dos jogadores. Endereço de conexão e convite do Discord ficam em Painel → Site público.
Fontes Teko e Barlow Semi Condensed hospedadas no próprio site (SIL OFL).
