export default function ScoreRing({
  score,
  size = 80,
  track = "#E2E0D8",
  color = "#556B2F",
}: {
  score: number
  size?: number
  track?: string
  color?: string
}) {
  const r = (size - 8) / 2
  const circ = 2 * Math.PI * r
  const dash = (score / 100) * circ
  return (
    <svg width={size} height={size} className="-rotate-90">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={track}
        strokeWidth="4"
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="4"
        strokeDasharray={`${dash} ${circ}`}
        strokeLinecap="round"
      />
    </svg>
  )
}
