"use client";

import React, { useState, useEffect } from "react";
import { Palette, Check, RefreshCw, Sun, Moon, Code2, Type, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export interface EditorThemeConfig {
  themeId: string;
  fontSize: number;
  wordWrap: "on" | "off";
  lineNumbers: "on" | "off" | "relative";
  cursorStyle: "line" | "block" | "underline";
  customColors: {
    commandColor: string;
    mathColor: string;
    commentColor: string;
    stringColor: string;
  };
}

export const DEFAULT_THEME_CONFIG: EditorThemeConfig = {
  themeId: "emerald-dark",
  fontSize: 13,
  wordWrap: "on",
  lineNumbers: "on",
  cursorStyle: "line",
  customColors: {
    commandColor: "#6366f1",
    mathColor: "#38bdf8",
    commentColor: "#6b7280",
    stringColor: "#a7f3d0",
  },
};

export const COLOR_SCHEMES = [
  {
    id: "emerald-dark",
    name: "Kinetic Emerald",
    description: "Deep dark zinc with #6366f1 TeX command highlights",
    previewBg: "bg-zinc-950",
    previewBorder: "border-indigo-500",
    previewAccent: "#6366f1",
    isDark: true,
  },
  {
    id: "vs-dark",
    name: "VS Code Dark",
    description: "Classic VS Code dark editor color scheme",
    previewBg: "bg-[#1e1e1e]",
    previewBorder: "border-blue-500",
    previewAccent: "#569cd6",
    isDark: true,
  },
  {
    id: "monokai",
    name: "Monokai Pro",
    description: "High contrast dark theme with vibrant pink & yellow TeX tokens",
    previewBg: "bg-[#272822]",
    previewBorder: "border-amber-400",
    previewAccent: "#f92672",
    isDark: true,
  },
  {
    id: "nord",
    name: "Nordic Arctic",
    description: "Cool arctic dark blue palette with ice mint TeX commands",
    previewBg: "bg-[#2e3440]",
    previewBorder: "border-sky-400",
    previewAccent: "#81a1c1",
    isDark: true,
  },
  {
    id: "github-dark",
    name: "GitHub Dark",
    description: "Official GitHub dark high-contrast syntax colors",
    previewBg: "bg-[#0d1117]",
    previewBorder: "border-rose-400",
    previewAccent: "#ff7b72",
    isDark: true,
  },
  {
    id: "vs-light",
    name: "VS Code Light",
    description: "Clean light mode for daylight editing",
    previewBg: "bg-white",
    previewBorder: "border-zinc-300",
    previewAccent: "#0000ff",
    isDark: false,
  },
];

interface EditorThemeModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: EditorThemeConfig;
  onConfigChange: (newConfig: EditorThemeConfig) => void;
}

