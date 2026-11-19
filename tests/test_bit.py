import pytest

from byubit import Bit
from byubit.bit import MoveBlockedByBlackException, MoveOutOfBoundsException


def make_bit(*, world=None, pos=(1, 1), orientation=0):
    if world is None:
        world = [["white"] * 3 for _ in range(3)]
    return Bit("test", world, pos, orientation)


def test_new_world_starts_at_origin_facing_right():
    bit = Bit.new_world(3, 2)

    assert bit.name == "New World (3, 2)"
    assert bit.world == [["white", "white", "white"], ["white", "white", "white"]]
    assert bit.pos == (0, 0)
    assert bit.orientation == 0


def test_move_advances_in_facing_direction():
    bit = make_bit(pos=(1, 1))

    bit.move()

    assert bit.pos == (1, 2)


@pytest.mark.parametrize(
    ("turn", "expected_orientation"),
    [("turn_left", 1), ("turn_right", 3)],
)
def test_turn_changes_orientation(turn, expected_orientation):
    bit = make_bit(orientation=0)

    getattr(bit, turn)()

    assert bit.orientation == expected_orientation


def test_turns_wrap_around():
    bit = make_bit(orientation=3)

    bit.turn_left()

    assert bit.orientation == 0


def test_can_move_checks_bounds_and_black_squares_in_each_direction():
    world = [["white"] * 3 for _ in range(3)]
    world[1][2] = "black"
    bit = make_bit(world=world)

    assert bit.can_move_front() is False  # black square to the right
    assert bit.can_move_left() is True
    assert bit.can_move_right() is True

    bit.pos = (0, 0)
    bit.orientation = 1  # facing up, so left is out of bounds
    assert bit.can_move_left() is False


def test_move_raises_when_blocked_or_out_of_bounds():
    blocked = make_bit(world=[["white", "black"], ["white", "white"]], pos=(0, 0))
    with pytest.raises(MoveBlockedByBlackException):
        blocked.move()
    assert blocked.pos == (0, 0)

    edge = make_bit(world=[["white", "white"]], pos=(0, 1))
    with pytest.raises(MoveOutOfBoundsException):
        edge.move()
    assert edge.pos == (0, 1)


def test_paint_erase_and_color_queries():
    bit = make_bit(pos=(1, 1))

    bit.paint("blue")
    assert bit.get_color() == "blue"
    assert bit.is_on_blue() is True
    assert bit.is_blue() is True
    assert bit.is_on_white() is False

    bit.erase()
    assert bit.get_color() == "white"
    assert bit.is_empty() is True


def test_paint_rejects_unknown_color_without_changing_world():
    bit = make_bit(pos=(1, 1))

    with pytest.raises(Exception, match="Unrecognized color"):
        bit.paint("not-a-color")

    assert bit.get_color() == "white"
