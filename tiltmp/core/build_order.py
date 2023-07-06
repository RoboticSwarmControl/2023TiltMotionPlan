import time
from collections import Counter
from copy import copy
import random
from typing import Iterable, List, Set, Dict

from tiltmp.core.algorithms import (
    is_connected_by_glues,
    is_connected,
    compute_distances,
    breadth_first_path_exists,
    find_largest_glue_connected_component,
)
from tiltmp.core.tumbletiles import *


class BuildOrderPlanner:
    def __init__(
        self,
        board: Board,
        target_shape: Polyomino,
        precomputed_distances=None,
        timeout=600,
        build_order_timeout=10,
    ):
        self.end_time = time.time() + timeout
        self._board = board
        self._target_shape = target_shape
        self._build_order_timeout = build_order_timeout
        self._glues = None
        self._build_order_generator = None

        if hasattr(self._board, "fixed_tiles"):
            offset = self._target_shape.position
            self._fixed = [
                (t.x - offset[0], t.y - offset[1]) for t in self._board.fixed_tiles
            ]
        else:
            self._fixed = []

        self.change_build_order()

        self._distances = precomputed_distances or compute_distances(
            self._board, self._target_shape
        )

    def finished(self):
        return not self._build_order

    def change_build_order(self):
        shape = set(self._target_shape.get_shape()[1])
        tiles = list(self._board.get_tiles())

        while True:
            if time.time() > self.end_time:
                raise TimeoutError("Unable to find blueprint for target shape")

            if self._glues is None:
                self._glues = get_blueprint_with_glue_types(
                    shape,
                    tiles,
                    self._board.glue_rules,
                    fixed_tiles=self._board.fixed_tiles
                    if hasattr(self._board, "fixed_tiles")
                    else [],
                    offset=self._target_shape.position,
                    timeout=self._build_order_timeout,
                )
                if self._glues is None:
                    continue

            if hasattr(self._board, "fixed_tiles"):
                self._build_order_generator = FixedTilesBuildOrderFinder(
                    self._glues,
                    self._board.glue_rules,
                    self._board,
                    self._target_shape,
                    end_time=self.end_time,
                    max_time_per_result=self._build_order_timeout,
                )
            else:
                self._build_order_generator = BuildOrderFinder(
                    self._glues,
                    self._board.glue_rules,
                    self._fixed,
                    end_time=self.end_time,
                    max_time_per_result=self._build_order_timeout,
                )

            try:
                self._build_order = next(self._build_order_generator)
            except StopIteration:
                # there is no build order for these glues try other tiling
                self._glues = None
                continue
            except TimeoutError:
                self._glues = None
                # no build order was found for some time. Try a different tiling
                continue
            else:
                # found good tiling and build order
                break

    def get_next_tile(self, current_poly, offset):
        next_destination = self._build_order.pop(0)
        relative_to_poly = (
            next_destination[0] - offset[0],
            next_destination[1] - offset[1],
        )
        next_glue_type = self._glues[next_destination]
        poly = current_poly if current_poly is not None else self._target_shape
        absolute_destination = (
            poly.position[0] + relative_to_poly[0],
            poly.position[1] + relative_to_poly[1],
        )
        return next_destination, self._find_nearest_tile_with_glue_type(
            poly, {absolute_destination}, next_glue_type
        )

    def _find_nearest_tile_with_glue_type(self, poly, destination, glue_type):
        distance = {xy: 0 for xy in destination}
        active = deque(distance.keys())
        while active:
            current = active.popleft()
            t = self._board.get_tile_at(*current)
            if t and t.parent is not poly and t.glues == glue_type:
                return t
            for xy in direct_neighbors(*current):
                if self._board.is_blocked(*xy):
                    continue
                if xy in distance:
                    continue
                distance[xy] = distance[current] + 1
                active.append(xy)
        return None


