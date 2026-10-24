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
    R -.-> L[("SQLite audit log<br/>integration pending")]
    A -.-> L
    L -.-> E["Evidence report<br/>B + D integration pending"]
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
        "Start with the session demo. Use the page links or sidebar in this browser "
        "tab so your mock applications and reviews stay in the same app session. "
        "Refreshing the browser or opening another tab may reset or separate the demo data."
    )

    st.subheader("How the workflow fits together")
    if callable(getattr(st, "mermaid_chart", None)):
        st.mermaid_chart(
            WORKFLOW,
            alt="Batch applications pass through a risk gate to human review or automatic routing. "
                "Both feed oversight indicators; database audit and evidence-report integration remain pending.",
        )
    else:
        st.code(
            "Batch applications → Risk gate → Human review → Oversight indicators\n"
            "                            ↘ Automatic routing → Oversight indicators\n"
            "Human review / Automatic routing ┄→ SQLite audit log ┄→ Evidence report\n"
            "                                    Database and report integration pending",
            language="text",
        )
    st.caption(
        "Solid arrows: the available mock-session workflow. "
        "Dashed arrows: database-backed audit and report integration still to complete."
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
        {"Workspace": "Run Batch", "Available now": "Mock batches, routing and a shared session queue; separate model preview",
         "Integration still pending": "Database persistence and real review-queue handoff"},
        {"Workspace": "Review Queue", "Available now": "Mock approvals with reviewer, reason and elapsed time",
         "Integration still pending": "Database reads/writes and audit events"},
        {"Workspace": "Oversight Dashboard", "Available now": "Indicators from completed reviews in this app session",
         "Integration still pending": "B's database-backed system and reviewer metrics"},
        {"Workspace": "Compliance", "Available now": "Four check states, fixture preview and Markdown / JSON downloads",
         "Integration still pending": "Real chain verification and D's reports using B's data"},
    ])

    st.subheader("Try the demo")
    st.markdown(
        "1. Open **Run Batch**, keep **Mock demo** and the default **50 applications**, then click **Run batch**.\n"
        "2. Open **Review Queue** in the sidebar, inspect a case, enter a reviewer and reason, then approve or reject it.\n"
        "3. Open **Oversight Dashboard**, keep **Session demo**, and refresh to inspect the updated indicators.\n"
        "4. Open **Compliance**, keep **UI demo**, choose **Pass**, verify, generate and download the fixture report."
    )
    st.warning(
        "Compliance UI demo uses a separate report fixture. Its downloads do not contain "
        "the approvals submitted in the steps above. Real evidence exports still require "
        "the B/D database interfaces to be connected and tested."
    )


if __name__ == "__main__":
    main()
