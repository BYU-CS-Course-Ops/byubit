# Inspired by Stanford: http://web.stanford.edu/class/cs106a/handouts_w2021/reference-bit.html
import functools
import os
import traceback
from copy import deepcopy
from inspect import stack
from typing import Literal, List, Tuple, Iterator

import matplotlib.pyplot as plt
import numpy as np
import importlib
import csv

# 0,0  1,0  2,0
# 0,1  1,1, 2,1
# 0,2  1,2, 2,2
# dx and dy
from byubit.core import BitHistoryRecord, BitHistoryRenderer, BitComparisonException, _codes_to_colors, \
    _colors_to_codes, draw_record, MoveOutOfBoundsException, BLACK, MoveBlockedByBlackException, EMPTY, \
    _names_to_colors, _colors_to_names, determine_figure_size, BitInfiniteLoopException, ParenthesesException
from byubit.renderers import AnimatedRenderer, LastFrameRenderer

_orientations = [
    np.array((1, 0)),  # Right
    np.array((0, 1)),  # Up
    np.array((-1, 0)),  # Left
    np.array((0, -1))  # Down
]

MAX_STEP_COUNT = 15_000

# Set default renderer
# - If running in IPython, use the LastFrameRenderer
# - Else use AnimatedRenderer
VERBOSE = False
try:
    RENDERER = AnimatedRenderer

    ipy = importlib.import_module("IPython")
    ip = getattr(ipy, "get_ipython")()
    if ip is not None:
        RENDERER = LastFrameRenderer

except Exception as _:
    pass


def set_verbose():
    global VERBOSE
    VERBOSE = True


class NewBit:
    def __getattribute__(self, item):
        raise Exception('You can only pass Bit.new_bit to a function with an @Bit decorator')


