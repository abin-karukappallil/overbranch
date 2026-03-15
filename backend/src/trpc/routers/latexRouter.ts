import { z } from "zod";
import { router, publicProcedure } from "../init";
import { exec } from "child_process";
import { promisify } from "util";
import fs from "fs/promises";
import path from "path";
import os from "os";

const execPromise = promisify(exec);

export const latexRouter = router({
  compile: publicProcedure
    .input(
      z.object({
        latex: z.string().min(1, "LaTeX content cannot be empty"),
        images: z
          .array(
            z.object({
              filename: z.string(),
              data: z.string(), // base64
            })
          )
          .optional(),
        files: z
          .array(
            z.object({
              filename: z.string(), // e.g. "references.bib", "figures/chart.png"
              data: z.string(), // base64
            })
          )
          .optional(),
      })
    )
    .mutation(async ({ input }) => {
      console.log("[BACKEND] Received compile request. Keys:", Object.keys(input));
      const { latex, images, files } = input;
      const tex = latex;


      const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "latex-"));
      const texFile = path.join(tmpDir, "main.tex");
      const pdfFile = path.join(tmpDir, "main.pdf");

      const writeFileSafely = async (filename: string, data: string) => {
        const resolvedPath = path.resolve(tmpDir, filename);
        if (!resolvedPath.startsWith(tmpDir)) {
          throw new Error(`Invalid filename (path traversal): ${filename}`);
        }
        await fs.mkdir(path.dirname(resolvedPath), { recursive: true });
        await fs.writeFile(resolvedPath, Buffer.from(data, "base64"));
      };

      try {
        await fs.writeFile(texFile, tex);

        // Write images
        if (images && images.length > 0) {
          await Promise.all(images.map((img) => writeFileSafely(img.filename, img.data)));
        }

        // Write .bib files and any other extra files (cls, sty, etc.)
        if (files && files.length > 0) {
          await Promise.all(files.map((f) => writeFileSafely(f.filename, f.data)));
        }

        const compileOptions = {
          cwd: tmpDir,
          timeout: 60000,
          maxBuffer: 1024 * 1024 * 10,
        };

        // -f forces compilation even with warnings/missing refs
        const { stdout, stderr } = await execPromise(
          "latexmk -pdf -f -silent main.tex",
          compileOptions
        );

        const pdfBuffer = await fs.readFile(pdfFile);
        const pdfBase64 = pdfBuffer.toString("base64");

        return {
          pdf: pdfBase64,
          logs: [stdout, stderr].filter(Boolean).join("\n"),
          success: true,
        };
      } catch (error: any) {
        // Try to return partial PDF even on error (e.g. only missing citations)
        let pdfBase64: string | null = null;
        try {
          const pdfBuffer = await fs.readFile(pdfFile);
          pdfBase64 = pdfBuffer.toString("base64");
        } catch {
          // No PDF was generated
        }

        const logs =
          [error?.stdout, error?.stderr, error?.message]
            .filter(Boolean)
            .join("\n") || "Unknown compilation error";

        return {
          pdf: pdfBase64, // Return partial PDF if it exists
          logs,
          success: pdfBase64 !== null, // Succeed if we at least got a PDF
        };
      } finally {
        try {
          await fs.rm(tmpDir, { recursive: true, force: true });
        } catch (cleanupError) {
          console.error("Failed to clean up temporary directory:", cleanupError);
        }
      }
    }),
});