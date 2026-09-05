import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  compress: true,
  poweredByHeader: false,
  allowedDevOrigins: ["20.193.136.181"],
  images: {
    formats: ["image/avif", "image/webp"],
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**",
      },
    ],
  },
  experimental: {
    optimizePackageImports: [
      "lucide-react",
      "@hugeicons/react",
      "@hugeicons/core-free-icons",
      "framer-motion",
      "@radix-ui/react-accordion",
      "@radix-ui/react-context-menu",
      "@radix-ui/react-dropdown-menu",
      "@radix-ui/react-tabs",
      "@radix-ui/react-tooltip",
      "sonner",
    ],
  },
  outputFileTracingExcludes: {
    "*": [
      "uploads/**",
      "uploads/**/*",
      "backend/**",
      "backend/**/*",
      "**/*.pyc",
      "**/__pycache__/**",
    ],
  },
};

export default nextConfig;
