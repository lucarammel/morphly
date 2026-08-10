import copy

import pytest
from pydantic import ValidationError

import morphly.workflow
from morphly import Config, Delete, Entity, Patch, Put, Step, Store, Workflow, Write, module, view


class Plant(Entity):
    pmax: float
    cost: float
    cleared: float = 0.0


class ThermalPlant(Plant):
    fuel: str = "gas"


class Order(Entity):
    volume: float
    price: float


class BidParams(Config):
    margin: float = 1.0


@module
def bidding(plants: list[Plant], params: BidParams) -> list[Order]:
    return [Order(name=f"o_{p.name}", volume=p.pmax, price=p.cost * params.margin) for p in plants]


@module
def clearing(orders: list[Order], plants: list[Plant]) -> list[Patch[Plant] | Delete[Order]]:
    by_order = {f"o_{p.name}": p for p in plants}
    ops: list[Patch[Plant] | Delete[Order]] = []
    for order in orders:
        if order.price < 30:
            ops.append(Patch(by_order[order.name], cleared=order.volume))
        else:
            ops.append(Delete(order))
    return ops


@pytest.fixture
def store() -> Store:
    return Store(
        Plant(name="a", pmax=100, cost=10),
        ThermalPlant(name="b", pmax=50, cost=40),
        BidParams(margin=1.2),
    )


def test_store_reads_subclasses(store: Store):
    assert sorted(p.name for p in store.all(Plant)) == ["a", "b"]
    assert [p.name for p in store.all(ThermalPlant)] == ["b"]
    assert store.one(BidParams).margin == 1.2


def test_workflow_runs_and_applies(store: Store):
    Workflow(bidding, clearing).run(store)

    # a bids at 10*1.2=12 -> cleared; b bids at 40*1.2=48 -> order dropped
    assert [o.name for o in store.all(Order)] == ["o_a"]
    assert store.find(Order, "o_a").price == 12
    assert store.find(Plant, "a").cleared == 100
    assert store.find(ThermalPlant, "b").cleared == 0


def test_step_config_overrides_store(store: Store):
    Workflow(Step(bidding, BidParams(margin=2.0))).run(store)
    assert store.find(Order, "o_a").price == 20


def test_same_module_twice_with_different_configs(store: Store):
    workflow = Workflow(Step(bidding, BidParams(margin=1.0)), Step(bidding, BidParams(margin=3.0)))
    assert [s.name for s in workflow.steps] == ["bidding", "bidding_2"]
    workflow.run(store)
    assert store.find(Order, "o_a").price == 30  # last step wins


def test_missing_config_is_an_error():
    with pytest.raises(LookupError):
        Workflow(bidding).run(Store(Plant(name="a", pmax=1, cost=1)))


def test_check_rejects_unsatisfied_read():
    class Trade(Entity):
        volume: float

    @module
    def settle(trades: list[Trade]) -> None: ...

    with pytest.raises(LookupError, match="Trade"):
        Workflow(settle).check(Store())


def test_check_accepts_type_produced_upstream(store: Store):
    Workflow(bidding, clearing).check(store)  # Order only exists after `bidding`


def test_check_rejects_config_neither_bound_nor_in_store():
    @module
    def needs_config(plants: list[Plant], params: BidParams) -> None: ...

    with pytest.raises(LookupError, match="BidParams"):
        Workflow(needs_config).check(Store(Plant(name="a", pmax=1, cost=1)))


def test_check_accepts_config_bound_to_step():
    @module
    def needs_config(plants: list[Plant], params: BidParams) -> None: ...

    Workflow(Step(needs_config, BidParams())).check(Store(Plant(name="a", pmax=1, cost=1)))


def test_check_rejects_touching_a_type_nobody_provides():
    class Ghost(Entity):
        pass

    @module
    def haunt() -> list[Patch[Ghost]]:
        raise NotImplementedError

    with pytest.raises(LookupError, match="touches Ghost"):
        Workflow(haunt).check(Store())


def test_inputs_are_isolated(store: Store):
    @module
    def sneaky(plants: list[Plant]) -> None:
        plants[0].cleared = 999

    Workflow(sneaky).run(store)
    assert {p.cleared for p in store.all(Plant)} == {0}


