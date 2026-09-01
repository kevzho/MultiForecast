import type { Metadata } from "next";
import { WorldCupGroups } from "@/components/world-cup-view";

export const metadata: Metadata = { title: "World Cup groups" };

export default function GroupsPage() {
  return <WorldCupGroups />;
}
