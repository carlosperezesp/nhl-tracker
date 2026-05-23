// screens-current.jsx — Temporada Actual screen + Playoff bracket

function getPlayoffTeams(teams) {
  const playoff = new Set();
  for (const conf of ["E", "W"]) {
    const confTeams = [...teams]
      .filter(t => t.conf === conf)
      .sort((a, b) => b.pts - a.pts || b.gd - a.gd);
    const divs = [...new Set(confTeams.map(t => t.div))];
    const divIn = new Set();
    for (const div of divs) {
      confTeams.filter(t => t.div === div).slice(0, 3).forEach(t => { playoff.add(t.code); divIn.add(t.code); });
    }
    confTeams.filter(t => !divIn.has(t.code)).slice(0, 2).forEach(t => playoff.add(t.code));
  }
  return playoff;
}

function StandingsConf({ teams, label, playoffSet, onTeamClick }) {
  const sorted = [...teams].sort((a, b) => b.pts - a.pts || b.gd - a.gd);
  return (
    <div className="standings-conf">
      <div className="standings-conf__label mono mono--muted">{label}</div>
      <table className="table table--dense">
        <thead>
          <tr>
            <th className="table__th" style={{ width: 28 }}>#</th>
            <th className="table__th">Team</th>
            <th className="table__th table__th--num" style={{ width: 80 }}>W–L–OT</th>
            <th className="table__th table__th--num" style={{ width: 44 }}>PTS</th>
            <th className="table__th table__th--num" style={{ width: 104 }}>Score</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((team, i) => (
            <React.Fragment key={team.code}>
              {i === 8 && (
                <tr className="standings__cutoff">
                  <td colSpan={5}>── Playoff line ──</td>
                </tr>
              )}
              <tr
                className={`table__row ${!playoffSet.has(team.code) ? "table__row--out" : ""}`}
                onClick={() => onTeamClick(team)}
              >
                <td className="table__td"><span className="mono mono--muted">{String(i + 1).padStart(2, "0")}</span></td>
                <td className="table__td">
                  <span className="team-cell">
                    <TeamSwatch colors={team.colors} code={team.code} />
                    <span className="team-cell__city">{team.shortName}</span>
                  </span>
                </td>
                <td className="table__td table__td--num"><span className="mono">{team.w}–{team.l}–{team.ot}</span></td>
                <td className="table__td table__td--num"><span className="mono mono--bold">{team.pts}</span></td>
                <td className="table__td table__td--num"><ScoreBar value={team.score} width={52} /></td>
              </tr>
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StandingsDivisions({ teams, playoffSet, onTeamClick }) {
  const DIV_ORDER = ["Atlantic", "Metro", "Central", "Pacific"];
  const byDiv = {};
  teams.forEach(t => { byDiv[t.div] = byDiv[t.div] || []; byDiv[t.div].push(t); });
  Object.keys(byDiv).forEach(d => byDiv[d].sort((a, b) => b.pts - a.pts || b.gd - a.gd));

  return (
    <div className="standings-divs">
      {DIV_ORDER.filter(d => byDiv[d]).map(name => (
        <div key={name} className="standings-div">
          <div className="standings-div__label mono mono--muted">{name} division</div>
          <table className="table table--dense">
            <thead>
              <tr>
                <th className="table__th" style={{ width: 28 }}>#</th>
                <th className="table__th">Team</th>
                <th className="table__th table__th--num" style={{ width: 80 }}>W–L–OT</th>
                <th className="table__th table__th--num" style={{ width: 44 }}>PTS</th>
                <th className="table__th table__th--num" style={{ width: 104 }}>Score</th>
              </tr>
            </thead>
            <tbody>
              {byDiv[name].map((team, i) => {
                const inPlayoff = playoffSet.has(team.code);
                const isWC = inPlayoff && i >= 3;
                return (
                  <React.Fragment key={team.code}>
                    {i === 3 && (
                      <tr className="standings__cutoff">
                        <td colSpan={5}>── Division line ──</td>
                      </tr>
                    )}
                    <tr
                      className={`table__row ${!inPlayoff ? "table__row--out" : ""}`}
                      onClick={() => onTeamClick(team)}
                    >
                      <td className="table__td"><span className="mono mono--muted">{String(i + 1).padStart(2, "0")}</span></td>
                      <td className="table__td">
                        <span className="team-cell">
                          <TeamSwatch colors={team.colors} code={team.code} />
                          <span className="team-cell__city">
                            {team.shortName}
                            {isWC && <span className="wc-badge">WC</span>}
                          </span>
                        </span>
                      </td>
                      <td className="table__td table__td--num"><span className="mono">{team.w}–{team.l}–{team.ot}</span></td>
                      <td className="table__td table__td--num"><span className="mono mono--bold">{team.pts}</span></td>
                      <td className="table__td table__td--num"><ScoreBar value={team.score} width={52} /></td>
                    </tr>
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

function CurrentSeason({ onTeamClick, onPlayerClick, onOpenMethodology }) {
  const { TEAMS, PLAYERS, BRACKET } = window.NHL_DATA;
  const [viewMode, setViewMode] = useState("both");
  const [posFilter, setPosFilter] = useState("ALL");

  const playoffSet = useMemo(() => getPlayoffTeams(TEAMS), [TEAMS]);

  // Top players: filter by position
  const topPlayers = useMemo(() => {
    const filtered = posFilter === "ALL"
      ? PLAYERS
      : posFilter === "W"
        ? PLAYERS.filter(p => p.pos === "LW" || p.pos === "RW")
        : PLAYERS.filter(p => p.pos === posFilter);
    return [...filtered].sort((a, b) => b.score - a.score);
  }, [PLAYERS, posFilter]);


  const playerCols = [
    {
      key: "rank", label: "#", w: 28, numeric: true, sortable: false,
      render: (_r, i) => <span className="mono mono--muted">{String(i + 1).padStart(2, "0")}</span>,
    },
    {
      key: "name", label: "Player", w: "auto",
      render: r => (
        <span className="player-cell">
          <span className="player-line">
            <TeamSwatch colors={r.colors} code={r.teamCode} />
            <span className="player-cell__name">{r.name}</span>
          </span>
          <span className="player-cell__meta">{r.teamCode}{r.country ? ` · ${r.country}` : ""}{r.age ? ` · age ${r.age}` : ""}</span>
        </span>
      ),
    },
    {
      key: "pos", label: "Pos", w: 52, sortable: false,
      render: r => <PosBadge pos={r.pos} />,
    },
    {
      key: "stat", label: "Headline stat", w: 120, sortable: false,
      render: r => r.pos === "G"
        ? <span className="mono mono--muted">{r.stats.svpct.toFixed(3)} SV%</span>
        : <span className="mono mono--muted">{r.stats.p} P · {r.stats.g} G</span>,
    },
    {
      key: "traj", label: "5-yr", w: 70, sortable: false,
      render: r => <Sparkline values={r.trajectory} width={56} height={16} />,
    },
    {
      key: "score", label: "Score", numeric: true, w: 124,
      render: r => <ScoreBar value={r.score} width={56} />,
    },
  ];

  return (
    <div className="screen screen--current">
      <SectionHead
        kicker="Screen 01 / Temporada actual"
        title="2025–26 season at a glance"
        sub="Real NHL standings, playoff bracket, and top performers ranked by a transparent position-adjusted tracker score."
        right={
          <button className="link-button" onClick={onOpenMethodology}>
            How is the score calculated? →
          </button>
        }
      />

      {/* ───── Playoff bracket ───── */}
      <section className="block">
        <div className="block__head">
          <WFLabel>PLAYOFF BRACKET — live from NHL</WFLabel>
          <span className="block__head-meta">First-to-4 series · best-of-7</span>
        </div>
        <Bracket bracket={BRACKET} onTeamClick={onTeamClick} />
      </section>

      {/* ───── Standings ───── */}
      <section className="block">
        <div className="block__head">
          <WFLabel>STANDINGS</WFLabel>
          <div className="seg">
            <button className={`seg__btn ${viewMode === "both" ? "seg__btn--on" : ""}`} onClick={() => setViewMode("both")}>Both</button>
            <button className={`seg__btn ${viewMode === "divisions" ? "seg__btn--on" : ""}`} onClick={() => setViewMode("divisions")}>Divisions</button>
          </div>
        </div>

        <div className="block__body block__body--rel">
          {viewMode === "both" ? (
            <div className="standings-split">
              <StandingsConf
                teams={TEAMS.filter(t => t.conf === "E")}
                label="Eastern Conference"
                playoffSet={playoffSet}
                onTeamClick={onTeamClick}
              />
              <StandingsConf
                teams={TEAMS.filter(t => t.conf === "W")}
                label="Western Conference"
                playoffSet={playoffSet}
                onTeamClick={onTeamClick}
              />
            </div>
          ) : (
            <StandingsDivisions
              teams={TEAMS}
              playoffSet={playoffSet}
              onTeamClick={onTeamClick}
            />
          )}
          <MarginNote side="right">
            Click a row → team detail<br />with full roster.
          </MarginNote>
        </div>
      </section>

      {/* ───── Top 10 players ───── */}
      <section className="block">
        <div className="block__head">
          <WFLabel>TOP PERFORMERS — position-adjusted</WFLabel>
          <div className="seg">
            {["ALL", "C", "W", "D", "G"].map(p => (
              <button
                key={p}
                className={`seg__btn ${posFilter === p ? "seg__btn--on" : ""}`}
                onClick={() => setPosFilter(p)}
              >
                {p === "ALL" ? "All" : p === "W" ? "Wingers" : p === "C" ? "Centers" : p === "D" ? "Defense" : "Goalies"}
              </button>
            ))}
          </div>
        </div>

        <div className="block__body block__body--rel">
          <div className="scroll-region" style={{ maxHeight: 440 }}>
            <SortableTable
              columns={playerCols}
              rows={topPlayers.slice(0, 80)}
              defaultSort={{ key: "score", dir: "desc" }}
              rowKey={r => r.id}
              onRowClick={onPlayerClick}
            />
          </div>
          <MarginNote side="right">
            Top 10 by default, scroll for more.<br />Score normalized within position.
          </MarginNote>
        </div>
      </section>
    </div>
  );
}

// ───────────────────────── Bracket ─────────────────────────
function Bracket({ bracket, onTeamClick }) {
  const { TEAMS } = window.NHL_DATA;
  const teamByCode = Object.fromEntries(TEAMS.map(t => [t.code, t]));

  function Match({ m, round }) {
    const hi = m.hi ? teamByCode[m.hi] : null;
    const lo = m.lo ? teamByCode[m.lo] : null;
    const [hiW, loW] = m.seriesScore.includes("-")
      ? m.seriesScore.split("-").map(n => parseInt(n, 10))
      : [null, null];

    function Row({ team, wins, isWinner, isLoser }) {
      if (!team) return (
        <div className="match__row match__row--empty">
          <span className="match__code">—</span>
          <span className="match__city">TBD</span>
          <span className="match__wins">·</span>
        </div>
      );
      return (
        <div
          className={`match__row ${isWinner ? "match__row--winner" : ""} ${isLoser ? "match__row--loser" : ""}`}
          style={{ "--team-color": team.colors?.primary || "#666" }}
          onClick={() => onTeamClick(team)}
          role="button"
          tabIndex={0}
        >
          <span className="match__code">
            <span className="match__swatch" style={{ background: team.colors?.primary || "#666" }}>
              <img src={`https://assets.nhle.com/logos/nhl/svg/${team.code}_dark.svg`} alt="" onError={e => { e.target.style.display = "none"; }} />
            </span>
          </span>
          <span className="match__city">{team.shortName || team.city}</span>
          <span className="match__wins">{wins ?? "·"}</span>
        </div>
      );
    }

    const decided = !!m.winner;
    const hasTeams = !!(hi || lo);

    return (
      <div className={`match ${decided ? "match--decided" : hasTeams ? "match--live" : ""}`}>
        <Row team={hi} wins={hiW} isWinner={decided && m.winner === m.hi} isLoser={decided && m.winner !== m.hi} />
        <Row team={lo} wins={loW} isWinner={decided && m.winner === m.lo} isLoser={decided && m.winner !== m.lo} />
        {!decided && hasTeams && <div className="match__live">SERIES LIVE · {m.seriesScore}</div>}
      </div>
    );
  }

  return (
    <div className="bracket">
      <div className="bracket__conf bracket__conf--east">
        <div className="bracket__conf-label">Eastern conference</div>
        <div className="bracket__rounds">
          <BracketRound label="Round 1" matches={bracket.east.r1} render={m => <Match m={m} round="r1" />} />
          <BracketRound label="Conf. semis" matches={bracket.east.r2} render={m => <Match m={m} round="r2" />} />
          <BracketRound label="Conf. final" matches={bracket.east.conf} render={m => <Match m={m} round="conf" />} />
        </div>
      </div>

      <div className="bracket__center">
        <div className="bracket__final">
          <div className="bracket__final-label">Stanley Cup Final</div>
          <Match m={bracket.final?.[0] || { hi: null, lo: null, winner: null, seriesScore: "-" }} round="final" />
        </div>
      </div>

      <div className="bracket__conf bracket__conf--west">
        <div className="bracket__conf-label">Western conference</div>
        <div className="bracket__rounds bracket__rounds--reverse">
          <BracketRound label="Conf. final" matches={bracket.west.conf} render={m => <Match m={m} round="conf" />} />
          <BracketRound label="Conf. semis" matches={bracket.west.r2} render={m => <Match m={m} round="r2" />} />
          <BracketRound label="Round 1" matches={bracket.west.r1} render={m => <Match m={m} round="r1" />} />
        </div>
      </div>
    </div>
  );
}

function BracketRound({ label, matches, render }) {
  return (
    <div className="bracket-round" data-count={matches.length}>
      <div className="bracket-round__label">{label}</div>
      <div className="bracket-round__matches">
        {matches.map((m, i) => <div key={i} className="bracket-round__match-wrap">{render(m)}</div>)}
      </div>
    </div>
  );
}

Object.assign(window, { CurrentSeason });
