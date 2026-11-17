import webbrowser

from byubit.bit import Bit
from byubit.renderers.html_renderer import HTMLRenderer


def _load_student(tmp_path, source):
    path = tmp_path / "student.py"
    path.write_text(source)
    namespace = {"Bit": Bit}
    exec(compile(source, str(path), "exec"), namespace)
    return path, namespace


def test_evaluation_records_full_trace_and_bit_state(tmp_path):
    _, namespace = _load_student(
        tmp_path,
        "def solve(bit):\n"
        "    if bit.can_move_front():\n"
        "        bit.move()\n"
        "    bit.paint('red')\n"
        "    print(bit.get_color())\n",
    )
    bit = Bit.new_world(2, 2, name="trace-test")

    name, recording = bit._evaluate(namespace["solve"], None)

    assert name == "trace-test"
    assert recording[0]["event"] == "source"
    assert any(item["event"] == "line" for item in recording)
    assert any(item.get("console") for item in recording)
    bit_local = next(item["locals"]["bit"] for item in recording if "bit" in item.get("locals", {}))
    assert bit_local == {"type": "Bit", "data": 'Bit("trace-test")', "display": True}
    returns = [item["call_return"] for item in recording if "call_return" in item]
    assert [item["function"] for item in returns] == [
        "can_move_front", "move", "paint", "get_color"
    ]
    assert all(item["qualified_function"].startswith("Bit.") for item in returns)
    move_return = next(
        item for item in recording
        if item.get("call_return", {}).get("function") == "move"
    )
    assert move_return["bit"]["pos"] == [0, 1]
    assert move_return["bit"]["world"][0][1] == "white"
    assert recording[-1]["event"] == "bit_outcome"
    assert recording[-1]["outcome"]["status"] == "success"
    assert recording[-1]["bit"]["world"][0][1] == "red"


def test_bit_state_carries_forward_on_events_without_bit_locals(tmp_path):
    _, namespace = _load_student(
        tmp_path,
        "def solve(bit):\n"
        "    bit.move()\n",
    )
    _, recording = Bit.new_world(2, 2)._evaluate(namespace["solve"], None)
    states = [item["bit"] for item in recording]

    assert states
    assert all(state["pos"] in ([0, 0], [0, 1]) for state in states)
    assert recording[-1]["bit"]["pos"] == [0, 1]


def test_expected_world_comparison_is_attached_as_final_outcome(tmp_path):
    _, namespace = _load_student(
        tmp_path,
        "def solve(bit):\n"
        "    bit.paint('red')\n",
    )
    bit = Bit.new_world(1, 1)
    expected = Bit.new_world(1, 1)

    _, recording = bit._evaluate(namespace["solve"], expected)

    assert recording[-1]["outcome"]["status"] == "error"
    assert recording[-1]["outcome"]["message"] == "Bit world does not match expected world"
    assert recording[-1]["outcome"]["annotations"] is not None


def test_renderer_creates_tracecode_view_with_bit_panel(tmp_path, monkeypatch):
    _, namespace = _load_student(tmp_path, "def solve(bit):\n    bit.turn_left()\n")
    _, recording = Bit.new_world(1, 1)._evaluate(namespace["solve"], None)
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))

    HTMLRenderer().render(tmp_path / "student.py", {"world": recording})

    view = tmp_path / "student.world.html"
    html = view.read_text()
    assert "Bit world" in html
    assert "window.renderTracecodePanel" in html
    assert "Call stack" in html
    assert "cellSize = 50" in html
    assert "grid.style.display = 'grid'" in html
    assert "className = 'triangle'" in html
    assert opened == [view.resolve().as_uri()]
