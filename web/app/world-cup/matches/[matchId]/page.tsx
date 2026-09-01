import type { Metadata } from "next";
import { WorldCupMatch } from "@/components/world-cup-view";

export const metadata: Metadata = { title: "World Cup match breakdown" };

export default async function WorldCupMatchPage({ params }: { params: Promise<{ matchId: string }> }) {
  const { matchId } = await params;
  return <WorldCupMatch matchId={matchId} />;
}
