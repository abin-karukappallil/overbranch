import { router, publicProcedure } from '../init';
import { z } from 'zod';

const mockTemplates = [
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
  {
    id: "tmpl-blank",
    name: "Blank TeX Canvas",
    category: "Basic",
    description: "Minimal document layout with essential preamble for custom packages and notes.",
    fileExtension: "tex",
    isFeatured: false,
    usageCount: 3200,
  },
];

export const templatesRouter = router({
  listTemplates: publicProcedure
    .input(z.object({ category: z.string().optional() }).optional())
    .query(async ({ input }) => {
      if (input?.category && input.category !== "all") {
        return mockTemplates.filter(t => t.category.toLowerCase() === input.category!.toLowerCase());
      }
      return mockTemplates;
    }),

  getById: publicProcedure
    .input(z.object({ id: z.string() }))
    .query(async ({ input }) => {
      return mockTemplates.find(t => t.id === input.id) || mockTemplates[0];
    }),
});
