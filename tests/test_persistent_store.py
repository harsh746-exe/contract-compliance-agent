from compliance_agent.memory.persistent_store import PersistentStore


def test_persistent_store_save_load_and_clear(tmp_path, requirement_objects, evidence_objects, decision_objects):
    store = PersistentStore(tmp_path / "store")

    store.save_requirements(requirement_objects)
    store.save_evidence_batch(evidence_objects)
    store.save_decisions(decision_objects)

    loaded_requirements = store.load_requirements()
    loaded_evidence = store.load_evidence()
    loaded_decisions = store.load_decisions()

    assert len(loaded_requirements) == 2
    assert len(loaded_evidence) == 2
    assert len(loaded_decisions) == 2
    assert store.get_evidence_for_requirement("REQ_0001")[0]["evidence_chunk_id"] == "response_chunk_1"
    assert store.get_decision_for_requirement("REQ_0002")["label"] == "partial"

    store.clear_all()

    assert store.load_requirements() == []
    assert store.load_evidence() == []
    assert store.load_decisions() == []
