import type { Metadata } from "next";
import { LeagueFixtures } from "@/components/league-view";

export const metadata: Metadata = { title: "League fixtures" };

export default async function FixturesPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <LeagueFixtures slug={slug} />;
}
