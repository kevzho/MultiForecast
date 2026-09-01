import Link from "next/link";
import type { ReactNode } from "react";
import type { ArtifactStatus, TeamRef } from "@/lib/contracts";
import { formatProbability, freshnessLabel } from "@/lib/format";

export function StatusBadge({
  status,
  generatedAt,
}: {
  status: ArtifactStatus;
  generatedAt: string | null;
}) {
  const freshness = freshnessLabel(status, generatedAt);
  return <span className={`status-badge status-${freshness.tone}`}>{freshness.label}</span>;
}

export function PageState({
  kind,
  title,
  message,
}: {
  kind: "loading" | "error" | "empty";
  title: string;
  message: string;
}) {
  return (
    <section className={`page-state page-state-${kind}`} aria-live="polite">
      <div className="state-signal" aria-hidden="true">
        {kind === "loading" ? <span className="spinner" /> : kind === "error" ? "!" : "—"}
      </div>
      <p className="eyebrow">{kind === "loading" ? "Loading forecast" : "Data status"}</p>
      <h1>{title}</h1>
      <p>{message}</p>
      {kind !== "loading" ? (
        <div className="state-actions">
          <Link className="button button-dark" href="/">Return to overview</Link>
          <Link className="text-link" href="/methodology">How data refreshes work</Link>
        </div>
      ) : null}
    </section>
  );
}

export function DataNotice({
  isDemo,
  disclaimer,
}: {
  isDemo: boolean;
  disclaimer: string | null;
}) {
  if (!isDemo && !disclaimer) return null;
  return (
    <aside className={isDemo ? "data-notice data-notice-demo" : "data-notice"}>
      <strong>{isDemo ? "Contract example" : "Forecast note"}</strong>
      <span>{disclaimer ?? "This artifact is illustrative and is not a current forecast."}</span>
    </aside>
  );
}

export function ProbabilityBar({
  label,
  value,
  tone = "ink",
  compact = false,
}: {
  label: string;
  value: number | null | undefined;
  tone?: "ink" | "lime" | "blue" | "orange" | "muted";
  compact?: boolean;
}) {
  const safeValue = value === null || value === undefined ? 0 : Math.max(0, Math.min(1, value));
  return (
    <div
      className={`probability-row ${compact ? "probability-compact" : ""}`}
      aria-label={`${label}: ${formatProbability(value)}`}
    >
      <div className="probability-label">
        <span>{label}</span>
        <strong>{formatProbability(value)}</strong>
      </div>
      <div className="probability-track" aria-hidden="true">
        <span className={`probability-fill fill-${tone}`} style={{ width: `${safeValue * 100}%` }} />
      </div>
    </div>
  );
}

export function TeamMark({ team, size = "normal" }: { team: TeamRef; size?: "small" | "normal" | "large" }) {
  return (
    <span className={`team-mark team-mark-${size}`} aria-hidden="true">
      {team.shortName.slice(0, 3).toUpperCase()}
    </span>
  );
}

export function SectionHeading({
  kicker,
  title,
  action,
}: {
  kicker?: string;
  title: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-heading">
      <div>
        {kicker ? <p className="eyebrow">{kicker}</p> : null}
        <h2>{title}</h2>
      </div>
      {action ? <div className="section-action">{action}</div> : null}
    </div>
  );
}

export function CompetitionMasthead({
  parentLabel,
  parentHref,
  title,
  subtitle,
  status,
  generatedAt,
  nav,
}: {
  parentLabel: string;
  parentHref: string;
  title: string;
  subtitle: string;
  status: ArtifactStatus;
  generatedAt: string | null;
  nav?: Array<{ label: string; href: string }>;
}) {
  return (
    <header className="competition-masthead">
      <div className="breadcrumbs">
        <Link href={parentHref}>{parentLabel}</Link>
        <span aria-hidden="true">/</span>
        <span>{title}</span>
      </div>
      <div className="masthead-title-row">
        <div>
          <p className="eyebrow">Forecast centre</p>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        <StatusBadge status={status} generatedAt={generatedAt} />
      </div>
      {nav?.length ? (
        <nav className="subnav" aria-label={`${title} sections`}>
          {nav.map((item) => <Link href={item.href} key={item.href}>{item.label}</Link>)}
        </nav>
      ) : null}
    </header>
  );
}

export function CoverageNote({
  included,
  expected,
  noun,
}: {
  included: number;
  expected: number | null;
  noun: string;
}) {
  if (expected === null || included >= expected) return null;
  return (
    <p className="coverage-note">
      Showing {included} of {expected} expected {noun}. The artifact is incomplete.
    </p>
  );
}
