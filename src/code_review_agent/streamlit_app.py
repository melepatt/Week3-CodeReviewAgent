from __future__ import annotations

import streamlit as st

from code_review_agent.approval import ApprovalState
from code_review_agent.github import HeadChangedError
from code_review_agent.ui_runtime import ApplicationRuntime
from code_review_agent.ui_state import WorkflowState

st.set_page_config(
    page_title="Pull request review",
    page_icon=":material/rate_review:",
    layout="centered",
)


@st.cache_resource(ttl="15m", max_entries=4)
def load_runtime() -> ApplicationRuntime:
    return ApplicationRuntime.from_environment()


st.session_state.setdefault("workflow", WorkflowState())
st.session_state.setdefault("pr_url", "")
st.session_state.setdefault("approve_model_calls", False)
st.session_state.setdefault("approve_exact", False)
if st.session_state.pop("_clear_exact_approval", False):
    st.session_state["approve_exact"] = False

runtime = st.session_state.get("_runtime_override") or load_runtime()
workflow: WorkflowState = st.session_state["workflow"]

st.title("Pull request review")
st.caption(
    "Three bounded AI specialists prepare a draft. GitHub publication is a separate, "
    "human-approved action and is disabled by default."
)
if publication_error := st.session_state.pop("_publication_error", None):
    st.error(publication_error, title="Publication failed")

if not runtime.model_available:
    st.warning(
        "Model review is unavailable until LLM_API_KEY and LLM_BASE_URL are configured.",
        title="Model not configured",
    )
if not runtime.publish_enabled:
    st.info(
        "Publishing is disabled by default. Preview remains available for public pull requests.",
        title="Safe default",
    )

with st.form("preview_form", border=False):
    st.text_input(
        "Canonical GitHub pull-request URL",
        placeholder="https://github.com/owner/repository/pull/123",
        key="pr_url",
    )
    st.form_submit_button(
        "Preview pull request",
        icon=":material/preview:",
        key="preview_submit",
    )

current_url = st.session_state["pr_url"].strip()
preview_clicked = st.session_state.get("preview_submit", False)
if current_url != workflow.url:
    workflow = workflow.with_url(current_url)
    st.session_state["approve_model_calls"] = False
    st.session_state["approve_exact"] = False

if preview_clicked:
    try:
        preview = runtime.preview(current_url)
    except Exception as exc:  # public error types are already sanitized
        st.error(str(exc), title="Preview failed")
    else:
        workflow = workflow.with_preview(preview)
        st.session_state["approve_model_calls"] = False
        st.session_state["approve_exact"] = False

st.session_state["workflow"] = workflow

if workflow.preview is not None:
    preview = workflow.preview
    with st.container(border=True):
        st.subheader("Pull-request snapshot")
        st.markdown(
            "\n".join(
                (
                    f"- Repository: `{preview.owner}/{preview.repo}`",
                    f"- Pull request: `#{preview.number}` — {preview.title}",
                    f"- Author: `{preview.author}`",
                    f"- Branches: `{preview.base_branch}` ← `{preview.head_branch}`",
                    f"- Head SHA: `{preview.head_sha}`",
                )
            )
        )

    if not runtime.model_available:
        st.warning(
            "Model review is unavailable until LLM_API_KEY and LLM_BASE_URL are configured.",
            title="Model not configured",
        )

    st.checkbox(
        f"I approve these model calls: {runtime.model_call_summary}",
        key="approve_model_calls",
        disabled=not runtime.model_available,
    )
    run_review = st.button(
        "Run review",
        icon=":material/play_arrow:",
        type="primary",
        key="run_review",
        disabled=not (runtime.model_available and st.session_state["approve_model_calls"]),
    )
    if run_review:
        try:
            with st.spinner("Running correctness, security, and test-coverage specialists…"):
                outcome = runtime.review(workflow.url)
        except Exception as exc:  # sanitized capability and service errors only
            st.error(str(exc), title="Review failed")
        else:
            workflow = workflow.with_outcome(outcome)
            st.session_state["review_body"] = workflow.edited_markdown
            st.session_state["approve_exact"] = False
            st.session_state["workflow"] = workflow

if workflow.outcome is not None:
    outcome = workflow.outcome
    st.header("Review result")
    if outcome.aborted:
        st.error(
            "Two or more specialists failed. Diagnostic results are shown, but no review "
            "can be approved.",
            title="Review aborted",
        )
    elif outcome.partial:
        st.warning(
            "Partial review: one specialist failed. The exact draft discloses the failure.",
            title="Partial result",
        )

    with st.container(border=True):
        st.subheader("Specialist status")
        for result in outcome.specialists:
            if result.status.value == "success":
                st.markdown(
                    f"- `{result.identity.value}`: completed with "
                    f"{len(result.findings)} candidate finding(s)"
                )
            else:
                st.markdown(f"- `{result.identity.value}`: failed — {result.failure}")

    if outcome.static_analysis.available:
        st.info(outcome.static_analysis.summary, title="Static analysis")
    else:
        st.warning(outcome.static_analysis.summary, title="Static analysis unavailable")

    if outcome.markdown is not None:
        st.subheader("Exact consolidated Markdown")
        st.caption(
            "The hidden idempotence marker is part of this exact body. Any edit resets approval."
        )
        st.session_state.setdefault("review_body", workflow.edited_markdown)
        edited_body = st.text_area(
            "Review Markdown",
            key="review_body",
            height=420,
        )
        if edited_body != workflow.edited_markdown:
            workflow = workflow.with_edited_markdown(edited_body)
            st.session_state["approve_exact"] = False

        approved = st.checkbox(
            "I approve this exact Markdown body for GitHub publication",
            key="approve_exact",
        )
        if approved:
            approval = ApprovalState.approve(
                workflow.url,
                outcome.metadata.head_sha,
                workflow.generated_markdown,
                workflow.edited_markdown,
            )
            workflow = workflow.with_approval(approval)
        elif workflow.approval.fingerprint is not None:
            workflow = workflow.with_approval(ApprovalState())

        if not runtime.publish_enabled:
            st.info(
                "Publishing is disabled. Set ENABLE_GITHUB_PUBLISH=true and provide "
                "GITHUB_WRITE_TOKEN only for a controlled acceptance test.",
                title="Safe default",
            )
        approved_exactly = workflow.approval.matches(
            workflow.url,
            outcome.metadata.head_sha,
            workflow.generated_markdown,
            workflow.edited_markdown,
        )
        publish_clicked = st.button(
            "Publish approved comment",
            icon=":material/publish:",
            key="publish_comment",
            disabled=not (runtime.publish_enabled and approved_exactly),
        )
        if publish_clicked:
            try:
                result = runtime.publish(
                    outcome,
                    workflow.url,
                    workflow.edited_markdown,
                    workflow.approval,
                )
            except HeadChangedError as exc:
                workflow = workflow.with_approval(ApprovalState())
                st.session_state["workflow"] = workflow
                st.session_state["_clear_exact_approval"] = True
                st.session_state["_publication_error"] = str(exc)
                st.rerun()
            except Exception as exc:
                st.error(str(exc), title="Publication failed")
            else:
                workflow = workflow.with_comment(result.comment_id, result.action)

    if workflow.comment_id is not None:
        st.success(
            f"GitHub comment {workflow.comment_id} {workflow.comment_action}.",
            title="Publication complete",
        )

st.session_state["workflow"] = workflow
