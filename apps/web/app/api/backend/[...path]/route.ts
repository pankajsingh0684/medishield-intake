import { NextRequest } from "next/server";
import { proxyApi, validateOrigin } from "@/lib/server-api";

type Context = { params: Promise<{ path: string[] }> };

async function handle(request: NextRequest, context: Context) {
    if (!["GET", "HEAD"].includes(request.method)) {
        const invalid = validateOrigin(request);
        if (invalid) return invalid;
    }
    const { path } = await context.params;
    return proxyApi(request, path.map(encodeURIComponent).join("/"));
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
