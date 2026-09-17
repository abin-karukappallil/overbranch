"use client";

import React, { useState, useEffect } from "react";
import { X, Key, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface ApiSettingsModalProps {
  onClose: () => void;
}

export function ApiSettingsModal({ onClose }: ApiSettingsModalProps) {
  const [keys, setKeys] = useState({
    groqApiKey: "",
    geminiApiKey: "",
    openaiApiKey: "",
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 font-sans animate-in fade-in">
      <div className="w-full max-w-md bg-[#141519] border border-[#282A30] rounded-xl shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#282A30] bg-[#1A1C22]">
          <div className="flex items-center gap-2">
            <Key className="w-4 h-4 text-[#10B981]" />
            <h3 className="font-archivo font-bold text-xs text-[#E2E4E9]">API Keys & Providers Settings</h3>
          </div>
          <button
            onClick={onClose}
            className="text-[#9E9E9E] hover:text-[#E2E4E9] p-1 rounded-md hover:bg-[#22242C] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-4 space-y-4 text-xs">
          <p className="text-[#9E9E9E]">
            Custom API keys are saved locally in your browser storage and used for direct fallback requests.
          </p>

          <div className="space-y-3 font-mono">
            <div className="space-y-1">
              <label className="text-[10px] text-[#9E9E9E] uppercase block font-archivo font-bold">Groq API Key (Primary)</label>
              <Input
                type="password"
                placeholder="gsk_..."
                value={keys.groqApiKey}
                onChange={(e) => setKeys({ ...keys, groqApiKey: e.target.value })}
                className="bg-[#1A1C22] border-[#282A30] text-[#E2E4E9] placeholder:text-[#62666D] focus-visible:ring-1 focus-visible:ring-[#282A30] font-mono text-xs h-9 rounded-lg"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[10px] text-[#9E9E9E] uppercase block font-archivo font-bold">Gemini API Key (Fallback)</label>
              <Input
                type="password"
                placeholder="AIzaSy..."
                value={keys.geminiApiKey}
                onChange={(e) => setKeys({ ...keys, geminiApiKey: e.target.value })}
                className="bg-[#1A1C22] border-[#282A30] text-[#E2E4E9] placeholder:text-[#62666D] focus-visible:ring-1 focus-visible:ring-[#282A30] font-mono text-xs h-9 rounded-lg"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[10px] text-[#9E9E9E] uppercase block font-archivo font-bold">OpenAI API Key (Optional)</label>
              <Input
                type="password"
                placeholder="sk-..."
                value={keys.openaiApiKey}
                onChange={(e) => setKeys({ ...keys, openaiApiKey: e.target.value })}
                className="bg-[#1A1C22] border-[#282A30] text-[#E2E4E9] placeholder:text-[#62666D] focus-visible:ring-1 focus-visible:ring-[#282A30] font-mono text-xs h-9 rounded-lg"
              />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-3.5 border-t border-[#282A30] bg-[#0E0F12] flex justify-end gap-2 font-mono">
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="text-xs text-[#9E9E9E] hover:text-[#E2E4E9] hover:bg-[#1A1C22] h-8 px-3 rounded-lg"
          >
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            className="bg-[#22242C] hover:bg-[#2A2C36] text-[#E2E4E9] border border-[#282A30] text-xs h-8 px-3.5 rounded-lg gap-1.5 font-archivo font-bold"
          >
            <Check className="w-3.5 h-3.5 text-[#10B981]" />
            <span>Save API Keys</span>
          </Button>
        </div>
      </div>
    </div>
  );
}
