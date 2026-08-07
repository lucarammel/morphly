import copy

import pytest
from pydantic import ValidationError

from morph import Config, Delete, Entity, Patch, Pipeline, Step, Store, module, view


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


def test_pipeline_runs_and_applies(store: Store):
    Pipeline(bidding, clearing).run(store)

    # a bids at 10*1.2=12 -> cleared; b bids at 40*1.2=48 -> order dropped
    assert [o.name for o in store.all(Order)] == ["o_a"]
    assert store.find(Order, "o_a").price == 12
    assert store.find(Plant, "a").cleared == 100
    assert store.find(ThermalPlant, "b").cleared == 0


def test_step_config_overrides_store(store: Store):
    Pipeline(Step(bidding, BidParams(margin=2.0))).run(store)
    assert store.find(Order, "o_a").price == 20


def test_same_module_twice_with_different_configs(store: Store):
    pipeline = Pipeline(Step(bidding, BidParams(margin=1.0)), Step(bidding, BidParams(margin=3.0)))
    assert [s.name for s in pipeline.steps] == ["bidding", "bidding_2"]
    pipeline.run(store)
    assert store.find(Order, "o_a").price == 30  # last step wins


def test_missing_config_is_an_error():
    with pytest.raises(LookupError):
        Pipeline(bidding).run(Store(Plant(name="a", pmax=1, cost=1)))


def test_check_rejects_unsatisfied_read():
    class Trade(Entity):
        volume: float

    @module
    def settle(trades: list[Trade]) -> None: ...

    with pytest.raises(LookupError, match="Trade"):
        Pipeline(settle).check(Store())


def test_check_accepts_type_produced_upstream(store: Store):
    Pipeline(bidding, clearing).check(store)  # Order only exists after `bidding`


def test_check_rejects_config_neither_bound_nor_in_store():
    @module
    def needs_config(plants: list[Plant], params: BidParams) -> None: ...

    with pytest.raises(LookupError, match="BidParams"):
        Pipeline(needs_config).check(Store(Plant(name="a", pmax=1, cost=1)))


def test_check_accepts_config_bound_to_step():
    @module
    def needs_config(plants: list[Plant], params: BidParams) -> None: ...

    Pipeline(Step(needs_config, BidParams())).check(Store(Plant(name="a", pmax=1, cost=1)))


def test_check_rejects_touching_a_type_nobody_provides():
    class Ghost(Entity):
        pass

    @module
    def haunt() -> list[Patch[Ghost]]:
        raise NotImplementedError

    with pytest.raises(LookupError, match="touches Ghost"):
        Pipeline(haunt).check(Store())


def test_inputs_are_isolated(store: Store):
    @module
    def sneaky(plants: list[Plant]) -> None:
        plants[0].cleared = 999

    Pipeline(sneaky).run(store)
    assert {p.cleared for p in store.all(Plant)} == {0}


def test_undeclared_output_is_rejected(store: Store):
    @module
    def liar(plants: list[Plant]) -> list[Order]:
        return [Plant(name="ghost", pmax=1, cost=1)]  # ty: ignore[invalid-return-type]

    with pytest.raises(TypeError, match="not in its return type"):
        Pipeline(liar).run(store)


def test_patch_on_a_module_view_reaches_the_stored_object(store: Store):
    class PlantMC(Plant):
        times: int = 0

    @module
    def enrich(plants: list[Plant]) -> list[Patch[Plant]]:
        views = [view(PlantMC, p, times=3) for p in plants]
        return [Patch(v, cleared=v.times * 2) for v in views]

    Pipeline(enrich).run(store)
    assert {p.cleared for p in store.all(Plant)} == {6}
    assert not any(isinstance(p, PlantMC) for p in store.all(Plant))


def test_patch_rejects_unknown_field(store: Store):
    @module
    def bad(plants: list[Plant]) -> list[Patch[Plant]]:
        return [Patch(plants[0], nope=1)]

    with pytest.raises(ValueError, match="no field"):
        Pipeline(bad).run(store)


