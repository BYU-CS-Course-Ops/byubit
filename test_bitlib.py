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
    returns = [
        item["call_return"] for item in recording
        if "call_return" in item and not item.get("module_return")
    ]
    assert [item["function"] for item in returns] == [
        "can_move_front", "move", "paint", "get_color"
    ]
    assert all(item["qualified_function"].startswith("Bit.") for item in returns)
    calls = {
        event["function_call"]["qualified_function"]: event["function_call"]
        for event in recording if "function_call" in event
    }
    assert calls["Bit.can_move_front"]["arguments"] == {}
    assert calls["Bit.can_move_front"]["positional_arguments"] == []
    assert calls["Bit.paint"]["arguments"] == {}
    assert calls["Bit.paint"]["positional_arguments"] == [{"type": "str", "data": "red"}]
    move_return = next(
        item for item in recording
        if item.get("call_return", {}).get("function") == "move"
    )
    assert move_return["bit"]["pos"] == [0, 1]
    assert move_return["bit"]["world"][0][1] == "white"
    assert recording[-1]["event"] == "call_return"
    assert recording[-1]["module_return"] is True
    assert recording[-1]["call_return"]["qualified_function"] == "solve"
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
    assert recording[-1]["run_status"] == "incorrect"


def test_expected_world_success_marks_run_correct_and_empty_world_has_no_status(tmp_path):
    _, namespace = _load_student(tmp_path, "def solve(bit):\n    bit.move()\n")
    start = Bit.new_world(2, 1, name="Correct")
    expected = Bit.new_world(2, 1, name="Expected")
    expected.move()

    _, correct = start._evaluate(namespace["solve"], expected)
    _, no_expected = Bit.new_world(2, 1)._evaluate(namespace["solve"], None)

    assert correct[-1]["run_status"] == "correct"
    assert no_expected[-1]["run_status"] is None


def test_decorator_prepares_source_and_records_each_world(tmp_path, monkeypatch):
    path = tmp_path / "student.py"
    source = (
        "from byubit.bit import Bit\n"
        "@Bit.worlds(Bit.new_world(3, 1, name='World A'), Bit.new_world(3, 1, name='World B'), Bit.new_world(3, 1, name='World A'))\n"
        "def solve(bit):\n"
        "    if bit.can_move_front():\n"
        "        bit.move()\n"
    )
    path.write_text(source)
    namespace = {"__name__": "student", "__file__": str(path)}
    exec(compile(source, str(path), "exec"), namespace)

    class CaptureRenderer:
        def render(self, code_file, recordings):
            self.code_file = code_file
            self.recordings = recordings

    renderer = CaptureRenderer()
    monkeypatch.setattr(Bit.new_bit, "renderer", renderer)
    namespace["solve"](Bit.new_bit)

    assert renderer.code_file == path.resolve()
    assert list(renderer.recordings) == ["World A", "World B", "World A (2)"]
    for recording in renderer.recordings.values():
        assert recording[1]["event"] == "call"
        assert recording[1]["module_call"] is True
        assert recording[1]["function_call"]["qualified_function"] == "solve"
        assert any(event["event"] == "condition" for event in recording)
        assert recording[-1]["event"] == "call_return"
        assert recording[-1]["module_return"] is True
        module_frames = [
            caller for event in recording for caller in event.get("callers", [])
            if caller.get("module_call")
        ]
        assert module_frames
        assert all(frame["locals"] == {} for frame in module_frames)
        assert all(
            frame["function_call"]["qualified_function"] == "solve"
            for frame in module_frames
        )


def test_first_call_step_highlights_the_module_call_site(tmp_path, monkeypatch):
    path = tmp_path / "student.py"
    source = (
        "from byubit.bit import Bit\n"
        "@Bit.worlds(Bit.new_world(2, 1, name='Call site'))\n"
        "def main(bit):\n"
        "    bit.move()\n"
        "if __name__ == 'student':\n"
        "    main(Bit.new_bit)\n"
    )
    path.write_text(source)

    class CaptureRenderer:
        def render(self, code_file, recordings):
            self.recordings = recordings

    renderer = CaptureRenderer()
    monkeypatch.setattr(Bit.new_bit, "renderer", renderer)
    namespace = {"__name__": "student", "__file__": str(path)}
    exec(compile(source, str(path), "exec"), namespace)

    first_step = renderer.recordings["Call site"][1]
    assert first_step["function_call"]["qualified_function"] == "main"
    assert first_step["lineno"] == 6


def test_new_bit_uses_tracecode_renderer_by_default():
    assert isinstance(Bit.new_bit.renderer, HTMLRenderer)


def test_renderer_creates_tracecode_view_with_bit_panel(tmp_path, monkeypatch):
    _, namespace = _load_student(tmp_path, "def solve(bit):\n    bit.turn_left()\n")
    _, recording = Bit.new_world(1, 1)._evaluate(namespace["solve"], None)
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))

    HTMLRenderer().render(tmp_path / "student.py", {"world": recording})

    view = tmp_path / "student.html"
    html = view.read_text()
    assert 'id="run-tabs"' in html
    assert '"start_at_end": true' in html
    assert "Bit world" in html
    assert "window.renderTracecodePanel" in html
    assert "Call stack" in html
    assert "cellSize = 50" in html
    assert "grid.style.display = 'grid'" in html
    assert "grid.style.gap = '0'" in html
    assert "cell.style.borderBottom = '1px solid black'" in html
    assert "annotations.world[row][col]" in html
    assert "createBitTriangle(annotations.orientation" in html
    assert "triangle.className = wrong ? 'triangle wrong' : 'triangle'" in html
    assert opened == [view.resolve().as_uri()]
