import { NextRequest, NextResponse } from "next/server";
import { COOKIE, validateOrigin } from "@/lib/server-api";

type LoginResponse = { access_token: string; expires_in: number };

export async function POST(request: NextRequest) {
    const invalid = validateOrigin(request);
    if (invalid) return invalid;
    const apiUrl = process.env.API_URL;
    if (!apiUrl) return new NextResponse("Configuration error", { status: 500 });
    const response = await fetch(`${apiUrl.replace(/\/$/, "")}/api/v1/auth/login`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: await request.text(), cache: "no-store",
    }).catch(() => null);
    if (!response) return NextResponse.json({ error: { message: "The API is unavailable." } }, { status: 503 });
    if (!response.ok) return new NextResponse(response.body, { status: response.status, headers: { "Content-Type": "application/json" } });
    const payload = await response.json() as LoginResponse;
    const result = NextResponse.json({ ok: true });
    result.cookies.set(COOKIE, payload.access_token, {
        httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax",
        path: "/", maxAge: payload.expires_in,
    });
    return result;
}
