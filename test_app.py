"""Streamlit interaction checks use real form controls, not mocked editor state."""

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from fea.examples import examples

APP = Path(__file__).resolve().parents[1] / "app.py"


def find(items, label):
    return next(item for item in items if item.label == label)


def press(at, label):
    find(at.button, label).click().run()
    assert not at.exception


def app():
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
    return at


@pytest.mark.parametrize("name", list(examples()))
def test_examples_and_results(name):
    at = app()
    at.selectbox(key="example_choice").select(name)
    press(at, "Load example")
    press(at, "Analyse")
    assert len(at.success) == 1
    assert len(at.metric) == 3
    at.radio(key="section").set_value("Results").run()
    assert not at.exception
    assert len(at.get("download_button")) == 5
    press(at, "Run parameter study")
    assert len(at.session_state["study"]) == 9
    assert len(at.get("download_button")) == 6


def test_case_change_hides_outdated_results():
    at = app()
    press(at, "Analyse")
    at.selectbox(key="active_case").select("Dead").run()
    assert any("outdated" in w.value for w in at.warning)
    assert len(at.metric) == 0
    press(at, "Analyse")
    assert at.session_state["result"].name == "Dead"


def test_saved_node_edit_and_undo():
    at = app()
    press(at, "Analyse")
    find(at.number_input, "X [m]").set_value(-1.0)
    press(at, "Save node")
    assert at.session_state["model"]["nodes"][0]["x"] == -1.0
    assert any("outdated" in w.value for w in at.warning)
    press(at, "Undo last saved edit")
    assert at.session_state["model"]["nodes"][0]["x"] == 0.0


def test_support_edit_reports_mechanism():
    at = app()
    at.radio(key="section").set_value("Supports").run()
    find(at.selectbox, "Restraint").select("Free")
    press(at, "Save support")
    press(at, "Analyse")
    assert any("Unstable" in e.value for e in at.error)


def test_edit_distributed_load_doubles_answer():
    at = app()
    at.selectbox(key="active_case").select("Dead")
    press(at, "Analyse")
    old = at.session_state["result"].max_displacement()
    at.radio(key="section").set_value("Loads").run()
    find(at.selectbox, "Distributed load").select("D1").run()
    find(at.number_input, "Intensity [kN/m]").set_value(20.0)
    press(at, "Save distributed load")
    press(at, "Analyse")
    assert at.session_state["result"].max_displacement() == pytest.approx(2 * old)


def test_partial_multi_member_load_and_invalid_range():
    at = app()
    at.selectbox(key="example_choice").select("Multi-element beam")
    press(at, "Load example")
    at.radio(key="section").set_value("Loads").run()
    find(at.selectbox, "Distributed load").select("D2").run()
    find(at.number_input, "Start distance [m]").set_value(2.0)
    find(at.number_input, "End distance [m]").set_value(3.0)
    press(at, "Save distributed load")
    assert at.session_state["model"]["distributed_loads"][1]["start"] == 2.0
    find(at.selectbox, "Distributed load").select("D2").run()
    find(at.number_input, "End distance [m]").set_value(1.0)
    press(at, "Save distributed load")
    assert any("start < end" in e.value for e in at.error)
    assert at.session_state["model"]["distributed_loads"][1]["end"] == 3.0


def test_empty_model_can_be_built_and_deleted():
    at = app()
    find(at.checkbox, "Confirm replacing the current model").check().run()
    press(at, "Start empty model")
    assert not at.session_state["model"]["nodes"]
    press(at, "Add node")
    assert len(at.session_state["model"]["nodes"]) == 1
    find(at.radio, "Node action").set_value("Add new").run()
    find(at.number_input, "X [m]").set_value(4.0)
    press(at, "Add node")
    assert len(at.session_state["model"]["nodes"]) == 2
    at.radio(key="geometry_target").set_value("Elements").run()
    press(at, "Add element")
    assert len(at.session_state["model"]["elements"]) == 1
    at.radio(key="geometry_target").set_value("Nodes").run()
    find(at.radio, "Node action").set_value("Edit selected").run()
    press(at, "Delete selected node")
    assert len(at.session_state["model"]["elements"]) == 0
    press(at, "Undo last saved edit")
    assert len(at.session_state["model"]["elements"]) == 1


def test_selected_node_form_tracks_new_selection():
    at = app()
    at.selectbox(key="selected_node").select(2).run()
    assert find(at.number_input, "X [m]").value == 6.0
    at.selectbox(key="selected_node").select(1).run()
    assert find(at.number_input, "X [m]").value == 0.0


def test_create_case_and_change_properties():
    at = app()
    at.radio(key="section").set_value("Loads").run()
    at.radio(key="load_editor").set_value("Cases & combinations").run()
    find(at.text_input, "New load case name").set_value("Wind")
    press(at, "Add load case")
    assert "Wind" in at.session_state["model"]["cases"]
    at.radio(key="section").set_value("Properties").run()
    find(at.number_input, "Young’s modulus E [GPa]").set_value(100.0)
    press(at, "Save properties")
    assert at.session_state["model"]["elements"][0]["E"] == 100e9


def test_section_releases_and_member_point_workflow():
    at = app()
    at.radio(key="section").set_value("Properties").run()
    find(at.selectbox, "Section shape").select("Rectangle").run()
    find(at.number_input, "Width b [mm]").set_value(100.0)
    find(at.number_input, "Depth h [mm]").set_value(200.0)
    find(at.checkbox, "Release moment at start i").check()
    press(at, "Save properties")
    assert at.session_state["model"]["elements"][0]["A"] == pytest.approx(0.02)
    at.radio(key="section").set_value("Loads").run()
    at.radio(key="load_editor").set_value("Member point").run()
    find(at.number_input, "Position from i [m]").set_value(3.0)
    press(at, "Save member point load")
    press(at, "Analyse")
    assert abs(at.session_state["result"].elements[0].end_forces[2]) < 1e-7
    at.radio(key="section").set_value("Results").run()
    assert any("Governing assessed limit" in i.value for i in at.info)
    find(at.number_input, "Translation limit [mm]").set_value(5.0)
    press(at, "Save limit")
    assert any("outdated" in w.value for w in at.warning)
    press(at, "Analyse")
    assert any("Governing assessed limit" in i.value for i in at.warning)


def test_redo_and_clear_confirmation():
    at = app()
    assert find(at.button, "Start empty model").disabled
    find(at.number_input, "X [m]").set_value(-1.0)
    press(at, "Save node")
    press(at, "Undo")
    assert at.session_state["model"]["nodes"][0]["x"] == 0.0
    press(at, "Redo")
    assert at.session_state["model"]["nodes"][0]["x"] == -1.0
