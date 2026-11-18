import csv
import functools
import os
import re
import traceback
from inspect import currentframe, stack, getfile
from pathlib import Path
from typing import Literal
from contextvars import ContextVar

import webcolors

from tracecode import RecordingLimitExceeded, TraceRecorder, prepare_file

from .renderers.html_renderer import HTMLRenderer
from .rendering import BitRenderer, Pos


class NewBit:
    def __init__(self, renderer: BitRenderer = HTMLRenderer()):
        self.renderer = renderer

    def __getattr__(self, item):
        raise Exception('You can only pass Bit.new_bit to a function with an @Bit decorator')


# row, column
_orientations = [
    (0, 1),  # Right
    (1, 0),  # Up
    (0, -1),  # Left
    (-1, 0)  # Down
]

MAX_STEP_COUNT = 15_000
MAX_REPEAT_STATE = 10
_ANNOTATION_ONLY = ContextVar("bit_annotation_only", default=False)

# For converting simple color codes to color names
# The simple color codes are used in the Bit world files
_codes_to_colors = {
    '-': 'white',
    'k': 'black',
    'o': 'orange',
    'g': 'green',
    'y': 'yellow',
    'b': 'blue',
    'r': 'red',
    'p': 'purple'
}

BLACK = 'black'  # for blocked squares
WHITE = 'white'  # for empty squares

css_colors = set(webcolors._definitions._CSS3_NAMES_TO_HEX.keys())


class MoveOutOfBoundsException(Exception):
    """Raised when Bit tries to move out of bounds"""


class MoveBlockedByBlackException(Exception):
    """Raised when Bit tries to move out of bounds"""


class BitComparisonException(Exception):
    def __init__(self, message, annotations):
        self.message = message
        self.annotations = annotations

    def __str__(self):
        return self.message


class BitInfiniteLoopException(BitComparisonException):
    def __init__(self, message, annotations):
        self.message = message
        self.annotations = annotations

    def __str__(self):
        return self.message


def _get_caller_info(ex=None) -> tuple[str, int]:
    if ex:
        s = list(reversed(traceback.TracebackException.from_exception(ex).stack))
    else:
        s = stack()
    # Find index of the first non-bit.py frame following a bit.py frame
    index = 0
    while s[index].filename == __file__:
        index += 1
    return s[index].filename, s[index].lineno


def _registered(func):
    @functools.wraps(func)
    def new_func(self, *args, **kwargs):
        ret = func(self, *args, **kwargs)
        title = ' '.join([func.__name__, *(str(a) for a in args)])
        if ret is not None:
            title += f': {ret}'
        self._register(title)
        return ret

    new_func.__code__ = new_func.__code__.replace(
        co_name=func.__name__, co_qualname=f"Bit.{func.__name__}"
    )
    return new_func


def _check_extraneous_args(func):
    @functools.wraps(func)
    def new_func(self, *args):
        try:
            return func(self, *args)
        except TypeError as err:
            # TypeError: Boo.move() takes 1 positional arguments but 2 were given
            # the first positional arg is self
            # let's adjust the count to match what students expect
            if 'positional arguments' in str(err):
                m = re.search(
                    r'Bit.(\S+) takes (\d+) positional arguments but (\d+) were given',
                    str(err)
                )
                if not m:
                    raise
                name = m.group(1)
                takes = int(m.group(2)) - 1
                given = int(m.group(3)) - 1
                raise Exception(f'{name} takes {takes} arguments but {given} were given.')
            else:
                raise

    new_func.__code__ = new_func.__code__.replace(
        co_name=func.__name__, co_qualname=f"Bit.{func.__name__}"
    )
    return new_func


def _serialize_annotations(annotations):
    if annotations is None:
        return None
    world, pos, orientation = annotations
    return {
        "world": [[str(cell) for cell in row] for row in world],
        "pos": [int(value) for value in pos],
        "orientation": int(orientation),
    }


def _serialize_bit(bit):
    return {
        "name": str(bit.name),
        "world": [[str(cell) for cell in row] for row in bit.world],
        "pos": [int(value) for value in bit.pos],
        "orientation": int(bit.orientation),
    }


def _decode_trace_value(value):
    if not isinstance(value, dict) or "type" not in value or "data" not in value:
        return value
    value_type, data = value["type"], value["data"]
    if value_type == "dict":
        return {
            _decode_trace_value(key): _decode_trace_value(item)
            for key, item in data
        }
    if value_type in ("list", "tuple"):
        return [_decode_trace_value(item) for item in data]
    return data


