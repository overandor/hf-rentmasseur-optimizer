import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from main import run
def test_run():
    result = run()
    assert result["name"] == "Base64Tool"
    assert result["status"] == "running"
def test_returns_dict():
    result = run()
    assert isinstance(result, dict)
