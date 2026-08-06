"use client";

import React, { use } from "react";
import { LatexEditorView } from "@/components/editor/LatexEditorView";

interface ProjectEditorPageProps {
  params: Promise<{ id: string }>;
}

export default function ProjectEditorPage({ params }: ProjectEditorPageProps) {
  const resolvedParams = use(params);

  return (
    <div className="animate-fade-in -m-4 sm:-m-8">
      <LatexEditorView projectId={resolvedParams.id} />
    </div>
  );
}
