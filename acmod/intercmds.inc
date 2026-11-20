// ===== CubeForge: comandos de Inter (!inter, !ready, !go, pausa automática...) =====
// Admins controlam a partida; !ready, !notready, !status e !help são para todos.

extern const char *modeacronymnames[];

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
        imsg("\f3[INTER] %s left the match. Game paused. \f5When they are back (or replaced), an admin types \f0!go\f5.", c.name);
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
    ipriv(cn, "\f2[INTER] \f5Admins: \f0!inter [teamsize] \f5start inter, \f0!pub \f5back to public, \f0!go \f5start/resume, \f0!pause");
    ipriv(cn, "\f2[INTER] \f5Admins: \f0!shuffle\f5, \f0!map <name> [ctf|tdm|tosok|...] [minutes]\f5, \f0!time <minutes>\f5, \f0!teamsize <n>");
}

// devolve true se a mensagem era um comando (não vai para o chat)
static bool intercommand(int sender, const char *text)
{
    if(text[0] != '!' || !valid_client(sender)) return false;
    client &c = *clients[sender];
    string buf;
    copystring(buf, text + 1);
    char *args[4] = { NULL, NULL, NULL, NULL };
    int n = 0;
    for(char *t = strtok(buf, " "); t && n < 4; t = strtok(NULL, " ")) args[n++] = t;
    if(!n) return false;
    const char *cmd = args[0];
    bool admin = c.role == CR_ADMIN;
    #define NEEDADMIN if(!admin) { ipriv(sender, "\f3[INTER] Only admins can use !%s.", cmd); return true; }
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
        NEEDADMIN
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
        defformatstring(why)("INTER MODE ON: %dv%d %s on %s. Teams are locked.", size, size, modestr(mode, true), mapname);
        inter_wait(why);
        return true;
    }

    if(!strcasecmp(cmd, "pub") || !strcasecmp(cmd, "public"))
    {
        NEEDADMIN
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
        imsg("\f2[INTER] \f5Game paused by %s. An admin types \f0!go \f5to resume.", c.name);
        return true;
    }

    if(!strcasecmp(cmd, "shuffle"))
    {
        NEEDADMIN
        if(!m_teammode) { ipriv(sender, "\f3[INTER] This is not a team mode."); return true; }
        shuffleteams(FTR_SILENTFORCE);
        if(inter.active && inter.waiting) inter_clearready();
        imsg("\f2[INTER] \f5Teams shuffled by %s.%s", c.name, inter.active && inter.waiting ? " Type \f0!ready \f5again." : "");
        return true;
    }

    if(!strcasecmp(cmd, "map"))
    {
        NEEDADMIN
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
        NEEDADMIN
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
        NEEDADMIN
        int size = args[1] ? atoi(args[1]) : 0;
        if(size < 1 || size > 8) { ipriv(sender, "\f2[INTER] \f5Use: \f0!teamsize <1-8>"); return true; }
        changematchteamsize(size);
        imsg("\f2[INTER] \f5Team size is now %dv%d.", size, size);
        return true;
    }
    #undef NEEDADMIN

    ipriv(sender, "\f3[INTER] Unknown command !%s. \f5Type \f0!help\f5.", cmd);
    return true;
}
// ===== fim dos comandos de Inter =====
