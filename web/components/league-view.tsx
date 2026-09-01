"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useLeagueArtifact } from "@/lib/data";
import {
  formatDecimal,
  formatProbability,
} from "@/lib/format";
import {
  CompetitionMasthead,
  CoverageNote,
  DataNotice,
  PageState,
  ProbabilityBar,
  SectionHeading,
  TeamMark,
} from "@/components/ui";
import { FixtureCard, MatchBreakdownPanel } from "@/components/forecast-components";

function stateView(
  phase: "loading" | "ready" | "unavailable" | "error",
  message: string | null,
) {
  if (phase === "ready") return null;
  if (phase === "loading") {
    return <PageState kind="loading" title="Loading league forecast" message="Reading the latest table and fixture artifact." />;
  }
  return (
    <PageState
      kind={phase === "error" ? "error" : "empty"}
      title={phase === "error" ? "League artifact unavailable" : "League forecast not published"}
      message={message ?? "There is no forecast data for this league yet."}
    />
  );
}

function LeagueTable({ artifact }: { artifact: NonNullable<ReturnType<typeof useLeagueArtifact>["artifact"]> }) {
  return (
    <div className="table-shell">
      <table className="data-table standings-table">
        <thead>
          <tr>
            <th scope="col"><span className="visually-hidden">Position</span>#</th>
            <th scope="col">Club</th>
            <th scope="col">Pld</th>
            <th scope="col">Pts</th>
            <th scope="col">xPts</th>
            <th scope="col">Avg. finish</th>
            <th scope="col">Title</th>
            <th scope="col">Champions League</th>
            <th scope="col">Relegation</th>
          </tr>
        </thead>
        <tbody>
          {artifact.standings.map((row) => (
            <tr key={row.team.id}>
              <td className="position-cell">{row.position}</td>
              <th scope="row">
                <span className="table-team"><TeamMark team={row.team} size="small" />{row.team.name}</span>
              </th>
              <td>{row.played ?? "—"}</td>
              <td><strong>{row.points ?? "—"}</strong></td>
              <td>{formatDecimal(row.expectedPoints)}</td>
              <td>{formatDecimal(row.expectedPosition)}</td>
              <td>{formatProbability(row.titleProbability)}</td>
              <td>{formatProbability(row.championsLeagueProbability)}</td>
              <td>{formatProbability(row.relegationProbability)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LeagueShell({
  slug,
  children,
}: {
  slug: string;
  children: (artifact: NonNullable<ReturnType<typeof useLeagueArtifact>["artifact"]>) => ReactNode;
}) {
  const state = useLeagueArtifact(slug);
  const fallback = stateView(state.phase, state.message);

  if (fallback) return <main className="shell main-content">{fallback}</main>;
  if (!state.artifact) return null;

  const artifact = state.artifact;
  return (
    <main className="shell main-content">
      <CompetitionMasthead
        parentLabel="Leagues"
        parentHref="/"
        title={artifact.competition.name}
        subtitle={`${artifact.season} · ${artifact.model.name} ${artifact.model.version}`}
        status={artifact.status}
        generatedAt={artifact.generatedAt}
        nav={[
          { label: "Forecast", href: `/leagues/${slug}` },
          { label: "Fixtures", href: `/leagues/${slug}/fixtures` },
          { label: "Methodology", href: "/methodology" },
        ]}
      />
      <DataNotice isDemo={artifact.isDemo} disclaimer={artifact.disclaimer} />
      {children(artifact)}
    </main>
  );
}

export function LeagueOverview({ slug }: { slug: string }) {
  return (
    <LeagueShell slug={slug}>
      {(artifact) => {
        const champion = [...artifact.standings].sort(
          (a, b) => (b.titleProbability ?? -1) - (a.titleProbability ?? -1),
        )[0];
        const relegationRisk = [...artifact.standings].sort(
          (a, b) => (b.relegationProbability ?? -1) - (a.relegationProbability ?? -1),
        )[0];
        const upcoming = artifact.fixtures.filter((fixture) => fixture.status === "scheduled").slice(0, 3);

        return (
          <>
            <section className="league-summary-grid">
              <article className="summary-lead">
                <p className="eyebrow">Highest title probability</p>
                <div className="summary-team">
                  {champion ? <TeamMark team={champion.team} size="large" /> : null}
                  <div>
                    <h2>{champion?.team.name ?? "Not available"}</h2>
                    <strong>{formatProbability(champion?.titleProbability)}</strong>
                  </div>
                </div>
                {champion ? <ProbabilityBar label="Title probability" value={champion.titleProbability} tone="lime" /> : null}
              </article>
              <article className="summary-stat">
                <p className="eyebrow">Highest relegation probability</p>
                <h3>{relegationRisk?.team.name ?? "Not available"}</h3>
                <strong>{formatProbability(relegationRisk?.relegationProbability)}</strong>
              </article>
              <article className="summary-stat summary-stat-dark">
                <p className="eyebrow eyebrow-light">Simulation runs</p>
                <strong>{artifact.model.simulations?.toLocaleString() ?? "—"}</strong>
                <span>{artifact.model.trainedThrough ? `Inputs through ${artifact.model.trainedThrough}` : "Training cutoff not exported"}</span>
              </article>
            </section>

            <section className="content-section">
              <SectionHeading
                kicker="Season projection"
                title="Forecast table"
                action={<Link className="text-link" href={`/leagues/${slug}/fixtures`}>Browse fixtures <span aria-hidden="true">→</span></Link>}
              />
              <CoverageNote included={artifact.coverage.teamsIncluded} expected={artifact.coverage.teamsExpected} noun="teams" />
              {artifact.standings.length ? <LeagueTable artifact={artifact} /> : (
                <div className="inline-empty"><h3>No table rows exported</h3><p>The artifact is valid, but its standings collection is empty.</p></div>
              )}
            </section>

            <section className="content-section">
              <SectionHeading
                kicker="Match desk"
                title="Next fixtures"
                action={<Link className="text-link" href={`/leagues/${slug}/fixtures`}>All fixtures <span aria-hidden="true">→</span></Link>}
              />
              {upcoming.length ? (
                <div className="fixture-grid">
                  {upcoming.map((fixture) => (
                    <FixtureCard
                      fixture={fixture}
                      href={`/leagues/${slug}/matches/${encodeURIComponent(fixture.id)}`}
                      key={fixture.id}
                    />
                  ))}
                </div>
              ) : <div className="inline-empty"><h3>No upcoming fixtures</h3><p>Scheduled matches have not been included in this artifact.</p></div>}
            </section>

            <section className="method-strip">
              <div>
                <p className="eyebrow eyebrow-light">Inside this forecast</p>
                <h2>{artifact.methodology.primaryModel}</h2>
              </div>
              <div className="method-components">
                {artifact.methodology.components.map((component) => <span key={component}>{component}</span>)}
              </div>
              <Link className="button button-ghost" href="/methodology">Read methodology</Link>
            </section>
          </>
        );
      }}
    </LeagueShell>
  );
}

export function LeagueFixtures({ slug }: { slug: string }) {
  return (
    <LeagueShell slug={slug}>
      {(artifact) => (
        <section className="content-section fixture-page-section">
          <SectionHeading
            kicker={`${artifact.fixtures.length} matches in artifact`}
            title="Fixtures & predictions"
          />
          <CoverageNote
            included={artifact.coverage.fixturesIncluded}
            expected={artifact.coverage.fixturesExpected}
            noun="fixtures"
          />
          {artifact.fixtures.length ? (
            <div className="fixture-grid">
              {artifact.fixtures.map((fixture) => (
                <FixtureCard
                  fixture={fixture}
                  href={`/leagues/${slug}/matches/${encodeURIComponent(fixture.id)}`}
                  key={fixture.id}
                />
              ))}
            </div>
          ) : (
            <div className="inline-empty"><h2>No fixtures exported</h2><p>The fixture collection is empty. Check again after the next data refresh.</p></div>
          )}
        </section>
      )}
    </LeagueShell>
  );
}

export function LeagueMatch({ slug, matchId }: { slug: string; matchId: string }) {
  return (
    <LeagueShell slug={slug}>
      {(artifact) => {
        const fixture = artifact.fixtures.find((item) => item.id === decodeURIComponent(matchId));
        if (!fixture) {
          return (
            <section className="inline-empty inline-empty-large">
              <h1>Match not found</h1>
              <p>This match ID is not present in the current {artifact.competition.name} artifact.</p>
              <Link className="button button-dark" href={`/leagues/${slug}/fixtures`}>View current fixtures</Link>
            </section>
          );
        }
        return <MatchBreakdownPanel fixture={fixture} />;
      }}
    </LeagueShell>
  );
}
