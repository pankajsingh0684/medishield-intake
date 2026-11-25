import { NextRequest, NextResponse } from "next/server";
import { COOKIE } from "@/lib/server-api";

export async function GET(request: NextRequest) {
    const token = request.cookies.get(COOKIE)?.value;
    if (!token) return new NextResponse("Unauthorized", { status: 401 });
    try {
        const payload = token.split(".")[1];
        const claims = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
        if (!["REVIEWER", "SUPERVISOR", "AUDITOR", "ADMIN"].includes(claims.role)) throw new Error();
        return NextResponse.json({ role: claims.role });
    } catch {
        return new NextResponse("Unauthorized", { status: 401 });
    }
}