def test_patch_validates_values(store: Store):
    @module
    def bad(plants: list[Plant]) -> list[Patch[Plant]]:
        return [Patch(plants[0], cleared="not a float")]

    with pytest.raises(ValidationError):
        Pipeline(bad).run(store)


def test_step_is_atomic(store: Store):
    @module
    def half_bad(plants: list[Plant]) -> list[Patch[Plant] | Delete[Plant]]:
        return [Patch(plants[0], cleared=42), Delete(Plant(name="unknown", pmax=0, cost=0))]

    with pytest.raises(KeyError):
        Pipeline(half_bad).run(store)
    assert {p.cleared for p in store.all(Plant)} == {0}
    assert len(store.all(Plant)) == 2


def test_delete_then_patch_same_target_is_rejected(store: Store):
    @module
    def dp(plants: list[Plant]) -> list[Delete[Plant] | Patch[Plant]]:
        p = plants[0]
        return [Delete(p), Patch(p, cleared=9.0)]

    with pytest.raises(ValueError, match="which the same step deletes"):
        Pipeline(dp).run(store)
    assert store.find(Plant, "a") is not None


def test_on_step_hook(store: Store):
    seen: list[tuple[str, int]] = []
    Pipeline(bidding, clearing).run(store, on_step=lambda s, ops, st: seen.append((s.name, len(st.all(Order)))))
    assert seen == [("bidding", 2), ("clearing", 1)]


def test_on_step_hook_receives_the_operations(store: Store):
    seen: list[list[str]] = []
    Pipeline(bidding, clearing).run(store, on_step=lambda s, ops, st: seen.append([type(o).__name__ for o in ops]))
    assert seen == [["Order", "Order"], ["Patch", "Delete"]]


def test_reuse_is_none_before_the_first_run():
    assert Pipeline(bidding).last_run is None


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

    pipeline = Pipeline(step_a, step_b)
    pipeline.run(store)
    assert calls == ["a", "b"]

    calls.clear()
    pipeline.run(before, reuse=pipeline.last_run)
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

    pipeline = Pipeline(step_a, step_b)
    pipeline.run(store)
    assert calls == ["a", "b"]

    calls.clear()
    changed = Store(
        Plant(name="a", pmax=999, cost=10),
        ThermalPlant(name="b", pmax=50, cost=40),
        BidParams(margin=1.2),
    )
    pipeline.run(changed, reuse=pipeline.last_run)
    assert calls == ["a", "b"]
    assert changed.find(Plant, "a").cleared == 999


def test_reuse_still_calls_on_step_for_a_skipped_step(store: Store):
    before = copy.deepcopy(store)

    @module
    def step_a(plants: list[Plant]) -> list[Patch[Plant]]:
        return [Patch(p, cleared=p.pmax) for p in plants]

    pipeline = Pipeline(step_a)
    pipeline.run(store)

    seen: list[str] = []
    pipeline.run(before, reuse=pipeline.last_run, on_step=lambda s, ops, st: seen.append(s.name))
    assert seen == ["step_a"]


def test_deepcopy_is_the_snapshot(store: Store):
    before = copy.deepcopy(store)
    Pipeline(bidding).run(store)
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
    assert Pipeline(bidding, clearing).explain() == (
        "1. bidding: bidding(Plant[], BidParams) -> Order\n2. clearing: clearing(Order[], Plant[]) -> ~Plant, ~Order"
    )


def test_to_mermaid(store: Store):
    assert Pipeline(bidding, clearing).to_mermaid() == (
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


def test_pipeline_repr():
    assert repr(Pipeline(bidding, clearing)) == "Pipeline(bidding, clearing)"


def test_step_rejects_duplicate_config_type(store: Store):
    with pytest.raises(LookupError, match="several BidParams"):
        Pipeline(Step(bidding, BidParams(margin=1.0), BidParams(margin=2.0))).run(store)


def test_patch_target_runtime_type_mismatch_is_rejected(store: Store):
    @module
    def bad(plants: list[Plant]) -> list[Patch[Plant]]:
        return [Patch(Order(name="o_x", volume=1, price=1), cleared=1)]  # ty: ignore[invalid-return-type]

    with pytest.raises(TypeError, match="not in its return type"):
        Pipeline(bad).run(store)
