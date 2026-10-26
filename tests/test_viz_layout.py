import pytest

from app.viz_chat import SYSTEM, ChangeError, validate_change

COLUMNS = [
    {"name": "country", "type": "category", "distinct": 2, "values": ["Spain", "Belgium"]},
    {"name": "rate", "type": "number", "distinct": 12, "min": 1.0, "max": 40.0},
]


def change(**set_):
    return validate_change({"reply": "ok", "set": set_}, COLUMNS, ["Spain", "Belgium"])


def test_colour_bar_right_vertical():
    assert change(legendPos="right", legendDir="vertical")["set"] == {"legendPos": "right", "legendDir": "vertical"}


@pytest.mark.parametrize("fields", [
    {"legend": "off"},
    {"legend": "on", "legendPos": "top", "legendDir": "horizontal"},
    {"legendPos": "left"},
    {"legendSort": "az"},
    {"legendSort": "value"},
    {"tickAngle": 45},
    {"tickAngle": 0},
    {"tickAngle": 90},
    {"grid": "off"},
    {"grid": "both"},
    {"valueMin": 0, "valueMax": 50},
    {"valueLog": True, "valueMin": 1},
    {"xMin": -2.5, "xMax": 10, "xLog": False},
    {"ticks": 4},
    {"fontSize": "large"},
    {"barGap": 0},
    {"barGap": 0.5},
    {"lineWidth": 4},
    {"markers": "off"},
    {"curve": "step"},
    {"titleAlign": "center"},
    {"refLine": 13.5, "refLabel": "EU average"},
    {"trendline": True, "pointSize": "small"},
    {"donutHole": 0},
    {"height": 700},
])
def test_layout_fields_pass(fields):
    assert change(**fields)["set"] == fields


def test_null_resets_to_automatic():
    assert change(valueMin=None, legendPos=None, tickAngle=None)["set"] == {"valueMin": None, "legendPos": None, "tickAngle": None}


def test_number_strings_are_read():
    out = change(valueMax="50%", refLine="1,200")["set"]
    assert out == {"valueMax": 50.0, "refLine": 1200.0}


def test_ref_label_is_cleaned():
    assert change(refLabel=" EU → average ")["set"]["refLabel"] == "EU  average"


@pytest.mark.parametrize("fields", [
    {"legendPos": "middle"},
    {"legendDir": "diagonal"},
    {"legend": True},
    {"tickAngle": 120},
    {"tickAngle": -10},
    {"grid": "dense"},
    {"valueMin": 50, "valueMax": 10},
    {"xMin": 5, "xMax": 5},
    {"valueLog": True, "valueMin": 0},
    {"xLog": True, "xMin": -1},
    {"ticks": 1},
    {"ticks": 40},
    {"fontSize": "huge"},
    {"fontSize": 30},
    {"barGap": 0.95},
    {"lineWidth": 0.2},
    {"lineWidth": 20},
    {"markers": "big"},
    {"curve": "spline"},
    {"titleAlign": "justify"},
    {"refLine": "about half"},
    {"refLabel": "x" * 60},
    {"pointSize": 12},
    {"donutHole": 0.9},
    {"height": 2000},
    {"legendSort": "random"},
    {"position": "right"},
])
def test_layout_fields_rejected(fields):
    with pytest.raises(ChangeError):
        change(**fields)


def test_prompt_names_every_layout_field_and_never_template():
    for f in ["legendPos", "legendDir", "legendSort", "tickAngle", "grid", "valueMin", "valueMax", "valueLog", "xMin", "xLog",
              "ticks", "fontSize", "barGap", "lineWidth", "markers", "curve", "titleAlign", "refLine", "trendline", "pointSize",
              "donutHole", "height"]:
        assert f in SYSTEM
    assert "colour bar" in SYSTEM
    assert "Never say a thing is handled automatically or by the template." in SYSTEM


def test_map_value_labels_become_a_hover_note():
    from app.viz_chat import MAP_LABELS, no_map_labels

    out = no_map_labels({"reply": "Highlighted Belgium.", "set": {"highlight": ["Belgium"], "valueLabels": "on"}, "ops": []}, "map")
    assert out["set"] == {"highlight": ["Belgium"]}
    assert out["reply"] == "Highlighted Belgium. " + MAP_LABELS


def test_map_value_labels_alone():
    from app.viz_chat import MAP_LABELS, no_map_labels

    out = no_map_labels({"reply": "Turned the labels on.", "set": {"valueLabels": "on"}, "ops": []}, "map")
    assert out == {"reply": MAP_LABELS, "set": {}, "ops": []}


def test_value_labels_stay_on_bars():
    from app.viz_chat import no_map_labels

    ch = {"reply": "ok", "set": {"valueLabels": "on"}, "ops": []}
    assert no_map_labels(ch, "bar") == ch
    assert no_map_labels({**ch, "set": {"valueLabels": "on", "kind": "bar"}}, "map")["set"]["valueLabels"] == "on"
