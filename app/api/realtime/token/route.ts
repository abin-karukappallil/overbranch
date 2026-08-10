import { NextRequest, NextResponse } from "next/server";
import { SignJWT } from "jose";
import { auth } from "@/lib/auth";
import { db } from "@/db";
import { projects, projectMembers } from "@/db/schema";
import { eq, and } from "drizzle-orm";

const JWT_SECRET = process.env.SUPABASE_JWT_SECRET || process.env.BETTER_AUTH_SECRET || "";

/**
 * GET /api/realtime/token?projectId=...
 *
 * Auth bridge (spec section 12):
 * 1. Validates Better Auth session from request cookies
 * 2. Checks project membership via Drizzle
 * 3. Mints a short-lived JWT compatible with Supabase Realtime
 * 4. Returns { token } to the client
 */
export async function GET(request: NextRequest) {
  try {
    // 1. Validate Better Auth session
    const session = await auth.api.getSession({
      headers: request.headers,
    });

    if (!session?.user) {
      return NextResponse.json(
        { error: "Not authenticated" },
        { status: 401 }
      );
    }

    // 2. Validate projectId parameter
    const projectId = request.nextUrl.searchParams.get("projectId");
    if (!projectId) {
      return NextResponse.json(
        { error: "projectId is required" },
        { status: 400 }
      );
    }

    // 3. Verify project membership
    const [project] = await db
      .select()
      .from(projects)
      .where(eq(projects.id, projectId));

    if (!project) {
      return NextResponse.json(
        { error: "Project not found" },
        { status: 404 }
      );
    }

    let memberRole: string = "none";

    if (project.ownerId === session.user.id) {
      memberRole = "Owner";
    } else {
      const [member] = await db
        .select()
        .from(projectMembers)
        .where(
          and(
            eq(projectMembers.projectId, projectId),
            eq(projectMembers.userId, session.user.id)
          )
        );

      if (!member) {
        return NextResponse.json(
          { error: "Not a member of this project" },
          { status: 403 }
        );
      }

      memberRole = member.role;
    }

    // 4. Mint a short-lived JWT (60s) with Supabase-compatible claims
    const secret = new TextEncoder().encode(JWT_SECRET);

    const token = await new SignJWT({
      sub: session.user.id,
      role: "authenticated",
      project_id: projectId,
      member_role: memberRole,
      user_name: session.user.name,
      user_email: session.user.email,
      user_image: session.user.image || null,
    })
      .setProtectedHeader({ alg: "HS256", typ: "JWT" })
      .setIssuedAt()
      .setExpirationTime("60s")
      .setIssuer("overbranch")
      .setAudience("authenticated")
      .sign(secret);

    return NextResponse.json({ token });
  } catch (error) {
    console.error("[realtime/token] Error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
