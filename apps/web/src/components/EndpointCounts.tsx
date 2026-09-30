import type { EndpointCounts as Counts } from "../data/interfaces";

export function EndpointCounts({ counts }: { counts: Counts }) {
  return <p className="endpoint-counts small">
    <span>{counts.W} Working</span><span>{counts.M} Simulated</span><span>{counts.P} Planned</span>
    {counts["?"] > 0 ? <span>{counts["?"]} Definition pending</span> : null}
  </p>;
}
