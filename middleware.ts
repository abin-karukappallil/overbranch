import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname;
  const protectedRoutes = [
    "/dashboard",
    "/projects",
    "/workspaces",
    "/templates",
    "/settings",
    "/profile",
    "/billing",
    "/editor",
  ];

  const isProtectedPath = protectedRoutes.some((route) => path.startsWith(route));
  const isAuthPath = path === "/login" || path === "/register" || path === "/forgot-password";
  const sessionToken = request.cookies.get("better-auth.session_token")?.value;

  const response = NextResponse.next();

  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");

  return response;
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/projects/:path*",
    "/workspaces/:path*",
    "/templates/:path*",
    "/settings/:path*",
    "/profile/:path*",
    "/billing/:path*",
    "/editor/:path*",
    "/login",
    "/register",
    "/forgot-password",
  ],
};