def test_undeclared_output_is_rejected(store: Store):
    @module
    def liar(plants: list[Plant]) -> list[Order]:
        return [Plant(name="ghost", pmax=1, cost=1)]  # ty: ignore[invalid-return-type]

    with pytest.raises(TypeError, match="not in its return type"):
        Workflow(liar).run(store)


def test_patch_on_a_module_view_reaches_the_stored_object(store: Store):
    class PlantMC(Plant):
        times: int = 0

    @module
    def enrich(plants: list[Plant]) -> list[Patch[Plant]]:
        views = [view(PlantMC, p, times=3) for p in plants]
        return [Patch(v, cleared=v.times * 2) for v in views]

    Workflow(enrich).run(store)
    assert {p.cleared for p in store.all(Plant)} == {6}
    assert not any(isinstance(p, PlantMC) for p in store.all(Plant))


def test_patch_rejects_unknown_field(store: Store):
    @module
    def bad(plants: list[Plant]) -> list[Patch[Plant]]:
        return [Patch(plants[0], nope=1)]

    with pytest.raises(ValueError, match="no field"):
        Workflow(bad).run(store)


def test_patch_validates_values(store: Store):
    @module
    def bad(plants: list[Plant]) -> list[Patch[Plant]]:
        return [Patch(plants[0], cleared="not a float")]

    with pytest.raises(ValidationError):
        Workflow(bad).run(store)


def test_step_is_atomic(store: Store):
    @module
    def half_bad(plants: list[Plant]) -> list[Patch[Plant] | Delete[Plant]]:
        return [Patch(plants[0], cleared=42), Delete(Plant(name="unknown", pmax=0, cost=0))]

    with pytest.raises(KeyError):
        Workflow(half_bad).run(store)
    assert {p.cleared for p in store.all(Plant)} == {0}
    assert len(store.all(Plant)) == 2


def test_delete_then_patch_same_target_is_rejected(store: Store):
    @module
    def dp(plants: list[Plant]) -> list[Delete[Plant] | Patch[Plant]]:
        p = plants[0]
        return [Delete(p), Patch(p, cleared=9.0)]

    with pytest.raises(ValueError, match="which the same step deletes"):
        Workflow(dp).run(store)
    assert store.find(Plant, "a") is not None


def test_on_step_hook(store: Store):
    seen: list[tuple[str, int]] = []
    Workflow(bidding, clearing).run(store, on_step=lambda s, ops, st: seen.append((s.name, len(st.all(Order)))))
    assert seen == [("bidding", 2), ("clearing", 1)]


def test_on_step_hook_receives_the_operations(store: Store):
    seen: list[list[str]] = []
    Workflow(bidding, clearing).run(store, on_step=lambda s, ops, st: seen.append([type(o).__name__ for o in ops]))
    assert seen == [["Order", "Order"], ["Patch", "Delete"]]


def test_reuse_is_none_before_the_first_run():
    assert Workflow(bidding).last_run is None


def test_reuse_skips_steps_whose_inputs_are_unchanged(store: Store):
    before = copy.deepcopy(store)
    calls: list[str] = []

    @module
    def step_a(plants: list[Plant]) -> list[Patch[Plant]]:
        calls.append("a")
        return [Patch(p, cleared=p.pmax) for p in plants]

    @module
    def step_b(plants: list[Plant]) -> None:
        calls.append("b")

    workflow = Workflow(step_a, step_b)
    workflow.run(store, record=True)
    assert calls == ["a", "b"]

    calls.clear()
    workflow.run(before, reuse=workflow.last_run)
    assert calls == []
    assert before.find(Plant, "a").cleared == 100


def test_reuse_reruns_from_the_first_changed_step(store: Store):
    calls: list[str] = []

    @module
    def step_a(plants: list[Plant]) -> list[Patch[Plant]]:
        calls.append("a")
        return [Patch(p, cleared=p.pmax) for p in plants]

    @module
    def step_b(plants: list[Plant]) -> None:
        calls.append("b")

    workflow = Workflow(step_a, step_b)
    workflow.run(store, record=True)
    assert calls == ["a", "b"]

    calls.clear()
    changed = Store(
        Plant(name="a", pmax=999, cost=10),
        ThermalPlant(name="b", pmax=50, cost=40),
        BidParams(margin=1.2),
    )
    workflow.run(changed, reuse=workflow.last_run)
    assert calls == ["a", "b"]
    assert changed.find(Plant, "a").cleared == 999


