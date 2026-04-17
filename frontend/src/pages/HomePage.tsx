import { AppFrame } from "../components/AppFrame";
import { navigate } from "../app/router";

export function HomePage() {
  return (
    <AppFrame
      eyebrow="Oracle Migration Decision Support"
      title="Track migration readiness, blockers, and execution planning from one dashboard"
      summary="Review source-to-target fit, watch validation progress, surface blockers early, and keep the next migration actions visible for DBAs and application teams."
      pageClassName="page--dashboard"
      actions={
        <>
          <button className="primary-button" type="button" onClick={() => navigate("/migration/new")}>
            New Assessment
          </button>
          <button className="secondary-button" type="button" onClick={() => navigate("/reports")}>
            Open Reports
          </button>
        </>
      }
    >
      <section className="dashboard-metric-row">
        <article className="dashboard-stat dashboard-stat--blue">
          <span>Validated Sources</span>
          <strong>17</strong>
          <small>source environments completed intake and validation</small>
        </article>
        <article className="dashboard-stat dashboard-stat--coral">
          <span>Open Blockers</span>
          <strong>08</strong>
          <small>schema, wallet, ACL, and target readiness issues pending</small>
        </article>
        <article className="dashboard-stat dashboard-stat--white">
          <span>Migration Methods in Play</span>
          <strong>05</strong>
          <small>Data Pump, XTTS, RMAN, GoldenGate, and ZDM candidates</small>
        </article>
        <article className="dashboard-donut panel">
          <div className="dashboard-donut__ring" aria-hidden="true" />
          <ul className="dashboard-donut__legend">
            <li><span className="dashboard-dot dashboard-dot--purple" />Ready to plan 35%</li>
            <li><span className="dashboard-dot dashboard-dot--blue" />Needs remediation 25%</li>
            <li><span className="dashboard-dot dashboard-dot--coral" />Target gaps 25%</li>
            <li><span className="dashboard-dot dashboard-dot--amber" />Connectivity issues 15%</li>
          </ul>
        </article>
      </section>

      <section className="dashboard-grid">
        <article className="panel dashboard-chart-panel">
          <div className="dashboard-section-head">
            <div>
              <p className="chip">Migration Pipeline</p>
              <h2>Validation, blocker clearance, and execution planning timeline</h2>
            </div>
            <div className="dashboard-toggle">
              <span className="dashboard-toggle__pill dashboard-toggle__pill--active">Hr</span>
              <span className="dashboard-toggle__pill">Day</span>
              <span className="dashboard-toggle__pill">Week</span>
            </div>
          </div>
          <div className="dashboard-chart">
            <div className="dashboard-chart__grid" />
            <div className="dashboard-chart__wave dashboard-chart__wave--purple" />
            <div className="dashboard-chart__wave dashboard-chart__wave--amber" />
            <div className="dashboard-chart__callout">
              <strong>Window: 07:00</strong>
              <span>Cutover review checkpoint</span>
            </div>
          </div>
          <div className="dashboard-chart__legend">
            <span><i className="dashboard-line dashboard-line--purple" />Readiness</span>
            <span><i className="dashboard-line dashboard-line--blue" />Source analysis</span>
            <span><i className="dashboard-line dashboard-line--coral" />Remediation</span>
            <span><i className="dashboard-line dashboard-line--amber" />Execution planning</span>
          </div>
        </article>

        <article className="panel dashboard-side-stack">
          <div className="dashboard-mini-card">
            <p className="chip">Readiness Score</p>
            <div className="score-ring" aria-hidden="true">
              <div>
                <span>84</span>
                <small>Ready</small>
              </div>
            </div>
          </div>
          <div className="dashboard-mini-card">
            <p className="chip">Decision Signals</p>
            <ul className="tag-list">
              <li>Method fit</li>
              <li>TDE aware</li>
              <li>Wallet checks</li>
              <li>Network reachability</li>
            </ul>
          </div>
        </article>
      </section>

      <section className="dashboard-bottom-grid">
        <article className="panel dashboard-compare-panel">
          <div className="dashboard-section-head">
            <div>
              <p className="chip">Comparison Details</p>
              <h2>Migration workbench summary</h2>
            </div>
            <button className="secondary-button" type="button">
              View Runbook
            </button>
          </div>
          <div className="dashboard-progress-list">
            <div className="dashboard-progress-item">
              <span>Source Validation</span>
              <div className="dashboard-progress"><i style={{ width: "62%" }} /></div>
              <strong>17 complete</strong>
            </div>
            <div className="dashboard-progress-item">
              <span>Target Readiness</span>
              <div className="dashboard-progress dashboard-progress--blue"><i style={{ width: "74%" }} /></div>
              <strong>12 ready</strong>
            </div>
            <div className="dashboard-progress-item">
              <span>Execution Plans</span>
              <div className="dashboard-progress dashboard-progress--amber"><i style={{ width: "58%" }} /></div>
              <strong>09 drafted</strong>
            </div>
          </div>
        </article>

        <article className="panel dashboard-volume-panel">
          <div className="dashboard-section-head">
            <div>
              <p className="chip">Priority Findings</p>
              <h2>Most common migration blockers</h2>
            </div>
          </div>
          <div className="dashboard-tag-cards">
            <div className="dashboard-tag-card dashboard-tag-card--coral">
              <strong>Missing Target Schema</strong>
              <span>pre-create user, profile, and quota</span>
            </div>
            <div className="dashboard-tag-card dashboard-tag-card--blue">
              <strong>Wallet / Certificate Gaps</strong>
              <span>object storage and TCPS trust still required</span>
            </div>
            <div className="dashboard-tag-card dashboard-tag-card--purple">
              <strong>Tablespace / Directory Gaps</strong>
              <span>DDL generation recommended before import</span>
            </div>
          </div>
        </article>

        <article className="panel dashboard-status-panel">
          <p className="chip">Next Actions</p>
          <h2>Control room</h2>
          <dl className="snapshot-grid snapshot-grid--sidebar">
            <div>
              <dt>Current focus</dt>
              <dd>Target remediation</dd>
            </div>
            <div>
              <dt>Recommended method</dt>
              <dd>Data Pump</dd>
            </div>
            <div>
              <dt>Run state</dt>
              <dd className="dashboard-status-badge">PLAN READY</dd>
            </div>
          </dl>
        </article>
      </section>
    </AppFrame>
  );
}
