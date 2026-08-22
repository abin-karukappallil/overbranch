import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname;
  const protectedRoutes = [
    "/dashboard",
    "/projects",
    "/templates",
    "/profile",
    "/editor",
  ];

  const isProtectedPath = protectedRoutes.some((route) => path.startsWith(route));
  const isAuthPath = path === "/login" || path === "/register" || path === "/forgot-password";
  
  const sessionToken =
    request.cookies.get("better-auth.session_token")?.value ||
    request.cookies.get("__Secure-better-auth.session_token")?.value ||
    request.cookies.get("better-auth.session-token")?.value ||
    request.cookies.get("__Secure-better-auth.session-token")?.value ||
    request.cookies.get("better_auth_session")?.value;

  if (isProtectedPath && !sessionToken) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", path);
    return NextResponse.redirect(loginUrl);
  }

  const response = NextResponse.next();

  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");

  return response;
}

export const config = {
  matcher: [
    "/dashboard",
    "/dashboard/:path*",
    "/projects",
    "/projects/:path*",
    "/templates",
    "/templates/:path*",
    "/profile",
    "/profile/:path*",
    "/editor",
    "/editor/:path*",
    "/login",
    "/register",
    "/forgot-password",
  ],
};

