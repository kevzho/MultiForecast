export type ArtifactStatus =
  | "ready"
  | "stale"
  | "building"
  | "unavailable"
  | "sample";

export type CompetitionRef = {
  id: string;
  name: string;
  shortName: string;
  country?: string;
  code?: string;
};

export type ArtifactLink = {
  status: ArtifactStatus;
  dataUrl: string | null;
  generatedAt: string | null;
  note: string | null;
};

export type LeagueManifestEntry = CompetitionRef &
  ArtifactLink & {
    kind: "domestic-league";
    season: string;
    expectedTeams: number;
  };

export type TournamentManifestEntry = CompetitionRef &
  ArtifactLink & {
    kind: "tournament";
    edition: string;
    expectedTeams: number;
  };

export type ForecastManifest = {
  schemaVersion: string;
  artifactVersion: string;
  generatedAt: string | null;
  leagues: LeagueManifestEntry[];
  worldCup: TournamentManifestEntry;
  extensions?: Record<string, unknown>;
};

export type TeamRef = {
  id: string;
  name: string;
  shortName: string;
};

export type ScorelineProbability = {
  home: number;
  away: number;
  probability: number;
};

export type MatchForecast = {
  homeWin: number;
  draw: number;
  awayWin: number;
  expectedHomeGoals: number | null;
  expectedAwayGoals: number | null;
  over25: number | null;
  bothTeamsScore: number | null;
  homeCleanSheet: number | null;
  awayCleanSheet: number | null;
  topScorelines: ScorelineProbability[];
  modelProbabilities?: Array<{
    model: string;
    homeWin: number;
    draw: number;
    awayWin: number;
  }>;
  seasonImpact?: Array<{
    outcome: "home" | "draw" | "away";
    label: string;
    homeDelta: number | null;
    awayDelta: number | null;
  }>;
};

export type ForecastFixture = {
  id: string;
  stage: string;
  round: string | null;
  kickoff: string | null;
  venue: string | null;
  status: "scheduled" | "live" | "final" | "postponed" | "unknown";
  homeTeam: TeamRef | null;
  awayTeam: TeamRef | null;
  homeSource?: string | null;
  awaySource?: string | null;
  score: {
    home: number;
    away: number;
  } | null;
  forecast: MatchForecast | null;
};

export type StandingForecast = {
  position: number;
  team: TeamRef;
  played: number | null;
  points: number | null;
  goalDifference: number | null;
  expectedPoints: number | null;
  expectedPosition: number | null;
  titleProbability: number | null;
  championsLeagueProbability: number | null;
  relegationProbability: number | null;
  positionProbabilities?: number[];
};

export type MethodologySummary = {
  primaryModel: string;
  components: string[];
  evaluation: string | null;
  assumptions: string[];
};

export type LeagueForecastArtifact = {
  kind: "domestic-league-forecast";
  schemaVersion: string;
  artifactVersion: string;
  status: ArtifactStatus;
  isDemo: boolean;
  disclaimer: string | null;
  competition: CompetitionRef;
  season: string;
  generatedAt: string | null;
  model: {
    name: string;
    version: string;
    simulations: number | null;
    trainedThrough: string | null;
  };
  coverage: {
    teamsIncluded: number;
    teamsExpected: number;
    fixturesIncluded: number;
    fixturesExpected: number | null;
  };
  standings: StandingForecast[];
  fixtures: ForecastFixture[];
  methodology: MethodologySummary;
};

export type TournamentTeamForecast = {
  team: TeamRef;
  group: string;
  rating: number | null;
  probabilities: {
    advanceGroup: number | null;
    roundOf16: number | null;
    quarterfinal: number | null;
    semifinal: number | null;
    final: number | null;
    champion: number | null;
  };
};

export type TournamentGroup = {
  id: string;
  label: string;
  teamIds: string[];
  fixtureIds: string[];
};

export type BracketRound = {
  id: string;
  label: string;
  matches: Array<{
    fixtureId: string;
    homeSource: string;
    awaySource: string;
  }>;
};

export type TournamentForecastArtifact = {
  kind: "tournament-forecast";
  schemaVersion: string;
  artifactVersion: string;
  status: ArtifactStatus;
  isDemo: boolean;
  disclaimer: string | null;
  competition: CompetitionRef;
  edition: string;
  generatedAt: string | null;
  model: {
    name: string;
    version: string;
    simulations: number | null;
    trainedThrough: string | null;
  };
  coverage: {
    teamsIncluded: number;
    teamsExpected: number;
    groupsIncluded: number;
    groupsExpected: number;
  };
  teams: TournamentTeamForecast[];
  groups: TournamentGroup[];
  fixtures: ForecastFixture[];
  bracket: BracketRound[];
  methodology: MethodologySummary;
};

export type DataPhase = "loading" | "ready" | "unavailable" | "error";

export type ArtifactLoadState<T, E> = {
  phase: DataPhase;
  manifest: ForecastManifest | null;
  entry: E | null;
  artifact: T | null;
  message: string | null;
};
