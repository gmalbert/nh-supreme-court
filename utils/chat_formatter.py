"""
Format LLM responses with clickable case links and styled components.
"""

import re
from typing import List, Dict, Optional
import streamlit as st


class ResponseFormatter:
    """
    Format and enhance LLM responses for display.
    """

    def __init__(self):
        self.case_link_pattern = re.compile(r'\*([A-Z][^*]+v\.\s+[^*]+)\*')

    def format_response_with_links(
        self,
        response_text: str,
        retrieved_cases: List[Dict]
    ) -> str:
        """
        Parse response and inject clickable markdown links for case citations.

        Args:
            response_text: Raw LLM response
            retrieved_cases: Cases that were provided as context

        Returns:
            Response with [case name](url) markdown links
        """
        # Build case name -> URL mapping
        case_map = {}
        for case in retrieved_cases:
            case_name = case.get("name", "")
            url = case.get("url", "")
            if case_name and url:
                case_map[case_name.lower()] = (case_name, url)

        # Find case citations in italics (*Case v. Name*)
        def replace_citation(match):
            cited_name = match.group(1)
            cited_lower = cited_name.lower()

            # Check if this case is in our retrieved cases
            for key, (original_name, url) in case_map.items():
                if key in cited_lower or cited_lower in key:
                    # Replace with markdown link
                    return f"[*{cited_name}*]({url})"

            # Not found in our cases - leave as is
            return f"*{cited_name}*"

        # Apply replacements
        formatted = self.case_link_pattern.sub(replace_citation, response_text)

        return self.normalize_case_links(formatted)

    @staticmethod
    def normalize_case_links(response_text: str) -> str:
        """Upgrade legacy chat links to the registered Streamlit page route.

        Assistant messages are persisted in session state after formatting, so
        conversations created before the route fix can still contain
        ``1_Cases.py?...`` links.  Streamlit resolves those to the app root and
        displays its Page not found dialog.
        """
        if not response_text:
            return response_text

        # Restrict replacements to Markdown link destinations so ordinary prose
        # containing these strings is never modified.
        return re.sub(
            r"\]\((?:/?1_Cases(?:\.py)?|/?)\?(q=[^)]+)\)",
            r"](/Cases?\1)",
            response_text,
        )

    def ensure_narrative(self, response_text: str, retrieved_cases: List[Dict]) -> str:
        """Return a visible narrative even when the provider returns no prose."""
        text = (response_text or "").strip()
        provider_error = text.startswith("⚠️")
        if provider_error:
            return text
        if text:
            return text

        usable = [case for case in retrieved_cases if case.get("name") and case.get("name") != "Error"]
        if not usable:
            return "I couldn't find enough case material to answer that question. Try rephrasing it with a legal issue or fact pattern."

        lead = "The most relevant cases in the collection are "
        citations = []
        for case in usable:
            name = case["name"]
            year = case.get("term") or case.get("year")
            citations.append(f"*{name}*" + (f" ({year})" if year else ""))
        narrative = lead + ", ".join(citations[:-1])
        if len(citations) > 1:
            narrative += f", and {citations[-1]}"
        else:
            narrative += citations[0]
        narrative += ". Open the source summaries below for the facts and legal questions available in the case data."
        return narrative

    def validate_citations(
        self,
        response_text: str,
        retrieved_cases: List[Dict]
    ) -> List[str]:
        """
        Check if LLM cited cases that weren't in the retrieved set.

        Returns:
            List of case names that appear to be hallucinated
        """
        retrieved_names = {c.get("name", "").lower() for c in retrieved_cases}

        # Find all case citations
        citations = self.case_link_pattern.findall(response_text)

        hallucinated = []
        for cited in citations:
            cited_lower = cited.lower()

            # Check if it matches any retrieved case
            matched = any(
                name in cited_lower or cited_lower in name
                for name in retrieved_names
            )

            if not matched:
                hallucinated.append(cited)

        return hallucinated

    def render_case_card(self, case: Dict, key_suffix: str = "") -> None:
        """
        Render a styled case card in Streamlit.

        Args:
            case: Case dict from retriever
            key_suffix: Unique suffix for Streamlit widgets
        """
        source_emoji = "🏛️" if case["source"] == "supreme-court" else "⚖️"
        source_label = "U.S. Supreme Court" if case["source"] == "supreme-court" else "NH Supreme Court"

        with st.container(border=True):
            col1, col2 = st.columns([5, 1])

            with col1:
                st.markdown(f"### {source_emoji} {case['name']}")

                # Metadata badges
                badges = []
                if case.get("term"):
                    badges.append(f"📅 {case['term']} Term")
                elif case.get("year"):
                    badges.append(f"📅 {case['year']}")

                if case.get("outcome"):
                    badges.append(f"⚖️ {case['outcome']}")

                if case.get("author"):
                    badges.append(f"✍️ {case['author']}")

                if badges:
                    st.caption(" • ".join(badges))

                # Snippet
                if case.get("snippet"):
                    with st.expander("📄 Case Summary", expanded=False):
                        st.write(case["snippet"])

            with col2:
                # Store case info in session state and create navigation button
                if case.get("url"):
                    # Parse case name from URL
                    full_url = case["url"]
                    case_name = case.get("name", "")

                    # Create unique button key
                    button_key = f"view_case_{key_suffix}_{case_name[:20].replace(' ', '_')}"

                    if st.button("View →", key=button_key, type="primary"):
                        # Set session state for Cases page to pick up
                        st.session_state["search_query"] = case_name
                        st.session_state["_chat_selected_case"] = case_name
                        # Navigate to Cases page
                        st.switch_page("pages/1_Cases.py")

    def render_sources_section(
        self,
        cases: List[Dict],
        key_suffix: str = ""
    ) -> None:
        """
        Render expandable sources section with case cards.

        Args:
            cases: List of retrieved cases
            key_suffix: Unique key suffix
        """
        with st.expander(f"📚 Sources ({len(cases)} cases)", expanded=False):
            for i, case in enumerate(cases):
                self.render_case_card(case, key_suffix=f"{key_suffix}_{i}")
                if i < len(cases) - 1:
                    st.divider()

    def render_follow_up_buttons(
        self,
        questions: List[str],
        key_suffix: str = ""
    ) -> Optional[str]:
        """
        Render follow-up question buttons and return selected question.

        Args:
            questions: List of follow-up question strings
            key_suffix: Unique key suffix

        Returns:
            Selected question text if clicked, else None
        """
        if not questions:
            return None

        st.markdown("#### 💡 Follow-up Questions")

        for i, question in enumerate(questions):
            if st.button(
                question,
                key=f"followup_{key_suffix}_{i}",
                use_container_width=True,
            ):
                return question

        return None


# Singleton instance
_formatter = None

def get_formatter() -> ResponseFormatter:
    """Get or create formatter instance."""
    global _formatter
    if _formatter is None:
        _formatter = ResponseFormatter()
    return _formatter


# Convenience functions
def format_with_links(response_text: str, cases: List[Dict]) -> str:
    """Format response with links. See ResponseFormatter.format_response_with_links."""
    formatter = get_formatter()
    narrative = formatter.ensure_narrative(response_text, cases)
    return formatter.format_response_with_links(narrative, cases)


def normalize_case_links(response_text: str) -> str:
    """Normalize links in already-formatted/stored assistant messages."""
    return get_formatter().normalize_case_links(response_text)


def render_sources(cases: List[Dict], key_suffix: str = "") -> None:
    """Render sources section. See ResponseFormatter.render_sources_section."""
    formatter = get_formatter()
    formatter.render_sources_section(cases, key_suffix)


def render_follow_ups(questions: List[str], key_suffix: str = "") -> Optional[str]:
    """Render follow-up buttons. See ResponseFormatter.render_follow_up_buttons."""
    formatter = get_formatter()
    return formatter.render_follow_up_buttons(questions, key_suffix)
