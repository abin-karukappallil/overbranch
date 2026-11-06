"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Search, Loader2, ArrowRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { toast } from "sonner";
import { trpc } from "@/trpc/client";

const TEMPLATE_GRID = "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3";
const DIALOG_OVERLAY = "fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4";
const DIALOG_PANEL =
  "flex w-full max-w-md flex-col gap-4 rounded-xl border border-ob-line bg-ob-card p-6 text-ob-text shadow-[0_16px_48px_rgba(0,0,0,0.32)]";
const DIALOG_TITLE = "text-[15px] leading-6 font-medium text-ob-text";
const DIALOG_BODY = "text-[13px] leading-5 text-ob-text-2";
const DIALOG_FOOTER = "flex justify-end gap-2 pt-2";

export default function TemplatesPage() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [submittingId, setSubmittingId] = useState<string | null>(null);

  const [selectedTemplate, setSelectedTemplate] = useState<{ id: string; name: string } | null>(null);
  const [projectNameInput, setProjectNameInput] = useState("");

  useEffect(() => {
    document.title = "OverBranch | Templates";
  }, []);

  const { data: templates, isLoading } = trpc.templates.listTemplates.useQuery({
    search,
    category: categoryFilter,
  });

  const useTemplateMutation = trpc.templates.useTemplate.useMutation({
    onSuccess: (data) => {
      toast.success(`Project "${data.name}" created`);
      setSelectedTemplate(null);
      router.push(`/editor/${data.projectId || data.id}`);
    },
    onError: (error) => {
      setSubmittingId(null);
      toast.error(error.message || "Failed to create project from template");
    },
  });

  const handleOpenPrompt = (templateId: string, templateName: string) => {
    setSelectedTemplate({ id: templateId, name: templateName });
    setProjectNameInput(templateName);
  };

  const handleConfirmCreate = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!selectedTemplate || !projectNameInput.trim()) return;

    setSubmittingId(selectedTemplate.id);
    useTemplateMutation.mutate({
      templateId: selectedTemplate.id,
      name: projectNameInput.trim(),
    });
  };

  const rawTemplates = templates || [];
  const categories = Array.from(new Set(rawTemplates.map((t) => t.category))).filter(Boolean);
  const templateCount = rawTemplates.length;

  return (
    <div className="ob-enter flex flex-col gap-8 pb-16">
      {/* Header */}
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex items-baseline gap-3">
            <h1 className="font-ob-title text-[32px] leading-[1.15] font-normal text-ob-text">Templates</h1>
            {!isLoading && (
              <span className="font-mono text-[13px] text-ob-muted tabular-nums">
                {search || categoryFilter !== "all"
                  ? `${templateCount} matching`
                  : `${templateCount} ${templateCount === 1 ? "template" : "templates"}`}
              </span>
            )}
          </div>
          <p className="max-w-2xl text-sm leading-[22px] text-ob-text-2">
            Pre-configured LaTeX templates for research papers, presentations, theses and resumes
          </p>
        </div>
      </header>

      {/* Filter and Search Bar */}
      <div className="flex flex-col gap-3 rounded-xl border border-ob-line bg-ob-card p-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ob-muted" />
          <Input
            placeholder="Search templates"
            aria-label="Search templates"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-9 rounded-lg border-ob-line bg-ob-raised pr-3 pl-9 text-sm text-ob-text shadow-none placeholder:text-ob-muted md:text-sm dark:bg-ob-raised"
          />
        </div>

        <div className="flex items-center gap-2">
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="h-9 cursor-pointer rounded-lg border border-ob-line bg-ob-raised px-3 text-xs text-ob-text transition-colors hover:border-ob-text/15"
          >
            <option value="all">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Loading Skeletons */}
      {isLoading && (
        <div className={TEMPLATE_GRID}>
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="flex flex-col overflow-hidden rounded-xl border border-ob-line bg-ob-card"
            >
              <div className="aspect-[3/2] w-full bg-ob-deep" />
              <div className="flex flex-1 flex-col gap-3 p-5">
                <div className="h-4 w-1/2 rounded bg-ob-raised" />
                <div className="h-3 w-full rounded bg-ob-raised" />
                <div className="mt-auto h-8 w-full rounded bg-ob-raised" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && rawTemplates.length === 0 && (
        <EmptyState
          title="No templates found"
          description="No templates match your current search or category filter"
          primaryActionLabel="Clear filters"
          onPrimaryAction={() => {
            setSearch("");
            setCategoryFilter("all");
          }}
        />
      )}

      {/* Template Grid */}
      {!isLoading && rawTemplates.length > 0 && (
        <div className={TEMPLATE_GRID}>
          {rawTemplates.map((tmpl) => {
            const isSubmitting = submittingId === tmpl.id;
            return (
              <article
                key={tmpl.id}
                className="group flex flex-col overflow-hidden rounded-xl border border-ob-line bg-ob-card transition-colors hover:border-ob-text/15"
              >
                {/* Thumbnail Preview */}
                <div className="relative aspect-[3/2] w-full overflow-hidden border-b border-ob-line bg-ob-deep p-4">
                  <img
                    src={tmpl.thumbnail}
                    alt={tmpl.name}
                    className="h-full w-full object-contain object-top transition-transform duration-200 group-hover:-translate-y-0.5"
                  />
                  <div className="absolute top-3 left-3">
                    <span className="rounded-md border border-ob-line bg-ob-card/90 px-2 py-0.5 font-mono text-[11px] text-ob-muted backdrop-blur-sm">
                      {tmpl.category}
                    </span>
                  </div>
                </div>

                {/* Card Body */}
                <div className="flex flex-1 flex-col justify-between gap-4 p-5">
                  <div className="flex flex-col gap-1.5">
                    <h3 className="text-[15px] leading-[22px] font-medium text-ob-text">
                      {tmpl.name}
                    </h3>
                    <p className="line-clamp-2 text-[13px] leading-5 text-ob-text-2">
                      {tmpl.description}
                    </p>
                  </div>

                  <div className="pt-2">
                    <Button
                      variant="ob-primary"
                      size="sm"
                      onClick={() => handleOpenPrompt(tmpl.id, tmpl.name)}
                      disabled={isSubmitting || submittingId !== null}
                      className="w-full cursor-pointer text-[13px]"
                    >
                      {isSubmitting ? (
                        <>
                          <Loader2 className="size-3.5 animate-spin" />
                          <span>Creating document\u2026</span>
                        </>
                      ) : (
                        <span>Use template</span>
                      )}
                    </Button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {/* Project Name Prompt Modal */}
      {selectedTemplate && (
        <div className={DIALOG_OVERLAY} onClick={() => setSelectedTemplate(null)}>
          <div className={DIALOG_PANEL} onClick={(e) => e.stopPropagation()}>
            <div className="flex flex-col gap-1">
              <h3 className={DIALOG_TITLE}>Name your project</h3>
              <p className={DIALOG_BODY}>
                Creating from <span className="font-medium text-ob-text">{selectedTemplate.name}</span>
              </p>
            </div>

            <form onSubmit={handleConfirmCreate} className="flex flex-col gap-4">
              <Input
                value={projectNameInput}
                onChange={(e) => setProjectNameInput(e.target.value)}
                placeholder="Project title"
                autoFocus
                className="h-9 rounded-lg border-ob-line bg-ob-raised px-3 text-sm text-ob-text shadow-none placeholder:text-ob-muted"
              />

              <div className={DIALOG_FOOTER}>
                <Button
                  type="button"
                  variant="ob-quiet"
                  size="sm"
                  onClick={() => setSelectedTemplate(null)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="ob-primary"
                  size="sm"
                  disabled={!projectNameInput.trim() || submittingId !== null}
                >
                  {submittingId !== null ? (
                    <>
                      <Loader2 className="size-3.5 animate-spin" />
                      <span>Creating\u2026</span>
                    </>
                  ) : (
                    <>
                      <span>Create and open</span>
                      <ArrowRight className="size-3.5" />
                    </>
                  )}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
