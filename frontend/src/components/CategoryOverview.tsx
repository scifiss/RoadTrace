import type { Capability, CategorySummary, CanonicalCategory } from '../types'

interface CategoryOverviewProps {
  activeCategory: CanonicalCategory | 'ALL'
  categories: CategorySummary[]
  capabilities: Capability[]
  onCategoryChange: (category: CanonicalCategory | 'ALL') => void
  onSelect: (capability: Capability) => void
  query: string
}

const categoryIcons: Record<CanonicalCategory, string> = {
  'Product & UX': '◎',
  'Core Capability': '◆',
  Data: '▤',
  'Platform & Integration': '↔',
  'Reliability & Safety': '◇',
  'Quality & Evaluation': '✓',
  Operations: '⌁',
  'Developer & Documentation': '⌘',
}

export function CategoryOverview({
  activeCategory,
  categories,
  capabilities,
  onCategoryChange,
  onSelect,
  query,
}: CategoryOverviewProps) {
  const normalizedQuery = query.trim().toLowerCase()

  return (
    <section aria-labelledby="overview-heading" className="section-block overview">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Capability landscape</p>
          <h2 id="overview-heading">What exists now</h2>
        </div>
        <p>Eight stable lenses. Select one to focus the constellation and roadmap.</p>
      </div>
      <div className="category-grid">
        {categories.map((summary, index) => {
          const matches = capabilities.filter(
            (item) =>
              item.category === summary.category &&
              (!normalizedQuery || `${item.name} ${item.description}`.toLowerCase().includes(normalizedQuery)),
          )
          return (
            <article
              className="category-card"
              data-active={activeCategory === summary.category || undefined}
              data-muted={(activeCategory !== 'ALL' && activeCategory !== summary.category) || undefined}
              key={summary.category}
              style={{ '--delay': `${index * 35}ms` } as React.CSSProperties}
            >
              <div className="category-card__top">
                <span className="category-icon" aria-hidden="true">
                  {categoryIcons[summary.category]}
                </span>
                <span className="count-badge">{summary.capability_count}</span>
              </div>
              <button
                aria-pressed={activeCategory === summary.category}
                className="category-card__title"
                onClick={() => onCategoryChange(activeCategory === summary.category ? 'ALL' : summary.category)}
                type="button"
              >
                {summary.category} <span aria-hidden="true">↗</span>
              </button>
              {matches.length ? (
                <div className="capability-list">
                  {matches.slice(0, 1).map((capability) => (
                    <button key={capability.id} onClick={() => onSelect(capability)} type="button">
                      <span>{capability.name}</span>
                      <span className={`maturity-dot maturity-dot--${capability.maturity.toLowerCase()}`} />
                    </button>
                  ))}
                  {matches.length > 1 && <small>+{matches.length - 1} more in constellation</small>}
                </div>
              ) : (
                <p className="empty-copy">
                  {normalizedQuery ? 'No matching capability' : 'No grounded capability found'}
                </p>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}
