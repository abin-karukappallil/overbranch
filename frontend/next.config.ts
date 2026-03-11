import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  turbopack: {
    root: path.join(__dirname, ".."),
  },
  async rewrites() {
    return [
      {
        source: "/trpc/:path*",
        destination: "http://localhost:8080/trpc/:path*",
      },
    ];
  },
};

export default nextConfig;
