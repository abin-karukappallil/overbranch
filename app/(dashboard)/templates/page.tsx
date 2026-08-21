"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Search, Presentation, Sparkles, Loader2, ArrowRight, FolderPlus } from "lucide-react";
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

  const { data: templates, isLoading, isError } = trpc.templates.listTemplates.useQuery({
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
    <div className="space-y-8 animate-fade-in pb-16 font-sans text-zinc-100 max-w-7xl mx-auto">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-zinc-800/80 pb-6">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#00CC68]/10 border border-[#00CC68]/20 text-[#00CC68] text-xs font-mono font-bold tracking-wider uppercase">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Template Gallery</span>
          </div>
          <h1 className="text-2xl sm:text-4xl font-archivo font-black uppercase tracking-tight text-white flex items-center gap-3">
            Quick Start
          </h1>
          <p className="text-sm sm:text-base text-zinc-400 font-sans italic">
            Start with a professional LaTeX template for resumes, letters, or presentations
          </p>
        </div>

        {/* Filter and Search Bar */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 font-mono">
          <div className="relative flex-1 sm:w-72">
            <Input
              placeholder="Search templates..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-10 text-xs pl-9 bg-zinc-900 border-zinc-800 text-white rounded-xl focus-visible:ring-2 focus-visible:ring-[#00CC68]"
            />
            <Search className="w-4 h-4 text-zinc-500 absolute left-3 top-1/2 -translate-y-1/2" />
          </div>

          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="h-10 px-3.5 text-xs rounded-xl border border-zinc-800 bg-zinc-900 text-white outline-none font-mono cursor-pointer hover:border-zinc-700 transition-colors"
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
            <Card key={i} className="bg-zinc-900 border-zinc-800 rounded-2xl overflow-hidden animate-pulse p-4 space-y-4">
              <div className="w-full h-48 bg-zinc-800/60 rounded-xl" />
              <div className="h-5 w-2/3 bg-zinc-800/80 rounded" />
              <div className="h-4 w-full bg-zinc-800/40 rounded" />
              <div className="h-10 w-full bg-zinc-800/60 rounded-xl" />
            </Card>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && rawTemplates.length === 0 && (
        <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-zinc-800 rounded-3xl bg-zinc-900/50 space-y-4">
          <div className="p-4 rounded-2xl bg-zinc-800/40 text-zinc-500">
            <Presentation className="w-10 h-10 text-[#00CC68]" />
          </div>
          <h3 className="text-lg font-archivo font-bold text-white">No Templates Found</h3>
          <p className="text-xs text-zinc-400 max-w-sm">
            No presentation templates matched your search criteria. Try clearing search or selecting another category filter.
          </p>
          <Button
            onClick={() => {
              setSearch("");
              setCategoryFilter("all");
            }}
            className="bg-zinc-800 hover:bg-zinc-700 text-white font-mono text-xs rounded-xl"
          >
            Reset Filters
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
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, delay: idx * 0.05 }}
              >
                <Card className="group bg-zinc-900 border-zinc-800 hover:border-[#00CC68]/50 rounded-2xl overflow-hidden transition-all duration-300 flex flex-col justify-between h-full shadow-xl hover:shadow-[#00CC68]/5">
                  {/* Card Thumbnail Preview Container */}
                  <div className="relative w-full aspect-[3/2] bg-zinc-950 overflow-hidden border-b border-zinc-800/80 group">
                    {/* Thumbnail Image */}
                    <img
                      src={tmpl.thumbnail}
                      alt={tmpl.name}
                      className="w-full h-full object-contain object-top p-2 bg-zinc-950 group-hover:scale-105 transition-transform duration-500"
                    />
                    
                    {/* Category Badge overlay */}
                    <div className="absolute top-3 left-3">
                      <span className="px-2.5 py-1 rounded-lg bg-zinc-950/80 backdrop-blur-md text-[#00CC68] font-mono text-[10px] font-bold border border-zinc-800 uppercase tracking-wider shadow-md">
                        {tmpl.category}
                      </span>
                    </div>

                    <div className="absolute inset-0 bg-gradient-to-t from-zinc-950 via-transparent to-transparent opacity-40 group-hover:opacity-20 transition-opacity" />
                  </div>

                  {/* Card Body */}
                  <div className="p-5 space-y-3 flex-1 flex flex-col justify-between">
                    <div className="space-y-2">
                      <h3 className="font-archivo font-bold text-lg text-white group-hover:text-[#00CC68] transition-colors leading-snug">
                        {tmpl.name}
                      </h3>
                      <p className="text-xs text-zinc-400 line-clamp-2 leading-relaxed font-sans">
                        {tmpl.description}
                      </p>
                    </div>

                    {/* Use Template Action Button */}
                    <div className="pt-3 border-t border-zinc-800/60">
                      <Button
                        onClick={() => handleOpenPrompt(tmpl.id, tmpl.name)}
                        disabled={isSubmitting || submittingId !== null}
                        className="w-full bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold text-xs uppercase tracking-wider rounded-xl h-11 border border-black shadow-[3px_3px_0px_0px_#000000] cursor-pointer transition-all duration-150 active:translate-x-[2px] active:translate-y-[2px] active:shadow-none flex items-center justify-center gap-2"
                      >
                        {isSubmitting ? (
                          <>
                            <Loader2 className="w-4 h-4 animate-spin stroke-[2.5]" />
                            <span>Creating Workspace...</span>
                          </>
                        ) : (
                          <>
                            <span>Use Template</span>
                            <ArrowRight className="w-4 h-4 stroke-[2.5]" />
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
        <DialogContent className="sm:max-w-md bg-zinc-900 border-zinc-800 text-white rounded-2xl p-6 shadow-2xl">
          <DialogHeader className="space-y-2">
            <DialogTitle className="text-xl font-archivo font-bold text-white flex items-center gap-2">
              <FolderPlus className="w-5 h-5 text-[#00CC68]" />
              Name Your Project
            </DialogTitle>
            <DialogDescription className="text-xs text-zinc-400 font-sans leading-relaxed">
              Give your new workspace a name before initializing it from{" "}
              <span className="text-[#00CC68] font-mono font-semibold">{selectedTemplate?.name}</span>.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleConfirmCreate} className="space-y-4 py-2">
            <div className="space-y-2">
              <Label className="text-xs font-mono font-bold text-zinc-300 uppercase tracking-wider">
                Project Name
              </Label>
              <Input
                value={projectNameInput}
                onChange={(e) => setProjectNameInput(e.target.value)}
                placeholder="e.g. Q3 Research Seminar Slides"
                className="h-11 bg-zinc-950 border-zinc-800 text-white rounded-xl focus-visible:ring-2 focus-visible:ring-[#00CC68] text-sm font-sans"
                autoFocus
              />
            </div>

            <DialogFooter className="flex items-center justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setSelectedTemplate(null)}
                className="border-zinc-800 hover:bg-zinc-800 text-zinc-300 font-mono text-xs rounded-xl h-10 px-4"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={!projectNameInput.trim() || submittingId !== null}
                className="bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold text-xs uppercase tracking-wider rounded-xl h-10 px-5 flex items-center gap-2"
              >
                {submittingId !== null ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Initializing...</span>
                  </>
                ) : (
                  <>
                    <span>Continue & Start</span>
                    <ArrowRight className="w-4 h-4" />
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
