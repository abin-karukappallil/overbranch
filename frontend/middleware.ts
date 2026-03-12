import { NextRequest, NextResponse } from "next/server";

const publicRoutes = ["/login", "/register"];
const authApiPrefix = "/api/auth";

export async function middleware(request: NextRequest) {
    const { pathname } = request.nextUrl;

    // Always allow auth API routes
    if (pathname.startsWith(authApiPrefix)) {
        return NextResponse.next();
    }

    // Always allow public assets and API routes
    if (
        pathname.startsWith("/_next") ||
        pathname.startsWith("/api/trpc") ||
        pathname.startsWith("/api/upload") ||
        pathname.startsWith("/uploads") ||
        pathname.match(/\.(ico|svg|png|jpg|jpeg|gif|webp|css|js)$/)
    ) {
        return NextResponse.next();
    }

    // Check session by calling Better Auth's session endpoint
    const sessionCookie = request.cookies.get("overbranch.session_token")?.value;

    let isAuthenticated = false;

    if (sessionCookie) {
        try {
            const response = await fetch(
                `${request.nextUrl.origin}/api/auth/get-session`,
                {
                    headers: {
                        cookie: request.headers.get("cookie") || "",
                    },
                }
            );
            if (response.ok) {
                const session = await response.json();
                isAuthenticated = !!session?.user;
            }
        } catch {
            isAuthenticated = false;
        }
    }

    const isPublicRoute = publicRoutes.includes(pathname);

    // Redirect authenticated users away from login/register
    if (isAuthenticated && isPublicRoute) {
        return NextResponse.redirect(new URL("/dashboard", request.url));
    }

    // Redirect unauthenticated users to login
    if (!isAuthenticated && !isPublicRoute) {
        return NextResponse.redirect(new URL("/login", request.url));
    }

    return NextResponse.next();
}

export const config = {
    matcher: [
        "/((?!_next/static|_next/image|favicon.ico).*)",
    ],
};
