import type { MetadataRoute } from "next";
import { getBaseUrl } from "./sitemap";

export default function robots(): MetadataRoute.Robots {
  const baseUrl = getBaseUrl();

  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/convert", "/login", "/register"],
        disallow: [
          "/api/",
          "/dashboard/",
          "/projects/",
          "/templates/",
          "/profile/",
          "/editor/",
          "/auth/",
        ],
      },
    ],
    sitemap: `${baseUrl}/sitemap.xml`,
  };
}
