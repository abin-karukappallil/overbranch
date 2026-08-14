import { NextRequest, NextResponse } from "next/server";

export const maxDuration = 120; // 2 minute timeout for long file processing

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const file = formData.get("file");
    const prompt = formData.get("prompt");

    if (!file || !(file instanceof Blob)) {
      return NextResponse.json(
        { success: false, error: "A file is required for analysis." },
        { status: 400 }
      );
    }

    if (!prompt || typeof prompt !== "string" || !prompt.trim()) {
      return NextResponse.json(
        { success: false, error: "A prompt describing analysis instructions is required." },
        { status: 400 }
      );
    }

    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

    // Forward multipart form data to Python backend API
    const response = await fetch(`${backendUrl}/api/ai/analyze-file`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text();
      let parsedError = errorText;
      try {
        const jsonErr = JSON.parse(errorText);
        parsedError = jsonErr.detail || jsonErr.error || errorText;
      } catch {
        // Keep raw text if not JSON
      }

      return NextResponse.json(
        { success: false, error: parsedError || `Backend returned HTTP ${response.status}` },
        { status: response.status }
      );
    }

    const contentType = response.headers.get("content-type") || "";

    // Check if streaming response (SSE)
    if (contentType.includes("text/event-stream") && response.body) {
      return new NextResponse(response.body, {
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          "Connection": "keep-alive",
        },
      });
    }

    // Standard JSON response
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error("Error in Next.js /api/ai/analyze-file route:", error);
    return NextResponse.json(
      {
        success: false,
        error: error?.message || "Internal server error occurred while processing file analysis.",
      },
      { status: 500 }
    );
  }
}
