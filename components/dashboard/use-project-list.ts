"use client";

import { useMemo } from "react";
import { authClient } from "@/lib/auth-client";
import { filterProjects, type ProjectFilters } from "@/lib/project-filters";
import { trpc } from "@/trpc/client";

export function useProjectList({ search, template, favoritesOnly }: ProjectFilters) {
  const { data: session, isPending } = authClient.useSession();
  const viewerId = session?.user.id;
  const { data, isLoading } = trpc.projects.listProjects.useQuery({ viewerId }, {
    enabled: Boolean(viewerId) && !isPending,
    staleTime: 60 * 1000,
    gcTime: 15 * 60 * 1000,
    refetchOnWindowFocus: true,
  });

  const projects = useMemo(
    () => data && filterProjects(data, { search, template, favoritesOnly }),
    [data, search, template, favoritesOnly],
  );

  return { data: projects, isLoading: isPending || isLoading };
}
