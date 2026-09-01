"use client";

import Link from "next/link";
import { useManifest } from "@/lib/data";
import { formatDate } from "@/lib/format";
import { PageState, StatusBadge } from "@/components/ui";

const leagueMonograms: Record<string, string> = {
  "premier-league": "PL",
  "serie-a": "SA",
  "la-liga": "LL",
  bundesliga: "BL",
  "ligue-1": "L1",
};

export function OverviewClient() {
  const state = useManifest();

  if (state.phase === "loading") {
    return (
      <main className="shell main-content">
        <PageState kind="loading" title="Reading the forecast index" message="Checking competition coverage and artifact freshness." />
      </main>
    );
  }

  if (state.phase === "error" || !state.manifest) {
    return (
      <main className="shell main-content">
        <PageState kind="error" title="Forecast index unavailable" message={state.message ?? "The data manifest could not be read."} />
      </main>
    );
  }

  const { manifest } = state;
  const availableCount = manifest.leagues.filter((league) => league.dataUrl).length;

  return (
    <main>
      <section className="overview-hero">
        <div className="shell hero-grid">
          <div className="hero-copy">
            <p className="eyebrow eyebrow-light">Domestic leagues + World Cup 2026</p>
            <h1>One model room.<br /><span>Six competitions.</span></h1>
            <p className="hero-intro">
              Season outcomes, match-level probabilities and tournament paths—each tied to a versioned forecast artifact.
            </p>
            <div className="hero-actions">
              <Link className="button button-accent" href="/world-cup">Explore World Cup</Link>
              <Link className="button button-ghost" href="/leagues/premier-league">Open league forecasts</Link>
            </div>
          </div>
          <div className="hero-scoreboard" aria-label="Forecast coverage summary">
            <div className="scoreboard-top">
              <span>Coverage board</span>
              <span>2026/27</span>
            </div>
            <div className="scoreboard-main">
              <strong>{availableCount}<small>/5</small></strong>
              <span>league artifacts published</span>
            </div>
            <div className="scoreboard-row">
              <span>World Cup</span>
              <StatusBadge status={manifest.worldCup.status} generatedAt={manifest.worldCup.generatedAt} />
            </div>
            <div className="scoreboard-row">
              <span>Manifest version</span>
              <b>{manifest.artifactVersion}</b>
            </div>
            <div className="scoreboard-row">
              <span>Index refreshed</span>
              <b>{formatDate(manifest.generatedAt)}</b>
            </div>
          </div>
        </div>
        <div className="ticker" aria-label="Available forecast views">
          <div className="ticker-inner shell">
            <span><b>Forecast desk</b></span>
            <span>Tables</span><i>◆</i>
            <span>Fixtures</span><i>◆</i>
            <span>Scorelines</span><i>◆</i>
            <span>Groups</span><i>◆</i>
            <span>Knockout paths</span>
          </div>
        </div>
      </section>

      <section className="shell content-section">
        <div className="section-heading section-heading-large">
          <div>
            <p className="eyebrow">The big five</p>
            <h2>Choose a league</h2>
          </div>
          <p>Open a competition for its projected table, fixture probabilities and match breakdowns.</p>
        </div>
        <div className="league-card-grid">
          {manifest.leagues.map((league, index) => (
            <Link className="league-card" href={`/leagues/${league.id}`} key={league.id}>
              <div className="league-card-top">
                <span className="league-number">0{index + 1}</span>
                <StatusBadge status={league.status} generatedAt={league.generatedAt} />
              </div>
              <div className="league-monogram" aria-hidden="true">{leagueMonograms[league.id] ?? league.shortName}</div>
              <p>{league.country}</p>
              <h3>{league.name}</h3>
              <div className="league-card-meta">
                <span>{league.season}</span>
                <span>{league.expectedTeams} teams</span>
                <span aria-hidden="true">→</span>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section className="world-cup-promo">
        <div className="shell world-cup-promo-grid">
          <div>
            <p className="eyebrow eyebrow-light">Tournament engine</p>
            <h2>World Cup 2026</h2>
            <p>Follow group advancement, every team’s tournament path and the knockout bracket as the artifact fills in.</p>
            <Link className="text-link text-link-light" href="/world-cup">Enter tournament centre <span aria-hidden="true">→</span></Link>
          </div>
          <div className="tournament-route" aria-hidden="true">
            <span>48</span><i /><span>32</span><i /><span>16</span><i /><span>8</span><i /><span>1</span>
          </div>
          <div className="promo-status">
            <StatusBadge status={manifest.worldCup.status} generatedAt={manifest.worldCup.generatedAt} />
            <p>{manifest.worldCup.note ?? "Open the tournament centre for artifact coverage."}</p>
          </div>
        </div>
      </section>

      <section className="shell principles-grid">
        <div>
          <p className="eyebrow">Built for scrutiny</p>
          <h2>Probabilities with context.</h2>
        </div>
        <article>
          <span>01</span>
          <h3>Timestamped</h3>
          <p>Every view exposes when its underlying artifact was generated.</p>
        </article>
        <article>
          <span>02</span>
          <h3>Versioned</h3>
          <p>The data contract and model version travel with each forecast.</p>
        </article>
        <article>
          <span>03</span>
          <h3>Honest gaps</h3>
          <p>Missing, partial and stale exports are shown as states—not filled with guesses.</p>
        </article>
      </section>
    </main>
  );
}
