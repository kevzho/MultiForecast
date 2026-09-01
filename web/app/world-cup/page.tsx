import type { Metadata } from "next";
import { WorldCupOverview } from "@/components/world-cup-view";

export const metadata: Metadata = { title: "World Cup 2026" };

export default function WorldCupPage() {
  return <WorldCupOverview />;
}
