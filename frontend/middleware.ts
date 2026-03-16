export const runtime = "nodejs";

import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";

const publicRoutes = ["/login", "/register"];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith("/api/auth")) {
    return NextResponse.next();
  }

  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api/trpc") ||
    pathname.startsWith("/api/upload") ||
    pathname.startsWith("/uploads") ||
    pathname.match(/\.(ico|svg|png|jpg|jpeg|gif|webp|css|js)$/)
  ) {
    return NextResponse.next();
  }

  const isPublicRoute = publicRoutes.includes(pathname);

  const session = await auth.api.getSession({
    headers: request.headers,
  });

  const isAuthenticated = !!session?.user;

  if (isAuthenticated && isPublicRoute) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  if (!isAuthenticated && !isPublicRoute) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/auth).*)"],
};