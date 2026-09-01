import Link from "next/link";
import type { ForecastFixture } from "@/lib/contracts";
import {
  fixtureTitle,
  formatDecimal,
  formatKickoff,
  formatProbability,
} from "@/lib/format";
import { ProbabilityBar, SectionHeading, TeamMark } from "@/components/ui";

export function OutcomeBand({ fixture }: { fixture: ForecastFixture }) {
  if (!fixture.forecast) return null;
  const { homeWin, draw, awayWin } = fixture.forecast;
  return (
    <div
      className="outcome-band"
      role="img"
      aria-label={`Home win ${formatProbability(homeWin)}, draw ${formatProbability(draw)}, away win ${formatProbability(awayWin)}`}
    >
      <span className="outcome-home" style={{ width: `${Math.max(0, homeWin) * 100}%` }} />
      <span className="outcome-draw" style={{ width: `${Math.max(0, draw) * 100}%` }} />
      <span className="outcome-away" style={{ width: `${Math.max(0, awayWin) * 100}%` }} />
    </div>
  );
}

function TeamSlot({ fixture, side }: { fixture: ForecastFixture; side: "home" | "away" }) {
  const team = side === "home" ? fixture.homeTeam : fixture.awayTeam;
  const source = side === "home" ? fixture.homeSource : fixture.awaySource;
  return (
    <div className={`fixture-team fixture-team-${side}`}>
      {team ? <TeamMark team={team} size="small" /> : <span className="team-mark team-mark-small">TBD</span>}
      <span>{team?.name ?? source ?? "To be decided"}</span>
    </div>
  );
}

export function FixtureCard({
  fixture,
  href,
}: {
  fixture: ForecastFixture;
  href: string;
}) {
  return (
    <article className="fixture-card">
      <div className="fixture-card-meta">
        <span>{fixture.round ?? fixture.stage}</span>
        <time dateTime={fixture.kickoff ?? undefined}>{formatKickoff(fixture.kickoff)}</time>
      </div>
      <div className="fixture-matchup">
        <TeamSlot fixture={fixture} side="home" />
        <div className="fixture-score">
          {fixture.score ? <strong>{fixture.score.home}–{fixture.score.away}</strong> : <span>vs</span>}
        </div>
        <TeamSlot fixture={fixture} side="away" />
      </div>
      {fixture.forecast ? (
        <div className="fixture-forecast">
          <OutcomeBand fixture={fixture} />
          <div className="fixture-odds" aria-label="Match outcome probabilities">
            <span>Home <b>{formatProbability(fixture.forecast.homeWin)}</b></span>
            <span>Draw <b>{formatProbability(fixture.forecast.draw)}</b></span>
            <span>Away <b>{formatProbability(fixture.forecast.awayWin)}</b></span>
          </div>
        </div>
      ) : (
        <p className="fixture-no-forecast">Match forecast not included in this artifact.</p>
      )}
      <Link className="fixture-link" href={href} aria-label={`Open breakdown for ${fixtureTitle(fixture)}`}>
        Match breakdown <span aria-hidden="true">→</span>
      </Link>
    </article>
  );
}

