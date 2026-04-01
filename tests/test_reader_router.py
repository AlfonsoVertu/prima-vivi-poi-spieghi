from reader_orchestrator_v2 import _pick_intent


def test_router_mapping_minimo():
    assert _pick_intent("riassumimi il capitolo") == "recap"
    assert _pick_intent("raccontamelo dal punto di vista di Michael") == "alternate_pov"
    assert _pick_intent("perché ha fatto così?") == "explain"
