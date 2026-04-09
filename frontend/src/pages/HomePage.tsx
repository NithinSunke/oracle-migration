import { AppFrame } from "../components/AppFrame";
import { navigate } from "../app/router";

export function HomePage() {
  return (
    <AppFrame
      eyebrow="Oracle Migration Decision Support"
      title="Plan Oracle-to-Oracle migrations with an explainable intake flow"
      summary="Capture migration facts, generate a recommendation, and review why the engine chose that path before you commit to execution planning."
      actions={
        <button className="primary-button" type="button" onClick={() => navigate("/migration/new")}>
          Start New Assessment
        </button>
      }
    >
      <section className="overview-grid">
        <article className="panel">
          <p className="chip">Flow</p>
          <h2>Intake to Recommendation</h2>
          <p>
            The UI follows the architecture plan: collect inputs, submit to the API,
            and render the explainable recommendation payload without exposing rule internals.
          </p>
        </article>
        <article className="panel">
          <p className="chip">What Reviewers See</p>
          <h2>Decision Context, Not Just a Winner</h2>
          <p>
            Confidence, rationale, prerequisites, risks, companion tools, and rejected
            methods are all visible for DBA and application-owner review.
          </p>
        </article>
        <article className="panel">
          <p className="chip">Designed For Extension</p>
          <h2>History and Reports Included</h2>
          <p>
            Saved assessments can now be reopened through history views and exported
            as structured JSON reports for operational review and audit workflows.
          </p>
        </article>
      </section>
    </AppFrame>
  );
}
