export function AgentActivity() {
  return <section className="panel" aria-labelledby="activity-title">
    <span className="eyebrow">02 / COORDINATION</span>
    <h2 id="activity-title">Agent activity</h2>
    <p>No active run. Live Planner and Reviewer events will appear here.</p>
    <ol className="steps"><li>Retrieve relevant memory</li><li>Plan and save a handoff</li><li>Review against current decisions</li></ol>
    <small>Workflow outline only, not completed execution.</small>
  </section>;
}
