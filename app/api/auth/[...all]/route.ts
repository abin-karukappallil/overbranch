import { auth } from "@/lib/auth";
import { toNextJsHandler } from "better-auth/next-js";
import { NextRequest } from "next/server";

const handlers = toNextJsHandler(auth.handler);

export const GET = async (req: NextRequest) => {
  try {
    return await handlers.GET(req);
  } catch (error) {
    console.error("[Auth API Exception - GET]:", error);
    throw error;
  }
};

export const POST = async (req: NextRequest) => {
  try {
    return await handlers.POST(req);
  } catch (error) {
    console.error("[Auth API Exception - POST]:", error);
    throw error;
  }
};