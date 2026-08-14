export interface FileAnalysisUsage {
  promptTokens?: number;
  candidatesTokens?: number;
  totalTokens?: number;
}

export interface FileAnalysisResponse {
  success: boolean;
  filename: string;
  mimeType: string;
  analysis: string;
  usage?: FileAnalysisUsage;
  provider?: string;
  error?: string;
}

export interface AnalyzeFileOptions {
  file: File;
  prompt: string;
  provider?: string;
  model?: string;
  stream?: boolean;
  onChunk?: (chunkText: string) => void;
  signal?: AbortSignal;
}

/**
 * Reusable client function for sending uploaded files + custom prompts
 * to Gemini (or other configured providers) via OverBranch's file analysis API.
 */
export async function analyzeFile(options: AnalyzeFileOptions): Promise<FileAnalysisResponse> {
  const { file, prompt, provider = "gemini", model, stream = true, onChunk, signal } = options;

  const formData = new FormData();
  formData.append("file", file);
  formData.append("prompt", prompt);
  formData.append("provider", provider);
  if (model) {
    formData.append("model", model);
  }
  formData.append("stream", stream ? "true" : "false");

  const response = await fetch("/api/ai/analyze-file", {
    method: "POST",
    body: formData,
    signal,
  });

  if (!response.ok) {
    let errorText = "";
    try {
      const errJson = await response.json();
      errorText = errJson.error || errJson.detail || `Server returned HTTP ${response.status}`;
    } catch {
      errorText = await response.text();
    }
    throw new Error(errorText || `Analysis request failed with status ${response.status}`);
  }

  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("text/event-stream") && response.body) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let accumulatedText = "";
    let finalUsage: FileAnalysisUsage | undefined = undefined;
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // Keep partial line in buffer

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            const dataStr = trimmed.substring(6).trim();
            if (!dataStr) continue;

            try {
              const data = JSON.parse(dataStr);
              if (data.error) {
                throw new Error(data.detail || "Error during streaming analysis.");
              }

              if (data.chunk) {
                accumulatedText += data.chunk;
                if (onChunk) {
                  onChunk(data.chunk);
                }
              }

              if (data.done) {
                if (data.usage) {
                  finalUsage = data.usage;
                }
              }
            } catch (e: any) {
              if (e.message && e.message !== "Unexpected end of JSON input") {
                console.warn("Failed to parse SSE data chunk:", e);
              }
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    return {
      success: true,
      filename: file.name,
      mimeType: file.type || "application/octet-stream",
      analysis: accumulatedText,
      usage: finalUsage,
      provider,
    };
  }

  // Handle standard JSON response
  const jsonResult: FileAnalysisResponse = await response.json();
  if (!jsonResult.success && jsonResult.error) {
    throw new Error(jsonResult.error);
  }
  return jsonResult;
}
