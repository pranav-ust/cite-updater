from cite_updater.matchers import initial_matches, is_compound_initial, is_name_match
from cite_updater.normalize import parse_author


def _author(s: str):
    return parse_author(s)


def test_is_name_match_exact():
    assert is_name_match(_author("Ashish Vaswani"), _author("Ashish Vaswani"))


def test_is_name_match_with_initial():
    assert is_name_match(_author("A. Vaswani"), _author("Ashish Vaswani"))


def test_is_name_match_with_accents():
    assert is_name_match(_author("Jose Hernandez"), _author("José Hernández"))


def test_initial_does_not_match_full_to_full():
    # "Jeff" and "Jeffrey" are both full names — should NOT match via initials.
    assert not initial_matches("Jeff", "Jeffrey")


def test_initial_matches_single_letter():
    assert initial_matches("A.", "Ashish")


def test_compound_initial_pattern():
    assert is_compound_initial("K.-T")
    assert is_compound_initial("C.-J.")
    assert not is_compound_initial("Kim")


def test_different_first_names_dont_match():
    assert not is_name_match(_author("Jeff Sun"), _author("Jian Sun"))


def test_last_name_prefix_handled_in_match():
    # "De Choudhury" vs "Choudhury" with same first name. is_name_match itself does not strip
    # prefixes, but the higher-level _authors_equivalent does. Make sure parse_author leaves it intact.
    a = _author("Munmun De Choudhury")
    assert "choudhury" in a["last_name"].lower()