def test_reuse_still_calls_on_step_for_a_skipped_step(store: Store):
    before = copy.deepcopy(store)

    @module
    def step_a(plants: list[Plant]) -> list[Patch[Plant]]:
        return [Patch(p, cleared=p.pmax) for p in plants]

    workflow = Workflow(step_a)
    workflow.run(store, record=True)

    seen: list[str] = []
    workflow.run(before, reuse=workflow.last_run, on_step=lambda s, ops, st: seen.append(s.name))
    assert seen == ["step_a"]


def test_deepcopy_is_the_snapshot(store: Store):
    before = copy.deepcopy(store)
    Workflow(bidding).run(store)
    assert store.all(Order) and not before.all(Order)


def test_declaration_errors():
    with pytest.raises(TypeError, match="must be annotated"):
        module(lambda plants: None)

    with pytest.raises(TypeError, match="return type must be annotated"):

        @module
        def no_return(plants: list[Plant]): ...

    with pytest.raises(TypeError, match="element type must be an Entity"):

        @module
        def bad_list(names: list[str]) -> None: ...

    with pytest.raises(TypeError, match="unsupported annotation"):

        @module
        def bad_param(store: Store) -> None: ...

    with pytest.raises(TypeError, match=r"Patch\[YourEntity\]"):

        @module
        def bare_patch(plants: list[Plant]) -> list[Patch]:
            raise NotImplementedError

    with pytest.raises(TypeError, match=r"Put\[YourEntity\]"):

        @module
        def bare_put(plants: list[Plant]) -> list[Put]:
            raise NotImplementedError


def test_exact_type_wins_over_lineage():
    store = Store(Plant(name="x", pmax=1, cost=1), ThermalPlant(name="x", pmax=2, cost=1))
    assert store.find(Plant, "x").pmax == 1
    assert store.find(ThermalPlant, "x").pmax == 2


def test_ambiguous_lineage_is_reported():
    class HydroPlant(Plant):
        pass

    store = Store(ThermalPlant(name="x", pmax=1, cost=1), HydroPlant(name="x", pmax=2, cost=1))
    with pytest.raises(KeyError, match=r"ambiguous.*HydroPlant, ThermalPlant"):
        store.find(Plant, "x")


def test_explain(store: Store):
    assert Workflow(bidding, clearing).explain() == (
        "1. bidding: bidding(Plant[], BidParams) -> Order\n2. clearing: clearing(Order[], Plant[]) -> ~Plant, ~Order"
    )


def test_to_mermaid(store: Store):
    assert Workflow(bidding, clearing).to_mermaid() == (
        "flowchart LR\n"
        "    Plant --> bidding\n"
        "    bidding --> Order\n"
        "    Order --> clearing\n"
        "    Plant --> clearing\n"
        "    clearing -.-> Plant\n"
        "    clearing -.-> Order"
    )


def test_put_rejects_foreign_objects():
    with pytest.raises(TypeError, match="neither an Entity nor a Config"):
        Store("nope")  # ty: ignore[invalid-argument-type]


def test_entity_repr():
    assert repr(Plant(name="a", pmax=1, cost=1)) == "Plant(name='a')"


def test_delete_repr():
    order = Order(name="o_a", volume=1, price=1)
    assert repr(Delete(order)) == "Delete(Order(name='o_a'))"


def test_patch_repr():
    plant = Plant(name="a", pmax=1, cost=1)
    assert repr(Patch(plant, cleared=5)) == "Patch(Plant(name='a'), cleared)"


def test_patch_requires_at_least_one_field():
    with pytest.raises(ValueError, match="no field"):
        Patch(Plant(name="a", pmax=1, cost=1))


def test_drop_by_type_and_name(store: Store):
    store.drop(Plant, "a")
    assert [p.name for p in store.all(Plant)] == ["b"]


