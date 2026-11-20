// ===== CubeForge: comandos de Inter (!inter, !ready, !go, pausa automática...) =====
// Admins controlam a partida; !ready, !notready, !status e !help são para todos.

extern const char *modeacronymnames[];

// inter_open:1 no serverparameters.cfg libera os comandos de controle para todos os jogadores
SERVPAR(inter_open, 0, 0, 1, "sCubeForge: everyone can use the inter commands (!inter, !go, !private...), 0: admins only");

static struct interstate
{
    bool active;              // modo inter ligado
    bool waiting;             // pausado esperando todos darem !ready (ou um admin dar !go)
    int countdown;            // servmillis em que a contagem termina (0 = sem contagem)
    int lastshown;            // último número da contagem já mostrado
    int lastgm;               // gamemillis da última volta (para perceber mapa novo)
    bool ready[MAXCLIENTS];
} inter = { false, false, 0, 0, 0, { false } };

static void imsg(const char *fmt, ...) PRINTFARGS(1, 2);
static void imsg(const char *fmt, ...)
{
    defvformatstring(s, fmt, fmt);
    sendservmsg(s);
}

static void ipriv(int cn, const char *fmt, ...) PRINTFARGS(2, 3);
static void ipriv(int cn, const char *fmt, ...)
{
    defvformatstring(s, fmt, fmt);
    sendservmsg(s, cn);
}

// ===== CubeForge: votação do próximo mapa (mapvote:1 no serverparameters.cfg) =====
// Faltando mapvote_seconds para o fim, mostra todos os mapas favoritos da rotação (manual:0), menos o atual,
// e os jogadores votam digitando o número no chat. O mais votado vira o próximo mapa.
SERVPAR(mapvote, 0, 0, 1, "sCubeForge: vote for the next map near the end of each game (1: on)");
SERVPAR(mapvote_seconds, 20, 60, 180, "sCubeForge: seconds before the end of the game to start the next-map vote");

#define MAPVOTE_OPTIONS 15
static struct mapvotestate
{
    bool open, done;
    int count;
    string names[MAPVOTE_OPTIONS];
    int modes[MAPVOTE_OPTIONS];
    int votes[MAXCLIENTS];      // 0 = não votou, 1..3 = opção
    int lastgm;
} mv;

static void mapvote_reset() { mv.open = mv.done = false; mv.count = 0; loopi(MAXCLIENTS) mv.votes[i] = 0; loopi(MAPVOTE_OPTIONS) { mv.names[i][0] = '\0'; mv.modes[i] = 0; } }

static void mapvote_tally(int *t)
{
    loopi(MAPVOTE_OPTIONS) t[i] = 0;
    loopv(clients) if(i < MAXCLIENTS && valid_client(i) && mv.votes[i] >= 1 && mv.votes[i] <= mv.count) t[mv.votes[i] - 1]++;
}

static void mapvote_showtally()
{
    int t[MAPVOTE_OPTIONS];
    mapvote_tally(t);
    // só os mapas com voto, do mais votado para o menos
    string line = "";
    bool used[MAPVOTE_OPTIONS] = { false };
    int shown = 0;
    loopk(mv.count)
    {
        int b = -1;
        loopi(mv.count) if(!used[i] && t[i] > 0 && (b < 0 || t[i] > t[b])) b = i;
        if(b < 0 || shown >= 5) break;
        used[b] = true;
        concatformatstring(line, "%s\f5%s \f0%d", shown ? "\f4 | " : "", mv.names[b], t[b]);
        shown++;
    }
    if(shown) imsg("\f2[VOTE] %s", line);
}

static void mapvote_start()
{
    mapvote_reset();
    mv.done = true; // uma votação por partida
    if(sg->nextmapname[0]) return; // alguém já escolheu o próximo mapa (voto normal do jogo)
    maprot.recalcgamesuggestions(numclients());
    loopv(gamesuggestions)
    {
        if(mv.count >= MAPVOTE_OPTIONS) break;
        servermap *m = gamesuggestions[i];
        if(!m || m->bestmode < 0 || !strcmp(m->fname, sg->smapname)) continue;
        copystring(mv.names[mv.count], m->fname);
        mv.modes[mv.count] = m->bestmode;
        mv.count++;
    }
    if(mv.count < 2) { mv.count = 0; return; } // poucas opções: segue a rotação normal
    mv.open = true;
    imsg("\f2[VOTE] \f5Vote for the next map! Press \f0T\f5, type the \f0number \f5and press \f0Enter\f5:");
    for(int i = 0; i < mv.count; i += 3) // 3 mapas por linha
    {
        string line = "";
        for(int j = i; j < i + 3 && j < mv.count; j++) concatformatstring(line, "  \f0%d \f5%s", j + 1, mv.names[j]);
        imsg("\f2[VOTE]%s", line);
    }
}

