"""LoopLedger homepage; business actions remain in the individual pages."""

import streamlit as st


PAGES = (
    (
        "pages/1_Run_Batch.py", "Run Batch", "▶️",
        "Choose a batch size, inspect AI recommendations and route applications for review.",
    ),
    (
        "pages/2_Review_Queue.py", "Review Queue", "📋",
        "Inspect an application, compare the AI recommendation and record your own decision.",
    ),
    (
        "pages/3_Oversight_Dashboard.py", "Oversight Dashboard", "📊",
        "Explore reviewer activity, override rates, control checks and review-time distributions.",
    ),
    (
        "pages/4_Compliance.py", "Compliance", "📄",
        "Check the verification interface, preview an evidence report and download Markdown or JSON.",
    ),
)

WORKFLOW = """
flowchart LR
    B["Batch applications"] --> G{"Risk gate"}
    G -->|Needs review| R["Human review"]
    G -->|Auto eligible| A["Automatic routing"]
    R --> M["Oversight indicators"]
    A --> M
    R --> L[("SQLite audit log")]
    A --> L
    L --> E["Evidence report"]
"""


def main() -> None:
    st.set_page_config(page_title="LoopLedger | AI Oversight", page_icon="🔎", layout="wide")
    st.caption("Synoptix Responsible AI Hackathon · HumanLoop + ComplyFlow")
    st.title("LoopLedger")
    st.markdown("### Oversight that proves itself.")
    st.write(
        "A prototype for making AI-assisted decisions reviewable and gathering evidence "
        "about human oversight. Explore loan-application routing, record a review, "
        "inspect oversight indicators and try the evidence-report interface."
    )
    st.info(
        "Pages use the connected model and database interfaces. Run a batch, "
        "review saved applications, inspect persisted oversight metrics, then verify "
        "and export an evidence report."
    )

    st.subheader("How the workflow fits together")
    if callable(getattr(st, "mermaid_chart", None)):
        st.mermaid_chart(
            WORKFLOW,
            alt="Batch applications pass through a risk gate to human review or automatic routing. "
                "Both feed oversight indicators and a SQLite audit log used by evidence reports.",
        )
    else:
        st.code(
            "Batch applications → Risk gate → Human review → Oversight indicators\n"
            "                            ↘ Automatic routing → Oversight indicators\n"
            "Human review / Automatic routing → SQLite audit log → Evidence report",
            language="text",
        )
    st.caption(
        "Connected prototype workflow: model and gate → saved routing → human review → metrics and evidence."
    )

    st.subheader("Choose a workspace")
    for start in (0, 2):
        for column, (path, title, icon, description) in zip(st.columns(2), PAGES[start:start + 2]):
            with column:
                with st.container(border=True):
                    st.markdown(f"#### {icon} {title}")
                    st.write(description)
                    st.page_link(path, label=f"Open {title}", icon=icon, width="stretch")

    st.subheader("What is available today")
    st.table([
        {"Workspace": "Run Batch", "Available now": "Model predictions, risk gate and persisted routing",
         "Scope": "German Credit dataset; no loan transactions are executed"},
        {"Workspace": "Review Queue", "Available now": "Database queue; approve, reject or modify / hold with audit events",
         "Scope": "Modify records a request; it does not edit loan terms"},
        {"Workspace": "Oversight Dashboard", "Available now": "B's persisted system and reviewer metrics",
         "Scope": "Heuristic indicators; small samples remain insufficient"},
        {"Workspace": "Compliance", "Available now": "B's chain verification and D's Markdown / JSON reports",
         "Scope": "Local event consistency; no certification or independent anchoring"},
    ])

    st.subheader("Try the demo")
    st.markdown(
        "1. Open **Run Batch**, choose a batch size, then click **Run batch**.\n"
        "2. Open **Review Queue** in the sidebar, inspect a case, enter a reviewer and reason, then approve or reject it.\n"
        "3. Open **Oversight Dashboard** and refresh to inspect the updated indicators.\n"
        "4. Open **Compliance**, verify, generate and download the report."
    )


if __name__ == "__main__":
    main()
