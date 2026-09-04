import { auth } from "@/lib/auth";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

async function handleWithTimeout(
  method: string,
  req: NextRequest
) {
  try {
    const timeoutPromise = new Promise<Response>((_, reject) => {
      const timer = setTimeout(() => {
        reject(new Error(`Auth ${method} ${req.nextUrl.pathname} timed out after 20s`));
      }, 20000);
      if (typeof timer === "object" && "unref" in timer) {
        (timer as any).unref();
      }
    });

    const response = await Promise.race([
      auth.handler(req),
      timeoutPromise,
    ]);

    return response;
  } catch (error: any) {
    console.error(`[Auth API Exception - ${method} ${req.nextUrl.pathname}]:`, error);
    return NextResponse.json(
      {
        error: "Authentication service error",
        message: error?.message || "An unexpected error occurred during authentication",
      },
      { status: error?.message?.includes("timed out") ? 504 : 500 }
    );
  }
}

export const GET = (req: NextRequest) => handleWithTimeout("GET", req);
export const POST = (req: NextRequest) => handleWithTimeout("POST", req);
export const PATCH = (req: NextRequest) => handleWithTimeout("PATCH", req);
export const PUT = (req: NextRequest) => handleWithTimeout("PUT", req);
export const DELETE = (req: NextRequest) => handleWithTimeout("DELETE", req);