def _find_bit_state(snapshot):
    scopes = [snapshot.get("locals", {})]
    scopes.extend(caller.get("locals", {}) for caller in reversed(snapshot.get("callers", [])))
    for scope in scopes:
        value = scope.get("bit")
        if isinstance(value, dict) and value.get("type") == "byubit.bit.Bit":
            return _decode_trace_value(value["data"])
    return None


def _compact_bit_values(value, world_name):
    if isinstance(value, dict):
        if value.get("type") == "byubit.bit.Bit":
            return {
                "type": "Bit",
                "data": f'Bit("{world_name}")',
                "display": True,
            }
        return {key: _compact_bit_values(item, world_name) for key, item in value.items()}
    if isinstance(value, list):
        return [_compact_bit_values(item, world_name) for item in value]
    return value


def _add_bit_states(recording, initial_state, entry_point_name):
    current = initial_state
    for snapshot in recording:
        current = _find_bit_state(snapshot) or current
        snapshot["bit"] = current
        module_frame = {
            "function": "<module>",
            "qualified_function": "<module>",
            "lineno": None,
            "locals": {},
            "module_call": True,
            "function_call": {
                "qualified_function": entry_point_name,
                "arguments": {},
                "positional_arguments": [],
            },
        }
        callers = snapshot.get("callers", [])
        module_index = next(
            (index for index, caller in enumerate(callers) if caller.get("function") == "<module>"),
            None,
        )
        if module_index is None:
            callers.insert(0, module_frame)
        else:
            callers[module_index] = module_frame
        snapshot["callers"] = callers
        world_name = current["name"]
        for key, value in list(snapshot.items()):
            if key != "bit":
                snapshot[key] = _compact_bit_values(value, world_name)
        call = snapshot.get("function_call")
        if call and call.get("qualified_function", "").startswith("Bit."):
            wrapper_args = call.get("arguments", {}).get("args", {})
            call["positional_arguments"] = (
                wrapper_args.get("data", []) if wrapper_args.get("type") == "tuple" else []
            )
            call["arguments"] = {}
    return current


def _clone_bit(bit):
    return Bit(
        bit.name,
        [[str(cell) for cell in row] for row in bit.world],
        tuple(int(value) for value in bit.pos),
        int(bit.orientation),
    )


def _evaluate_all(
        bit_function,
        bits,
        *args,
        save=None,
        entry_point_call_line=None,
        **kwargs
) -> dict[str, list[dict]]:
    results = {}
    for start_bit, end_bit in bits:
        start_bit = _load_bit_from_file(start_bit) if isinstance(start_bit, str) else _clone_bit(start_bit)
        if isinstance(end_bit, str):
            end_bit = _load_bit_from_file(end_bit)
        elif end_bit is not None:
            end_bit = _clone_bit(end_bit)

        name, history = start_bit._evaluate(
            bit_function,
            end_bit,
            *args,
            save=save,
            entry_point_name=getattr(bit_function, "__name__", "<entry point>"),
            entry_point_call_line=entry_point_call_line,
            **kwargs
        )
        unique_name = name
        suffix = 2
        while unique_name in results:
            unique_name = f"{name} ({suffix})"
            suffix += 1
        results[unique_name] = history

    return results


def _parse_lines_from_string(content: str):
    content = [line.split() for line in content.splitlines() if line]
    content[:-2] = [list(line[0]) for line in content[:-2]]
    return content


def _parse_lines_from_file(filename: str):
    """Parse either csv or txt file into list[list[str]] format. """
    if filename.endswith(".txt"):
        with open(filename, 'r') as file:
            content = _parse_lines_from_string(file.read())
    elif filename.endswith(".csv"):
        with open(filename, 'r') as file:
            reader = csv.reader(file)
            content = [line for line in reader]
    else:
        raise ValueError("Unsupported file format")

    return content


def _load_bit_from_file(filename: str):
    """Parse the file into a new Bit"""
    content = _parse_lines_from_file(filename)
    base, ext = os.path.splitext(filename)
    name = os.path.basename(base).split('.')[0]
    return _parse_bit_from_lines(name, content)


def _parse_bit_from_lines(name: str, content: list[list[str]]):
    """Parse the bitmap from nested list."""
    # There must be at least three lines
    assert len(content) >= 3

    # Position is the second-to-last line
    # col, row
    pos = int(content[-2][1]), int(content[-2][0])

    # Orientation is the last line: 0, 1, 2, 3
    orientation = int(content[-1][0])

    # World lines are all lines up to the second-to-last
    world = [
        [_codes_to_colors[code] for code in row]
        for row in content[:-2][::-1]
    ]

    return Bit(name, world, pos, orientation)


