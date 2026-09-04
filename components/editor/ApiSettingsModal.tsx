"use client";

import React, { useState, useEffect } from "react";
import { X, Key, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface ApiSettingsModalProps {
  onClose: () => void;
}

export function ApiSettingsModal({ onClose }: ApiSettingsModalProps) {
  const [keys, setKeys] = useState({
    gemini: "",
    groq: "",
    openrouter: "",
    freellm: "",
  });

  useEffect(() => {
    try {
      const stored = localStorage.getItem("ob_api_keys");
      if (stored) {
        setKeys(JSON.parse(stored));
      }
    } catch (e) {
      console.error("Failed to load API keys", e);
    }
  }, []);

  const handleSave = () => {
    try {
      localStorage.setItem("ob_api_keys", JSON.stringify(keys));
      onClose();
    } catch (e) {
      console.error("Failed to save API keys", e);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 font-sans">
      <div className="w-full max-w-md bg-zinc-950 border border-zinc-800 rounded-xl shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-zinc-800 bg-zinc-900/50">
          <div className="flex items-center gap-2">
            <Key className="w-5 h-5 text-emerald-400" />
            <h2 className="text-lg font-bold text-white tracking-tight">API Settings</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-4 space-y-4">
          <p className="text-xs text-zinc-400 leading-relaxed">
            Configure your own API keys to bypass rate limits or use custom providers. 
            Keys are stored locally in your browser.
          </p>

          <div className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-zinc-300">OpenRouter API Key</label>
              <Input
                type="password"
                placeholder="sk-or-v1-..."
                value={keys.openrouter}
                onChange={(e) => setKeys({ ...keys, openrouter: e.target.value })}
                className="bg-zinc-900 border-zinc-800 text-white placeholder:text-zinc-600 focus-visible:ring-emerald-500/50 font-mono text-xs"
              />
            </div>
            
            <div className="space-y-1">
              <label className="text-xs font-semibold text-zinc-300">Google Gemini API Key</label>
              <Input
                type="password"
                placeholder="AIza..."
                value={keys.gemini}
                onChange={(e) => setKeys({ ...keys, gemini: e.target.value })}
                className="bg-zinc-900 border-zinc-800 text-white placeholder:text-zinc-600 focus-visible:ring-emerald-500/50 font-mono text-xs"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-zinc-300">Groq API Key</label>
              <Input
                type="password"
                placeholder="gsk_..."
                value={keys.groq}
                onChange={(e) => setKeys({ ...keys, groq: e.target.value })}
                className="bg-zinc-900 border-zinc-800 text-white placeholder:text-zinc-600 focus-visible:ring-emerald-500/50 font-mono text-xs"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-zinc-300">FreeLLM API Key</label>
              <Input
                type="password"
                placeholder="fl_..."
                value={keys.freellm}
                onChange={(e) => setKeys({ ...keys, freellm: e.target.value })}
                className="bg-zinc-900 border-zinc-800 text-white placeholder:text-zinc-600 focus-visible:ring-emerald-500/50 font-mono text-xs"
              />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-zinc-800 bg-zinc-900/30 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} className="text-zinc-300 hover:text-white hover:bg-zinc-800">
            Cancel
          </Button>
          <Button onClick={handleSave} className="bg-emerald-600 hover:bg-emerald-500 text-white gap-2">
            <Save className="w-4 h-4" />
            Save Keys
          </Button>
        </div>
      </div>
    </div>
  );
}
