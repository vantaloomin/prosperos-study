import type { DiscoveredModel } from './discovery'

export function filterModels(models: DiscoveredModel[], query: string) {
  const words = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean)
  return models.filter(model => words.every(word => `${model.name} ${model.id}`.toLocaleLowerCase().includes(word)))
}