class Bit:
    # Stores the results of the run, so we can retrieve them after
    # Set in the @Bit.worlds function
    _results = {}

    new_bit = NewBit()

    @staticmethod
    def get_json_results() -> dict[str, list[dict]]:
        return {
            k: records  # [r.to_json() for r in records]
            for k, records in Bit._results.items()
        }

    @staticmethod
    def empty_world(width, height, name=None, **kwargs):
        return Bit.worlds(Bit.new_world(width, height, name=name), **kwargs)

    @staticmethod
    def worlds(*bit_worlds, **world_kwargs):
        bits = []
        for bit_world in bit_worlds:
            if isinstance(bit_world, str):
                filename, _ = _get_caller_info()
                code_folder = os.path.dirname(filename)
                possible_worlds = [
                    bit_world + '.start.txt',
                    bit_world + '.start.csv',
                    os.path.join('worlds', bit_world + '.start.txt'),
                    os.path.join('worlds', bit_world + '.start.csv'),
                    os.path.join(code_folder, bit_world + '.start.txt'),
                    os.path.join(code_folder, bit_world + '.start.csv'),
                    os.path.join(code_folder, 'worlds', bit_world + '.start.txt'),
                    os.path.join(code_folder, 'worlds', bit_world + '.start.csv')
                ]
                start = next((file for file in possible_worlds if os.path.isfile(file)), None)
                if start is None:
                    raise FileNotFoundError(bit_world)

                if not os.path.isfile(end := start.replace('.start.', '.finish.')):
                    end = None
                bits.append((start, end))
            else:
                bits.append((bit_world, None))

        def decorator(bit_func):
            if _ANNOTATION_ONLY.get():
                bit_func.__bit_entry_point__ = True
                return bit_func

            file = Path(getfile(bit_func)).resolve()

            @functools.wraps(bit_func)
            def new_function(bit, *args, **kwargs):
                if not isinstance(bit, NewBit):
                    raise TypeError("You must pass Bit.new_bit to your main function.")

                caller_frame = currentframe().f_back
                call_line = (
                    caller_frame.f_lineno
                    if caller_frame is not None
                    and os.path.realpath(caller_frame.f_code.co_filename) == str(file)
                    else None
                )
                del caller_frame
                prepared = prepare_file(file)
                namespace = {
                    "__name__": f"_bit_prepared_{file.stem}",
                    "__file__": str(file),
                }
                token = _ANNOTATION_ONLY.set(True)
                try:
                    prepared.execute(namespace)
                finally:
                    _ANNOTATION_ONLY.reset(token)

                entry_point = namespace.get(bit_func.__name__)
                if not callable(entry_point) or not getattr(entry_point, "__bit_entry_point__", False):
                    raise RuntimeError(f"Could not find prepared Bit entry point {bit_func.__name__!r}")

                Bit._results = _evaluate_all(
                    entry_point,
                    bits,
                    *args,
                    entry_point_call_line=call_line,
                    **kwargs,
                    **world_kwargs,
                )
                bit.renderer.render(file, Bit._results)

            return new_function

        return decorator

    @staticmethod
    def new_world(width, height, name=None):
        if name is None:
            name = f"New World ({width}, {height})"

        world = [
            [WHITE for c in range(width)]
            for r in range(height)
        ]
        return Bit(name, world, (0, 0), 0)

    def __init__(self, name: str, world: list[list[str]], pos: tuple[int, int], orientation: int):
        self.name = name
        self.world = world
        self.pos = pos
        self.orientation = orientation
        self.n_rows = len(world)
        self.n_cols = len(world[0])

        self.state_counts = {}  # for infinite loop detection
        self.operation_count = 0

    def _register(self, name, message=None, annotations=None, ex=None):
        self.operation_count += 1
        world_tuple = tuple(tuple(row) for row in self.world)
        pos_tuple = tuple(int(value) for value in self.pos)
        bit_state = (name, world_tuple, pos_tuple, int(self.orientation))
        self.state_counts[bit_state] = self.state_counts.get(bit_state, 0) + 1

        if message is None and self.state_counts[bit_state] >= MAX_REPEAT_STATE:
            message = "Bit's been doing the same thing for a while. Is he stuck in an infinite loop?"
            raise BitInfiniteLoopException(message, annotations)
        elif message is None and self.operation_count > MAX_STEP_COUNT:
            message = "Bit has done too many things. Is he stuck in an infinite loop?"
            raise BitInfiniteLoopException(message, annotations)

    def _next_orientation(self, turn: Literal[1, 0, -1]) -> int:
        return (len(_orientations) + self.orientation + turn) % len(_orientations)

    def _get_next_pos(self, turn: Literal[1, 0, -1] = 0) -> Pos:
        row, col = self.pos
        drow, dcol = _orientations[self._next_orientation(turn)]
        return row + drow, col + dcol

    def _pos_in_bounds(self, pos) -> bool:
        row, col = pos
        return 0 <= row < self.n_rows and 0 <= col < self.n_cols

    def _compare(self, other: 'Bit'):
        """Compare this bit to another"""
        my_shape = (self.n_rows, self.n_cols)
        other_shape = (other.n_rows, other.n_cols)
        if my_shape != other_shape:
            raise Exception(
                f"Cannot compare Bit worlds of different dimensions: {my_shape} vs {other_shape}")

        if any(self.world[r][c] != other.world[r][c]
               for r in range(self.n_rows)
               for c in range(self.n_cols)
               ):
            raise BitComparisonException(f"Bit world does not match expected world",
                                         (other.world, other.pos, other.orientation))

        if self.pos != other.pos:
            raise BitComparisonException(
                f"Location of Bit does not match: {self.pos} vs {other.pos}",
                (other.world, other.pos, other.orientation)
            )

        self._register("compare correct!")

    def _evaluate(
        self,
        bit_function,
        other_bit,
        *args,
        save=None,
        entry_point_name=None,
        entry_point_call_line=None,
        **kwargs,
    ):
        filename = getattr(getattr(bit_function, "__code__", None), "co_filename", None)
        if filename is None:
            filename = getfile(bit_function)
        recorder = TraceRecorder(
            serializers=[(Bit, _serialize_bit)],
            target_file=filename,
            max_snapshots=100_000,
        )
        initial_state = _serialize_bit(self)
        outcome = {"status": "success", "message": None, "annotations": None}
        student_completed = False
        try:
            with recorder:
                student_return_value = bit_function(self, *args, **kwargs)
                student_completed = True
            if other_bit is not None:
                self._compare(other_bit)
        except RecordingLimitExceeded as ex:
            outcome = {"status": "error", "message": f"Execution recording limit exceeded: {ex}", "annotations": None}
        except BitInfiniteLoopException as ex:
            print(ex)
            outcome = {"status": "error", "message": str(ex), "annotations": _serialize_annotations(ex.annotations)}
        except BitComparisonException as ex:
            outcome = {"status": "error", "message": str(ex), "annotations": _serialize_annotations(ex.annotations)}
        except MoveOutOfBoundsException as ex:
            print(ex)
            outcome = {"status": "error", "message": str(ex), "annotations": None}
        except MoveBlockedByBlackException as ex:
            print(ex)
            outcome = {"status": "error", "message": str(ex), "annotations": None}
        except Exception as ex:
            print(ex)
            outcome = {"status": "error", "message": str(ex), "annotations": None}
        finally:
            if save:
                self.save(save)

        primary_entry_point = entry_point_name or getattr(bit_function, "__name__", "<entry point>")
        _add_bit_states(recorder.recording, initial_state, primary_entry_point)
        recorder.recording.insert(1, {
            "event": "call",
            "filename": filename,
            "lineno": (
                entry_point_call_line
                if entry_point_call_line is not None
                else getattr(getattr(bit_function, "__code__", None), "co_firstlineno", None)
            ),
            "function": "<module>",
            "qualified_function": "<module>",
            "locals": {},
            "callers": [],
            "module_call": True,
            "function_call": {
                "qualified_function": primary_entry_point,
                "arguments": {},
                "positional_arguments": [],
            },
            "bit": initial_state,
        })
        if student_completed:
            return_record = next(
                (
                    event for event in reversed(recorder.recording)
                    if event.get("event") == "return"
                    and event.get("function") == getattr(bit_function, "__name__", None)
                ),
                None,
            )
            return_value = (
                return_record["return"]["value"]
                if return_record is not None
                else {"type": "NoneType", "data": None}
            )
            recorder.recording.append({
                "event": "call_return",
                "filename": filename,
                "lineno": entry_point_call_line or (return_record or {}).get("lineno"),
                "function": "<module>",
                "qualified_function": "<module>",
                "locals": {},
                "callers": [],
                "module_return": True,
                "call_return": {
                    "function": primary_entry_point,
                    "qualified_function": primary_entry_point,
                    "value": return_value,
                },
                "bit": _serialize_bit(self),
                "outcome": outcome,
            })
        elif len(recorder.recording) > 1:
            recorder.recording[-1]["outcome"] = outcome
        return self.name, recorder.recording

    def __getattr__(self, usr_attr):
        """Checks if a non-existent method or property is accessed, and gives a suggestion"""
        message = f"bit.{usr_attr} does not exist. "
        # A side effect of converting functions to properties is that they lose their callable status
        # Since we convert all functions the students use to properties, we filter to only those methods.
        # Checking that the method doesn't start with _ is not currently necessary, though potentially useful.
        bit_methods = [method for method in dir(Bit) if
                       not callable(getattr(Bit, method)) and str(method)[0] != "_"]
        min_diff = (len(usr_attr), "")
        for method in bit_methods:
            # Find number of different symbols from the start
            difference = sum(1 for a, b in zip(usr_attr, method) if a != b)
            # Find number of different symbols from the end
            difference = min(difference, sum(1 for a, b in zip(usr_attr[::-1], method[::-1]) if a != b))
            if difference <= min_diff[0]:
                min_diff = (difference, method)
        # Suggest the method with the minimum difference
        message += f"Did you mean bit.{min_diff[1]}?"
        raise Exception(message)

    @_check_extraneous_args
    @_registered
    def move(self):
        """If the direction is clear, move that way"""
        next_pos = self._get_next_pos()
        if not self._pos_in_bounds(next_pos):
            message = f"Bit tried to move to {next_pos}, but that is out of bounds"
            raise MoveOutOfBoundsException(message)

        elif self._get_color_at(next_pos) == BLACK:
            message = f"Bit tried to move to {next_pos}, but that space is blocked"
            raise MoveBlockedByBlackException(message)

        else:
            self.pos = next_pos

    # @check_for_parentheses
    @_check_extraneous_args
    @_registered
    def turn_left(self):
        """Turn the bit to the left"""
        self.orientation = self._next_orientation(1)

    left = turn_left

    # @check_for_parentheses
    @_check_extraneous_args
    @_registered
    def turn_right(self):
        """Turn the bit to the right"""
        self.orientation = self._next_orientation(-1)

    right = turn_right

    def _get_color_at(self, pos):
        row, col = pos
        return self.world[row][col]

    def _space_is_clear(self, pos):
        return self._pos_in_bounds(pos) and self._get_color_at(pos) != BLACK

    # @check_for_parentheses
    @_check_extraneous_args
    @_registered
    def can_move_front(self) -> bool:
        """Can a move to the front succeed?

        The edge of the world is not clear.

        Black squares are not clear.
        """
        return self._space_is_clear(self._get_next_pos())

    front_clear = can_move_front

    # @check_for_parentheses
    @_check_extraneous_args
    @_registered
    def can_move_left(self) -> bool:
        return self._space_is_clear(self._get_next_pos(1))

    left_clear = can_move_left

    # @check_for_parentheses
    @_check_extraneous_args
    @_registered
    def can_move_right(self) -> bool:
        return self._space_is_clear(self._get_next_pos(-1))

    right_clear = can_move_right

    def _paint(self, color: str):
        row, col = self.pos
        self.world[row][col] = color

    # @check_for_parentheses
    @_check_extraneous_args
    @_registered
    def erase(self):
        """Clear the current position
        DEPRECATED: use paint('white') instead
        """
        self._paint(WHITE)

    # @check_for_parentheses
    @_check_extraneous_args
    @_registered
    def paint(self, color: str):
        """Color the current position with the specified color"""
        if color not in css_colors:
            message = f"Unrecognized color: '{color}'. \nTry: 'red', 'green', 'blue', or 'white'"
            raise Exception(message)
        self._paint(color)

    def _get_color(self) -> str:
        # This function isn't registered
        # So it can be used by the is_on_* methods
        return self._get_color_at(self.pos)

    # @check_for_parentheses
    @_check_extraneous_args
    @_registered
    def get_color(self) -> str:
        """Return the color at the current position"""
        return self._get_color()

    # @check_for_parentheses
    @_check_extraneous_args
    @_registered
    def is_on_blue(self):
        return self._get_color() == 'blue'

    is_blue = is_on_blue

    # @check_for_parentheses
    @_check_extraneous_args
    @_registered
    def is_on_green(self):
        return self._get_color() == 'green'

    is_green = is_on_green

    # @check_for_parentheses
    @_check_extraneous_args
    @_registered
    def is_on_red(self):
        return self._get_color() == 'red'

    is_red = is_on_red

    # @check_for_parentheses
    @_check_extraneous_args
    @_registered
    def is_on_white(self):
        return self._get_color() == 'white'

    is_empty = is_on_white

    # @check_for_parentheses
    @_check_extraneous_args
    @_registered
    def snapshot(self, title: str):
        pass  # The function simply registers a frame, which @registered already does
