import Link from "next/link";

const leagues = [
  ["Premier League", "premier-league"],
  ["Serie A", "serie-a"],
  ["La Liga", "la-liga"],
  ["Bundesliga", "bundesliga"],
  ["Ligue 1", "ligue-1"],
] as const;

function validExternalUrl(value: string | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

export function SiteHeader() {
  const analyticsUrl = validExternalUrl(process.env.NEXT_PUBLIC_STREAMLIT_URL);

  return (
    <header className="site-header">
      <div className="header-top shell">
        <Link className="brand" href="/" aria-label="Football Forecast home">
          <span className="brand-mark" aria-hidden="true">F/90</span>
          <span className="brand-copy">
            <strong>Football Forecast</strong>
            <small>2026 model room</small>
          </span>
        </Link>
        <div className="header-actions">
          <span className="artifact-label">Artifact-driven</span>
          {analyticsUrl ? (
            <a
              className="button button-small button-accent"
              href={analyticsUrl}
              target="_blank"
              rel="noreferrer"
            >
              Open live analytics <span aria-hidden="true">↗</span>
            </a>
          ) : null}
        </div>
      </div>
      <nav className="main-nav" aria-label="Primary navigation">
        <div className="shell nav-scroll">
          <Link href="/">Overview</Link>
          <Link href="/world-cup">World Cup 2026</Link>
          {leagues.map(([name, slug]) => (
            <Link key={slug} href={`/leagues/${slug}`}>
              {name}
            </Link>
          ))}
          <Link href="/methodology">Methodology</Link>
        </div>
      </nav>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="shell footer-grid">
        <div>
          <span className="brand-mark brand-mark-small" aria-hidden="true">F/90</span>
          <p>Probabilistic football forecasts, presented with their limits intact.</p>
        </div>
        <nav aria-label="Footer navigation">
          <Link href="/world-cup">World Cup</Link>
          <Link href="/methodology">Methodology</Link>
          <a href="/data/manifest.json">Data manifest</a>
        </nav>
      </div>
    </footer>
  );
}
