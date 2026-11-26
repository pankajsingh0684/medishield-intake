import { NextRequest, NextResponse } from "next/server";
import { COOKIE } from "@/lib/server-api";

export async function GET(request: NextRequest) {
    const token = request.cookies.get(COOKIE)?.value;
    const apiUrl = process.env.API_URL?.replace(/\/$/, "");
    if (!token) return new NextResponse("Unauthorized", { status: 401 });
    if (!apiUrl) return new NextResponse("Configuration error", { status: 500 });
    const response = await fetch(`${apiUrl}/api/v1/cases/stats`, {
        headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
        cache: "no-store",
    }).catch(() => null);
    if (!response) return NextResponse.json({ error: { message: "The API is unavailable." } }, { status: 503 });
    if (!response.ok) return new NextResponse(response.body, { status: response.status, headers: { "Content-Type": "application/json" } });
    return NextResponse.json(await response.json());
}
