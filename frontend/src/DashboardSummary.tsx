import type { DashboardSummary as DashboardSummaryData } from './api'

type Props = {
  summary: DashboardSummaryData | null
  loading: boolean
}

function metric(value: number | null, suffix = '') {
  return value === null ? '—' : `${value}${suffix}`
}

export function DashboardSummary({ summary, loading }: Props) {
  const cards = [
    {
      label: 'Monitors',
      value: summary?.total_monitors ?? 0,
      className: '',
    },
    {
      label: 'Operational',
      value: summary?.up_monitors ?? 0,
      className: 'metric-up',
    },
    {
      label: 'Down',
      value: summary?.down_monitors ?? 0,
      className: 'metric-down',
    },
    {
      label: 'Pending',
      value: summary?.pending_monitors ?? 0,
      className: 'metric-pending',
    },
    {
      label: 'Paused',
      value: summary?.paused_monitors ?? 0,
      className: '',
    },
    {
      label: 'Checks / 24h',
      value: summary?.checks_last_24h ?? 0,
      className: '',
    },
    {
      label: 'Avg response / 24h',
      value: summary
        ? metric(
            summary.average_response_time_ms_24h === null
              ? null
              : Math.round(summary.average_response_time_ms_24h),
            ' ms',
          )
        : '—',
      className: '',
    },
  ]

  return (
    <section className="dashboard-summary" aria-labelledby="overview-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Overview</p>
          <h2 id="overview-title">Monitoring overview</h2>
        </div>

        {summary && (
          <span className="summary-active">
            {summary.active_monitors} active
          </span>
        )}
      </div>

      <div className="metrics-grid">
        {cards.map(card => (
          <article className={`metric-card ${card.className}`} key={card.label}>
            <span className="metric-label">{card.label}</span>
            <strong className="metric-value">
              {loading && !summary ? '—' : card.value}
            </strong>
          </article>
        ))}
      </div>
    </section>
  )
}