static void mapvote_finish()
{
    mv.open = false;
    int t[MAPVOTE_OPTIONS];
    mapvote_tally(t);
    int best = 0, total = 0;
    loopi(mv.count) { total += t[i]; if(t[i] > best) best = t[i]; }
    if(!total || sg->nextmapname[0]) return;
    int tied[MAPVOTE_OPTIONS], n = 0;
    loopi(mv.count) if(t[i] == best) tied[n++] = i;
    int w = tied[n > 1 ? rnd(n) : 0];
    copystring(sg->nextmapname, mv.names[w]);
    sg->nextgamemode = mv.modes[w];
    imsg("\f2[VOTE] \f5Next map: \f0%s \f5(%d vote%s)%s", mv.names[w], t[w], t[w] == 1 ? "" : "s", n > 1 ? " \f4- tie broken at random" : "");
}

// chamado a cada volta do servidor
static void mapvote_tick()
{
    if(sg->gamemillis + 1000 < mv.lastgm) mapvote_reset(); // mapa novo
    mv.lastgm = sg->gamemillis;
    if(!mapvote || numclients() == 0 || inter.active) { if(mv.open) mv.open = false; return; } // no modo inter não tem votação
    bool ending = sg->interm || sg->minremain <= 0 || sg->gamemillis >= sg->gamelimit;
    if(mv.open && ending) { mapvote_finish(); return; }
    if(!mv.done && !ending && !sg->sispaused && !m_demo && sg->gamelimit - sg->gamemillis <= mapvote_seconds * 1000 && sg->gamemillis > 5000)
        mapvote_start();
}

// voto no chat: "1", "2", "3" (ou "!1"...) enquanto a votação está aberta
static bool mapvote_chat(int sender, const char *text)
{
    if(!mv.open || sender < 0 || sender >= MAXCLIENTS) return false;
    const char *t = text[0] == '!' ? text + 1 : text;
    // só número (1 ou 2 dígitos) dentro da lista
    if(!isdigit(t[0]) || (t[1] && (!isdigit(t[1]) || t[2]))) return false;
    int choice = atoi(t);
    if(choice < 1 || choice > mv.count) return false;
    bool changed = mv.votes[sender] && mv.votes[sender] != choice;
    mv.votes[sender] = choice;
    client &c = *clients[sender];
    mlog(ACLOG_INFO, "[%s] %s voted for map %s", c.hostname, c.name, mv.names[choice - 1]);
    imsg("\f2[VOTE] \f5%s %s \f0%s", c.name, changed ? "changed vote to" : "voted for", mv.names[choice - 1]);
    mapvote_showtally();
    return true;
}
// ===== fim da votação do próximo mapa =====

static void inter_clearready() { loopi(MAXCLIENTS) inter.ready[i] = false; }

// jogadores nos times (CLA/RVSF), prontos e por time
static void inter_count(int &players, int &ready, int &cla, int &rvsf)
{
    players = ready = cla = rvsf = 0;
    loopv(clients) if(valid_client(i) && clients[i]->isauthed && team_isactive(clients[i]->team))
    {
        players++;
        if(clients[i]->team == TEAM_CLA) cla++; else rvsf++;
        if(i < MAXCLIENTS && inter.ready[i]) ready++;
    }
}

static void inter_wait(const char *why)
{
    inter.waiting = true;
    inter.countdown = 0;
    inter_clearready();
    setpausemode(1);
    imsg("\f2[INTER] \f5%s Type \f0!ready \f5when you are ready. The game starts when everyone is ready.", why);
}

static void inter_startcountdown()
{
    inter.countdown = servmillis + 3000;
    inter.lastshown = 4;
    imsg("\f2[INTER] \f5Starting in 3 seconds...");
}

static void inter_checkready()
{
    if(!inter.active || !inter.waiting || inter.countdown) return;
    int players, ready, cla, rvsf;
    inter_count(players, ready, cla, rvsf);
    if(cla > 0 && rvsf > 0 && ready == players) inter_startcountdown();
}

