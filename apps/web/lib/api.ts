import { redirect } from "next/navigation";

export class ApiError extends Error {
    constructor(public status: number, message: string) {
        super(message);
    }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`/api/backend${path}`, {
        ...init,
        cache: "no-store",
    }).catch(() => null);
    if (!response) throw new ApiError(503, "The service is unavailable. Please try again.");
    if (response.status === 401) {
        redirect("/login");
        throw new ApiError(401, "Your session has expired.");
    }
    if (!response.ok) {
        let message = "The request could not be completed.";
        try {
            const body = await response.json();
            message = body?.error?.message ?? message;
        } catch { }
        if (response.status === 403) message = "You do not have access to this resource.";
        if (response.status === 429) message = "Too many requests. Please wait and try again.";
        throw new ApiError(response.status, message);
    }
    return response.json() as Promise<T>;
}
