"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useTournamentArtifact } from "@/lib/data";
import { formatProbability } from "@/lib/format";
import type { TournamentForecastArtifact } from "@/lib/contracts";
import {
  CompetitionMasthead,
  CoverageNote,
  DataNotice,
  PageState,
  SectionHeading,
  TeamMark,
} from "@/components/ui";
import { FixtureCard, MatchBreakdownPanel } from "@/components/forecast-components";

function WorldCupShell({
  children,
}: {
  children: (artifact: TournamentForecastArtifact) => ReactNode;
}) {
  const state = useTournamentArtifact("world-cup-2026");

  if (state.phase === "loading") {
    return <main className="shell main-content"><PageState kind="loading" title="Loading World Cup forecast" message="Reading team, group and knockout-path artifacts." /></main>;
  }
  if (state.phase !== "ready" || !state.artifact) {
    return (
      <main className="shell main-content">
        <PageState
          kind={state.phase === "error" ? "error" : "empty"}
          title={state.phase === "error" ? "Tournament artifact unavailable" : "Tournament forecast not published"}
          message={state.message ?? "There is no World Cup artifact to display yet."}
        />
      </main>
    );
  }

  const artifact = state.artifact;
  return (
    <main className="shell main-content">
      <CompetitionMasthead
        parentLabel="Tournaments"
        parentHref="/"
        title={artifact.competition.name}
        subtitle={`${artifact.edition} · ${artifact.model.name} ${artifact.model.version}`}
        status={artifact.status}
        generatedAt={artifact.generatedAt}
        nav={[
          { label: "Overview", href: "/world-cup" },
          { label: "Groups", href: "/world-cup/groups" },
          { label: "Bracket", href: "/world-cup/bracket" },
          { label: "Methodology", href: "/methodology" },
        ]}
      />
      <DataNotice isDemo={artifact.isDemo} disclaimer={artifact.disclaimer} />
      {children(artifact)}
    </main>
  );
}