export function EditorThemeModal({
  open,
  onOpenChange,
  config,
  onConfigChange,
}: EditorThemeModalProps) {
  const [activeTab, setActiveTab] = useState<"schemes" | "custom" | "typography">("schemes");
  const [localConfig, setLocalConfig] = useState<EditorThemeConfig>(config);

  useEffect(() => {
    setLocalConfig(config);
  }, [config]);

  if (!open) return null;

  const handleSelectScheme = (schemeId: string) => {
    const scheme = COLOR_SCHEMES.find((s) => s.id === schemeId);
    let updatedColors = { ...localConfig.customColors };

    if (schemeId === "emerald-dark") {
      updatedColors = {
        commandColor: "#6366f1",
        mathColor: "#38bdf8",
        commentColor: "#6b7280",
        stringColor: "#a7f3d0",
      };
    } else if (schemeId === "monokai") {
      updatedColors = {
        commandColor: "#f92672",
        mathColor: "#e6db74",
        commentColor: "#75715e",
        stringColor: "#a6e22e",
      };
    } else if (schemeId === "nord") {
      updatedColors = {
        commandColor: "#81a1c1",
        mathColor: "#88c0d0",
        commentColor: "#4c566a",
        stringColor: "#a3be8c",
      };
    } else if (schemeId === "github-dark") {
      updatedColors = {
        commandColor: "#ff7b72",
        mathColor: "#79c0ff",
        commentColor: "#8b949e",
        stringColor: "#a5d6ff",
      };
    }

    const updated = {
      ...localConfig,
      themeId: schemeId,
      customColors: updatedColors,
    };
    setLocalConfig(updated);
    onConfigChange(updated);
    toast.success(`Color scheme set to ${scheme?.name || schemeId}`);
  };

  const handleCustomColorChange = (key: keyof EditorThemeConfig["customColors"], value: string) => {
    const updated = {
      ...localConfig,
      customColors: {
        ...localConfig.customColors,
        [key]: value,
      },
    };
    setLocalConfig(updated);
    onConfigChange(updated);
  };

  const handleResetDefaults = () => {
    setLocalConfig(DEFAULT_THEME_CONFIG);
    onConfigChange(DEFAULT_THEME_CONFIG);
    toast.info("Editor theme reset to Kinetic Emerald default.");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fade-in font-sans">
      <div className="fixed inset-0" onClick={() => onOpenChange(false)} />

      <div className="relative w-full max-w-lg rounded-xl border border-[#282A30] bg-[#141519] text-[#E2E4E9] shadow-2xl overflow-hidden z-10 font-sans">
        {/* Modal Header */}
        <div className="p-4 border-b border-[#282A30] flex items-center justify-between bg-[#1A1C22]">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-[#22242C] border border-[#282A30] flex items-center justify-center text-[#10B981]">
              <Palette className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-archivo font-bold text-xs tracking-tight text-[#E2E4E9]">
                Editor Appearance & Syntax
              </h3>
              <p className="text-[11px] text-[#9E9E9E]">
                Customize LaTeX syntax highlighting and typography
              </p>
            </div>
          </div>

          <button
            onClick={() => onOpenChange(false)}
            className="w-6 h-6 rounded-md hover:bg-[#22242C] text-[#9E9E9E] hover:text-[#E2E4E9] flex items-center justify-center text-xs transition-colors cursor-pointer"
          >
            ✕
          </button>
        </div>

        {/* Modal Navigation Tabs */}
        <div className="flex border-b border-[#282A30] bg-[#0E0F12] p-1 gap-1 text-xs select-none">
          <button
            onClick={() => setActiveTab("schemes")}
            className={`flex-1 py-1.5 rounded-lg font-archivo font-bold transition-all text-center cursor-pointer text-xs ${
              activeTab === "schemes"
                ? "bg-[#22242C] text-[#E2E4E9] border border-[#282A30]"
                : "text-[#9E9E9E] hover:text-[#E2E4E9] hover:bg-[#1A1C22]/50"
            }`}
          >
            Color Schemes
          </button>
          <button
            onClick={() => setActiveTab("custom")}
            className={`flex-1 py-1.5 rounded-lg font-archivo font-bold transition-all text-center cursor-pointer text-xs ${
              activeTab === "custom"
                ? "bg-[#22242C] text-[#E2E4E9] border border-[#282A30]"
                : "text-[#9E9E9E] hover:text-[#E2E4E9] hover:bg-[#1A1C22]/50"
            }`}
          >
            Syntax Tokens
          </button>
          <button
            onClick={() => setActiveTab("typography")}
            className={`flex-1 py-1.5 rounded-lg font-archivo font-bold transition-all text-center cursor-pointer text-xs ${
              activeTab === "typography"
                ? "bg-[#22242C] text-[#E2E4E9] border border-[#282A30]"
                : "text-[#9E9E9E] hover:text-[#E2E4E9] hover:bg-[#1A1C22]/50"
            }`}
          >
            Typography
          </button>
        </div>

        {/* Tab 1: Color Schemes Grid */}
        {activeTab === "schemes" && (
          <div className="p-4 space-y-3 max-h-[380px] overflow-y-auto">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {COLOR_SCHEMES.map((scheme) => {
                const isSelected = localConfig.themeId === scheme.id;
                return (
                  <button
                    key={scheme.id}
                    onClick={() => handleSelectScheme(scheme.id)}
                    className={`p-3 rounded-xl border text-left transition-all cursor-pointer relative overflow-hidden flex flex-col justify-between ${
                      isSelected
                        ? "border-[#282A30] bg-[#22242C] ring-1 ring-[#282A30]"
                        : "border-[#282A30] bg-[#1A1C22]/40 hover:border-[#282A30] hover:bg-[#1A1C22]"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="font-archivo font-bold text-xs text-[#E2E4E9] tracking-tight">
                        {scheme.name}
                      </span>
                      {isSelected && (
                        <span className="w-4 h-4 rounded-full bg-[#10B981] text-white flex items-center justify-center">
                          <Check className="w-2.5 h-2.5 stroke-[3]" />
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] text-[#9E9E9E] mb-2.5 line-clamp-2">
                      {scheme.description}
                    </p>

                    {/* Syntax Code Preview Snippet Pill */}
                    <div className={`p-2 rounded-lg border border-[#282A30] text-[10px] font-mono leading-tight ${scheme.previewBg}`}>
                      <span style={{ color: scheme.previewAccent }} className="font-bold">
                        \documentclass
                      </span>
                      <span className="text-[#9E9E9E]">{`{article}`}</span>
                      <div className="text-[#62666D] italic">% TeX comment</div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Tab 2: Custom Syntax Token Colors */}
        {activeTab === "custom" && (
          <div className="p-4 space-y-3 max-h-[380px] overflow-y-auto text-xs">
            <div className="p-3 rounded-xl bg-[#1A1C22] border border-[#282A30] space-y-1">
              <span className="text-[11px] font-archivo font-bold text-[#10B981] block">
                Live Syntax Token Customizer
              </span>
              <p className="text-[10px] text-[#9E9E9E]">
                Fine-tune specific LaTeX element colors across your editor.
              </p>
            </div>

            <div className="space-y-2">
              <div className="p-2.5 rounded-xl bg-[#1A1C22] border border-[#282A30] flex items-center justify-between">
                <div>
                  <span className="font-archivo font-bold text-[#E2E4E9] block text-xs">LaTeX Commands</span>
                  <span className="text-[10px] text-[#9E9E9E] font-mono">\documentclass, \begin, \section</span>
                </div>
                <input
                  type="color"
                  value={localConfig.customColors.commandColor}
                  onChange={(e) => handleCustomColorChange("commandColor", e.target.value)}
                  className="w-7 h-7 rounded border border-[#282A30] bg-transparent cursor-pointer"
                />
              </div>

              <div className="p-2.5 rounded-xl bg-[#1A1C22] border border-[#282A30] flex items-center justify-between">
                <div>
                  <span className="font-archivo font-bold text-[#E2E4E9] block text-xs">Math Formulas</span>
                  <span className="text-[10px] text-[#9E9E9E] font-mono">$E = mc^2$, \[\int x\,dx\]</span>
                </div>
                <input
                  type="color"
                  value={localConfig.customColors.mathColor}
                  onChange={(e) => handleCustomColorChange("mathColor", e.target.value)}
                  className="w-7 h-7 rounded border border-[#282A30] bg-transparent cursor-pointer"
                />
              </div>

              <div className="p-2.5 rounded-xl bg-[#1A1C22] border border-[#282A30] flex items-center justify-between">
                <div>
                  <span className="font-archivo font-bold text-[#E2E4E9] block text-xs">Comments (% TeX)</span>
                  <span className="text-[10px] text-[#9E9E9E] font-mono">% author notes</span>
                </div>
                <input
                  type="color"
                  value={localConfig.customColors.commentColor}
                  onChange={(e) => handleCustomColorChange("commentColor", e.target.value)}
                  className="w-7 h-7 rounded border border-[#282A30] bg-transparent cursor-pointer"
                />
              </div>

              <div className="p-2.5 rounded-xl bg-[#1A1C22] border border-[#282A30] flex items-center justify-between">
                <div>
                  <span className="font-archivo font-bold text-[#E2E4E9] block text-xs">Parameters & Environments</span>
                  <span className="text-[10px] text-[#9E9E9E] font-mono">{`{document}`}, {`{tabular}`}</span>
                </div>
                <input
                  type="color"
                  value={localConfig.customColors.stringColor}
                  onChange={(e) => handleCustomColorChange("stringColor", e.target.value)}
                  className="w-7 h-7 rounded border border-[#282A30] bg-transparent cursor-pointer"
                />
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Typography & Display Controls */}
        {activeTab === "typography" && (
          <div className="p-4 space-y-4 max-h-[380px] overflow-y-auto text-xs">
            {/* Font Size Selector */}
            <div className="space-y-1.5">
              <span className="text-[11px] font-archivo font-bold text-[#9E9E9E] block">Font Size</span>
              <div className="grid grid-cols-4 gap-2">
                {[12, 13, 14, 16].map((size) => (
                  <button
                    key={size}
                    onClick={() => {
                      const updated = { ...localConfig, fontSize: size };
                      setLocalConfig(updated);
                      onConfigChange(updated);
                    }}
                    className={`py-1.5 rounded-lg border text-center font-mono font-medium transition-all cursor-pointer text-xs ${
                      localConfig.fontSize === size
                        ? "border-[#282A30] bg-[#22242C] text-[#10B981]"
                        : "border-[#282A30] bg-[#1A1C22] text-[#9E9E9E] hover:text-[#E2E4E9]"
                    }`}
                  >
                    {size}px
                  </button>
                ))}
              </div>
            </div>

            {/* Word Wrap Selector */}
            <div className="space-y-1.5">
              <span className="text-[11px] font-archivo font-bold text-[#9E9E9E] block">Word Wrap</span>
              <div className="grid grid-cols-2 gap-2">
                {(["on", "off"] as const).map((wrap) => (
                  <button
                    key={wrap}
                    onClick={() => {
                      const updated = { ...localConfig, wordWrap: wrap };
                      setLocalConfig(updated);
                      onConfigChange(updated);
                    }}
                    className={`py-1.5 rounded-lg border text-center font-mono font-medium transition-all cursor-pointer text-xs ${
                      localConfig.wordWrap === wrap
                        ? "border-[#282A30] bg-[#22242C] text-[#10B981]"
                        : "border-[#282A30] bg-[#1A1C22] text-[#9E9E9E] hover:text-[#E2E4E9]"
                    }`}
                  >
                    {wrap === "on" ? "Enabled (Wrap)" : "Disabled (Scroll)"}
                  </button>
                ))}
              </div>
            </div>

            {/* Line Numbers Selector */}
            <div className="space-y-1.5">
              <span className="text-[11px] font-archivo font-bold text-[#9E9E9E] block">Line Numbers</span>
              <div className="grid grid-cols-2 gap-2">
                {(["on", "off"] as const).map((nums) => (
                  <button
                    key={nums}
                    onClick={() => {
                      const updated = { ...localConfig, lineNumbers: nums };
                      setLocalConfig(updated);
                      onConfigChange(updated);
                    }}
                    className={`py-1.5 rounded-lg border text-center font-mono font-medium transition-all cursor-pointer text-xs ${
                      localConfig.lineNumbers === nums
                        ? "border-[#282A30] bg-[#22242C] text-[#10B981]"
                        : "border-[#282A30] bg-[#1A1C22] text-[#9E9E9E] hover:text-[#E2E4E9]"
                    }`}
                  >
                    {nums === "on" ? "Show Line Numbers" : "Hide Line Numbers"}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Modal Footer Controls */}
        <div className="p-3 border-t border-[#282A30] bg-[#0E0F12] flex items-center justify-between gap-2">
          <button
            onClick={handleResetDefaults}
            className="px-2.5 py-1 rounded-lg border border-[#282A30] text-[#9E9E9E] hover:text-[#E2E4E9] hover:bg-[#1A1C22] text-xs flex items-center gap-1.5 transition-colors cursor-pointer font-mono"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Reset Defaults</span>
          </button>

          <Button
            onClick={() => onOpenChange(false)}
            className="h-8 px-4 bg-[#22242C] hover:bg-[#2A2C36] text-[#E2E4E9] font-archivo font-bold rounded-lg border border-[#282A30] text-xs cursor-pointer"
          >
            Done
          </Button>
        </div>
      </div>
    </div>
  );
}