// chamado a cada volta do servidor
static void intertick()
{
    mapvote_tick();
    if(!inter.active) return;
    if(numclients() == 0) { inter.active = inter.waiting = false; inter.countdown = 0; inter_clearready(); return; }
    // mapa novo começou durante o modo inter: espera todos de novo
    if(sg->gamemillis + 1000 < inter.lastgm && !sg->interm && !inter.waiting)
    {
        defformatstring(why)("New map: %s.", sg->smapname);
        inter_wait(why);
    }
    inter.lastgm = sg->gamemillis;
    if(inter.countdown)
    {
        int left = (inter.countdown - servmillis + 999) / 1000;
        if(left <= 0)
        {
            inter.countdown = 0;
            inter.waiting = false;
            setpausemode(0);
            imsg("\f0[INTER] GO! Good luck, have fun!");
        }
        else if(left < inter.lastshown)
        {
            inter.lastshown = left;
            imsg("\f2[INTER] \f5%d...", left);
        }
    }
}

// alguém saiu do servidor: no meio da partida, pausa
static void interplayerleft(int cn)
{
    if(cn >= 0 && cn < MAXCLIENTS) inter.ready[cn] = false;
    if(!inter.active || !clients.inrange(cn)) return;
    client &c = *clients[cn];
    if(!team_isactive(c.team) || sg->interm || sg->minremain <= 0) return;
    if(inter.countdown) { inter.countdown = 0; imsg("\f2[INTER] \f5Countdown cancelled."); }
    if(!sg->sispaused)
    {
        setpausemode(1);
        imsg("\f3[INTER] %s left the match. Game paused. \f5When they are back, %s \f0!go\f5.", c.name, inter_open ? "type" : "an admin types");
    }
}

static int inter_parsemode(const char *s)
{
    if(!s || !*s) return -1;
    loopi(GMODE_NUM) if(!strcasecmp(s, modeacronymnames[i + 1])) return i;
    return -1;
}

static void inter_help(int cn)
{
    ipriv(cn, "\f2[INTER] \f5Commands for everyone: \f0!ready \f5(I'm ready), \f0!notready\f5, \f0!status\f5, \f0!help");
    const char *who = inter_open ? "Match control" : "Admins";
    ipriv(cn, "\f2[INTER] \f5%s: \f0!inter [teamsize] \f5start inter, \f0!pub \f5back to public, \f0!go \f5start/resume, \f0!pause", who);
    ipriv(cn, "\f2[INTER] \f5%s: \f0!private\f5/\f0!open \f5lock or open the server, \f0!shuffle\f5, \f0!map <name> [mode] [min]\f5, \f0!time <min>\f5, \f0!teamsize <n>", who);
    if(inter_open) ipriv(cn, "\f2[INTER] \f5During a running match, only admins can change map, time, teams or go back to public.");
}

