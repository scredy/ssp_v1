import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/seo";

export default function sitemap(): MetadataRoute.Sitemap {
  const routes = [
    "/",
    "/cars",
    "/finance",
    "/about",
    "/contact",
    "/track",
    "/request-quote",
    "/book-appointment",
  ];

  return routes.map((route) => ({
    url: new URL(route, SITE_URL).href,
  }));
}
