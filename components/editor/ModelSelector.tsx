"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import { ChevronDown, Search, X, Check, Sparkles, Bot } from "lucide-react";

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
    if (activeModelName === "auto:smart") return "Auto (Smart)";
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
      {/* Trigger Button: Strictly bounded max width to prevent navbar overflow */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen((prev) => !prev)}
        className={`flex items-center gap-1.5 px-2 py-1 rounded-lg bg-[#00CC68]/10 text-[#00CC68] font-mono text-[11px] border border-[#00CC68]/25 font-bold hover:bg-[#00CC68]/20 transition-all cursor-pointer select-none max-w-[140px] sm:max-w-[170px] shrink min-w-0 ${
          disabled ? "opacity-60 cursor-not-allowed" : "active:scale-98"
        } ${triggerClassName}`}
        title={`AI Model: ${activeLabel}`}
      >
        <span
          className={`w-1.5 h-1.5 rounded-full shrink-0 ${
            disabled ? "bg-amber-400 animate-ping" : "bg-[#00CC68]"
          }`}
        />
        <span className="truncate max-w-[75px] sm:max-w-[110px]">
          {disabled ? "Reasoning..." : activeLabel}
        </span>
        <ChevronDown
          className={`w-3 h-3 text-[#00CC68] shrink-0 transition-transform duration-150 ${
            isOpen ? "rotate-180" : ""
          }`}
        />
      </button>

      {/* Desktop Dropdown Popover (Right Aligned, max 280px) */}
      {!isMobile && isOpen && (
        <div className="absolute right-0 top-full mt-1.5 w-72 max-w-[90vw] bg-zinc-900/95 backdrop-blur-md border border-zinc-700/80 rounded-2xl shadow-2xl z-[99999] overflow-hidden p-2.5 space-y-2 animate-in fade-in zoom-in-95 duration-100 font-sans">
          {/* Header & Search */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between px-1 text-[11px] font-archivo uppercase tracking-wider text-zinc-400 font-bold">
              <span>Select Model</span>
              <span className="text-[9px] text-[#00CC68] bg-[#00CC68]/15 px-1.5 py-0.2 rounded font-mono">
                {availableModels.reduce((acc, g) => acc + g.models.length, 0)} available
              </span>
            </div>

            <div className="relative">
              <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                ref={searchInputRef}
                type="text"
                placeholder="Search models..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full h-7 pl-8 pr-7 bg-zinc-950 border border-zinc-800 rounded-lg text-xs font-mono text-zinc-200 placeholder:text-zinc-500 outline-none focus:border-[#00CC68] transition-colors"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-white p-0.5"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>

          {/* Model List */}
          <div className="max-h-64 overflow-y-auto space-y-2 pr-1 scrollbar-thin scrollbar-thumb-zinc-700">
            {filteredGroups.length === 0 ? (
              <div className="py-4 text-center text-xs font-mono text-zinc-500">
                No matching models found
              </div>
            ) : (
              filteredGroups.map((group) => (
                <div key={group.name} className="space-y-1">
                  <div className="text-[10px] font-archivo uppercase tracking-wider text-[#00CC68] font-bold px-1.5 pt-1">
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
                          className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs font-mono flex items-center justify-between gap-2 transition-all cursor-pointer ${
                            isSelected
                              ? "bg-[#00CC68]/20 text-[#00CC68] font-bold border border-[#00CC68]/40"
                              : "text-zinc-300 hover:bg-zinc-800 hover:text-white border border-transparent"
                          }`}
                        >
                          <span className="truncate">
                            {model.label}
                            {model.default ? " (Default)" : ""}
                          </span>
                          {isSelected && (
                            <Check className="w-3.5 h-3.5 text-[#00CC68] shrink-0 stroke-[3]" />
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

      {/* Mobile Bottom Sheet (Full width, safe area padding, sticky search) */}
      {isMobile && isOpen && (
        <div className="fixed inset-0 z-[99999] flex flex-col justify-end bg-black/60 backdrop-blur-xs animate-in fade-in duration-150">
          <div className="w-full bg-zinc-900 border-t border-zinc-700/80 rounded-t-3xl shadow-2xl p-4 space-y-3 animate-in slide-in-from-bottom duration-200 font-sans max-h-[80vh] flex flex-col pb-[max(1.5rem,env(safe-area-inset-bottom))]">
            {/* Sheet Handle */}
            <div className="w-12 h-1.5 bg-zinc-700 rounded-full mx-auto shrink-0 mb-1" />

            {/* Header */}
            <div className="flex items-center justify-between border-b border-zinc-800 pb-2.5 shrink-0">
              <div className="flex items-center gap-2 font-archivo uppercase text-white font-bold text-xs tracking-wide">
                <Bot className="w-4 h-4 text-[#00CC68]" />
                <span>Select AI Model</span>
              </div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1.5 text-zinc-400 hover:text-white rounded-lg hover:bg-zinc-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Sticky Search Input */}
            <div className="relative shrink-0">
              <Search className="w-4 h-4 text-zinc-500 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                ref={searchInputRef}
                type="text"
                placeholder="Search models..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full h-9 pl-9 pr-8 bg-zinc-950 border border-zinc-800 rounded-xl text-xs font-mono text-zinc-200 placeholder:text-zinc-500 outline-none focus:border-[#00CC68]"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-400 p-1"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Scrolling List */}
            <div className="flex-1 overflow-y-auto space-y-3 pr-1 pt-1 min-h-0">
              {filteredGroups.length === 0 ? (
                <div className="py-8 text-center text-xs font-mono text-zinc-500">
                  No matching models found
                </div>
              ) : (
                filteredGroups.map((group) => (
                  <div key={group.name} className="space-y-1.5">
                    <div className="text-[10px] font-archivo uppercase tracking-widest text-[#00CC68] font-bold px-1">
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
                                ? "bg-[#00CC68]/20 text-[#00CC68] font-bold border border-[#00CC68]/40"
                                : "bg-zinc-950/60 text-zinc-300 hover:bg-zinc-800 border border-zinc-800/80"
                            }`}
                          >
                            <span className="truncate">
                              {model.label}
                              {model.default ? " (Default)" : ""}
                            </span>
                            {isSelected && (
                              <Check className="w-4 h-4 text-[#00CC68] shrink-0 stroke-[3]" />
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