# Convention:
# We'll have 0,0 be the origin
# The position defines the X,Y coordinates
class Bit:
    _name: str
    _world: np.array
    _pos: np.array  # x and y
    _orientation: int  # _orientations[orientation] => dx and dy

    _history: List[BitHistoryRecord]

    _state_history = {}
    _results = None
    new_bit = NewBit()
    _paren_error = None

    @staticmethod
    def _pictures(path='', ext='png', title=None, bwmode=False, name=None):
        def decorator(function):
            def new_function(bit):
                # Draw starting conditions
                filename = name or bit._name
                bit._draw(path + filename + '.start.' + ext, message=title, bwmode=bwmode)

                # Run function
                function(bit)

                # Save ending conditions
                bit._draw(path + filename + '.finish.' + ext, message=title, bwmode=bwmode)

            return new_function

        return decorator

    @staticmethod
    def empty_world(width, height, name=None, **kwargs):
        return Bit.worlds(Bit._new_world(width, height, name=name), **kwargs)

    @staticmethod
    def worlds(*bit_worlds, **kwargs):
        bits = []
        for bit_world in bit_worlds:
            if isinstance(bit_world, str):
                possible_worlds = [
                    bit_world + '.start.txt',
                    bit_world + '.start.csv',
                    os.path.join('worlds', bit_world + '.start.txt'),
                    os.path.join('worlds', bit_world + '.start.csv')
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
            def new_function(bit):
                if bit is Bit.new_bit:
                    return Bit._evaluate(bit_func, bits, **kwargs)
                else:
                    raise TypeError(f"You must pass Bit.new_bit to your main function.")

            return new_function

        return decorator

    @staticmethod
    def _evaluate(
            bit_function,
            bits,
            save=None,
            renderer: BitHistoryRenderer = None
    ) -> bool:
        """Return value communicates whether the run succeeded or not"""

        renderer = renderer or RENDERER(verbose=VERBOSE)

        results = []
        for bit1, bit2 in bits:
            if isinstance(bit1, str):
                bit1 = Bit._load(bit1)

            if isinstance(bit2, str):
                bit2 = Bit._load(bit2)
            try:
                bit_function(bit1)

                if bit2 is not None:
                    bit1.__compare(bit2)

            except BitInfiniteLoopException as ex:
                print(ex)
                bit1._register("infinite loop 😵", str(ex), ex.annotations)

            except BitComparisonException as ex:
                bit1._register("comparison error", str(ex), ex.annotations)

            except MoveOutOfBoundsException as ex:
                print(ex)
                bit1._register("move out of bounds", str(ex), ex=ex)

            except MoveBlockedByBlackException as ex:
                print(ex)
                bit1._register("move blocked", str(ex), ex=ex)

            except ParenthesesException as ex:
                print(ex)
                bit1._register(ex.name, str(ex), ex=ex)
                bit1._history[-1].line_number = ex.line_number

            except Exception as ex:
                print(ex)
                bit1._register("error", str(ex), ex=ex)

            finally:
                if save:
                    bit1._save(save)

                results.append((bit1._name, bit1._history))
        Bit._results = results
        return renderer.render(results)

    @staticmethod
    def _new_world(size_x, size_y, name=None):
        if name is None:
            name = f"New World({size_x}, {size_y})"
        return Bit(name, np.zeros((size_x, size_y)), (0, 0), 0)

    @staticmethod
    def _parse_string(content: str):
        content = [line.split() for line in content.splitlines() if line]
        content[:-2] = [list(line[0]) for line in content[:-2]]
        return content

    @staticmethod
    def _parse_file(filename: str):
        """Parse either csv or txt file into list[list[str]] format. """
        if filename.endswith(".txt"):
            with open(filename, 'r') as file:
                content = Bit._parse_string(file.read())
        elif filename.endswith(".csv"):
            with open(filename, 'r') as file:
                reader = csv.reader(file)
                content = [line for line in reader]
        else:
            raise ValueError("Unsupported file format")

        return content

    @staticmethod
    def _load(filename: str):
        """Parse the file into a new Bit"""
        content = Bit._parse_file(filename)
        base, ext = os.path.splitext(filename)
        name = os.path.basename(base)
        return Bit._parse(name, content)

    @staticmethod
    def _parse(name: str, content: list[list[str]]):
        """Parse the bitmap from nested list."""
        # There must be at least three lines
        assert len(content) >= 3

        # Position is the second-to-last line
        pos = np.array([int(x) for x in content[-2]]).astype(int)

        # Orientation is the last line: 0, 1, 2, 3
        orientation = int(content[-1][0])

        # World lines are all lines up to the second-to-last
        # We transpose because numpy stores our lines as columns,
        # and we want them represented as rows in memory
        world = np.array([[_codes_to_colors[code] for code in line] for line in content[-3::-1]]).transpose()

        return Bit(name, world, pos, orientation)

    def __init__(self, name: str, world: np.array, pos: np.array, orientation: int):
        self._name = name
        self._world = world
        self._pos = np.array(pos)
        self._orientation = orientation
        self._history = []
        self._register("initial state")

    def __repr__(self) -> str:
        """Present the bit information as a string"""
        # We print out each row in reverse order so 0,0 is at the bottom of the text, not the top
        world_str = "\n".join(
            "".join(_colors_to_codes[self._world[x, self._world.shape[1] - 1 - y]] for x in range(self._world.shape[0]))
            for y in range(self._world.shape[1])
        )
        pos_str = f"{self._pos[0]} {self._pos[1]}"
        orientation = self._orientation
        return f"{world_str}\n{pos_str}\n{orientation}\n"

    def _get_caller_info(self, ex=None) -> Tuple[str, int]:
        if ex:
            s = list(reversed(traceback.TracebackException.from_exception(ex).stack))
        else:
            s = stack()
        # Find index of the first non-bit.py frame following a bit.py frame
        index = 0
        while s[index].filename == __file__:
            index += 1
        return os.path.basename(s[index].filename), s[index].lineno

    def _record(self, name, message=None, annotations=None, ex=None, line=None):
        filename, line_number = self._get_caller_info(ex=ex)
        return BitHistoryRecord(
            name, message, self._world.copy(), self._pos, self._orientation,
            deepcopy(annotations) if annotations is not None else None,
            filename, line_number
        )

    def _register(self, name, message=None, annotations=None, ex=None):
        self._history.append(self._record(name, message, annotations, ex))

        world_tuple = tuple(tuple(self._world[x, y] for x in range(self._world.shape[0]))
                            for y in range(self._world.shape[1]))

        bit_state = (name, world_tuple, tuple(self._pos), self._orientation)

        self._state_history[bit_state] = self._state_history.get(bit_state, 0) + 1

        if message is None and self._state_history[bit_state] >= 5:
            message = "Bit's been doing the same thing for a while. Is he stuck in an infinite loop?"
            raise BitInfiniteLoopException(message, annotations)

        elif message is None and len(self._history) > MAX_STEP_COUNT:
            message = "Bit has done too many things. Is he stuck in an infinite loop?"
            raise BitInfiniteLoopException(message, annotations)

    def _save(self, filename: str):
        """Save your bit world to a text file"""
        with open(filename, 'wt') as f:
            f.write(repr(self))
        print(f"Bit saved to {filename}")

    def _draw(self, filename=None, message=None, annotations=None, bwmode=False):
        """Display the current state of the world"""
        record = self._record("", annotations=annotations)
        fig = plt.figure(figsize=determine_figure_size(record.world.shape))
        ax = fig.add_axes([0.02, 0.05, 0.96, 0.75])
        draw_record(ax, record, bwmode=bwmode)

        if message:
            ax.set_title(message)

        if filename:
            print("Saving bit world to " + filename)
            fig.savefig(filename)
        else:
            plt.show()

    def _next_orientation(self, direction: Literal[1, 0, -1]) -> np.array:
        return (len(_orientations) + self._orientation + direction) % len(_orientations)

    def _get_next_pos(self, turn: Literal[1, 0, -1] = 0) -> np.array:
        return self._pos + _orientations[self._next_orientation(turn)]

    def _pos_in_bounds(self, pos) -> bool:
        return np.logical_and(pos >= 0, pos < self._world.shape).all()

    def __getattr__(self, usr_attr):
        """Checks if a non-existent method or property is accessed, and gives a suggestion"""
        message = f"bit.{usr_attr} does not exist. "
        # A side effect of converting functions to properties is that they lose their callable status
        # Since we convert all functions the students use to properties, we filter to only those methods.
        # Checking that the method doesn't start with _ is not currently necessary, though potentially useful.
        bit_methods = [method for method in dir(Bit) if not callable(getattr(Bit, method)) and str(method)[0] != "_"]
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

    def _check_extraneous_args(func):
        @functools.wraps(func)
        def new_func(self, *args):
            # Get argument names for the given function
            arg_names = func.__code__.co_varnames[1:func.__code__.co_argcount]
            argc = len(arg_names)
            # Convert the user arguments to a list of strings
            user_args = ["bit" if type(x) == type(self) else f"'{x}'" if type(x) is str else str(x) for x in args]
            # If the number of arguments given is incorrect, suggest the correct arguments
            if len(args) != argc:
                raise Exception(f"Error: bit.{func.__name__}() takes {argc if argc else 'no'} argument{'s' if argc != 1 else ''}, but {len(user_args)} {'was' if len(user_args) == 1 else 'were'} given.")
            return func(self, *args)
        return new_func

    def _check_for_parentheses(func):
        @functools.wraps(func)
        def new_func(self):
            filename, line_number = self._get_caller_info()
            if self._paren_error:
                raise self._paren_error
            else:
                ex = f"Error: bit.{func.__name__} requires parentheses to be used."
                self._paren_error = ParenthesesException(ex, func.__name__, line_number)
            bit_self = self


            class ForceParentheses:
                def __call__(self, *args):
                    bit_self._paren_error = None
                    return func(bit_self, *args)
            return ForceParentheses()
        return property(new_func)

    @_check_for_parentheses
    @_check_extraneous_args
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
            self._pos = next_pos
            self._register("move")

    @_check_for_parentheses
    @_check_extraneous_args
    def left(self):
        """Turn the bit to the left"""
        self._orientation = self._next_orientation(1)
        self._register("left")

    @_check_for_parentheses
    @_check_extraneous_args
    def right(self):
        """Turn the bit to the right"""
        self._orientation = self._next_orientation(-1)
        self._register("right")

    def _get_color_at(self, pos):
        return self._world[pos[0], pos[1]]

    def _space_is_clear(self, pos):
        return self._pos_in_bounds(pos) and self._get_color_at(pos) != BLACK

    @_check_for_parentheses
    @_check_extraneous_args
    def front_clear(self) -> bool:
        """Can a move to the front succeed?

        The edge of the world is not clear.

        Black squares are not clear.
        """
        ret = self._space_is_clear(self._get_next_pos())
        self._register(f"front_clear: {ret}")
        return ret

    @_check_for_parentheses
    @_check_extraneous_args
    def left_clear(self) -> bool:
        ret = self._space_is_clear(self._get_next_pos(1))
        self._register(f"left_clear: {ret}")
        return ret

    @_check_for_parentheses
    @_check_extraneous_args
    def right_clear(self) -> bool:
        ret = self._space_is_clear(self._get_next_pos(-1))
        self._register(f"right_clear: {ret}")
        return ret

    def _paint(self, color: int):
        self._world[self._pos[0], self._pos[1]] = color

    @_check_for_parentheses
    @_check_extraneous_args
    def erase(self):
        """Clear the current position"""
        self._paint(EMPTY)
        self._register("erase")

    @_check_for_parentheses
    @_check_extraneous_args
    def paint(self, color):
        """Color the current position with the specified color"""
        if color not in _names_to_colors:
            message = f"Unrecognized color: '{color}'. \nTry: 'red', 'green', or 'blue'"
            raise Exception(message)
        self._paint(_names_to_colors[color])
        self._register(f"paint {color}")

    def _get_color(self) -> str:
        """Return the color at the current position"""
        ret = _colors_to_names[self._get_color_at(self._pos)]
        return ret

    @_check_for_parentheses
    @_check_extraneous_args
    def get_color(self) -> str:
        """Return the color at the current position"""
        ret = self._get_color()
        self._register(f"get_color: {ret}")
        return ret

    @_check_for_parentheses
    @_check_extraneous_args
    def is_blue(self):
        ret = self._get_color() == 'blue'
        self._register(f"is_blue: {ret}")
        return ret

    @_check_for_parentheses
    @_check_extraneous_args
    def is_green(self):
        ret = self._get_color() == 'green'
        self._register(f"is_green: {ret}")
        return ret

    @_check_for_parentheses
    @_check_extraneous_args
    def is_red(self):
        ret = self._get_color() == 'red'
        self._register(f"is_red: {ret}")
        return ret

    @_check_for_parentheses
    @_check_extraneous_args
    def is_empty(self):
        ret = self._get_color() is None
        self._register(f"is_empty: {ret}")
        return ret

    def __compare(self, other: 'Bit'):
        """Compare this bit to another"""
        if not self._world.shape == other._world.shape:
            raise Exception(
                f"Cannot compare Bit worlds of different dimensions: {tuple(self._pos)} vs {tuple(other._pos)}")

        if not np.array_equal(self._world, other._world):
            raise BitComparisonException(f"Bit world does not match expected world",
                                         (other._world, other._pos, other._orientation))

        if self._pos[0] != other._pos[0] or self._pos[1] != other._pos[1]:
            raise BitComparisonException(
                f"Location of Bit does not match: {tuple(self._pos)} vs {tuple(other._pos)}",
                (other._world, other._pos, other._orientation)
            )

        self._register("compare correct!")

    def _compare(self, other: 'Bit'):
        try:
            self.__compare(other)
            return True

        except BitComparisonException as ex:
            self._draw(message=str(ex), annotations=ex.annotations)

        finally:
            self._draw()

        return False

    @_check_for_parentheses
    @_check_extraneous_args
    def snapshot(self, title: str):
        self._register("snapshot: " + title)
