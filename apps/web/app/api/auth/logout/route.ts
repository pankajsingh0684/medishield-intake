import { NextRequest, NextResponse } from "next/server";
import { COOKIE, validateOrigin } from "@/lib/server-api";

export async function POST(request: NextRequest) {
    const invalid = validateOrigin(request);
    if (invalid) return invalid;
    const response = NextResponse.json({ ok: true });
    response.cookies.set(COOKIE, "", { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 0 });
    return response;
}
