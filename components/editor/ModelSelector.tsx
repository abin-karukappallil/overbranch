"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import { ChevronDown, Search, X, Check, Bot } from "lucide-react";

export interface ModelOption {
  id: string;
  label: string;
  default?: boolean;
}

export interface ProviderGroup {
  name: string;
  models: ModelOption[];
}

interface ModelSelectorProps {
  activeModelName: string;
  onSelectModel: (modelId: string) => void;
  availableModels: ProviderGroup[];
  disabled?: boolean;
  className?: string;
  triggerClassName?: string;
}

export function ModelSelector({
  activeModelName,
  onSelectModel,
  availableModels,
  disabled = false,
  className = "",
  triggerClassName = "",
}: ModelSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [isMobile, setIsMobile] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  // Close dropdown on click outside
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent | TouchEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("touchstart", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("touchstart", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  // Focus search input on open
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        searchInputRef.current?.focus();
      }, 50);
    } else {
      setSearchQuery("");
    }
  }, [isOpen]);

  // Get active model label
  const activeLabel = useMemo(() => {
    if (activeModelName === "gemini-3.7-flash") return "Gemini 3.7 Flash";
    if (activeModelName === "auto:smart") return "FreeLLM Auto Smart";
    for (const group of availableModels) {
      const match = group.models.find((m) => m.id === activeModelName);
      if (match) return match.label;
    }
    return activeModelName;
  }, [activeModelName, availableModels]);

  // Filter models by search query
  const filteredGroups = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return availableModels;

    return availableModels
      .map((group) => {
        const matchedModels = group.models.filter(
          (m) =>
            m.label.toLowerCase().includes(query) ||
            m.id.toLowerCase().includes(query) ||
            group.name.toLowerCase().includes(query)
        );
        return {
          ...group,
          models: matchedModels,
        };
      })
      .filter((group) => group.models.length > 0);
  }, [availableModels, searchQuery]);

  const handleSelect = (modelId: string) => {
    onSelectModel(modelId);
    setIsOpen(false);
  };

  return (
    <div className={`relative inline-block ${className}`} ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen((prev) => !prev)}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-[#1A1C22] text-slate-800 dark:text-[#E2E4E9] font-mono text-[11px] border border-slate-200 dark:border-[#282A30] hover:border-slate-300 dark:hover:border-[#282A30] hover:bg-slate-200/70 dark:hover:bg-[#22242C] font-medium transition-all cursor-pointer select-none max-w-[140px] sm:max-w-[170px] shrink min-w-0 ${
          disabled ? "opacity-60 cursor-not-allowed" : "active:scale-98"
        } ${triggerClassName}`}
        title={`AI Model: ${activeLabel}`}
      >
        <span
          className={`w-1.5 h-1.5 rounded-full shrink-0 ${
            disabled ? "bg-amber-400 animate-ping" : "bg-emerald-600 dark:bg-[#10B981]"
          }`}
        />
        <span className="truncate max-w-[75px] sm:max-w-[110px]">
          {disabled ? "Reasoning..." : activeLabel}
        </span>
        <ChevronDown
          className={`w-3 h-3 text-slate-500 dark:text-[#9E9E9E] shrink-0 transition-transform duration-150 ${
            isOpen ? "rotate-180" : ""
          }`}
        />
      </button>

      {/* Desktop Dropdown Popover */}
      {!isMobile && isOpen && (
        <div className="absolute right-0 top-full mt-1.5 w-72 max-w-[90vw] bg-white dark:bg-[#141519] border border-slate-200 dark:border-[#282A30] rounded-2xl shadow-2xl z-[99999] overflow-hidden p-2.5 space-y-2 animate-in fade-in zoom-in-95 duration-100 font-sans">
          {/* Header & Search */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between px-1 text-[11px] font-archivo font-bold uppercase tracking-wider text-slate-500 dark:text-[#9E9E9E]">
              <span>Model Selection</span>
              <span className="text-[9px] text-emerald-700 dark:text-[#10B981] bg-slate-100 dark:bg-[#22242C] border border-slate-200 dark:border-[#282A30] px-1.5 py-0.2 rounded font-mono">
                {availableModels.reduce((acc, g) => acc + g.models.length, 0)} models
              </span>
            </div>

            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 dark:text-[#62666D] absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                ref={searchInputRef}
                type="text"
                placeholder="Search models..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full h-8 pl-8 pr-7 bg-slate-50 dark:bg-[#1A1C22] border border-slate-200 dark:border-[#282A30] rounded-xl text-xs font-mono text-slate-900 dark:text-[#E2E4E9] placeholder:text-slate-400 dark:placeholder:text-[#62666D] outline-none focus:ring-1 focus:ring-emerald-500 dark:focus:border-[#282A30] transition-colors"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-white p-0.5"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>

          {/* Model List */}
          <div className="max-h-64 overflow-y-auto space-y-2 pr-1 font-mono">
            {filteredGroups.length === 0 ? (
              <div className="py-4 text-center text-xs font-mono text-slate-400 dark:text-[#62666D]">
                No matching models found
              </div>
            ) : (
              filteredGroups.map((group) => (
                <div key={group.name} className="space-y-1">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-[#9E9E9E] font-medium px-1.5 pt-1">
                    {group.name}
                  </div>
                  <div className="space-y-0.5">
                    {group.models.map((model) => {
                      const isSelected = activeModelName === model.id;
                      return (
                        <button
                          key={model.id}
                          type="button"
                          onClick={() => handleSelect(model.id)}
                          className={`w-full text-left px-2.5 py-1.5 rounded-xl text-xs font-mono flex items-center justify-between gap-2 transition-all cursor-pointer ${
                            isSelected
                              ? "bg-emerald-50 dark:bg-[#22242C] text-slate-900 dark:text-[#E2E4E9] font-medium border border-emerald-200 dark:border-[#282A30]"
                              : "text-slate-600 dark:text-[#9E9E9E] hover:bg-slate-100 dark:hover:bg-[#1A1C22] hover:text-slate-900 dark:hover:text-[#E2E4E9] border border-transparent"
                          }`}
                        >
                          <span className="truncate">
                            {model.label}
                            {model.default ? " (Default)" : ""}
                          </span>
                          {isSelected && (
                            <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-[#10B981] shrink-0 stroke-[2.5]" />
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Mobile Bottom Sheet */}
      {isMobile && isOpen && (
        <div className="fixed inset-0 z-[99999] flex flex-col justify-end bg-black/60 dark:bg-black/80 animate-in fade-in duration-150 backdrop-blur-xs">
          <div className="w-full bg-white dark:bg-[#141519] border-t border-slate-200 dark:border-[#282A30] rounded-t-3xl shadow-2xl p-4 space-y-3 animate-in slide-in-from-bottom duration-200 font-mono max-h-[80vh] flex flex-col pb-[max(1.5rem,env(safe-area-inset-bottom))]">
            {/* Sheet Handle */}
            <div className="w-12 h-1.5 bg-slate-300 dark:bg-[#282A30] rounded-full mx-auto shrink-0 mb-1" />

            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-[#282A30] pb-2.5 shrink-0">
              <div className="flex items-center gap-2 text-slate-900 dark:text-[#E2E4E9] font-archivo font-bold text-xs tracking-wide">
                <Bot className="w-4 h-4 text-emerald-600 dark:text-[#10B981]" />
                <span>Select AI Model</span>
              </div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1.5 text-slate-400 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-white rounded-lg hover:bg-slate-100 dark:hover:bg-[#1A1C22] transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Sticky Search Input */}
            <div className="relative shrink-0">
              <Search className="w-4 h-4 text-slate-400 dark:text-[#62666D] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                ref={searchInputRef}
                type="text"
                placeholder="Search models..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full h-9 pl-9 pr-8 bg-slate-50 dark:bg-[#1A1C22] border border-slate-200 dark:border-[#282A30] rounded-xl text-xs font-mono text-slate-900 dark:text-[#E2E4E9] placeholder:text-slate-400 dark:placeholder:text-[#62666D] outline-none focus:ring-1 focus:ring-emerald-500 dark:focus:border-[#282A30]"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 dark:text-[#9E9E9E] p-1"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Scrolling List */}
            <div className="flex-1 overflow-y-auto space-y-3 pr-1 pt-1 min-h-0 font-mono">
              {filteredGroups.length === 0 ? (
                <div className="py-8 text-center text-xs font-mono text-slate-400 dark:text-[#62666D]">
                  No matching models found
                </div>
              ) : (
                filteredGroups.map((group) => (
                  <div key={group.name} className="space-y-1.5">
                    <div className="text-[10px] uppercase tracking-widest text-slate-500 dark:text-[#9E9E9E] font-medium px-1">
                      {group.name}
                    </div>
                    <div className="space-y-1">
                      {group.models.map((model) => {
                        const isSelected = activeModelName === model.id;
                        return (
                          <button
                            key={model.id}
                            type="button"
                            onClick={() => handleSelect(model.id)}
                            className={`w-full text-left px-3.5 py-2.5 rounded-xl text-xs font-mono flex items-center justify-between gap-3 transition-all cursor-pointer ${
                              isSelected
                                ? "bg-emerald-50 dark:bg-[#22242C] text-slate-900 dark:text-[#E2E4E9] font-medium border border-emerald-200 dark:border-[#282A30]"
                                : "bg-slate-50 dark:bg-[#1A1C22] text-slate-700 dark:text-[#9E9E9E] hover:bg-slate-100 dark:hover:bg-[#22242C] hover:text-slate-900 dark:hover:text-[#E2E4E9] border border-slate-200 dark:border-[#282A30]"
                            }`}
                          >
                            <span className="truncate">
                              {model.label}
                              {model.default ? " (Default)" : ""}
                            </span>
                            {isSelected && (
                              <Check className="w-4 h-4 text-emerald-600 dark:text-[#10B981] shrink-0 stroke-[2.5]" />
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

