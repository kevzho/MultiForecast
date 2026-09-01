"use client";

import { useCallback, useEffect, useState } from "react";
import type {
  ArtifactLoadState,
  ForecastManifest,
  LeagueForecastArtifact,
  LeagueManifestEntry,
  TournamentForecastArtifact,
  TournamentManifestEntry,
} from "@/lib/contracts";

const EMPTY_MANIFEST_STATE = {
  phase: "loading" as const,
  manifest: null,
  message: null,
};

type ManifestState = {
  phase: "loading" | "ready" | "error";
  manifest: ForecastManifest | null;
  message: string | null;
};

function isSupportedSchema(version: string | undefined): boolean {
  return typeof version === "string" && version.split(".")[0] === "1";
}

async function getJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal, cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

export function useManifest(): ManifestState {
  const [state, setState] = useState<ManifestState>(EMPTY_MANIFEST_STATE);

  useEffect(() => {
    const controller = new AbortController();

    getJson<ForecastManifest>("/data/manifest.json", controller.signal)
      .then((manifest) => {
        if (!isSupportedSchema(manifest.schemaVersion)) {
          throw new Error(`Unsupported manifest schema ${manifest.schemaVersion}`);
        }
        setState({ phase: "ready", manifest, message: null });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState({
          phase: "error",
          manifest: null,
          message: "The forecast index could not be loaded.",
        });
      });

    return () => controller.abort();
  }, []);

  return state;
}

function useArtifact<T, E extends { dataUrl: string | null; status: string }>(
  findEntry: (manifest: ForecastManifest) => E | undefined,
  dependency: string,
): ArtifactLoadState<T, E> {
  const [state, setState] = useState<ArtifactLoadState<T, E>>({
    phase: "loading",
    manifest: null,
    entry: null,
    artifact: null,
    message: null,
  });

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const manifest = await getJson<ForecastManifest>(
          "/data/manifest.json",
          controller.signal,
        );
        if (!isSupportedSchema(manifest.schemaVersion)) {
          throw new Error(`Unsupported manifest schema ${manifest.schemaVersion}`);
        }

        const entry = findEntry(manifest);
        if (!entry) {
          setState({
            phase: "unavailable",
            manifest,
            entry: null,
            artifact: null,
            message: "This competition is not listed in the current forecast index.",
          });
          return;
        }

        if (!entry.dataUrl) {
          setState({
            phase: "unavailable",
            manifest,
            entry,
            artifact: null,
            message: entry.status === "building"
              ? "The first forecast export is still being built."
              : "No forecast artifact has been published for this competition yet.",
          });
          return;
        }

        const artifact = await getJson<T>(entry.dataUrl, controller.signal);
        const version = (artifact as { schemaVersion?: string }).schemaVersion;
        if (!isSupportedSchema(version)) {
          throw new Error(`Unsupported artifact schema ${version ?? "unknown"}`);
        }

        setState({
          phase: "ready",
          manifest,
          entry,
          artifact,
          message: null,
        });
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState({
          phase: "error",
          manifest: null,
          entry: null,
          artifact: null,
          message: "The forecast artifact could not be loaded. Try again after the next refresh.",
        });
      }
    }

    load();
    return () => controller.abort();
  }, [dependency, findEntry]);

  return state;
}

export function useLeagueArtifact(
  slug: string,
): ArtifactLoadState<LeagueForecastArtifact, LeagueManifestEntry> {
  const findEntry = useCallback(
    (manifest: ForecastManifest) => manifest.leagues.find((entry) => entry.id === slug),
    [slug],
  );
  return useArtifact<LeagueForecastArtifact, LeagueManifestEntry>(
    findEntry,
    slug,
  );
}

export function useTournamentArtifact(
  slug: string,
): ArtifactLoadState<TournamentForecastArtifact, TournamentManifestEntry> {
  const findEntry = useCallback(
    (manifest: ForecastManifest) => manifest.worldCup.id === slug ? manifest.worldCup : undefined,
    [slug],
  );
  return useArtifact<TournamentForecastArtifact, TournamentManifestEntry>(
    findEntry,
    slug,
  );
}
