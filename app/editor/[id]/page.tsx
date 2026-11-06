"use client";

import React, { use } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { authClient } from "@/lib/auth-client";
import { trpc } from "@/trpc/client";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EditorSkeleton } from "@/components/ui/skeleton-loader";

const EditorLayout = dynamic(
  () => import("@/components/editor/EditorLayout").then((mod) => mod.EditorLayout),
  {
    ssr: false,
    loading: () => <EditorSkeleton label="Initializing editor workspace" />,
  }
);

interface StandaloneProjectEditorPageProps {
  params: Promise<{ id: string }>;
}

export default function StandaloneProjectEditorPage({ params }: StandaloneProjectEditorPageProps) {
  const resolvedParams = use(params);
  const projectId = resolvedParams.id;

  const { data: sessionData, isPending: isSessionLoading } = authClient.useSession();
  const {
    data: projectData,
    isLoading: isProjectLoading,
    isError,
  } = trpc.projects.getById.useQuery(
    { projectId },
    {
      enabled: !!projectId && !isSessionLoading,
      retry: 1,
      staleTime: 5 * 60 * 1000,
      placeholderData: (previousData) => previousData,
    }
  );

  React.useEffect(() => {
    if (projectData?.name) {
      document.title = `${projectData.name} — OverBranch`;
    } else {
      document.title = "OverBranch | Editor";
    }
  }, [projectData?.name]);

  if (isSessionLoading || isProjectLoading) {
    return <EditorSkeleton label="Verifying project access" />;
  }

  const isOwner = projectData?.isOwner;
  const isCoAuthor = projectData?.role === "Editor" || projectData?.role === "Viewer" || projectData?.role === "Owner";
  const isGuest = (projectData as any)?.isGuest;

  if (isError || !projectData || (!isOwner && !isCoAuthor && !isGuest)) {
    return (
      <div className="ob-app flex min-h-dvh flex-col items-center justify-center gap-4 bg-ob-bg p-6 text-center text-ob-text">
        <div className="flex max-w-sm flex-col gap-2">
          <h1 className="font-ob-title text-2xl font-normal text-ob-text">Access denied</h1>
          <p className="text-[13px] leading-5 text-ob-text-2">
            You do not have permission to view this project or the session has expired
          </p>
        </div>
        <Button asChild variant="ob-secondary" size="sm" className="mt-2 text-[13px]">
          <Link href="/dashboard">Return to dashboard</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="ob-app">
      <EditorLayout
        projectId={projectId}
        isGuest={isGuest}
        expiresAt={(projectData as any)?.expiresAt}
      />
    </div>
  );
}
