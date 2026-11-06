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
    if (activeModelName === "auto:smart") return "FreeLLM Auto";
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
      .map((group) => ({
        ...group,
        models: group.models.filter(
          (m) =>
            m.label.toLowerCase().includes(query) ||
            m.id.toLowerCase().includes(query) ||
            group.name.toLowerCase().includes(query)
        ),
      }))
      .filter((group) => group.models.length > 0);
  }, [searchQuery, availableModels]);

  const handleSelect = (modelId: string) => {
    onSelectModel(modelId);
    setIsOpen(false);
    setSearchQuery("");
  };

  const totalModelCount = availableModels.reduce((acc, g) => acc + g.models.length, 0);

  return (
    <div ref={dropdownRef} className={`relative shrink min-w-0 ${className}`}>
      {/* Trigger Button */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen((prev) => !prev)}
        className={`flex h-7 min-w-0 max-w-[140px] shrink cursor-pointer select-none items-center gap-1.5 rounded-lg border border-ob-line bg-ob-raised px-2 font-mono text-xs text-ob-text transition-colors hover:bg-ob-card hover:border-ob-text/15 sm:max-w-[170px] ${
          disabled ? "cursor-not-allowed opacity-60" : ""
        } ${triggerClassName}`}
        title={`AI model: ${activeLabel}`}
      >
        <span
          className={`size-1.5 shrink-0 rounded-full ${
            disabled ? "bg-ob-warn animate-pulse" : "bg-ob-accent"
          }`}
        />
        <span className="truncate max-w-[85px] sm:max-w-[115px]">
          {disabled ? "Thinking\u2026" : activeLabel}
        </span>
        <ChevronDown
          className={`size-3 shrink-0 text-ob-muted transition-transform duration-150 ${
            isOpen ? "rotate-180" : ""
          }`}
        />
      </button>

      {/* Desktop Dropdown Popover */}
      {!isMobile && isOpen && (
        <div className="absolute right-0 top-full z-[99999] mt-1.5 w-72 max-w-[90vw] space-y-2 overflow-hidden rounded-xl border border-ob-line bg-ob-card p-2.5 font-mono text-xs text-ob-text shadow-[0_12px_36px_rgba(0,0,0,0.24)]">
          {/* Header & Search */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between px-1 text-xs">
              <span className="font-medium text-ob-text">Model</span>
              <span className="font-mono text-[11px] text-ob-muted tabular-nums">
                {totalModelCount} models
              </span>
            </div>

            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ob-muted" />
              <input
                ref={searchInputRef}
                type="text"
                placeholder="Search models"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-8 w-full rounded-lg border border-ob-line bg-ob-raised pr-7 pl-8 font-mono text-xs text-ob-text placeholder:text-ob-muted outline-none transition-colors focus:border-ob-text/20"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute top-1/2 right-2 -translate-y-1/2 p-0.5 text-ob-muted hover:text-ob-text"
                >
                  <X className="size-3" />
                </button>
              )}
            </div>
          </div>

          {/* Model List */}
          <div className="max-h-64 space-y-2 overflow-y-auto pr-1 font-mono">
            {filteredGroups.length === 0 ? (
              <div className="py-4 text-center text-xs text-ob-muted">
                No matching models found
              </div>
            ) : (
              filteredGroups.map((group) => (
                <div key={group.name} className="space-y-1">
                  <div className="px-1.5 pt-1 text-[10px] text-ob-muted">
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
                          className={`flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left font-mono text-xs transition-colors ${
                            isSelected
                              ? "bg-ob-raised font-medium text-ob-text"
                              : "text-ob-text-2 hover:bg-ob-raised hover:text-ob-text"
                          }`}
                        >
                          <span className="truncate">
                            {model.label}
                            {model.default ? " (default)" : ""}
                          </span>
                          {isSelected && (
                            <Check className="size-3.5 shrink-0 text-ob-accent" />
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
        <div className="fixed inset-0 z-[99999] flex flex-col justify-end bg-black/60 p-0 backdrop-blur-xs">
          <div className="flex max-h-[80vh] w-full flex-col space-y-3 rounded-t-2xl border-t border-ob-line bg-ob-card p-4 pb-[max(1.5rem,env(safe-area-inset-bottom))] font-mono text-xs text-ob-text shadow-2xl">
            {/* Sheet Handle */}
            <div className="mx-auto mb-1 h-1 w-10 shrink-0 rounded-full bg-ob-raised" />

            {/* Header */}
            <div className="flex shrink-0 items-center justify-between border-b border-ob-line pb-2.5">
              <div className="flex items-center gap-2 text-xs font-medium text-ob-text">
                <Bot className="size-4 text-ob-accent" />
                <span>Select model</span>
              </div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="rounded-lg p-1 text-ob-muted hover:text-ob-text"
              >
                <X className="size-4" />
              </button>
            </div>

            {/* Search Input */}
            <div className="relative shrink-0">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-ob-muted" />
              <input
                type="text"
                placeholder="Search models"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-9 w-full rounded-lg border border-ob-line bg-ob-raised pr-8 pl-8 font-mono text-xs text-ob-text placeholder:text-ob-muted outline-none"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute top-1/2 right-2.5 -translate-y-1/2 p-0.5 text-ob-muted"
                >
                  <X className="size-3.5" />
                </button>
              )}
            </div>

            {/* Model List */}
            <div className="flex-1 space-y-2 overflow-y-auto pr-1">
              {filteredGroups.length === 0 ? (
                <div className="py-6 text-center text-xs text-ob-muted">
                  No matching models found
                </div>
              ) : (
                filteredGroups.map((group) => (
                  <div key={group.name} className="space-y-1">
                    <div className="px-1.5 pt-1 text-[10px] text-ob-muted">
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
                            className={`flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left font-mono text-xs transition-colors ${
                              isSelected
                                ? "bg-ob-raised font-medium text-ob-text"
                                : "text-ob-text-2 hover:bg-ob-raised hover:text-ob-text"
                            }`}
                          >
                            <span className="truncate">
                              {model.label}
                              {model.default ? " (default)" : ""}
                            </span>
                            {isSelected && (
                              <Check className="size-4 shrink-0 text-ob-accent" />
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
