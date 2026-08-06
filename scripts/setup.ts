import "dotenv/config";
import { db } from "../db";
import { templates } from "../db/schema";

async function main() {
  console.log("Initializing OverBranch Database Setup...");

  try {
    const defaultTemplates = [
      {
        id: "tmpl-ieee",
        name: "IEEE Conference Paper",
        category: "Proceedings",
        description: "Official two-column IEEEtran proceedings layout with equations, figure blocks, and BibTeX integration.",
        fileExtension: "cls",
        isFeatured: true,
        usageCount: 1420,
      },
      {
        id: "tmpl-arxiv",
        name: "arXiv Scientific Preprint",
        category: "Preprint",
        description: "Single-column preprint format optimized for computer science, physics, and mathematics submission.",
        fileExtension: "sty",
        isFeatured: true,
        usageCount: 980,
      },
      {
        id: "tmpl-acm",
        name: "ACM SIGCONF Proceedings",
        category: "ACM",
        description: "Official ACM Master Article Template for primary conferences and symposiums.",
        fileExtension: "cls",
        isFeatured: false,
        usageCount: 650,
      },
      {
        id: "tmpl-thesis",
        name: "University PhD Dissertation",
        category: "Thesis",
        description: "Multi-chapter thesis book class setup with list of figures, tables, and bibliography configuration.",
        fileExtension: "cls",
        isFeatured: true,
        usageCount: 1120,
      },
    ];

    for (const tmpl of defaultTemplates) {
      await db
        .insert(templates)
        .values(tmpl)
        .onConflictDoNothing();
    }

    console.log("OverBranch database setup and template seeding complete!");
  } catch (error) {
    console.error("Setup error:", error);
  }
}

main().catch(console.error);
