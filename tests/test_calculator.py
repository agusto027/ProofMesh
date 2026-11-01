import pytest

from proofmesh.evidence.calculator import calculate


def test_calculator_records_inputs_and_result():
    assert calculate("(price * quantity) + tax", {"price": 12, "quantity": 2, "tax": 3})["result"] == 27


def test_calculator_rejects_calls_and_attributes():
    with pytest.raises(ValueError):
        calculate("__import__('os').system('whoami')", {})