function TeamProbabilityTable({ artifact }: { artifact: TournamentForecastArtifact }) {
  const rows = [...artifact.teams].sort(
    (a, b) => (b.probabilities.champion ?? -1) - (a.probabilities.champion ?? -1),
  );
  return (
    <div className="table-shell">
      <table className="data-table tournament-table">
        <thead>
          <tr>
            <th>#</th><th>Team</th><th>Group</th><th>Advance</th><th>Round of 16</th><th>Quarter-final</th><th>Semi-final</th><th>Final</th><th>Champion</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.team.id}>
              <td className="position-cell">{index + 1}</td>
              <th scope="row"><span className="table-team"><TeamMark team={row.team} size="small" />{row.team.name}</span></th>
              <td>{row.group}</td>
              <td>{formatProbability(row.probabilities.advanceGroup)}</td>
              <td>{formatProbability(row.probabilities.roundOf16)}</td>
              <td>{formatProbability(row.probabilities.quarterfinal)}</td>
              <td>{formatProbability(row.probabilities.semifinal)}</td>
              <td>{formatProbability(row.probabilities.final)}</td>
              <td><strong>{formatProbability(row.probabilities.champion)}</strong></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GroupCard({
  artifact,
  groupId,
}: {
  artifact: TournamentForecastArtifact;
  groupId: string;
}) {
  const group = artifact.groups.find((item) => item.id === groupId);
  if (!group) return null;
  const teams = group.teamIds
    .map((teamId) => artifact.teams.find((team) => team.team.id === teamId))
    .filter((team): team is NonNullable<typeof team> => Boolean(team));

  return (
    <article className="group-card">
      <header><span>Group</span><strong>{group.label}</strong></header>
      <div className="group-card-heading"><span>Team</span><span>Advance</span></div>
      {teams.map((team) => (
        <div className="group-team" key={team.team.id}>
          <TeamMark team={team.team} size="small" />
          <span>{team.team.name}</span>
          <strong>{formatProbability(team.probabilities.advanceGroup)}</strong>
        </div>
      ))}
      {!teams.length ? <p className="inline-note">No team projections included.</p> : null}
      <Link className="fixture-link" href={`/world-cup/groups#group-${group.id}`}>Group fixtures <span aria-hidden="true">→</span></Link>
    </article>
  );
}

export function WorldCupOverview() {
  return (
    <WorldCupShell>
      {(artifact) => {
        const contenders = [...artifact.teams]
          .sort((a, b) => (b.probabilities.champion ?? -1) - (a.probabilities.champion ?? -1))
          .slice(0, 5);
        const fixtures = artifact.fixtures.filter((item) => item.status === "scheduled").slice(0, 3);

        return (
          <>
            <section className="tournament-summary">
              <div className="tournament-summary-copy">
                <p className="eyebrow eyebrow-light">Tournament path</p>
                <h2>From 48 teams to one.</h2>
                <p>Group advancement and knockout-stage probabilities update from the same tournament simulation.</p>
                <div className="tournament-facts">
                  <span><b>{artifact.coverage.teamsIncluded}</b> teams in artifact</span>
                  <span><b>{artifact.coverage.groupsIncluded}</b> groups in artifact</span>
                  <span><b>{artifact.model.simulations?.toLocaleString() ?? "—"}</b> simulations</span>
                </div>
              </div>
              <div className="contender-board">
                <div className="contender-head"><span>Rank</span><span>Champion probability</span></div>
                {contenders.map((team, index) => (
                  <div className="contender-row" key={team.team.id}>
                    <span>0{index + 1}</span>
                    <TeamMark team={team.team} size="small" />
                    <strong>{team.team.name}</strong>
                    <b>{formatProbability(team.probabilities.champion)}</b>
                  </div>
                ))}
                {!contenders.length ? <p>No team probabilities exported.</p> : null}
              </div>
            </section>

            <section className="content-section">
              <SectionHeading
                kicker="Group stage"
                title="Advancement picture"
                action={<Link className="text-link" href="/world-cup/groups">All groups <span aria-hidden="true">→</span></Link>}
              />
              <CoverageNote included={artifact.coverage.groupsIncluded} expected={artifact.coverage.groupsExpected} noun="groups" />
              <div className="group-grid">
                {artifact.groups.slice(0, 3).map((group) => <GroupCard artifact={artifact} groupId={group.id} key={group.id} />)}
              </div>
              {!artifact.groups.length ? <div className="inline-empty"><h3>No groups exported</h3><p>The group collection is empty.</p></div> : null}
            </section>

            <section className="content-section">
              <SectionHeading kicker="All teams" title="Tournament probabilities" />
              <CoverageNote included={artifact.coverage.teamsIncluded} expected={artifact.coverage.teamsExpected} noun="teams" />
              {artifact.teams.length ? <TeamProbabilityTable artifact={artifact} /> : <div className="inline-empty"><h3>No team paths exported</h3><p>Advancement probabilities are not available.</p></div>}
            </section>

            <section className="content-section">
              <SectionHeading
                kicker="Match centre"
                title="Upcoming fixtures"
                action={<Link className="text-link" href="/world-cup/bracket">View bracket <span aria-hidden="true">→</span></Link>}
              />
              {fixtures.length ? (
                <div className="fixture-grid">
                  {fixtures.map((fixture) => <FixtureCard fixture={fixture} href={`/world-cup/matches/${encodeURIComponent(fixture.id)}`} key={fixture.id} />)}
                </div>
              ) : <div className="inline-empty"><h3>No scheduled fixtures</h3><p>The current artifact does not include upcoming matches.</p></div>}
            </section>
          </>
        );
      }}
    </WorldCupShell>
  );
}

export function WorldCupGroups() {
  return (
    <WorldCupShell>
      {(artifact) => (
        <section className="content-section fixture-page-section">
          <SectionHeading kicker={`${artifact.groups.length} groups in artifact`} title="Groups & fixtures" />
          <CoverageNote included={artifact.coverage.groupsIncluded} expected={artifact.coverage.groupsExpected} noun="groups" />
          {artifact.groups.map((group) => {
            const fixtures = group.fixtureIds
              .map((fixtureId) => artifact.fixtures.find((fixture) => fixture.id === fixtureId))
              .filter((fixture): fixture is NonNullable<typeof fixture> => Boolean(fixture));
            return (
              <section className="group-section" id={`group-${group.id}`} key={group.id}>
                <SectionHeading kicker="Group" title={group.label} />
                <div className="group-detail-grid">
                  <GroupCard artifact={artifact} groupId={group.id} />
                  <div className="group-fixtures">
                    {fixtures.map((fixture) => (
                      <FixtureCard fixture={fixture} href={`/world-cup/matches/${encodeURIComponent(fixture.id)}`} key={fixture.id} />
                    ))}
                    {!fixtures.length ? <div className="inline-empty"><h3>No group fixtures</h3><p>Fixture IDs are not resolved in this artifact.</p></div> : null}
                  </div>
                </div>
              </section>
            );
          })}
          {!artifact.groups.length ? <div className="inline-empty"><h2>No group data exported</h2><p>Check again after a tournament refresh.</p></div> : null}
        </section>
      )}
    </WorldCupShell>
  );
}

export function WorldCupBracket() {
  return (
    <WorldCupShell>
      {(artifact) => (
        <section className="content-section fixture-page-section">
          <SectionHeading kicker="Knockout progression" title="Tournament bracket" />
          <p className="section-intro">Slots remain labeled by qualification source until a team is known in the artifact.</p>
          {artifact.bracket.length ? (
            <div className="bracket-scroll" tabIndex={0} aria-label="Scrollable knockout bracket">
              <div className="bracket">
                {artifact.bracket.map((round) => (
                  <section className="bracket-round" key={round.id}>
                    <header><span>{round.matches.length} matches</span><h2>{round.label}</h2></header>
                    <div className="bracket-matches">
                      {round.matches.map((match) => {
                        const fixture = artifact.fixtures.find((item) => item.id === match.fixtureId);
                        return (
                          <article className="bracket-match" key={match.fixtureId}>
                            <div><span>{fixture?.homeTeam?.name ?? match.homeSource}</span><b>{fixture?.score?.home ?? "—"}</b></div>
                            <div><span>{fixture?.awayTeam?.name ?? match.awaySource}</span><b>{fixture?.score?.away ?? "—"}</b></div>
                            {fixture ? <Link href={`/world-cup/matches/${encodeURIComponent(fixture.id)}`} aria-label={`Open ${fixture.id} breakdown`}>Open match <span aria-hidden="true">→</span></Link> : null}
                          </article>
                        );
                      })}
                    </div>
                  </section>
                ))}
              </div>
            </div>
          ) : <div className="inline-empty"><h2>No bracket exported</h2><p>The tournament artifact does not yet define knockout slots.</p></div>}
        </section>
      )}
    </WorldCupShell>
  );
}

export function WorldCupMatch({ matchId }: { matchId: string }) {
  return (
    <WorldCupShell>
      {(artifact) => {
        const fixture = artifact.fixtures.find((item) => item.id === decodeURIComponent(matchId));
        if (!fixture) {
          return (
            <section className="inline-empty inline-empty-large">
              <h1>Match not found</h1>
              <p>This match ID is not present in the current tournament artifact.</p>
              <Link className="button button-dark" href="/world-cup/groups">View current fixtures</Link>
            </section>
          );
        }
        return <MatchBreakdownPanel fixture={fixture} />;
      }}
    </WorldCupShell>
  );
}
