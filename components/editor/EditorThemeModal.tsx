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
    commandColor: "#00CC68",
    mathColor: "#38bdf8",
    commentColor: "#6b7280",
    stringColor: "#a7f3d0",
  },
};

export const COLOR_SCHEMES = [
  {
    id: "emerald-dark",
    name: "Kinetic Emerald",
    description: "Deep dark zinc with #00CC68 TeX command highlights",
    previewBg: "bg-zinc-950",
    previewBorder: "border-[#00CC68]",
    previewAccent: "#00CC68",
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
        commandColor: "#00CC68",
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in font-sans">
      <div className="fixed inset-0" onClick={() => onOpenChange(false)} />

      <div className="relative w-full max-w-lg rounded-3xl border border-zinc-800 bg-zinc-900 text-white shadow-2xl overflow-hidden z-10 font-mono">
        {/* Modal Header */}
        <div className="p-4 sm:p-5 border-b border-zinc-800 flex items-center justify-between bg-zinc-950">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-[#00CC68]/20 border border-[#00CC68]/30 flex items-center justify-center text-[#00CC68]">
              <Palette className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-archivo font-black text-sm uppercase tracking-wider text-white">
                Editor Color Scheme & Syntax
              </h3>
              <p className="text-[10px] text-zinc-400 font-mono">
                Customize LaTeX syntax highlighting & display parameters
              </p>
            </div>
          </div>

          <button
            onClick={() => onOpenChange(false)}
            className="w-7 h-7 rounded-full bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white flex items-center justify-center text-xs transition-colors cursor-pointer"
          >
            ✕
          </button>
        </div>

        {/* Modal Navigation Tabs */}
        <div className="flex border-b border-zinc-800 bg-zinc-950/60 p-1.5 gap-1 text-xs select-none">
          <button
            onClick={() => setActiveTab("schemes")}
            className={`flex-1 py-1.5 rounded-xl font-bold transition-all text-center cursor-pointer ${
              activeTab === "schemes"
                ? "bg-[#00CC68] text-black font-archivo uppercase"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800"
            }`}
          >
            Color Schemes
          </button>
          <button
            onClick={() => setActiveTab("custom")}
            className={`flex-1 py-1.5 rounded-xl font-bold transition-all text-center cursor-pointer ${
              activeTab === "custom"
                ? "bg-[#00CC68] text-black font-archivo uppercase"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800"
            }`}
          >
            Syntax Tokens
          </button>
          <button
            onClick={() => setActiveTab("typography")}
            className={`flex-1 py-1.5 rounded-xl font-bold transition-all text-center cursor-pointer ${
              activeTab === "typography"
                ? "bg-[#00CC68] text-black font-archivo uppercase"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800"
            }`}
          >
            Typography
          </button>
        </div>

        {/* Tab 1: Color Schemes Grid */}
        {activeTab === "schemes" && (
          <div className="p-4 sm:p-5 space-y-3 max-h-[380px] overflow-y-auto">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {COLOR_SCHEMES.map((scheme) => {
                const isSelected = localConfig.themeId === scheme.id;
                return (
                  <button
                    key={scheme.id}
                    onClick={() => handleSelectScheme(scheme.id)}
                    className={`p-3 rounded-2xl border text-left transition-all cursor-pointer relative overflow-hidden flex flex-col justify-between ${
                      isSelected
                        ? "border-[#00CC68] bg-zinc-950 ring-2 ring-[#00CC68]/30 shadow-lg"
                        : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700 hover:bg-zinc-800/40"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="font-archivo font-bold text-xs text-white uppercase tracking-wider">
                        {scheme.name}
                      </span>
                      {isSelected && (
                        <span className="w-5 h-5 rounded-full bg-[#00CC68] text-black flex items-center justify-center">
                          <Check className="w-3 h-3 stroke-[3]" />
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] text-zinc-400 font-sans mb-3 line-clamp-2">
                      {scheme.description}
                    </p>

                    {/* Syntax Code Preview Snippet Pill */}
                    <div className={`p-2 rounded-xl border border-zinc-800 text-[10px] font-mono leading-tight ${scheme.previewBg}`}>
                      <span style={{ color: scheme.previewAccent }} className="font-bold">
                        \documentclass
                      </span>
                      <span className="text-zinc-400">{`{article}`}</span>
                      <div className="text-zinc-500 italic">% TeX comment</div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Tab 2: Custom Syntax Token Colors */}
        {activeTab === "custom" && (
          <div className="p-4 sm:p-5 space-y-4 max-h-[380px] overflow-y-auto font-mono text-xs">
            <div className="p-3 rounded-2xl bg-zinc-950 border border-zinc-800 space-y-1">
              <span className="text-[11px] font-bold text-[#00CC68] uppercase block">
                Live Syntax Token Customizer
              </span>
              <p className="text-[10px] text-zinc-400 font-sans">
                Fine-tune specific LaTeX element colors across your editor.
              </p>
            </div>

            <div className="space-y-3">
              <div className="p-3 rounded-2xl bg-zinc-950 border border-zinc-800 flex items-center justify-between">
                <div>
                  <span className="font-bold text-white block">LaTeX Commands</span>
                  <span className="text-[10px] text-zinc-400">\documentclass, \begin, \section</span>
                </div>
                <input
                  type="color"
                  value={localConfig.customColors.commandColor}
                  onChange={(e) => handleCustomColorChange("commandColor", e.target.value)}
                  className="w-8 h-8 rounded-lg border border-zinc-700 bg-transparent cursor-pointer"
                />
              </div>

              <div className="p-3 rounded-2xl bg-zinc-950 border border-zinc-800 flex items-center justify-between">
                <div>
                  <span className="font-bold text-white block">Math Formulas & Delimiters</span>
                  <span className="text-[10px] text-zinc-400">$E = mc^2$, \[\int x\,dx\]</span>
                </div>
                <input
                  type="color"
                  value={localConfig.customColors.mathColor}
                  onChange={(e) => handleCustomColorChange("mathColor", e.target.value)}
                  className="w-8 h-8 rounded-lg border border-zinc-700 bg-transparent cursor-pointer"
                />
              </div>

              <div className="p-3 rounded-2xl bg-zinc-950 border border-zinc-800 flex items-center justify-between">
                <div>
                  <span className="font-bold text-white block">Comments (% TeX)</span>
                  <span className="text-[10px] text-zinc-400">% author notes and comments</span>
                </div>
                <input
                  type="color"
                  value={localConfig.customColors.commentColor}
                  onChange={(e) => handleCustomColorChange("commentColor", e.target.value)}
                  className="w-8 h-8 rounded-lg border border-zinc-700 bg-transparent cursor-pointer"
                />
              </div>

              <div className="p-3 rounded-2xl bg-zinc-950 border border-zinc-800 flex items-center justify-between">
                <div>
                  <span className="font-bold text-white block">Parameters & Environments</span>
                  <span className="text-[10px] text-zinc-400">{`{document}`}, {`{tabular}`}</span>
                </div>
                <input
                  type="color"
                  value={localConfig.customColors.stringColor}
                  onChange={(e) => handleCustomColorChange("stringColor", e.target.value)}
                  className="w-8 h-8 rounded-lg border border-zinc-700 bg-transparent cursor-pointer"
                />
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Typography & Display Controls */}
        {activeTab === "typography" && (
          <div className="p-4 sm:p-5 space-y-4 max-h-[380px] overflow-y-auto font-mono text-xs">
            {/* Font Size Selector */}
            <div className="space-y-2">
              <span className="text-xs font-bold text-zinc-300 block uppercase">Font Size</span>
              <div className="grid grid-cols-4 gap-2">
                {[12, 13, 14, 16].map((size) => (
                  <button
                    key={size}
                    onClick={() => {
                      const updated = { ...localConfig, fontSize: size };
                      setLocalConfig(updated);
                      onConfigChange(updated);
                    }}
                    className={`py-2 rounded-xl border text-center font-bold transition-all cursor-pointer ${
                      localConfig.fontSize === size
                        ? "border-[#00CC68] bg-[#00CC68]/20 text-[#00CC68]"
                        : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-white"
                    }`}
                  >
                    {size}px
                  </button>
                ))}
              </div>
            </div>

            {/* Word Wrap Selector */}
            <div className="space-y-2">
              <span className="text-xs font-bold text-zinc-300 block uppercase">Word Wrap</span>
              <div className="grid grid-cols-2 gap-2">
                {(["on", "off"] as const).map((wrap) => (
                  <button
                    key={wrap}
                    onClick={() => {
                      const updated = { ...localConfig, wordWrap: wrap };
                      setLocalConfig(updated);
                      onConfigChange(updated);
                    }}
                    className={`py-2 rounded-xl border text-center font-bold uppercase transition-all cursor-pointer ${
                      localConfig.wordWrap === wrap
                        ? "border-[#00CC68] bg-[#00CC68]/20 text-[#00CC68]"
                        : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-white"
                    }`}
                  >
                    {wrap === "on" ? "Enabled (Wrap)" : "Disabled (Scroll)"}
                  </button>
                ))}
              </div>
            </div>

            {/* Line Numbers Selector */}
            <div className="space-y-2">
              <span className="text-xs font-bold text-zinc-300 block uppercase">Line Numbers</span>
              <div className="grid grid-cols-2 gap-2">
                {(["on", "off"] as const).map((nums) => (
                  <button
                    key={nums}
                    onClick={() => {
                      const updated = { ...localConfig, lineNumbers: nums };
                      setLocalConfig(updated);
                      onConfigChange(updated);
                    }}
                    className={`py-2 rounded-xl border text-center font-bold uppercase transition-all cursor-pointer ${
                      localConfig.lineNumbers === nums
                        ? "border-[#00CC68] bg-[#00CC68]/20 text-[#00CC68]"
                        : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-white"
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
        <div className="p-3 sm:p-4 border-t border-zinc-800 bg-zinc-950 flex items-center justify-between gap-2">
          <button
            onClick={handleResetDefaults}
            className="px-3 py-1.5 rounded-xl border border-zinc-800 text-zinc-400 hover:text-white text-xs flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Reset Defaults</span>
          </button>

          <Button
            onClick={() => onOpenChange(false)}
            className="h-8 px-4 bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold uppercase tracking-wider rounded-xl border border-black shadow-[2px_2px_0px_0px_#000000] text-xs cursor-pointer"
          >
            Done
          </Button>
        </div>
      </div>
    </div>
  );
}
