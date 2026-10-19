"""Canvas edits share the same atomic validation path as coordinate forms."""

from copy import deepcopy
import pytest
from fea.editing import canvas_edit, modernize, remove_elements
from fea.examples import examples
from fea.errors import ModelError


def test_drag_preserves_properties_releases_and_loads():
    m = modernize(examples()["Simply supported beam"])
    m["elements"][0]["release_i"] = True
    m["member_loads"] = [
        dict(id="P", case="Dead", element=1, x=2.0, p=-10.0, direction="Local Y")
    ]
    before = deepcopy(m)
    after, _ = canvas_edit(m, dict(action="move_node", id=2, x=7, y=1))
    assert (
        m == before
        and after["elements"] == m["elements"]
        and after["member_loads"] == m["member_loads"]
    )
    assert after["distributed_loads"] == m["distributed_loads"]


def test_invalid_drag_keeps_original():
    m = modernize(examples()["Simply supported beam"])
    before = deepcopy(m)
    with pytest.raises(ModelError):
        canvas_edit(m, dict(action="move_node", id=2, x=0, y=0))
    assert m == before


def test_deletion_cascades_member_points():
    m = modernize(examples()["Simply supported beam"])
    m["member_loads"] = [
        dict(id="P", case="Dead", element=1, x=2.0, p=-10.0, direction="Local Y")
    ]
    out = remove_elements(m, [1])
    assert not out["member_loads"] and not out["distributed_loads"]
