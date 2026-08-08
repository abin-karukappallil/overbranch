import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["20.193.136.181"],
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**",
      },
    ],
  },
};

export default nextConfig;
