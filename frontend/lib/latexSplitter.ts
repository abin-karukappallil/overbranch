/**
 * Utility to split large LaTeX documents into exactly 4 semantic chunks
 * while respecting environments and the preamble.
 */

// Environments that should never be split down the middle
const UNBREAKABLE_ENVS = [
    "figure", "figure*",
    "table", "table*",
    "equation", "equation*",
    "align", "align*",
    "itemize",
    "enumerate",
    "description",
    "tikzpicture"
];

export interface SplitLatexResult {
    preamble: string;
    chunks: string[];
}

export function estimateTokenCount(text: string): number {
    // Rough estimation: 1 token ≈ 4 characters for English text/code
    return Math.ceil(text.length / 4);
}

export function splitLatexDocument(content: string, targetChunks: number = 4): SplitLatexResult {
    const lines = content.split("\n");
    let preambleEndIdx = -1;

    // 1. Find the preamble end (\begin{document})
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].includes("\\begin{document}")) {
            preambleEndIdx = i;
            break;
        }
    }

    let preamble = "";
    let bodyLines = lines;

    // If preamble exists, separate it
    if (preambleEndIdx !== -1) {
        preamble = lines.slice(0, preambleEndIdx + 1).join("\n");
        bodyLines = lines.slice(preambleEndIdx + 1);
    } else {
        // Fallback: If no document environment, assume everything is body
        bodyLines = lines;
    }

    // Edge case handling: if body is very small, don't split it into empty chunks
    if (bodyLines.length < targetChunks * 2) {
        return {
            preamble,
            chunks: [bodyLines.join("\n")]
        };
    }

    // 2. Track open environments line by line to ensure safe splitting
    const safeSplitPoints: number[] = [];
    const openEnvs: string[] = [];

    for (let i = 0; i < bodyLines.length; i++) {
        const line = bodyLines[i].trim();

        // Check for opening environment
        const beginMatch = line.match(/\\begin\{([^}]+)\}/);
        if (beginMatch) {
            openEnvs.push(beginMatch[1]);
        }

        // Check for closing environment
        const endMatch = line.match(/\\end\{([^}]+)\}/);
        if (endMatch) {
            const envName = endMatch[1];
            // Pop the last matching environment if it matches
            if (openEnvs.length > 0 && openEnvs[openEnvs.length - 1] === envName) {
                openEnvs.pop();
            } else {
                // If it doesn't match, we still try to remove it to recover from malformed latex
                const idx = openEnvs.lastIndexOf(envName);
                if (idx !== -1) {
                    openEnvs.splice(idx, 1);
                }
            }
        }

        // A point is safe to split if there are NO unbreakable environments currently open
        const isCurrentlyInsideUnbreakable = openEnvs.some(env => UNBREAKABLE_ENVS.includes(env));

        // Prefer breaking at blank lines or section headers when safe
        if (!isCurrentlyInsideUnbreakable) {
            // We can technically break here. We assign a "score" to prefer better breaks.
            let score = 0;
            if (line === "") score += 10;
            if (line.startsWith("\\section")) score += 20;
            if (line.startsWith("\\subsection")) score += 15;
            if (openEnvs.length === 0) score += 5; // Best to not be in any environment at all

            // Keep track of every safe line and its desirability
            // We only consider lines safe if they aren't inside unbreakable blocks
            safeSplitPoints.push(i);
        }
    }

    // 3. Divide the document into target chunks
    const chunks: string[] = [];
    let lastSplitIdx = 0;
    const targetLinesPerChunk = Math.ceil(bodyLines.length / targetChunks);

    for (let c = 0; c < targetChunks; c++) {
        // If it's the last chunk, grab everything remaining
        if (c === targetChunks - 1) {
            chunks.push(bodyLines.slice(lastSplitIdx).join("\n"));
            break;
        }

        // We want to slice as close to (lastSplitIdx + targetLinesPerChunk) as possible
        const idealSplitEnd = lastSplitIdx + targetLinesPerChunk;

        // Find the closest safe split point to the ideal split
        let bestSplitIdx = idealSplitEnd;
        let minDiff = Infinity;

        // If no safe split points exist at all (e.g. malformed doc), we fallback to hard slicing
        if (safeSplitPoints.length === 0) {
            bestSplitIdx = idealSplitEnd;
        } else {
            // Find nearest safe point
            for (const sp of safeSplitPoints) {
                // Only consider split points that move us forward
                if (sp > lastSplitIdx) {
                    const diff = Math.abs(sp - idealSplitEnd);
                    if (diff < minDiff) {
                        minDiff = diff;
                        bestSplitIdx = sp;
                    }
                }
            }
        }

        // Ensure we advance at least by 1 line to prevent infinite loops on weird inputs
        if (bestSplitIdx <= lastSplitIdx) bestSplitIdx = lastSplitIdx + 1;

        // Slice chunk and push
        // Include the split line in the current chunk
        chunks.push(bodyLines.slice(lastSplitIdx, bestSplitIdx + 1).join("\n"));
        lastSplitIdx = bestSplitIdx + 1;
    }

    // Filter out any purely empty chunks resulting from bad math
    const finalChunks = chunks.filter(c => c.trim().length > 0);

    return {
        preamble,
        chunks: finalChunks
    };
}
