"use client";

import React from "react";
import { LatexEditorView } from "@/components/editor/LatexEditorView";

export default function EditorPage() {
  return (
    <div className="animate-fade-in -m-4 sm:-m-8">
      <LatexEditorView />
    </div>
  );
}
