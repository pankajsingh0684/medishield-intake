import { NextRequest, NextResponse } from "next/server";
import { COOKIE } from "@/lib/server-api";

export async function GET(request: NextRequest) {
    const token = request.cookies.get(COOKIE)?.value;
    const apiUrl = process.env.API_URL?.replace(/\/$/, "");
    if (!token) return new NextResponse("Unauthorized", { status: 401 });
    if (!apiUrl) return new NextResponse("Configuration error", { status: 500 });
    const headers = { Authorization: `Bearer ${token}`, Accept: "application/json" };
    const list = await fetch(`${apiUrl}/api/v1/cases${request.nextUrl.search}`, { headers, cache: "no-store" }).catch(() => null);
    if (!list) return NextResponse.json({ error: { message: "The API is unavailable." } }, { status: 503 });
    if (!list.ok) return new NextResponse(list.body, { status: list.status, headers: { "Content-Type": "application/json" } });
    const data = await list.json();
    const details = await Promise.all(data.items.map(async (item: { case_id: string }) => {
        const response = await fetch(`${apiUrl}/api/v1/cases/${encodeURIComponent(item.case_id)}`, { headers, cache: "no-store" });
        if (!response.ok) return { ...item, effective_decision: null };
        const detail = await response.json();
        return { ...item, effective_decision: detail.effective_decision ?? null };
    }));
    return NextResponse.json({ items: details, total: data.total });
}
