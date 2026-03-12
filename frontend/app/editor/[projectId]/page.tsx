import { redirect, notFound } from "next/navigation";
import { getSession } from "@/lib/get-session";
import { db } from "@/db/index";
import { projects } from "@/db/schema";
import { eq } from "drizzle-orm";
import EditorWorkspace from "./EditorWorkspace";

interface EditorPageProps {
    params: Promise<{ projectId: string }>;
}

export default async function EditorPage({ params }: EditorPageProps) {
    const session = await getSession();

    if (!session?.user) {
        redirect("/login");
    }

    const { projectId } = await params;

    const project = await db.query.projects.findFirst({
        where: eq(projects.id, projectId),
        with: {
            files: true,
            assets: true,
        },
    });

    if (!project) {
        notFound();
    }

    // Ownership check
    if (project.userId !== session.user.id) {
        redirect("/dashboard");
    }

    return (
        <EditorWorkspace
            projectId={project.id}
            projectName={project.name}
            initialFiles={project.files}
            initialAssets={project.assets}
        />
    );
}