def get_blueprint_with_glue_types(
    container: Iterable[tuple],
    tiles: Iterable[Tile],
    glue_rules,
    fixed_tiles=(),
    offset=(0, 0),
    timeout=600.0,
):
    available_glue_types = Counter()
    container = list(container)
    current_shape = {}
    for tile in tiles:
        if tile in fixed_tiles:
            current_shape[(tile.x - offset[0], tile.y - offset[1])] = tile.glues
            container.remove((tile.x - offset[0], tile.y - offset[1]))
            continue
        available_glue_types.update([tile.glues])
    start_time = time.time()
    while True:
        if time.time() - start_time > timeout:
            return None
        result = _get_blueprint_with_glue_types_recursive(
            container, current_shape, available_glue_types, glue_rules
        )
        if result:
            return result


def _get_blueprint_with_glue_types_recursive(
    missing: List[tuple], current_shape, available_glue_types, glue_rules
):
    if not missing:
        if is_connected_by_glues(current_shape, glue_rules):
            return current_shape
        else:
            return None
    glue_types = list(available_glue_types.keys())
    random.shuffle(glue_types)
    for glue in glue_types:
        if available_glue_types[glue] > 0:
            remaining_glues = copy(available_glue_types)
            remaining_glues[glue] -= 1
            new_shape = copy(current_shape)
            new_shape[missing[-1]] = glue
            return _get_blueprint_with_glue_types_recursive(
                missing[:-1], new_shape, remaining_glues, glue_rules
            )
    return None


def is_convex(shape: Set[tuple], tile: tuple):
    # check all 2x2 boxes the tile is a part of. Iff any of them does not contain another tile, tile is convex.
    squares = [
        [(-1, -1), (-1, 0), (0, -1)],  # tile is top right
        [(1, 1), (1, 0), (0, 1)],  # tile is bottom left
        [(-1, 1), (-1, 0), (0, 1)],  # tile is top left
        [(1, -1), (1, 0), (0, -1)],  # tile is bottom right
    ]
    for square in squares:
        convex = True
        for x, y in square:
            if (tile[0] + x, tile[1] + y) in shape:
                convex = False
        if convex:
            return True
    else:
        return False


def remove_path_exists(glues: Dict[tuple, Glues], tile_position, glue_rules: GlueRules):
    blocked_positions = set()
    tile_glues = glues[tile_position]
    for xy, g in glues.items():
        if xy == tile_position:
            continue
        blocked_positions.add(xy)
        for direction in Direction:
            glue1 = getattr(glues[xy], direction.value)
            glue2 = getattr(tile_glues, direction.inverse().value)
            if glue_rules.sticks(glue1, glue2):
                blocked_positions.add(neighbor(xy, direction))
    outside = (-2, 0)

    return breadth_first_path_exists(
        {tile_position},
        lambda p: p == outside,
        lambda p: direct_neighbors(*p),
        is_valid_neighbor=lambda p: p not in blocked_positions,
    )


def remove_path_exists_fixed(
    glues: Dict[tuple, Glues],
    tile_position,
    glue_rules: GlueRules,
    board: Board,
    outside,
):
    blocked_positions = set()
    tile_glues = glues[tile_position]
    for xy, g in glues.items():
        if xy == tile_position:
            continue
        blocked_positions.add(xy)
        for direction in Direction:
            glue1 = getattr(glues[xy], direction.value)
            glue2 = getattr(tile_glues, direction.inverse().value)
            if glue_rules.sticks(glue1, glue2):
                blocked_positions.add(neighbor(xy, direction))

    return breadth_first_path_exists(
        {tile_position},
        outside,
        lambda p: direct_neighbors(*p),
        is_valid_neighbor=lambda p: p not in blocked_positions
        and not board.is_blocked(*p),
    )


def is_removable(old_shape, new_shape, tile_position, glue_rules):
    return is_connected_by_glues(new_shape, glue_rules) and remove_path_exists(
        old_shape, tile_position, glue_rules
    )


def is_removable_fixed(old_shape, new_shape, tile_position, glue_rules, board, outside):
    return is_connected_by_glues(new_shape, glue_rules) and remove_path_exists_fixed(
        old_shape, tile_position, glue_rules, board, outside
    )