def test_drop_requires_a_name_when_given_a_type(store: Store):
    with pytest.raises(TypeError, match="requires a name"):
        store.drop(Plant)


def test_drop_removes_the_bucket_once_empty(store: Store):
    store.drop(ThermalPlant, "b")
    assert "ThermalPlant" not in repr(store)


def test_patch_by_type_and_name(store: Store):
    store.patch(Plant, "a", {"cleared": 42.0})
    assert store.find(Plant, "a").cleared == 42.0


def test_patch_requires_fields_when_given_a_type(store: Store):
    with pytest.raises(TypeError, match="requires fields"):
        store.patch(Plant, "a")


def test_store_repr(store: Store):
    assert repr(store) == "Store(Plant=1, ThermalPlant=1; BidParams)"


def test_workflow_repr():
    assert repr(Workflow(bidding, clearing)) == "Workflow(bidding, clearing)"


def test_step_rejects_duplicate_config_type(store: Store):
    with pytest.raises(LookupError, match="several BidParams"):
        Workflow(Step(bidding, BidParams(margin=1.0), BidParams(margin=2.0))).run(store)


def test_patch_target_runtime_type_mismatch_is_rejected(store: Store):
    @module
    def bad(plants: list[Plant]) -> list[Patch[Plant]]:
        return [Patch(Order(name="o_x", volume=1, price=1), cleared=1)]  # ty: ignore[invalid-return-type]

    with pytest.raises(TypeError, match="not in its return type"):
        Workflow(bad).run(store)


def test_last_run_is_only_recorded_on_demand(store: Store):
    workflow = Workflow(bidding)
    workflow.run(copy.deepcopy(store))
    assert workflow.last_run is None
    workflow.run(store, record=True)
    assert workflow.last_run is not None


def test_a_plain_run_does_not_pay_for_the_reuse_machinery(monkeypatch, store: Store):
    """Keying a step means serialising everything it reads — not paid unless asked."""
    keyed: list[str] = []
    monkeypatch.setattr(morphly.workflow, "_input_key", lambda step, st: keyed.append(step.name) or ())

    Workflow(bidding, clearing).run(copy.deepcopy(store))
    assert keyed == []

    Workflow(bidding, clearing).run(copy.deepcopy(store), record=True)
    assert keyed == ["bidding", "clearing"]


def test_a_failing_module_is_located_in_the_exception(store: Store):
    @module
    def boom(plants: list[Plant]) -> None:
        raise ZeroDivisionError("nope")

    with pytest.raises(ZeroDivisionError) as raised:
        Workflow(bidding, boom).run(store)
    note = raised.value.__notes__[0]
    assert "in step 2/2 'boom'" in note
    assert "boom(Plant[]) -> -" in note
    assert "Order=2" in note  # the state the step saw, not the initial one


def test_a_failing_apply_is_located_too(store: Store):
    @module
    def ghost_patch(plants: list[Plant]) -> list[Patch[Plant]]:
        return [Patch(Plant(name="unknown", pmax=0, cost=0), cleared=1.0)]

    with pytest.raises(KeyError) as raised:
        Workflow(ghost_patch).run(store)
    assert "in step 1/1 'ghost_patch'" in raised.value.__notes__[0]


def test_check_reports_a_wrong_order_as_such(store: Store):
    with pytest.raises(LookupError, match="produced by step 'bidding' at position 2 — move that step before it"):
        Workflow(clearing, bidding).check(store)


def test_check_still_reports_a_genuinely_missing_type(store: Store):
    class Ghost(Entity):
        pass

    @module
    def settle(ghosts: list[Ghost]) -> None: ...

    with pytest.raises(LookupError, match="neither in the store nor produced by an upstream step"):
        Workflow(settle).check(store)


def test_atomic_run_restores_the_store_on_failure(store: Store):
    @module
    def boom(orders: list[Order]) -> None:
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        Workflow(bidding, boom).run(store, atomic=True)
    assert store.all(Order) == []
    assert store.history(Order, "o_a") == []  # the log is rolled back with the rest


def test_a_non_atomic_run_leaves_the_intermediate_state(store: Store):
    @module
    def boom(orders: list[Order]) -> None:
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        Workflow(bidding, boom).run(store)
    assert len(store.all(Order)) == 2


