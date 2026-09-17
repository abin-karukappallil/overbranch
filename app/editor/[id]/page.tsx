"use client";

import React, { use } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { authClient } from "@/lib/auth-client";
import { trpc } from "@/trpc/client";
import { ShieldAlert, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

const EditorLayout = dynamic(
  () => import("@/components/editor/EditorLayout").then((mod) => mod.EditorLayout),
  {
    ssr: false,
    loading: () => (
      <div className="flex flex-col items-center justify-center min-h-screen bg-background text-muted-foreground gap-3">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
        <span className="text-xs font-mono">Initializing editor workspace...</span>
      </div>
    ),
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
    error,
  } = trpc.projects.getById.useQuery(
    { projectId },
    {
      enabled: !!projectId && !isSessionLoading,
      retry: 1,
      staleTime: 5 * 60 * 1000,
      placeholderData: (previousData) => previousData,
    }
  );

  if (isSessionLoading || isProjectLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-[#0E0F12] text-[#9E9E9E] gap-3">
        <Loader2 className="w-8 h-8 animate-spin text-[#10B981]" />
        <span className="text-xs font-mono">Verifying project access permissions...</span>
      </div>
    );
  }

  const currentUserId = sessionData?.user?.id;
  const isOwner = projectData?.isOwner;
  const isCoAuthor = projectData?.role === "Editor" || projectData?.role === "Viewer" || projectData?.role === "Owner";
  const isGuest = (projectData as any)?.isGuest;

  if (isError || !projectData || (!isOwner && !isCoAuthor && !isGuest)) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-[#0E0F12] text-[#E2E4E9] p-6 text-center space-y-6 animate-fade-in">
        <div className="p-4 rounded-2xl bg-[#1A1C22] border border-[#282A30] text-rose-400">
          <ShieldAlert className="w-12 h-12" />
        </div>
        <div className="space-y-2 max-w-md">
          <h1 className="text-2xl font-archivo font-bold tracking-tight text-[#E2E4E9]">Access Denied</h1>
          <p className="text-sm text-[#9E9E9E]">
            You do not have permission to view this project or the guest session has expired.
          </p>
        </div>
        <Button asChild size="lg" className="bg-[#22242C] hover:bg-[#2A2C36] text-[#E2E4E9] border border-[#282A30] rounded-xl font-archivo font-bold px-6">
          <Link href="/dashboard">Return to Dashboard</Link>
        </Button>
      </div>
    );
  }

  return (
    <EditorLayout
      projectId={projectId}
      isGuest={isGuest}
      expiresAt={(projectData as any)?.expiresAt}
    />
  );
}

