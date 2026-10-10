"""GTIN check shared by staging (barcode_valid) and the DQ rule R02.

gtin_check returns None when the barcode is a valid GTIN, otherwise a dict
that says why it failed (used as evidence in dq.dq_failure).
"""

VALID_LENGTHS = (8, 12, 13, 14)


def expected_check_digit(body_digits):
    """Check digit for the digits before it: weights 3,1,3,1 from the right."""
    body = body_digits[::-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(body))
    return (10 - total % 10) % 10


def gtin_check(barcode):
    if not isinstance(barcode, str) or not barcode.isascii() or not barcode.isdigit():
        return {"failure_type": "non_digit", "barcode": barcode}
    if len(barcode) not in VALID_LENGTHS:
        return {"failure_type": "bad_length", "barcode": barcode, "length": len(barcode)}
    digits = [int(c) for c in barcode]
    expected = expected_check_digit(digits[:-1])
    if expected != digits[-1]:
        return {
            "failure_type": "bad_check_digit",
            "barcode": barcode,
            "length": len(barcode),
            "expected_check_digit": expected,
            "actual_check_digit": digits[-1],
        }
    return None
