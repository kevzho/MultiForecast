import type { Metadata } from "next";
import { LeagueOverview } from "@/components/league-view";

export const metadata: Metadata = { title: "League forecast" };

export default async function LeaguePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <LeagueOverview slug={slug} />;
}
