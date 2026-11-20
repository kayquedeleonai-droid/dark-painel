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
- **Controle da partida:** `!inter [tamanho]`, `!pub`, `!go`, `!pause`, `!private`, `!open`, `!shuffle`, `!map <nome> [modo] [minutos]`, `!time <minutos>`, `!teamsize <n>`
- **Quem controla:** `inter_open:1` em `config/serverparameters.cfg` libera o controle para todos (o instalador faz isso no Inter Pro); `inter_open:0` deixa só para admins (Public). Com `inter_open:1`, durante uma partida rolando só admins usam `!pub`, `!map`, `!time`, `!shuffle`, `!teamsize`, `!open` e `!inter`.
- **Privado:** `!private` (e o modo inter) não deixam ninguém novo entrar; quem caiu da partida pode voltar. Quando o servidor esvazia, ele volta a ficar aberto sozinho.
- **Pausa automática:** no modo inter, se alguém de um time sai no meio da partida, o jogo pausa; um admin retoma com `!go` (contagem de 3 s).
- Cada mapa novo no modo inter espera todos darem `!ready`.

Instalar (como root na VPS, depois de atualizar o painel):
```
bash /home/ac/painel/acmod/install-inter.sh            # Inter Pro
bash /home/ac/painel/acmod/install-inter.sh public     # Public
bash /home/ac/painel/acmod/install-inter.sh remover    # volta o Inter Pro ao original
```
### Votação do próximo mapa (Public)
Com `mapvote:1` em `config/serverparameters.cfg`, faltando `mapvote_seconds` (padrão 60) para o fim da partida o servidor mostra no chat todos os mapas favoritos da rotação (os que têm `manual:0`), menos o atual, numerados. Cada jogador vota digitando o número no chat (T, número, Enter) e pode trocar o voto. No fim, o mais votado vira o próximo mapa (empate: sorteio; sem votos: rotação normal; se alguém já escolheu o próximo mapa pelo voto normal do jogo, ele vale). Não roda durante o modo inter. O instalador liga no Public e desliga no Inter Pro.

O script baixa o código oficial (tag v1.3.0.2), aplica `acmod/apply.py` + `acmod/intercmds.inc`, compila e instala como `bin_unix/native_server` (o `server.sh` usa esse arquivo quando existe). Guia para jogadores: https://cubeforge.kayquedeleon.app/en/inter
