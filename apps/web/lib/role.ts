import { useQuery } from "@tanstack/react-query";
import type { UserRole } from "@/lib/types";

export function useRole() {
    return useQuery<{ role: UserRole }>({
        queryKey: ["session-role"],
        queryFn: async () => {
            const response = await fetch("/api/auth/session", { cache: "no-store" });
            if (response.status === 401) throw new Error("Your session has expired.");
            if (!response.ok) throw new Error("The session could not be loaded.");
            return response.json();
        },
        retry: 0,
    });
}
