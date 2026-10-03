from slice_and_dice.dimension_value import DimensionValue
from slice_and_dice.scope import Scope
from slice_and_dice.stack_level import StackLevel


def test_scope_renders_operator_symbols():
    assert str(Scope("geo", "eq", "US")) == "geo = US"
    assert str(Scope("size", "gte", "1000")) == "size >= 1000"
    assert str(Scope("geo", "like", "U%")) == "geo like U%"


def test_scope_without_value_has_no_trailing_space():
    assert str(Scope("dns", "is-null", "")) == "dns is-null"


def test_range_scopes_render_their_bucket():
    assert str(Scope("size", "range", "lt 100")) == "size < 100"
    assert str(Scope("size", "range", "gt 500")) == "size > 500"
    assert str(Scope("size", "range", "100-500")) == "size = 100-500"


def test_scope_is_mapped_only_with_a_server_id():
    assert not Scope("geo", "eq", "US").is_mapped
    assert Scope("geo", "eq", "US", scope_id=7).is_mapped


def test_dimension_value_from_row_coerces_numbers():
    value = DimensionValue.from_row(
        {"scope_id": "12", "acc_ct": 90, "byp_ct": "10", "acc_spd": None, "network": "LTE"}
    )
    assert value.scope_id == 12
    assert value.total_ct == 100
    assert value.acc_spd == 0
    assert value.extra == {"network": "LTE"}
    assert str(value) == "sid 12"


def test_stack_level_describe():
    level = StackLevel(
        scope_id=5,
        scope=Scope("geo", "eq", "US"),
        count=42,
        dimension="network",
        dimension_values={"LTE": DimensionValue(scope_id=9)},
    )
    assert level.describe() == "[5] geo = US #ct=42 , network=LTE: sid 9"
    assert StackLevel().describe() == "[0] all #ct=0"
