import { Dashboard } from "@/components/dashboard";
import { Suspense } from "react";

export default function Home() {
  return (
    <Suspense fallback={<main className="p-5">Loading cases...</main>}>
      <Dashboard />
    </Suspense>
  );
}
