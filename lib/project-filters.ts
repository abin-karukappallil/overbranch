export type ProjectFilters = {
  search?: string;
  template?: string;
  favoritesOnly?: boolean;
};

export function filterProjects<T extends {
  name: string;
  description: string;
  template: string;
  isFavorite: boolean;
}>(projects: T[], filters?: ProjectFilters): T[] {
  const search = filters?.search?.toLowerCase();
  const template = filters?.template;
  const favoritesOnly = filters?.favoritesOnly;
  if (!search && (!template || template === "all") && !favoritesOnly) return projects;

  return projects.filter((project) => {
    const matchesSearch = !search || project.name.toLowerCase().includes(search) ||
      project.description.toLowerCase().includes(search);
    return matchesSearch && (!template || template === "all" || project.template === template) &&
      (!favoritesOnly || project.isFavorite);
  });
}
