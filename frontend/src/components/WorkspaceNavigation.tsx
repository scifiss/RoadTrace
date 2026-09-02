import type { View } from '../App'
import type { CanonicalCategory, CategorySummary } from '../types'

interface WorkspaceNavigationProps {
  categories: CategorySummary[]
  category: CanonicalCategory | 'ALL'
  onCategoryChange: (category: CanonicalCategory | 'ALL') => void
  onQueryChange: (query: string) => void
  onViewChange: (view: View) => void
  query: string
  view: View
}

const tabs: { id: View; label: string }[] = [
  { id: 'constellation', label: 'Constellation' },
  { id: 'roadmap', label: 'Reverse roadmap' },
  { id: 'code', label: 'Code explorer' },
  { id: 'workflows', label: 'Workflows' },
  { id: 'data', label: 'Data hints' },
]

const categoryColors = ['#7c5cff', '#17b8c5', '#f59e0b', '#ec4899', '#438cf5', '#ef5350', '#20b886', '#7890ae']

export function WorkspaceNavigation({
  categories,
  category,
  onCategoryChange,
  onQueryChange,
  onViewChange,
  query,
  view,
}: WorkspaceNavigationProps) {
  const supportsCategories = view === 'constellation' || view === 'roadmap'
  const placeholder = view === 'constellation' || view === 'roadmap'
    ? 'Search capabilities and history…'
    : `Search ${tabs.find((item) => item.id === view)?.label.toLowerCase()}…`

  return (
    <section className="workspace-navigation" aria-label="Analysis workspace controls">
      <div className="workspace-navigation__top">
        <nav className="view-tabs" aria-label="Analysis views">
          {tabs.map((tab) => (
            <button
              aria-current={view === tab.id ? 'page' : undefined}
              key={tab.id}
              onClick={() => onViewChange(tab.id)}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </nav>
        <label className="workspace-search">
          <span aria-hidden="true">⌕</span>
          <span className="sr-only">Search the current analysis view</span>
          <input
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder={placeholder}
            type="search"
            value={query}
          />
          {query && (
            <button aria-label="Clear search" onClick={() => onQueryChange('')} type="button">
              ×
            </button>
          )}
        </label>
      </div>
      {supportsCategories && (
        <div className="category-chips" aria-label="Filter by category">
          <button
            aria-pressed={category === 'ALL'}
            className="category-chip"
            onClick={() => onCategoryChange('ALL')}
            type="button"
          >
            <span style={{ background: '#e8f1ff' }} /> All categories
          </button>
          {categories.map((item, index) => (
            <button
              aria-pressed={category === item.category}
              className="category-chip"
              key={item.category}
              onClick={() => onCategoryChange(item.category)}
              type="button"
            >
              <span style={{ background: categoryColors[index % categoryColors.length] }} />
              {item.category} <small>{item.capability_count}</small>
            </button>
          ))}
        </div>
      )}
    </section>
  )
}
