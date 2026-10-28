"""P0-2: normalisation rules for company names (Q2), content hash (Q3) and skills."""
import pytest

from backend.db.normalize import company_name_key, content_hash, normalize_skills

DESC = "We are looking for a Senior React Developer.\nRemote, full time."


@pytest.mark.parametrize("name", ["Acme Corp", "ACME  corp", "  acme corp ", "Acme\tCorp\n"])
def test_company_name_variants_share_a_key(name):
    assert company_name_key(name) == "acme corp"


def test_company_name_keeps_punctuation_and_suffix():
    assert company_name_key("Acme Corp Inc.") == "acme corp inc."
    assert company_name_key("Acme Corp Inc.") != company_name_key("Acme Corp")
    assert company_name_key("Acme, Ltd.") == "acme, ltd."


def test_content_hash_is_sha256_hex():
    h = content_hash("Senior React Developer", DESC)
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


def test_whitespace_only_change_keeps_the_hash():
    a = content_hash("Senior React Developer", DESC)
    b = content_hash("  Senior  React Developer ", "We are looking for a  Senior React Developer. Remote,\n\nfull time.  ")
    assert a == b


def test_title_change_changes_the_hash():
    assert content_hash("Senior React Developer", DESC) != content_hash("Lead React Developer", DESC)


def test_description_change_changes_the_hash():
    assert content_hash("Senior React Developer", DESC) != content_hash("Senior React Developer", DESC + " Hybrid.")


def test_title_and_description_are_kept_apart():
    assert content_hash("a b", "c") != content_hash("a", "b c")


def test_normalize_skills():
    assert normalize_skills([" React ", "TypeScript", "react", "", "Node  JS", "typescript"]) == [
        "react", "typescript", "node js"]
    assert normalize_skills([]) == []