// devolve true se a mensagem era um comando (não vai para o chat)
static bool intercommand(int sender, const char *text)
{
    if(!valid_client(sender)) return false;
    if(mapvote_chat(sender, text)) return true;
    if(text[0] != '!') return false;
    client &c = *clients[sender];
    string buf;
    copystring(buf, text + 1);
    char *args[4] = { NULL, NULL, NULL, NULL };
    int n = 0;
    for(char *t = strtok(buf, " "); t && n < 4; t = strtok(NULL, " ")) args[n++] = t;
    if(!n) return false;
    const char *cmd = args[0];
    bool admin = c.role == CR_ADMIN;
    // partida rolando (modo inter, sem pausa de espera): só admin mexe em mapa, tempo, times e !pub
    bool running = inter.active && !inter.waiting && !sg->interm;
    #define NEEDADMIN if(!admin && !inter_open) { ipriv(sender, "\f3[INTER] Only admins can use !%s.", cmd); return true; }
    #define NEEDADMIN_RUNNING NEEDADMIN if(!admin && running) { ipriv(sender, "\f3[INTER] The match is running: only admins can use !%s now.", cmd); return true; }
    mlog(ACLOG_INFO, "[%s] %s used command: %s", c.hostname, c.name, text);

    if(!strcasecmp(cmd, "help") || !strcasecmp(cmd, "commands") || !strcasecmp(cmd, "cmds")) { inter_help(sender); return true; }

    if(!strcasecmp(cmd, "status"))
    {
        int players, ready, cla, rvsf;
        inter_count(players, ready, cla, rvsf);
        if(!inter.active) ipriv(sender, "\f2[INTER] \f5Inter mode is off. %d players (CLA %d, RVSF %d). An admin can start it with \f0!inter\f5.", players, cla, rvsf);
        else ipriv(sender, "\f2[INTER] \f5Inter ON, %s. CLA %d x RVSF %d, %d/%d ready%s.", modestr(gamemode, true), cla, rvsf, ready, players,
                   sg->sispaused ? ", game paused" : "");
        return true;
    }

    if(!strcasecmp(cmd, "ready") || !strcasecmp(cmd, "r") || !strcasecmp(cmd, "rdy"))
    {
        if(!inter.active) { ipriv(sender, "\f2[INTER] \f5Inter mode is off. An admin can start it with \f0!inter\f5."); return true; }
        if(!team_isactive(c.team)) { ipriv(sender, "\f2[INTER] \f5Join CLA or RVSF first."); return true; }
        if(!inter.waiting) { ipriv(sender, "\f2[INTER] \f5The game is already running."); return true; }
        if(sender < MAXCLIENTS) inter.ready[sender] = true;
        int players, ready, cla, rvsf;
        inter_count(players, ready, cla, rvsf);
        imsg("\f2[INTER] \f0%s is ready \f5(%d/%d)", c.name, ready, players);
        inter_checkready();
        return true;
    }

    if(!strcasecmp(cmd, "notready") || !strcasecmp(cmd, "unready") || !strcasecmp(cmd, "nr"))
    {
        if(!inter.active || !inter.waiting) return true;
        if(sender < MAXCLIENTS) inter.ready[sender] = false;
        if(inter.countdown) { inter.countdown = 0; imsg("\f2[INTER] \f5Countdown cancelled."); }
        imsg("\f2[INTER] \f3%s is not ready.", c.name);
        return true;
    }

    if(!strcasecmp(cmd, "inter") || !strcasecmp(cmd, "match"))
    {
        NEEDADMIN_RUNNING
        int players, ready, cla, rvsf;
        inter_count(players, ready, cla, rvsf);
        int size = args[1] ? atoi(args[1]) : max(max(cla, rvsf), 1);
        if(size < 1 || size > 8) { ipriv(sender, "\f3[INTER] Team size must be 1 to 8, e.g. !inter 4"); return true; }
        int mode = m_teammode ? (int)gamemode : (int)GMODE_CTF;
        servermap *sm = getservermap(sg->smapname);
        if(sm && !(sm->modes_allowed & (1 << mode)))
        {
            ipriv(sender, "\f3[INTER] This map can't be played in %s. Use \f0!map <name> ctf \f3first.", modestr(mode, true));
            return true;
        }
        inter.active = true;
        sg->autoteam = false;
        changemastermode(MM_MATCH);
        changematchteamsize(size);
        sendservermode();
        string mapname;
        copystring(mapname, sg->smapname);
        startgame(mapname, mode, 0, true);
        inter.lastgm = sg->gamemillis;
        defformatstring(why)("INTER MODE ON: %dv%d %s on %s. Teams are locked and new players can't join (dropped players can reconnect).", size, size, modestr(mode, true), mapname);
        inter_wait(why);
        return true;
    }

    if(!strcasecmp(cmd, "pub") || !strcasecmp(cmd, "public"))
    {
        NEEDADMIN_RUNNING
        inter.active = inter.waiting = false;
        inter.countdown = 0;
        inter_clearready();
        changemastermode(MM_OPEN);
        sg->autoteam = true;
        sendservermode();
        if(m_teammode) refillteams(true);
        setpausemode(0);
        imsg("\f2[INTER] \f5Inter mode OFF. Public game, have fun!");
        return true;
    }

    if(!strcasecmp(cmd, "go") || !strcasecmp(cmd, "resume") || !strcasecmp(cmd, "start") || !strcasecmp(cmd, "unpause"))
    {
        NEEDADMIN
        if(!sg->sispaused) { ipriv(sender, "\f2[INTER] \f5The game is not paused."); return true; }
        if(!inter.countdown) inter_startcountdown();
        return true;
    }

    if(!strcasecmp(cmd, "pause"))
    {
        NEEDADMIN
        if(sg->sispaused) { ipriv(sender, "\f2[INTER] \f5Already paused. Use \f0!go \f5to resume."); return true; }
        inter.countdown = 0;
        setpausemode(1);
        imsg("\f2[INTER] \f5Game paused by %s. %s \f0!go \f5to resume.", c.name, inter_open ? "Type" : "An admin types");
        return true;
    }

    if(!strcasecmp(cmd, "shuffle"))
    {
        NEEDADMIN_RUNNING
        if(!m_teammode) { ipriv(sender, "\f3[INTER] This is not a team mode."); return true; }
        shuffleteams(FTR_SILENTFORCE);
        if(inter.active && inter.waiting) inter_clearready();
        imsg("\f2[INTER] \f5Teams shuffled by %s.%s", c.name, inter.active && inter.waiting ? " Type \f0!ready \f5again." : "");
        return true;
    }

    if(!strcasecmp(cmd, "map"))
    {
        NEEDADMIN_RUNNING
        if(!args[1]) { ipriv(sender, "\f2[INTER] \f5Use: \f0!map <name> [ctf|tdm|tosok|tktf|htf] [minutes]"); return true; }
        string mapname;
        copystring(mapname, args[1]);
        for(char *q = mapname; *q; q++) *q = tolower(*q);
        servermap *sm = validmapname(mapname) ? getservermap(mapname) : NULL;
        if(!sm) { ipriv(sender, "\f3[INTER] The server does not have the map %s.", mapname); return true; }
        int mode = args[2] ? inter_parsemode(args[2]) : (int)gamemode;
        if(mode < 0 || !(sm->modes_allowed & (1 << mode)))
        {
            ipriv(sender, "\f3[INTER] %s can't be played in that mode.", mapname);
            return true;
        }
        int minutes = args[3] ? atoi(args[3]) : 0;
        if(minutes < 0 || minutes > 60) minutes = 0;
        imsg("\f2[INTER] \f5%s changed the map to %s (%s).", c.name, mapname, modestr(mode, true));
        startgame(mapname, mode, minutes, true);
        if(inter.active) { inter.lastgm = sg->gamemillis; defformatstring(why)("Map: %s.", mapname); inter_wait(why); }
        return true;
    }

    if(!strcasecmp(cmd, "time"))
    {
        NEEDADMIN_RUNNING
        int minutes = args[1] ? atoi(args[1]) : 0;
        if(minutes < 1 || minutes > 60) { ipriv(sender, "\f2[INTER] \f5Use: \f0!time <1-60> \f5(minutes left)"); return true; }
        sg->gamelimit = sg->gamemillis + minutes * 60000;
        sg->minremain = minutes;
        sendf(-1, 1, "ri3", SV_TIMEUP, sg->gamemillis, sg->gamelimit);
        imsg("\f2[INTER] \f5%s set the time: %d minute%s left.", c.name, minutes, minutes == 1 ? "" : "s");
        return true;
    }

    if(!strcasecmp(cmd, "teamsize"))
    {
        NEEDADMIN_RUNNING
        int size = args[1] ? atoi(args[1]) : 0;
        if(size < 1 || size > 8) { ipriv(sender, "\f2[INTER] \f5Use: \f0!teamsize <1-8>"); return true; }
        changematchteamsize(size);
        imsg("\f2[INTER] \f5Team size is now %dv%d.", size, size);
        return true;
    }
    if(!strcasecmp(cmd, "private") || !strcasecmp(cmd, "lock"))
    {
        NEEDADMIN
        if(sg->mastermode == MM_MATCH) { ipriv(sender, "\f2[INTER] \f5The server is in match mode (inter): teams are already locked."); return true; }
        changemastermode(MM_PRIVATE);
        imsg("\f2[INTER] \f5%s made the server \f3private\f5: new players can't join (players already here stay). \f0!open \f5opens it again.", c.name);
        return true;
    }

    if(!strcasecmp(cmd, "open") || !strcasecmp(cmd, "unlock"))
    {
        NEEDADMIN_RUNNING
        if(inter.active) { ipriv(sender, "\f2[INTER] \f5Inter mode is on. Use \f0!pub \f5to go back to public."); return true; }
        changemastermode(MM_OPEN);
        imsg("\f2[INTER] \f5%s opened the server \f0(public)\f5.", c.name);
        return true;
    }
    #undef NEEDADMIN_RUNNING
    #undef NEEDADMIN

    ipriv(sender, "\f3[INTER] Unknown command !%s. \f5Type \f0!help\f5.", cmd);
    return true;
}
// ===== fim dos comandos de Inter =====
