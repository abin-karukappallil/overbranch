"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Search, Presentation, Sparkles, Loader2, ArrowRight, FolderPlus, Plus } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { trpc } from "@/trpc/client";

export default function TemplatesPage() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [submittingId, setSubmittingId] = useState<string | null>(null);

  // Project Name Modal Prompt state
  const [selectedTemplate, setSelectedTemplate] = useState<{ id: string; name: string } | null>(null);
  const [projectNameInput, setProjectNameInput] = useState("");

  const { data: templates, isLoading } = trpc.templates.listTemplates.useQuery({
    search,
    category: categoryFilter,
  });

  const useTemplateMutation = trpc.templates.useTemplate.useMutation({
    onSuccess: (data) => {
      toast.success(`Project "${data.name}" created from template!`);
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

  // Extract unique categories for filter
  const rawTemplates = templates || [];
  const categories = Array.from(new Set(rawTemplates.map((t) => t.category))).filter(Boolean);

  return (
    <div className="space-y-8 animate-fade-in pb-16 text-slate-900 dark:text-[#E2E4E9] max-w-7xl mx-auto">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-slate-200 dark:border-[#282A30] pb-6">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-slate-100 dark:bg-[#1E2026] border border-slate-200 dark:border-[#282A30] text-slate-600 dark:text-[#9E9E9E] text-[11px] font-mono">
            <Sparkles className="w-3.5 h-3.5 text-emerald-600 dark:text-[#E2E4E9]" />
            <span>Curated Catalog</span>
          </div>
          <h1 className="text-xl sm:text-3xl font-archivo font-bold tracking-tight text-slate-900 dark:text-[#E2E4E9] flex items-center gap-3">
            Template Gallery
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 dark:text-[#9E9E9E]">
            Start with a pre-configured LaTeX template for research papers, seminar slides, thesis chapters, and resumes.
          </p>
        </div>

        {/* Filter and Search Bar */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 font-mono">
          <div className="relative flex-1 sm:w-72">
            <Input
              placeholder="Search templates..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-9 text-xs pl-9 bg-white dark:bg-[#1A1C22] border-slate-200 dark:border-[#282A30] text-slate-900 dark:text-[#E2E4E9] placeholder:text-slate-400 dark:placeholder:text-[#62666D] rounded-lg focus-visible:ring-1 focus-visible:ring-emerald-500 dark:focus-visible:ring-[#383B46]"
            />
            <Search className="w-4 h-4 text-slate-400 dark:text-[#62666D] absolute left-3 top-1/2 -translate-y-1/2" />
          </div>

          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="h-9 px-3 text-xs rounded-lg border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#1A1C22] text-slate-900 dark:text-[#E2E4E9] outline-none font-mono cursor-pointer hover:border-slate-300 dark:hover:border-[#383B46] transition-colors"
          >
            <option value="all">All Categories</option>
            {categories.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Loading Skeletons */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Card key={i} className="bg-white dark:bg-[#141519] border-slate-200 dark:border-[#282A30] rounded-xl overflow-hidden animate-pulse p-4 space-y-4">
              <div className="w-full h-48 bg-slate-100 dark:bg-[#1A1C22] rounded-lg" />
              <div className="h-5 w-2/3 bg-slate-100 dark:bg-[#1A1C22] rounded" />
              <div className="h-4 w-full bg-slate-100/60 dark:bg-[#1A1C22]/60 rounded" />
              <div className="h-9 w-full bg-slate-100 dark:bg-[#1A1C22] rounded-lg" />
            </Card>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && rawTemplates.length === 0 && (
        <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-slate-200 dark:border-[#282A30] rounded-xl bg-white dark:bg-[#141519] space-y-4">
          <div className="p-4 rounded-xl bg-slate-100 dark:bg-[#1A1C22] text-slate-500 dark:text-[#9E9E9E]">
            <Presentation className="w-10 h-10 text-slate-900 dark:text-[#E2E4E9]" />
          </div>
          <h3 className="text-base font-archivo font-bold text-slate-900 dark:text-[#E2E4E9]">No Templates Found</h3>
          <p className="text-xs text-slate-500 dark:text-[#9E9E9E] max-w-sm font-sans">
            No templates matched your search criteria. Try clearing search or selecting another category filter.
          </p>
          <Button
            onClick={() => {
              setSearch("");
              setCategoryFilter("all");
            }}
            variant="outline"
            className="h-8 text-xs font-mono border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] hover:bg-slate-100 dark:hover:bg-[#22242C] text-slate-900 dark:text-[#E2E4E9] rounded-lg"
          >
            Clear Filters
          </Button>
        </div>
      )}

      {/* Template Grid */}
      {!isLoading && rawTemplates.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {rawTemplates.map((tmpl, idx) => {
            const isSubmitting = submittingId === tmpl.id;
            return (
              <motion.div
                key={tmpl.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, delay: idx * 0.04 }}
              >
                <Card className="group bg-white dark:bg-[#141519] border-slate-200 dark:border-[#282A30] hover:border-slate-300 dark:hover:border-[#383B46] rounded-xl overflow-hidden transition-all duration-200 flex flex-col justify-between h-full shadow-sm dark:shadow-none">
                  {/* Card Thumbnail Preview Container */}
                  <div className="relative w-full aspect-[3/2] bg-slate-50 dark:bg-[#1A1C22] overflow-hidden border-b border-slate-200 dark:border-[#282A30] group">
                    <img
                      src={tmpl.thumbnail}
                      alt={tmpl.name}
                      className="w-full h-full object-contain object-top p-2 bg-slate-50 dark:bg-[#1A1C22] group-hover:scale-102 transition-transform duration-300"
                    />

                    {/* Category Badge overlay */}
                    <div className="absolute top-3 left-3">
                      <span className="px-2.5 py-1 rounded-lg bg-white/90 dark:bg-[#141519]/90 backdrop-blur-md text-slate-700 dark:text-[#9E9E9E] font-mono text-[10px] font-semibold border border-slate-200 dark:border-[#282A30] uppercase tracking-wider shadow-md">
                        {tmpl.category}
                      </span>
                    </div>
                  </div>

                  {/* Card Body */}
                  <div className="p-5 space-y-3 flex-1 flex flex-col justify-between">
                    <div className="space-y-1.5">
                      <h3 className="font-archivo font-bold text-sm text-slate-900 dark:text-[#E2E4E9] group-hover:text-emerald-600 dark:group-hover:text-white transition-colors leading-snug">
                        {tmpl.name}
                      </h3>
                      <p className="text-xs text-slate-500 dark:text-[#9E9E9E] line-clamp-2 leading-relaxed font-sans">
                        {tmpl.description}
                      </p>
                    </div>

                    {/* Use Template Action Button */}
                    <div className="pt-3 border-t border-slate-100 dark:border-[#282A30]">
                      <Button
                        onClick={() => handleOpenPrompt(tmpl.id, tmpl.name)}
                        disabled={isSubmitting || submittingId !== null}
                        className="w-full bg-emerald-600 hover:bg-emerald-700 dark:bg-[#22242C] dark:hover:bg-[#2A2C36] text-white dark:text-[#E2E4E9] font-archivo font-bold text-xs rounded-lg h-8 border border-emerald-600 dark:border-[#282A30] shadow-sm cursor-pointer transition-all flex items-center justify-center gap-2"
                      >
                        {isSubmitting ? (
                          <>
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            <span>Initializing Workspace...</span>
                          </>
                        ) : (
                          <>
                            <Plus className="w-3.5 h-3.5" />
                            <span>Use Template</span>
                          </>
                        )}
                      </Button>
                    </div>
                  </div>
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Project Name Input Dialog Modal */}
      <Dialog open={selectedTemplate !== null} onOpenChange={(open) => !open && setSelectedTemplate(null)}>
        <DialogContent className="sm:max-w-md bg-white dark:bg-[#141519] border-slate-200 dark:border-[#282A30] text-slate-900 dark:text-[#E2E4E9] rounded-xl p-6 shadow-2xl">
          <DialogHeader className="space-y-1.5">
            <DialogTitle className="text-base font-archivo font-bold text-slate-900 dark:text-[#E2E4E9] flex items-center gap-2">
              <FolderPlus className="w-4 h-4 text-emerald-600 dark:text-[#E2E4E9]" />
              Name Your Project
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-500 dark:text-[#9E9E9E] leading-relaxed font-sans">
              Give your new workspace a name before initializing it from{" "}
              <span className="text-slate-900 dark:text-[#E2E4E9] font-mono font-medium">{selectedTemplate?.name}</span>.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleConfirmCreate} className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs font-mono font-medium text-slate-600 dark:text-[#9E9E9E] uppercase tracking-wider">
                Project Name
              </Label>
              <Input
                value={projectNameInput}
                onChange={(e) => setProjectNameInput(e.target.value)}
                placeholder="e.g. Thesis Chapter 1"
                className="h-10 bg-slate-50 dark:bg-[#1A1C22] border-slate-200 dark:border-[#282A30] text-slate-900 dark:text-[#E2E4E9] placeholder:text-slate-400 dark:placeholder:text-[#62666D] rounded-lg focus-visible:ring-1 focus-visible:ring-emerald-500 dark:focus-visible:ring-[#383B46] text-xs font-mono"
                autoFocus
              />
            </div>

            <DialogFooter className="flex items-center justify-end gap-2 pt-2 font-mono">
              <Button
                type="button"
                variant="outline"
                onClick={() => setSelectedTemplate(null)}
                className="border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] hover:bg-slate-100 dark:hover:bg-[#22242C] text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] text-xs rounded-lg h-8 px-4"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={!projectNameInput.trim() || submittingId !== null}
                className="bg-emerald-600 hover:bg-emerald-700 dark:bg-[#22242C] dark:hover:bg-[#2A2C36] text-white dark:text-[#E2E4E9] font-archivo font-bold text-xs rounded-lg h-8 px-5 flex items-center gap-1.5 shadow-sm border border-emerald-600 dark:border-[#282A30] cursor-pointer"
              >
                {submittingId !== null ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Initializing...</span>
                  </>
                ) : (
                  <>
                    <span>Create & Launch</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </>
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

