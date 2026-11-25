"use client";

import Link from "next/link";
import { useRole } from "@/lib/role";

export function AppNav() {
  const role = useRole();
  return (
    <nav aria-label="Primary" className="flex gap-4 text-sm font-semibold">
      <Link className="text-blue-800 underline" href="/">
        Cases
      </Link>
      {role.data?.role !== "AUDITOR" && (
        <Link className="text-blue-800 underline" href="/review">
          Review
        </Link>
      )}
      {role.data &&
        ["REVIEWER", "SUPERVISOR", "ADMIN"].includes(role.data.role) && (
          <Link className="text-blue-800 underline" href="/policies">
            Policies
          </Link>
        )}
    </nav>
  );
}
