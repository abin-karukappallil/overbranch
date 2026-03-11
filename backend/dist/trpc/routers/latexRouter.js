"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.latexRouter = void 0;
const zod_1 = require("zod");
const init_1 = require("../init");
const child_process_1 = require("child_process");
const util_1 = require("util");
const promises_1 = __importDefault(require("fs/promises"));
const path_1 = __importDefault(require("path"));
const os_1 = __importDefault(require("os"));
const execPromise = (0, util_1.promisify)(child_process_1.exec);
exports.latexRouter = (0, init_1.router)({
    compileLatex: init_1.publicProcedure
        .input(zod_1.z.object({
        tex: zod_1.z.string().min(1, "LaTeX content cannot be empty"),
    }))
        .mutation(async ({ input }) => {
        const { tex } = input;
        const tmpDir = await promises_1.default.mkdtemp(path_1.default.join(os_1.default.tmpdir(), "latex-"));
        const texFile = path_1.default.join(tmpDir, "main.tex");
        const pdfFile = path_1.default.join(tmpDir, "main.pdf");
        try {
            await promises_1.default.writeFile(texFile, tex);
            // Security: Limit execution time to 30 seconds
            const compileOptions = {
                cwd: tmpDir,
                timeout: 30000,
            };
            // Compilation command with latexmk
            const { stdout, stderr } = await execPromise("latexmk -pdf -silent main.tex", compileOptions);
            const pdfBuffer = await promises_1.default.readFile(pdfFile);
            const pdfBase64 = pdfBuffer.toString("base64");
            return {
                pdf: pdfBase64,
                logs: stdout + stderr,
                success: true,
            };
        }
        catch (error) {
            return {
                pdf: null,
                logs: error.stdout + error.stderr || error.message,
                success: false,
            };
        }
        finally {
            // Cleanup: Remove the temporary directory
            // In a real production setup, we might want to keep it for a few minutes
            // but for this implementation we'll clean up immediately.
            try {
                await promises_1.default.rm(tmpDir, { recursive: true, force: true });
            }
            catch (cleanupError) {
                console.error("Failed to clean up temporary directory:", cleanupError);
            }
        }
    }),
});
