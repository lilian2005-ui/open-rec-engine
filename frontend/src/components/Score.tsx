import { scoreTone } from "../format";

/** A round score (0-100) like on the Leads screen. */
export function ScoreRing({ score, size = 64, caption }: { score: number; size?: number; caption?: string }) {
  const stroke = size > 60 ? 6 : 4;
  const r = (size - stroke) / 2;
  const length = 2 * Math.PI * r;
  return (
    <div className={`ring ${scoreTone(score)}`} style={{ width: size, height: size }} title={`Score ${score} of 100`}>
      <svg width={size} height={size}>
        <circle className="track" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} />
        <circle className="bar" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke}
          strokeDasharray={length} strokeDashoffset={length * (1 - score / 100)} strokeLinecap="round" />
      </svg>
      <b style={{ fontSize: size > 60 ? 20 : 15 }}>
        {score}
        {caption && <small>{caption}</small>}
      </b>
    </div>
  );
}

/** A small score pill for tables; "–" when the job has no score yet. */
export function ScorePill({ score }: { score: number | null }) {
  if (score == null) return <span className="muted">–</span>;
  return <span className={`pill ${scoreTone(score)}`}>{score}</span>;
}
