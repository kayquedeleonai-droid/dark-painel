# CubeForge · Painel dos servidores

Painel web para administrar um servidor **AssaultCube 1.3** rodando em Linux (Ubuntu), com login.

Funções: status do servidor, ligar/reiniciar/desligar, nome com cores, boas-vindas, máximo de jogadores,
rotação de mapas, senhas de admin, banidos permanentes, log ao vivo e atualização pelo próprio painel.

## Instalar ou atualizar pelo terminal

Como **root** no servidor (o AssaultCube precisa estar instalado no usuário `ac`):

```
bash <(curl -fsSL https://raw.githubusercontent.com/kayquedeleonai-droid/dark-painel/main/install.sh)
```

Depois abra o painel em `http://IP_DO_SERVIDOR:8080`.

Senhas, chave do servidor e configurações ficam só no servidor e **nunca** vão para este repositório.

## Comandos de emergência (como root)

```
sudo -u ac XDG_RUNTIME_DIR=/run/user/$(id -u ac) systemctl --user restart ac-server   # reinicia o jogo
sudo -u ac XDG_RUNTIME_DIR=/run/user/$(id -u ac) systemctl --user restart ac-painel   # reinicia o painel
```

Para trocar a senha do painel: apague `/home/ac/painel/config.json` e rode o instalador de novo.

## Site público

O site CubeForge fica no repositório privado `cubeforge` e é instalado à parte (veja o README de lá).
Ele lê daqui do painel: endereço de conexão e Discord (Painel → Site público), jogadores escondidos e
identidades juntadas no Ranking. O painel atualiza os dois em Atualizações.

## Comandos de Inter (acmod/)
Versão do servidor do AssaultCube 1.3.0.2 com comandos de chat para partidas Inter. O jogo dos jogadores não muda.

- **Todos:** `!ready` (`!r`), `!notready`, `!status`, `!help`
- **Admins:** `!inter [tamanho]`, `!pub`, `!go`, `!pause`, `!shuffle`, `!map <nome> [modo] [minutos]`, `!time <minutos>`, `!teamsize <n>`
- **Pausa automática:** no modo inter, se alguém de um time sai no meio da partida, o jogo pausa; um admin retoma com `!go` (contagem de 3 s).
- Cada mapa novo no modo inter espera todos darem `!ready`.

Instalar (como root na VPS, depois de atualizar o painel):
```
bash /home/ac/painel/acmod/install-inter.sh            # Inter Pro
bash /home/ac/painel/acmod/install-inter.sh public     # Public
bash /home/ac/painel/acmod/install-inter.sh remover    # volta o Inter Pro ao original
```
O script baixa o código oficial (tag v1.3.0.2), aplica `acmod/apply.py` + `acmod/intercmds.inc`, compila e instala como `bin_unix/native_server` (o `server.sh` usa esse arquivo quando existe). Guia para jogadores: https://cubeforge.kayquedeleon.app/en/inter
