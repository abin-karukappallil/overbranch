import { redirect } from "next/navigation";
import { getSession } from "@/lib/get-session";
import { db } from "@/db/index";
import { projects } from "@/db/schema";
import { eq, desc } from "drizzle-orm";
import DashboardClient from "./DashboardClient";

export default async function DashboardPage() {
    const session = await getSession();

    if (!session?.user) {
        redirect("/login");
    }

    const userProjects = await db
        .select()
        .from(projects)
        .where(eq(projects.userId, session.user.id))
        .orderBy(desc(projects.updatedAt));

    return (
        <DashboardClient
            initialProjects={userProjects}
            userName={session.user.name}
            userEmail={session.user.email}
        />
    );
}
