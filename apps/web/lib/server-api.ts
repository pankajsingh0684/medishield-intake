import { NextRequest, NextResponse } from "next/server";

const COOKIE = "medishield_token";

function apiUrl() {
    const value = process.env.API_URL;
    if (!value) throw new Error("API_URL is required");
    return value.replace(/\/$/, "");
}

export function validateOrigin(request: NextRequest) {
    const origin = request.headers.get("origin");
    const expected = process.env.UI_ORIGIN ?? "http://localhost:3000";
    if (origin !== expected) return new NextResponse("Forbidden", { status: 403 });
    return null;
}

export async function proxyApi(request: NextRequest, path: string) {
    const token = request.cookies.get(COOKIE)?.value;
    if (!token) return new NextResponse("Unauthorized", { status: 401 });
    const target = `${apiUrl()}/api/v1/${path}${request.nextUrl.search}`;
    const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();
    const contentType = request.headers.get("content-type");
    const response = await fetch(target, {
        method: request.method,
        headers: {
            Authorization: `Bearer ${token}`,
            Accept: "application/json",
            ...(contentType ? { "Content-Type": contentType } : {}),
        },
        body: body,
        cache: "no-store",
    }).catch(() => null);
    if (!response) return NextResponse.json({ error: { message: "The API is unavailable." } }, { status: 503 });
    return new NextResponse(response.body, {
        status: response.status,
        headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" },
    });
}

export { COOKIE };
