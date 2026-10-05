import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { MonitorCheck } from './api'

type Props = {
  checks: MonitorCheck[]
}

type ChartPoint = {
  checkedAt: string
  time: string
  responseTime: number
  status: 'UP' | 'DOWN'
}

function formatTime(value: string) {
  return new Date(value).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function ResponseTimeChart({
  checks,
}: Props) {
  const data: ChartPoint[] = checks
    .filter(
      check =>
        check.response_time_ms !== null,
    )
    .slice()
    .reverse()
    .map(check => ({
      checkedAt: check.checked_at,
      time: formatTime(check.checked_at),
      responseTime: check.response_time_ms as number,
      status: check.status,
    }))

  if (data.length === 0) {
    return (
      <section
        className="panel response-chart-panel"
        aria-labelledby="response-chart-title"
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">
              Recent checks
            </p>

            <h2 id="response-chart-title">
              Response time
            </h2>
          </div>
        </div>

        <p className="muted">
          No response time data available yet.
        </p>
      </section>
    )
  }

  return (
    <section
      className="panel response-chart-panel"
      aria-labelledby="response-chart-title"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">
            Recent checks
          </p>

          <h2 id="response-chart-title">
            Response time
          </h2>
        </div>

        <span className="chart-unit">
          milliseconds
        </span>
      </div>

      <div className="response-chart">
        <ResponsiveContainer
          width="100%"
          height="100%"
        >
          <LineChart
            data={data}
            margin={{
              top: 10,
              right: 12,
              bottom: 4,
              left: 0,
            }}
          >
            <CartesianGrid
              stroke="#293845"
              strokeDasharray="4 4"
              vertical={false}
            />

            <XAxis
              dataKey="time"
              stroke="#8195a8"
              tickLine={false}
              axisLine={false}
              minTickGap={28}
              fontSize={11}
            />

            <YAxis
              stroke="#8195a8"
              tickLine={false}
              axisLine={false}
              width={48}
              fontSize={11}
              unit=" ms"
            />

            <Tooltip
              contentStyle={{
                background: '#121d27',
                border: '1px solid #405366',
                borderRadius: '8px',
              }}
              labelStyle={{
                color: '#a2b3c3',
              }}
              formatter={value => [
                `${Number(value)} ms`,
                'Response',
              ]}
            />

            <Line
              type="monotone"
              dataKey="responseTime"
              name="Response"
              stroke="#63d9b5"
              strokeWidth={2}
              dot={false}
              activeDot={{
                r: 4,
              }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}