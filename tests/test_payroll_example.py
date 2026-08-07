"""The payroll example used throughout the documentation.

Kept as a test so the docs cannot drift from working code.
"""

import pytest

from morphly import Config, Delete, Entity, Patch, Store, Workflow, module

# --- business objects --------------------------------------------------------


class Employee(Entity):
    hourly_rate: float
    contract_hours: float = 35.0
    gross: float = 0.0


class Manager(Employee):
    bonus_target: float


class Timesheet(Entity):
    employee: str
    hours: float


class Payslip(Entity):
    employee: str
    gross: float
    withheld: float
    net: float


class PayrollPolicy(Config):
    overtime_after: float = 35.0
    overtime_rate: float = 1.25
    social_rate: float = 0.22


# --- modules -----------------------------------------------------------------


@module
def compute_gross(
    employees: list[Employee],
    sheets: list[Timesheet],
    policy: PayrollPolicy,
) -> list[Patch[Employee]]:
    worked: dict[str, float] = {}
    for s in sheets:
        worked[s.employee] = worked.get(s.employee, 0.0) + s.hours
    patches = []
    for e in employees:
        hours = worked.get(e.name, 0.0)
        overtime = max(0.0, hours - policy.overtime_after)
        paid = (hours - overtime) + overtime * policy.overtime_rate
        patches.append(Patch(e, gross=e.hourly_rate * paid))
    return patches


@module
def add_bonus(managers: list[Manager]) -> list[Patch[Manager]]:
    return [Patch(m, gross=m.gross * (1 + m.bonus_target)) for m in managers]


@module
def withhold(employees: list[Employee], policy: PayrollPolicy) -> list[Payslip]:
    return [
        Payslip(
            name=f"slip-{e.name}",
            employee=e.name,
            gross=e.gross,
            withheld=e.gross * policy.social_rate,
            net=e.gross * (1 - policy.social_rate),
        )
        for e in employees
    ]


@module
def archive(sheets: list[Timesheet]) -> list[Delete[Timesheet]]:
    return [Delete(s) for s in sheets]


@module
def report(slips: list[Payslip]) -> None:
    print(f"{len(slips)} payslips, net total {sum(s.net for s in slips):.2f}")


def fresh_store() -> Store:
    return Store(
        Employee(name="ada", hourly_rate=50.0),
        Manager(name="bob", hourly_rate=60.0, bonus_target=0.10),
        Timesheet(name="ada-w1", employee="ada", hours=38.0),
        Timesheet(name="bob-w1", employee="bob", hours=35.0),
        PayrollPolicy(),
    )


WORKFLOW = Workflow(compute_gross, add_bonus, withhold, archive, report)


# --- tests -------------------------------------------------------------------


def test_full_run():
    store = WORKFLOW.run(fresh_store())

    ada = store.find(Employee, "ada")
    bob = store.find(Manager, "bob")
    assert ada.gross == pytest.approx(1937.50)  # 35h + 3h at 1.25
    assert bob.gross == pytest.approx(2310.00)  # 35h, then +10% bonus

    slips = {s.employee: s for s in store.all(Payslip)}
    assert slips["ada"].net == pytest.approx(1511.25)
    assert slips["bob"].net == pytest.approx(1801.80)

    assert store.all(Timesheet) == []


def test_gross_patches_the_manager_through_its_parent_type():
    """`Patch[Employee]` on a `Manager` resolves through the lineage."""
    ops = compute_gross(fresh_store())
    assert len(ops) == 2
    assert all(isinstance(op, Patch) for op in ops)


def test_check_catches_a_wrong_order():
    wrong = Workflow(report, withhold)
    with pytest.raises(LookupError, match="step 'report' reads Payslip"):
        wrong.check(fresh_store())


def test_modules_are_isolated_from_the_store():
    """Mutating an input has no effect; only the return value is applied."""

    @module
    def sneaky(employees: list[Employee]) -> None:
        employees[0].gross = 999.0

    store = Workflow(sneaky).run(fresh_store())
    assert store.find(Employee, "ada").gross == 0.0


def test_explain():
    assert WORKFLOW.explain().splitlines()[0] == (
        "1. compute_gross: compute_gross(Employee[], Timesheet[], PayrollPolicy) -> ~Employee"
    )
