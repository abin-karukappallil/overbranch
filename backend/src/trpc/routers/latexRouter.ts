import { z } from "zod";
import { router, publicProcedure } from "../init";
import { exec } from "child_process";
import { promisify } from "util";
import fs from "fs/promises";
import path from "path";
import os from "os";

const execPromise = promisify(exec);

export const latexRouter = router({
    compileLatex: publicProcedure
        .input(
            z.object({
                tex: z.string().min(1, "LaTeX content cannot be empty"),
            })
        )
        .mutation(async ({ input }) => {
            const { tex } = input;
            const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "latex-"));
            const texFile = path.join(tmpDir, "main.tex");
            const pdfFile = path.join(tmpDir, "main.pdf");

            try {
                await fs.writeFile(texFile, tex);

                // Security: Limit execution time to 30 seconds
                const compileOptions = {
                    cwd: tmpDir,
                    timeout: 30000,
                };

                // Compilation command with latexmk
                const { stdout, stderr } = await execPromise(
                    "latexmk -pdf -silent main.tex",
                    compileOptions
                );

                const pdfBuffer = await fs.readFile(pdfFile);
                const pdfBase64 = pdfBuffer.toString("base64");

                return {
                    pdf: pdfBase64,
                    logs: stdout + stderr,
                    success: true,
                };
            } catch (error: any) {
                return {
                    pdf: null,
                    logs: error.stdout + error.stderr || error.message,
                    success: false,
                };
            } finally {
                // Cleanup: Remove the temporary directory
                // In a real production setup, we might want to keep it for a few minutes
                // but for this implementation we'll clean up immediately.
                try {
                    await fs.rm(tmpDir, { recursive: true, force: true });
                } catch (cleanupError) {
                    console.error("Failed to clean up temporary directory:", cleanupError);
                }
            }
        }),
});
