"""
test_file_analysis.py — Integration and Unit Verification Script
"""

import sys
import os
import tempfile

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from file_analyzer import (
    sanitize_filename,
    detect_mime_type,
    registry,
    GPT120BFileAnalysisProvider
)
from main import app
from fastapi.testclient import TestClient

def test_sanitization_and_mime():
    print("--- 1. Testing Filename Sanitization & MIME Detection ---")
    assert sanitize_filename("../../../etc/passwd") == "passwd"
    assert sanitize_filename("malware-report (1).pdf") == "malware-report__1_.pdf"
    print("OK: Filename sanitization passed.")

    # Test PDF signature
    with tempfile.NamedTemporaryFile("wb", suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.7 header content...")
        pdf_path = f.name

    mime = detect_mime_type("report.pdf", "application/pdf", pdf_path)
    os.unlink(pdf_path)
    assert mime == "application/pdf"
    print("OK: MIME detection passed.")

def test_provider_registry():
    print("--- 2. Testing Provider Registry ---")
    provider = registry.get_provider("gpt-120b")
    assert isinstance(provider, GPT120BFileAnalysisProvider)
    assert provider.get_provider_name() == "gpt-120b"
    print("OK: Provider registry lookup passed.")

def test_fastapi_endpoint():
    print("--- 3. Testing FastAPI endpoint /api/ai/analyze-file ---")
    client = TestClient(app)

    # Test missing prompt validation
    response = client.post(
        "/api/ai/analyze-file",
        data={"prompt": ""},
        files={"file": ("test.txt", b"Hello world", "text/plain")}
    )
    print("Endpoint response status:", response.status_code, "body:", response.text)
    assert response.status_code in (400, 422)
    print("OK: Missing prompt validation passed.")

    # Test missing file validation
    response = client.post(
        "/api/ai/analyze-file",
        data={"prompt": "Analyze this file"},
    )
    assert response.status_code == 422  # FastAPI validation error
    print("OK: Missing file validation passed (HTTP 422).")

if __name__ == "__main__":
    try:
        test_sanitization_and_mime()
        test_provider_registry()
        test_fastapi_endpoint()
        print("\nALL UNIT & INTEGRATION CHECKS PASSED SUCCESSFULLY!")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
