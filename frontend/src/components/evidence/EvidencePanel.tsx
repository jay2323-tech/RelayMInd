export function EvidencePanel() {
  return <section className="panel" aria-labelledby="evidence-title">
    <span className="eyebrow">03 / EVIDENCE</span>
    <h2 id="evidence-title">Follow the source.</h2>
    <p>Sources, decision versions, and recalled episodes will appear here when retrieved from FalkorDB.</p>
    <div className="empty-state compact">No evidence retrieved.</div>
  </section>;
}
