import type { ArtifactStatus, ForecastFixture } from "@/lib/contracts";

export function formatProbability(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }

  if (value > 0 && value < 0.005) {
    return "<1%";
  }

  return `${Math.round(value * 100)}%`;
}

export function formatDecimal(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }

  return value.toFixed(digits);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "Date not published";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Date not published";
  }

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

export function formatKickoff(value: string | null | undefined): string {
  if (!value) {
    return "Kickoff TBC";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Kickoff TBC";
  }

  return new Intl.DateTimeFormat("en", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

export function freshnessLabel(
  status: ArtifactStatus,
  generatedAt: string | null,
): { label: string; tone: "good" | "warn" | "muted" | "sample" } {
  if (status === "sample") {
    return { label: "Example data", tone: "sample" };
  }
  if (status === "building") {
    return { label: "Forecast building", tone: "warn" };
  }
  if (status === "unavailable") {
    return { label: "Awaiting data", tone: "muted" };
  }
  if (status === "stale") {
    return { label: "Refresh overdue", tone: "warn" };
  }
  if (!generatedAt) {
    return { label: "Freshness unknown", tone: "muted" };
  }

  return { label: `Updated ${formatDate(generatedAt)}`, tone: "good" };
}

export function fixtureTitle(fixture: ForecastFixture): string {
  const home = fixture.homeTeam?.name ?? fixture.homeSource ?? "TBD";
  const away = fixture.awayTeam?.name ?? fixture.awaySource ?? "TBD";
  return `${home} vs ${away}`;
}

export function sumProbabilities(values: Array<number | null | undefined>): number {
  return values.reduce<number>((total, value) => total + (value ?? 0), 0);
}
