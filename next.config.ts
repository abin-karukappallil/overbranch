import type { NextConfig } from "next";
import { initOpenNextCloudflareForDev } from "@opennextjs/cloudflare";

// Initialize OpenNext Cloudflare development platform in development mode
if (process.env.NODE_ENV === "development") {
  await initOpenNextCloudflareForDev();
}

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
