
// ===== CubeForge: boas-vindas com estatísticas e rank =====
// Quando o jogador entra, recebe (só ele) uma mensagem com as estatísticas que o próprio
// servidor já guarda em config/servervita.cfg (K, D, K/D, tempo jogado, flags) e a posição
// dele no ranking. O rank usa a mesma conta do painel: pontos por minuto ativo, só quem
// jogou pelo menos 10 minutos.

#define CFW_MINMINUTES 10

static double cfw_skill(const int *vs)
{
    if(vs[VS_MINUTESACTIVE] <= 0) return 0;
    double pos = vs[VS_FRAGS] * 100.0 + vs[VS_DAMAGE] * 2.0 + vs[VS_FLAGS] * 10.0;
    double neg = vs[VS_DEATHS] * 50.0 + vs[VS_FRIENDLYDAMAGE] * 3.0 + vs[VS_ANTIFLAGS] * 15.0 + vs[VS_TKS] * 100.0 + vs[VS_SUICIDES] * 100.0;
    return floor((pos - neg) / vs[VS_MINUTESACTIVE] + 0.5);
}

static void cfwelcome_send(int cn)
{
    if(!valid_client(cn)) return;
    client *cl = clients[cn];
    if(cl->type != ST_TCPIP) return;
    const vita_s *me = cl->vita;
    if(!me || (me->vs[VS_MINUTESACTIVE] <= 0 && me->vs[VS_FRAGS] <= 0 && me->vs[VS_DEATHS] <= 0))
    {
        defformatstring(msg)("\f5[CubeForge] \f2Welcome, \f0%s\f2! First time here - have fun. \f4| \f5Not ranked yet", cl->name);
        sendservmsg(msg, cn);
        return;
    }
    const int *vs = me->vs;
    int rank = 0, total = 0;
    if(vs[VS_MINUTESACTIVE] >= CFW_MINMINUTES)
    {
        double mys = cfw_skill(vs);
        int better = 0;
        enumeratekt(vitas, uchar32, k, vita_s, v,
        {
            if(v.vs[VS_MINUTESACTIVE] < CFW_MINMINUTES) continue;
            total++;
            if(&v == me) continue;
            double s = cfw_skill(v.vs);
            if(s > mys || (s == mys && v.vs[VS_FRAGS] > vs[VS_FRAGS])) better++;
        });
        rank = better + 1;
    }
    double kd = vs[VS_DEATHS] ? (double)vs[VS_FRAGS] / vs[VS_DEATHS] : (double)vs[VS_FRAGS];
    int mins = vs[VS_MINUTESACTIVE];
    string played;
    if(mins >= 60) formatstring(played)("%dh%02d", mins / 60, mins % 60);
    else formatstring(played)("%d min", mins);
    string ranktxt;
    if(rank) formatstring(ranktxt)("\f5Rank #%d of %d", rank, total);
    else formatstring(ranktxt)("\f5Not ranked yet \f4(%d min to go)", CFW_MINMINUTES - mins);
    defformatstring(msg)("\f5[CubeForge] \f2Welcome back, \f0%s \f4| \f0K %d \f3D %d \f2K/D %.2f \f4| \f1%s played \f4| \f3FLAGS %d \f4| %s",
                         cl->name, vs[VS_FRAGS], vs[VS_DEATHS], kd, played, vs[VS_FLAGS], ranktxt);
    sendservmsg(msg, cn);
    mlog(ACLOG_INFO, "[%s] CubeForge welcome sent to %s (rank %d of %d)", cl->hostname, cl->name, rank, total);
}

// A mensagem sai alguns segundos depois da entrada, quando o jogador já carregou o mapa
// (se sair junto com a mensagem do servidor, some no meio das linhas do carregamento).
#define CFW_DELAY 4000
static int cfw_due[MAXCLIENTS], cfw_seq[MAXCLIENTS];

static void cfwelcome(int cn)
{
    if(!valid_client(cn) || cn >= MAXCLIENTS) return;
    cfw_due[cn] = servmillis + CFW_DELAY;
    if(!cfw_due[cn]) cfw_due[cn] = 1;
    cfw_seq[cn] = clients[cn]->clientsequence;
    mlog(ACLOG_INFO, "[%s] CubeForge welcome scheduled for %s", clients[cn]->hostname, clients[cn]->name);
}

static void cfwelcome_tick()
{
    loopi(MAXCLIENTS)
    {
        if(!cfw_due[i] || servmillis - cfw_due[i] < 0) continue;
        cfw_due[i] = 0;
        if(valid_client(i) && clients[i]->clientsequence == cfw_seq[i] && clients[i]->isauthed) cfwelcome_send(i);
    }
}
// ===== fim das boas-vindas =====
