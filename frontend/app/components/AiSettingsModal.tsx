"use client";

import { useState, useEffect } from "react";

interface AiSettingsModalProps {
    onClose: () => void;
}

const STORAGE_KEY = "overbranch_groq_api_key";

export default function AiSettingsModal({ onClose }: AiSettingsModalProps) {
    const [apiKey, setApiKey] = useState("");
    const [saved, setSaved] = useState(false);

    useEffect(() => {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) setApiKey(stored);
    }, []);

    const handleSave = () => {
        if (apiKey.trim()) {
            localStorage.setItem(STORAGE_KEY, apiKey.trim());
        } else {
            localStorage.removeItem(STORAGE_KEY);
        }
        setSaved(true);
        setTimeout(() => onClose(), 600);
    };

    const handleClear = () => {
        localStorage.removeItem(STORAGE_KEY);
        setApiKey("");
        setSaved(false);
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                <h2 className="modal-title">
                    <svg className="inline-block h-5 w-5 mr-2 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M12 2a4 4 0 0 0-4 4v2H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10a2 2 0 0 0-2-2h-2V6a4 4 0 0 0-4-4z" />
                        <circle cx="12" cy="15" r="1.5" />
                    </svg>
                    AI Settings
                </h2>

                <div className="auth-form">
                    <div className="auth-field">
                        <label htmlFor="groq-api-key">Groq API Key</label>
                        <input
                            id="groq-api-key"
                            type="password"
                            value={apiKey}
                            onChange={(e) => {
                                setApiKey(e.target.value);
                                setSaved(false);
                            }}
                            placeholder="gsk_..."
                            autoFocus
                            onKeyDown={(e) => e.key === "Enter" && handleSave()}
                        />
                        <span className="text-xs text-muted" style={{ marginTop: 4 }}>
                            Your key is stored locally in this browser only. Get one at{" "}
                            <a
                                href="https://console.groq.com/keys"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="auth-link"
                            >
                                console.groq.com
                            </a>
                        </span>
                    </div>

                    <div className="modal-actions">
                        <button className="modal-cancel" onClick={handleClear} type="button">
                            Clear Key
                        </button>
                        <button className="modal-cancel" onClick={onClose} type="button">
                            Cancel
                        </button>
                        <button
                            className="auth-submit"
                            style={{ width: "auto" }}
                            onClick={handleSave}
                            type="button"
                        >
                            {saved ? "✓ Saved" : "Save Key"}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

export function getStoredApiKey(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(STORAGE_KEY);
}
