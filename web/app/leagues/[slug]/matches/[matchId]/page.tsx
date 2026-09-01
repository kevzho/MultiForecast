import type { Metadata } from "next";
import { LeagueMatch } from "@/components/league-view";

export const metadata: Metadata = { title: "Match breakdown" };

export default async function MatchPage({
  params,
}: {
  params: Promise<{ slug: string; matchId: string }>;
}) {
  const { slug, matchId } = await params;
  return <LeagueMatch slug={slug} matchId={matchId} />;
}
