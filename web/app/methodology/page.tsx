import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Methodology" };

const modelFamilies = [
  {
    name: "Elo",
    role: "Tracks relative team strength as results arrive and supplies a durable baseline.",
  },
  {
    name: "Poisson / Skellam",
    role: "Turns scoring rates into scoreline and match-outcome distributions.",
  },
  {
    name: "Dixon–Coles",
    role: "Adjusts the dependence of low-scoring football results.",
  },
  {
    name: "Bradley–Terry",
    role: "Provides a direct strength-based comparison for win, draw and loss outcomes.",
  },
];

export default function MethodologyPage() {
  return (
    <main className="shell main-content methodology-page">
      <header className="methodology-hero">
        <p className="eyebrow eyebrow-light">Methods & data</p>
        <h1>Read the forecast,<br />then read its limits.</h1>
        <p>Every probability shown in the product comes from a published artifact. The artifact—not this page—is the record of which engine, version and inputs produced a forecast.</p>
        <a className="button button-accent" href="/data/manifest.json">Inspect data manifest</a>
      </header>

      <section className="content-section method-flow-section">
        <div className="section-heading section-heading-large">
          <div><p className="eyebrow">Forecast lifecycle</p><h2>From match data to product</h2></div>
          <p>The interface leaves an honest empty state if any expected export is absent.</p>
        </div>
        <div className="method-flow">
          <article><span>01</span><h3>Normalize</h3><p>Fixtures, results and team identities enter a shared competition schema.</p></article>
          <i aria-hidden="true">→</i>
          <article><span>02</span><h3>Estimate</h3><p>Candidate engines produce calibrated scoreline or outcome distributions.</p></article>
          <i aria-hidden="true">→</i>
          <article><span>03</span><h3>Simulate</h3><p>Remaining matches are sampled repeatedly under competition-specific rules.</p></article>
          <i aria-hidden="true">→</i>
          <article><span>04</span><h3>Publish</h3><p>Versioned JSON carries probabilities, coverage, timestamps and assumptions.</p></article>
        </div>
      </section>

      <section className="content-section">
        <div className="section-heading section-heading-large">
          <div><p className="eyebrow">Model library</p><h2>Candidate engines</h2></div>
          <p>A competition artifact identifies its active model. Presence here does not mean an engine is active in every forecast.</p>
        </div>
        <div className="model-family-grid">
          {modelFamilies.map((model, index) => (
            <article key={model.name}>
              <span>0{index + 1}</span>
              <h3>{model.name}</h3>
              <p>{model.role}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="validation-section">
        <div>
          <p className="eyebrow eyebrow-light">Out-of-sample first</p>
          <h2>Validation should lead selection.</h2>
          <p>Rolling backtests preserve time order. Model comparisons can include log loss, Brier score, Ranked Probability Score, scoreline likelihood and calibration bands.</p>
        </div>
        <div className="validation-scorecard">
          <div><span>Outcome quality</span><b>Log loss · Brier · RPS</b></div>
          <div><span>Score quality</span><b>Likelihood · goal totals</b></div>
          <div><span>Reliability</span><b>Calibration by band</b></div>
          <div><span>Reference</span><b>Existing Elo baseline</b></div>
        </div>
      </section>

      <section className="content-section freshness-section">
        <div className="section-heading section-heading-large">
          <div><p className="eyebrow">Freshness states</p><h2>What the labels mean</h2></div>
        </div>
        <div className="freshness-grid">
          <article><span className="status-badge status-good">Updated date</span><h3>Ready</h3><p>A forecast artifact is published with a generation timestamp.</p></article>
          <article><span className="status-badge status-warn">Refresh overdue</span><h3>Stale</h3><p>The exporter explicitly marked the artifact stale. Probabilities remain visible with the warning.</p></article>
          <article><span className="status-badge status-warn">Forecast building</span><h3>Building</h3><p>The competition is known, but its next artifact is not ready.</p></article>
          <article><span className="status-badge status-muted">Awaiting data</span><h3>Unavailable</h3><p>No artifact URL is published. The interface does not invent a fallback forecast.</p></article>
          <article><span className="status-badge status-sample">Example data</span><h3>Sample</h3><p>A contract demonstration is present and is labeled throughout the view.</p></article>
        </div>
      </section>

      <section className="responsibility-callout">
        <div><p className="eyebrow">Interpretation</p><h2>A probability is not a promise.</h2></div>
        <p>Forecasts describe uncertainty under a model and its available inputs. Squad news, lineups, scheduling changes and data errors can alter the picture. Check the timestamp, coverage note and artifact methodology before drawing conclusions.</p>
        <Link className="text-link" href="/">Return to forecast overview <span aria-hidden="true">→</span></Link>
      </section>
    </main>
  );
}