class BuildOrderFinder:
    def __init__(
        self,
        glues: Dict[tuple, Glues],
        glue_rules,
        fixed_tiles_positions,
        end_time=None,
        max_time_per_result=10.0,
    ):
        self._end_time = end_time
        self.glue_rules = glue_rules
        self.fixed_tiles_positions = fixed_tiles_positions
        self._time_per_result = max_time_per_result
        self._next_result_timeout = None
        self.iter = self._generate_building_orders_recursive([], glues)

    def _check_timeouts(self):
        if self._end_time is not None and time.time() > self._end_time:
            raise TimeoutError("End time reached")
        if (
            self._next_result_timeout is not None
            and time.time() > self._next_result_timeout
        ):
            raise TimeoutError("No new result found in time")

    def _generate_building_orders_recursive(self, order, glues: Dict[tuple, Glues]):
        self._check_timeouts()

        if len(glues) == 0:
            yield list(reversed(order))

        s = copy(glues)
        for t in s:
            if (
                len(s) > len(self.fixed_tiles_positions)
                and t in self.fixed_tiles_positions
            ):
                continue
            new_shape = copy(s)
            new_shape.pop(t)
            if not is_removable(s, new_shape, t, self.glue_rules):
                continue
            new_order = order + [t]
            for o in self._generate_building_orders_recursive(new_order, new_shape):
                yield o

    def __iter__(self):
        return self

    def __next__(self):
        self._next_result_timeout = time.time() + self._time_per_result
        return next(self.iter)


class FixedTilesBuildOrderFinder(BuildOrderFinder):
    def __init__(
        self,
        glues: Dict[tuple, Glues],
        glue_rules,
        board: FixedSeedTilesBoard,
        target_shape: Polyomino,
        end_time=None,
        max_time_per_result=10.0,
    ):
        fixed_tiles_positions = [(t.x, t.y) for t in board.fixed_tiles]
        super().__init__(
            glues,
            glue_rules,
            fixed_tiles_positions,
            end_time=end_time,
            max_time_per_result=max_time_per_result,
        )
        # make board with same concrete positions
        self.board = FixedSeedTilesBoard(board.rows, board.cols, board.glue_rules)
        self.board.concrete = board.concrete

        self.dx, self.dy = target_shape.position
        glues = {(x + self.dx, y + self.dy): v for (x, y), v in glues.items()}

        positions = glues.keys()
        left = min(x for x, _ in positions) - 2
        right = max(x for x, _ in positions) + 2
        up = min(y for _, y in positions) - 2
        down = max(y for _, y in positions) + 2

        def outside(position):
            x, y = position
            return not (left < x < right and up < y < down)

        self.outside = outside
        self.iter = self._generate_building_orders_recursive([], glues)

    def _generate_building_orders_recursive(self, order, glues: Dict[tuple, Glues]):
        self._check_timeouts()

        if len(glues) == 0:
            yield list(reversed(order))

        s = copy(glues)
        for t in s:
            if (
                len(s) > len(self.fixed_tiles_positions)
                and t in self.fixed_tiles_positions
            ):
                continue
            new_shape = copy(s)
            new_shape.pop(t)
            if not is_removable_fixed(
                s, new_shape, t, self.glue_rules, self.board, self.outside
            ):
                continue
            new_order = order + [(t[0] - self.dx, t[1] - self.dy)]
            for o in self._generate_building_orders_recursive(new_order, new_shape):
                yield o


def generate_building_orders(
    glues: Dict[tuple, Glues], glue_rules, fixed_tiles_positions, end_time
):
    return _generate_building_orders_recursive(
        [], glues, glue_rules, fixed_tiles_positions, end_time
    )


def _generate_building_orders_recursive(
    order, glues: Dict[tuple, Glues], glue_rules, fixed_tiles_positions, end_time
):
    if time.time() > end_time:
        return

    if len(glues) == 0:
        yield list(reversed(order))

    s = copy(glues)
    for t in s:
        if len(s) > len(fixed_tiles_positions) and t in fixed_tiles_positions:
            continue
        new_shape = copy(s)
        new_shape.pop(t)
        if not is_removable(s, new_shape, t, glue_rules):
            continue
        new_order = order + [t]
        for o in _generate_building_orders_recursive(
            new_order, new_shape, glue_rules, fixed_tiles_positions, end_time
        ):
            yield o
