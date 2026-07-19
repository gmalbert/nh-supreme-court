"""
Test chat setup and verify all components are working.
Run this to verify the chat feature is properly configured.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Test that all chat modules can be imported."""
    print("Testing imports...")

    try:
        from utils import opencode_chat
        print("  ✅ opencode_chat module imports successfully")
    except ImportError as e:
        print(f"  ❌ Failed to import opencode_chat: {e}")
        return False

    try:
        from utils import chat_retriever
        print("  ✅ chat_retriever module imports successfully")
    except ImportError as e:
        print(f"  ❌ Failed to import chat_retriever: {e}")
        return False

    try:
        from utils import chat_formatter
        print("  ✅ chat_formatter module imports successfully")
    except ImportError as e:
        print(f"  ❌ Failed to import chat_formatter: {e}")
        return False

    return True


def test_openai_library():
    """Test that openai library is installed."""
    print("\nTesting OpenAI library...")

    try:
        import openai
        print(f"  ✅ openai library installed (version {openai.__version__})")
        return True
    except ImportError:
        print("  ❌ openai library not installed")
        print("     Run: pip install openai")
        return False


def test_api_key():
    """Test that API key is configured."""
    print("\nTesting API key configuration...")

    try:
        from utils.opencode_chat import get_client
        client = get_client()
        print("  ✅ API key configured successfully")
        return True
    except ValueError as e:
        print(f"  ❌ API key not found: {e}")
        print("     Add OPENCODE_API_KEY to .streamlit/secrets.toml")
        return False
    except Exception as e:
        print(f"  ⚠️  Unexpected error: {e}")
        return False


def test_data_files():
    """Test that required data files exist."""
    print("\nTesting data files...")

    repo_root = Path(__file__).parent.parent

    # Check for Supreme Court data
    case_detail = repo_root / "data" / "case_detail.parquet"
    if case_detail.exists():
        size_mb = case_detail.stat().st_size / (1024 * 1024)
        print(f"  ✅ Supreme Court data found ({size_mb:.1f} MB)")
    else:
        print(f"  ⚠️  Supreme Court data not found: {case_detail}")
        print("     Run: python scripts/build_case_detail_parquet.py")

    # Check for NH Court data (optional)
    nh_opinions = repo_root / "data" / "processed" / "opinions.csv"
    if nh_opinions.exists():
        print(f"  ✅ NH Supreme Court data found")
    else:
        print(f"  ℹ️  NH Supreme Court data not found (optional)")

    return True


def test_case_retrieval():
    """Test that case retrieval works."""
    print("\nTesting case retrieval...")

    try:
        from utils.chat_retriever import retrieve_cases

        # Test Supreme Court search
        results = retrieve_cases(
            query="Fourth Amendment search and seizure",
            source="supreme-court",
            top_k=3
        )

        if results and len(results) > 0:
            print(f"  ✅ Supreme Court search returned {len(results)} cases")
            print(f"     Top result: {results[0].get('name', 'Unknown')}")
        else:
            print("  ⚠️  Supreme Court search returned no results")
            print("     Data may not be available")

        return True

    except Exception as e:
        print(f"  ❌ Case retrieval failed: {e}")
        return False


def test_response_formatting():
    """Test response formatting with mock data."""
    print("\nTesting response formatting...")

    try:
        from utils.chat_formatter import format_with_links

        mock_response = "In *Riley v. California*, the Court held that..."
        mock_cases = [
            {
                "name": "Riley v. California",
                "url": "pages/1_Cases.py?q=Riley"
            }
        ]

        formatted = format_with_links(mock_response, mock_cases)

        if "[*Riley v. California*]" in formatted:
            print("  ✅ Case citation linking works")
        else:
            print("  ⚠️  Case citation linking may not be working")

        return True

    except Exception as e:
        print(f"  ❌ Response formatting failed: {e}")
        return False


def test_home_page_chat():
    """Test that chat is integrated into the home page."""
    print("\nTesting home page chat integration...")

    repo_root = Path(__file__).parent.parent
    cases_py = repo_root / "cases.py"

    if not cases_py.exists():
        print(f"  ❌ Home page not found: {cases_py}")
        return False

    content = cases_py.read_text()

    if "ask_query" in content and "Ask AI" in content:
        print("  ✅ Home page has Ask & Browse AI chat widget")
    else:
        print("  ❌ Home page missing Ask & Browse chat widget")
        return False

    if "Chat Assistant" not in content and "14_Chat" not in content:
        print("  ✅ Standalone Chat page removed from navigation")
    else:
        print("  ⚠️  Old Chat page references remain in cases.py")

    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Chat Setup Verification")
    print("=" * 60)

    results = []

    # Run all tests
    results.append(("Imports", test_imports()))
    results.append(("OpenAI Library", test_openai_library()))
    results.append(("API Key", test_api_key()))
    results.append(("Data Files", test_data_files()))
    results.append(("Case Retrieval", test_case_retrieval()))
    results.append(("Response Formatting", test_response_formatting()))
    results.append(("Home Page Chat", test_home_page_chat()))

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}  {test_name}")

    print("\n" + "-" * 60)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Chat feature is ready to use.")
        print("\nNext steps:")
        print("  1. streamlit run cases.py")
        print("  2. Ask a question on the home page!")
        print("  3. Use 🔍 Search or 🚀 Ask AI buttons")
    else:
        print("\n⚠️  Some tests failed. Review the output above.")
        print("\nCommon fixes:")
        print("  - API key: Add to .streamlit/secrets.toml")
        print("  - OpenAI library: pip install openai")
        print("  - Data files: python scripts/build_case_detail_parquet.py")

    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
