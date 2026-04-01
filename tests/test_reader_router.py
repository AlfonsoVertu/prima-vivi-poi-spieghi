from reader_orchestrator_v2 import _heuristic_router


def test_router_mapping_minimo():
    assert _heuristic_router("riassumimi il capitolo")["intent"] == "recap"
    assert _heuristic_router("raccontamelo dal punto di vista di Michael")["intent"] == "alternate_pov"
    assert _heuristic_router("perché ha fatto così?")["intent"] == "explain"
