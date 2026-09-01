import type { Metadata } from "next";
import { WorldCupBracket } from "@/components/world-cup-view";

export const metadata: Metadata = { title: "World Cup bracket" };

export default function BracketPage() {
  return <WorldCupBracket />;
}