export function MatchBreakdownPanel({ fixture }: { fixture: ForecastFixture }) {
  const forecast = fixture.forecast;

  return (
    <>
      <section className="match-hero">
        <div className="match-stage">
          <span>{fixture.round ?? fixture.stage}</span>
          <time dateTime={fixture.kickoff ?? undefined}>{formatKickoff(fixture.kickoff)}</time>
          {fixture.venue ? <span>{fixture.venue}</span> : null}
        </div>
        <div className="match-teams">
          <div>
            {fixture.homeTeam ? <TeamMark team={fixture.homeTeam} size="large" /> : <span className="team-mark team-mark-large">TBD</span>}
            <h1>{fixture.homeTeam?.name ?? fixture.homeSource ?? "To be decided"}</h1>
            {forecast ? <strong>{formatProbability(forecast.homeWin)}</strong> : null}
            {forecast ? <small>win probability</small> : null}
          </div>
          <span className="match-versus">{fixture.score ? `${fixture.score.home}–${fixture.score.away}` : "v"}</span>
          <div>
            {fixture.awayTeam ? <TeamMark team={fixture.awayTeam} size="large" /> : <span className="team-mark team-mark-large">TBD</span>}
            <h1>{fixture.awayTeam?.name ?? fixture.awaySource ?? "To be decided"}</h1>
            {forecast ? <strong>{formatProbability(forecast.awayWin)}</strong> : null}
            {forecast ? <small>win probability</small> : null}
          </div>
        </div>
        {forecast ? (
          <div className="match-outcome-summary">
            <span>Home <b>{formatProbability(forecast.homeWin)}</b></span>
            <span>Draw <b>{formatProbability(forecast.draw)}</b></span>
            <span>Away <b>{formatProbability(forecast.awayWin)}</b></span>
            <OutcomeBand fixture={fixture} />
          </div>
        ) : null}
      </section>

      {!forecast ? (
        <section className="inline-empty">
          <h2>No match forecast published</h2>
          <p>The fixture is part of the schedule, but its probability distribution is absent from this artifact.</p>
        </section>
      ) : (
        <>
          <section className="match-grid content-section-compact">
            <article className="panel expected-goals-panel">
              <p className="eyebrow">Goal expectation</p>
              <h2>Expected goals</h2>
              <div className="xg-matchup">
                <div><strong>{formatDecimal(forecast.expectedHomeGoals, 2)}</strong><span>{fixture.homeTeam?.shortName ?? "Home"}</span></div>
                <i aria-hidden="true" />
                <div><strong>{formatDecimal(forecast.expectedAwayGoals, 2)}</strong><span>{fixture.awayTeam?.shortName ?? "Away"}</span></div>
              </div>
              <p className="panel-note">Model expectation, not a score prediction.</p>
            </article>
            <article className="panel market-panel">
              <p className="eyebrow">Derived outcomes</p>
              <h2>Match profile</h2>
              <ProbabilityBar label="Over 2.5 goals" value={forecast.over25} tone="orange" />
              <ProbabilityBar label="Both teams score" value={forecast.bothTeamsScore} tone="blue" />
              <ProbabilityBar label="Home clean sheet" value={forecast.homeCleanSheet} tone="lime" />
              <ProbabilityBar label="Away clean sheet" value={forecast.awayCleanSheet} tone="muted" />
            </article>
          </section>

          <section className="content-section-compact">
            <SectionHeading kicker="Score matrix" title="Most likely scorelines" />
            {forecast.topScorelines.length ? (
              <div className="scoreline-grid">
                {forecast.topScorelines.slice(0, 5).map((scoreline, index) => (
                  <div className="scoreline-card" key={`${scoreline.home}-${scoreline.away}-${index}`}>
                    <span>#{index + 1}</span>
                    <strong>{scoreline.home}–{scoreline.away}</strong>
                    <b>{formatProbability(scoreline.probability)}</b>
                  </div>
                ))}
              </div>
            ) : <p className="inline-note">Scoreline probabilities were not exported.</p>}
          </section>

          {forecast.modelProbabilities?.length ? (
            <section className="content-section-compact">
              <SectionHeading kicker="Model room" title="Engine comparison" />
              <div className="model-table-wrap">
                <table className="data-table model-table">
                  <thead><tr><th>Engine</th><th>Home</th><th>Draw</th><th>Away</th></tr></thead>
                  <tbody>
                    {forecast.modelProbabilities.map((row) => (
                      <tr key={row.model}>
                        <th scope="row">{row.model}</th>
                        <td>{formatProbability(row.homeWin)}</td>
                        <td>{formatProbability(row.draw)}</td>
                        <td>{formatProbability(row.awayWin)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          {forecast.seasonImpact?.length ? (
            <section className="content-section-compact">
              <SectionHeading kicker="Scenario lens" title="Season impact by result" />
              <div className="impact-grid">
                {forecast.seasonImpact.map((impact) => (
                  <article key={impact.outcome}>
                    <span>{impact.outcome === "home" ? "1" : impact.outcome === "draw" ? "X" : "2"}</span>
                    <h3>{impact.label}</h3>
                    <p>Home change <b>{impact.homeDelta === null ? "—" : `${impact.homeDelta >= 0 ? "+" : ""}${Math.round(impact.homeDelta * 100)} pp`}</b></p>
                    <p>Away change <b>{impact.awayDelta === null ? "—" : `${impact.awayDelta >= 0 ? "+" : ""}${Math.round(impact.awayDelta * 100)} pp`}</b></p>
                  </article>
                ))}
              </div>
            </section>
          ) : null}
        </>
      )}
    </>
  );
}