def test_history_records_who_wrote_what(store: Store):
    Workflow(bidding, clearing).run(store)
    assert store.history(Order, "o_a") == [Write("bidding", "put")]
    assert store.history(Order, "o_b") == [Write("bidding", "put"), Write("clearing", "delete")]
    assert store.history(store.find(Plant, "a")) == [Write("clearing", "patch", ("cleared",))]


def test_history_ignores_writes_made_outside_a_run(store: Store):
    store.put(Plant(name="c", pmax=1, cost=1))
    store.patch(Plant, "c", {"cleared": 1.0})
    assert store.history(Plant, "c") == []


def test_history_follows_the_lineage(store: Store):
    @module
    def clear_all(plants: list[Plant]) -> list[Patch[Plant]]:
        return [Patch(p, cleared=1.0) for p in plants]

    Workflow(clear_all).run(store)
    assert store.history(Plant, "b") == [Write("clear_all", "patch", ("cleared",))]  # b is a ThermalPlant


def test_history_survives_a_snapshot(store: Store):
    Workflow(bidding).run(store)
    assert copy.deepcopy(store).history(Order, "o_a") == [Write("bidding", "put")]


def test_put_repr():
    order = Order(name="o_a", volume=1, price=1)
    assert repr(Put(order)) == "Put(Order(name='o_a'))"


def test_put_creates_like_a_bare_entity(store: Store):
    @module
    def explicit(plants: list[Plant]) -> list[Put[Order]]:
        return [Put(Order(name=f"o_{p.name}", volume=p.pmax, price=p.cost)) for p in plants]

    Workflow(explicit).run(store)
    assert sorted(o.name for o in store.all(Order)) == ["o_a", "o_b"]
    assert store.find(Order, "o_a").price == 10
    assert store.history(Order, "o_a") == [Write("explicit", "put")]


def test_put_replaces_the_stored_object(store: Store):
    store.put(Order(name="o_a", volume=1, price=1))

    @module
    def replace(orders: list[Order]) -> Put[Order]:
        return Put(Order(name="o_a", volume=9, price=9))

    Workflow(replace).run(store)
    assert store.find(Order, "o_a").volume == 9


def test_put_declares_the_type_as_produced(store: Store):
    @module
    def explicit(plants: list[Plant]) -> list[Put[Order] | Patch[Plant] | Delete[Plant]]:
        return [Put(Order(name="o_x", volume=1, price=1))]

    assert explicit.produces == [Order]
    assert explicit.touches == [Plant, Plant]
    Workflow(explicit, clearing).check(store)  # Order is produced upstream, wrapped in a Put


def test_put_works_for_configs(store: Store):
    class Summary(Config):
        total: float = 0.0

    @module
    def summarize(plants: list[Plant]) -> Put[Summary]:
        return Put(Summary(total=sum(p.pmax for p in plants)))

    Workflow(summarize).run(store)
    assert store.one(Summary).total == 150


def test_put_of_an_undeclared_type_is_rejected(store: Store):
    @module
    def liar(plants: list[Plant]) -> list[Put[Order]]:
        return [Put(Plant(name="ghost", pmax=1, cost=1))]  # ty: ignore[invalid-return-type]

    with pytest.raises(TypeError, match="produced a Plant, which is not in its return type"):
        Workflow(liar).run(store)


def test_put_and_bare_entities_mix(store: Store):
    @module
    def both(plants: list[Plant]) -> list[Put[Order] | Order]:
        return [Put(Order(name="o_a", volume=1, price=1)), Order(name="o_b", volume=2, price=2)]

    Workflow(both).run(store)
    assert sorted(o.name for o in store.all(Order)) == ["o_a", "o_b"]


def test_put_shows_up_as_produced_in_explain_and_mermaid(store: Store):
    @module
    def explicit(plants: list[Plant]) -> list[Put[Order]]:
        return [Put(Order(name="o_x", volume=1, price=1))]

    workflow = Workflow(explicit)
    assert workflow.explain() == "1. explicit: explicit(Plant[]) -> Order"
    assert workflow.to_mermaid() == "flowchart LR\n    Plant --> explicit\n    explicit --> Order"
