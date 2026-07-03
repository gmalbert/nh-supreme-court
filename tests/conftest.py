"""
Pytest configuration and shared fixtures for Granite State Appeals tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest


@pytest.fixture
def sample_opinion() -> dict[str, Any]:
    """Sample opinion record for testing."""
    return {
        "case_number": "2024-0123",
        "citation": "175 N.H. 456",
        "citation_year": 2024,
        "citation_seq": 123,
        "case_name": "State v. Smith",
        "pdf_url": "https://www.courts.nh.gov/sites/g/files/ehbemt471/files/documents/2024-06/2024-0123.pdf",
        "date_argued": "2024-03-15",
        "date_issued": "2024-06-20",
        "days_to_decision": 97,
        "term_year": 2024,
        "lower_court": "Hillsborough Superior Court",
        "lower_court_type": "Superior",
        "case_type": "Criminal",
        "appeal_type": "Direct Appeal",
        "outcome": "Affirmed",
        "author": "MacDonald",
        "author_display": "MacDonald, C.J.",
        "majority": ["macdonald", "hicks", "bassett", "donovan"],
        "dissent": ["hantz_marconi"],
        "concur_separate": [],
        "not_participating": [],
        "vote_string": "4-1",
        "is_unanimous": False,
        "has_dissent": True,
        "has_separate_concurrence": False,
        "topics": ["Criminal Law", "Evidence", "Search and Seizure"],
        "rsa_citations": ["RSA 595-A:3", "RSA 595-A:6"],
        "rsa_primary": "RSA 595-A",
        "involves_statutory_interpretation": True,
        "summary_paragraph": "The State appealed from a superior court order granting defendant's motion to suppress evidence...",
        "word_count": 4250,
        "opinion_type": "published",
        "parse_version": "2.0",
        "parse_confidence": "high",
    }


@pytest.fixture
def sample_opinions_df(sample_opinion) -> pd.DataFrame:
    """Sample opinions DataFrame for testing."""
    opinions = [
        sample_opinion,
        {
            **sample_opinion,
            "case_number": "2024-0124",
            "citation": "175 N.H. 457",
            "citation_seq": 124,
            "case_name": "Doe v. Public Service Co.",
            "case_type": "Civil",
            "outcome": "Reversed",
            "is_unanimous": True,
            "has_dissent": False,
            "dissent": [],
            "majority": ["macdonald", "hicks", "bassett", "donovan", "hantz_marconi"],
            "vote_string": "5-0",
        },
        {
            **sample_opinion,
            "case_number": "2023-0456",
            "citation": "174 N.H. 789",
            "citation_year": 2023,
            "citation_seq": 456,
            "case_name": "In re Estate of Johnson",
            "case_type": "Civil",
            "topics": ["Probate", "Wills", "Trusts"],
            "outcome": "Remanded",
        },
    ]
    return pd.DataFrame(opinions)


@pytest.fixture
def sample_vote_text() -> str:
    """Sample vote block text for testing vote parsing."""
    return """AFFIRMED.

MacDonald, C.J., and Hicks, Bassett, and Donovan, JJ., concurred; 
Hantz Marconi, J., dissented; the reasons for the dissent are stated 
in a separate opinion."""


@pytest.fixture
def sample_citation_text() -> str:
    """Sample opinion text with citations for testing citation extraction."""
    return """In State v. Ball, 124 N.H. 226, 231 (1983), we held that 
constitutional protections apply. See also State v. McKinnon-Andrews, 
151 N.H. 19, 24 (2004); State v. Cora, 170 N.H. 186 (2017). The neutral 
citation format, as in 2020 NH 012, should also be recognized."""


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory structure for testing."""
    data_dir = tmp_path / "data"
    processed_dir = data_dir / "processed"
    processed_dir.mkdir(parents=True)
    
    (processed_dir / "text").mkdir()
    (data_dir / "raw").mkdir(parents=True)
    
    return data_dir


@pytest.fixture
def mock_opinion_text() -> str:
    """Sample full opinion text for testing search and text analysis."""
    return """STATE OF NEW HAMPSHIRE

SUPREME COURT

In Case No. 2024-0123

State v. Smith

Opinion issued June 20, 2024

SUMMARY

The State appealed from a superior court order granting defendant's 
motion to suppress evidence obtained during a warrantless search of 
his vehicle. The Supreme Court affirmed, holding that the reasonable 
expectation of privacy standard under RSA 595-A:3 applies to vehicle 
searches, and that the State failed to establish an exception to the 
warrant requirement.

AFFIRMED.

MacDonald, C.J., and Hicks, Bassett, and Donovan, JJ., concurred; 
Hantz Marconi, J., dissented.

[Full opinion text would continue here...]
"""


@pytest.fixture
def mock_search_index_data() -> list[dict[str, Any]]:
    """Sample data for testing search index building."""
    return [
        {
            "case_number": "2024-0123",
            "citation": "175 N.H. 456",
            "case_name": "State v. Smith",
            "full_text": "reasonable expectation of privacy",
            "summary": "warrantless search of vehicle",
            "topics": ["Criminal Law", "Search and Seizure"],
            "author": "MacDonald",
            "outcome": "Affirmed",
            "year": 2024,
        },
        {
            "case_number": "2024-0124",
            "citation": "175 N.H. 457",
            "case_name": "Doe v. Public Service Co.",
            "full_text": "negligence standard breach of duty",
            "summary": "utility company liability for damages",
            "topics": ["Torts", "Negligence"],
            "author": "Hicks",
            "outcome": "Reversed",
            "year": 2024,
        },
    ]


@pytest.fixture
def sample_case_order() -> dict[str, Any]:
    """Sample case order for testing."""
    return {
        "docket_number": "2024-0123",
        "order_date": "2024-02-15",
        "order_type": "Motion Order",
        "description": "Motion for Extension of Time GRANTED",
        "pdf_url": "https://www.courts.nh.gov/orders/2024-02-15.pdf",
    }


@pytest.fixture
def sample_oral_argument() -> dict[str, Any]:
    """Sample oral argument record for testing."""
    return {
        "docket_number": "2024-0123",
        "case_name": "State v. Smith",
        "argument_date": "2024-03-15",
        "duration_minutes": 45,
        "transcript_available": True,
        "vimeo_url": "https://vimeo.com/123456789",
        "attorneys": [
            {"name": "Jane Attorney", "role": "Appellant Counsel", "firm": "State Attorneys"},
            {"name": "John Defender", "role": "Appellee Counsel", "firm": "Public Defender"},
        ],
    }
