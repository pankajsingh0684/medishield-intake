import { NextRequest, NextResponse } from "next/server";
import { COOKIE } from "@/lib/server-api";

export function proxy(request: NextRequest) {
    const token = request.cookies.get(COOKIE)?.value;
    if (!token && request.nextUrl.pathname !== "/login") {
        const login = new URL("/login", request.url);
        return NextResponse.redirect(login);
    }
    if (token && request.nextUrl.pathname === "/login") return NextResponse.redirect(new URL("/", request.url));
    return NextResponse.next();
}

export const config = { matcher: ["/((?!api|_next|favicon.ico|robots.txt).*)"] };
