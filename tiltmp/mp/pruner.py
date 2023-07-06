import heapq
from abc import ABC, abstractmethod
from copy import copy

from typing import Set

from tiltmp.core.algorithms import reachable_set, is_reachable_area, is_packable, fits

from tiltmp.core.tumbletiles import *


class Pruner(ABC):
    def __init__(self):
        self.board = None
        self.target_shape = None

    def setup(self, board: Board, target: Polyomino):
        self.board = board
        self.target_shape = target

    @abstractmethod
    def is_prunable(self, changed):
        pass

    def count_tiles(self):
        return sum(p.size for p in self.board.polyominoes if p.can_reach)


class NotEnoughTilesPruner(Pruner):
    def __init__(self):
        super().__init__()
        self.target_area = None

    def setup(self, board: Board, target: Polyomino):
        super().setup(board, target)
        pos = self.target_shape.position
        self.target_area = {
            (pos[0] + dx, pos[1] + dy) for dx, dy in self.target_shape.get_shape()[1]
        }

    def _recompute_reachable(self, p: Polyomino):
        p.can_reach = is_reachable_area(self.board, p, self.target_area)

    def is_prunable(self, changed: Set[Polyomino]):
        for p in changed:
            if p.can_reach:
                self._recompute_reachable(p)
        if self.count_tiles() < self.target_shape.size:
            return True
        return False


class NotEnoughTilesNoLeftoversPruner(NotEnoughTilesPruner):
    def is_prunable(self, changed: Set[Polyomino]):
        for p in changed:
            self._recompute_reachable(p)
            if not p.can_reach:
                return True
        return False


class PackingNoLeftoversPruner(Pruner):
    def __init__(self, n=3):
        super().__init__()
        self.n = n

    def is_prunable(self, changed):
        if not changed:
            return False
        largest = heapq.nlargest(self.n, self.board.polyominoes, key=lambda p: p.size)
        # if largest n polyominoes do not fit into the target polyomino, the branch can be pruned
        return not is_packable(
            self.target_shape.get_shape()[1], [p.get_shape()[1] for p in largest]
        )


class PackingPruner(Pruner):
    def is_prunable(self, changed):
        for p in changed:
            if p.can_reach:
                p.can_reach = fits(self.target_shape.get_shape()[1], p.get_shape()[1])
        if self.count_tiles() < self.target_shape.size:
            return True
        return False


class AnyTilesCombinedPruner(Pruner):
    def __init__(self, motion_planner):
        super().__init__()
        self.mp = motion_planner

    def is_prunable(self, changed):
        if changed:
            return True
        else:
            return False


class WrongTilesCombinedPruner(Pruner):
    def __init__(self, motion_planner):
        super().__init__()
        self.mp = motion_planner
        self.poly_size = self.mp.poly.size

    def is_prunable(self, changed):
        # handle special case, where the target polyomino does not exist on the board anymore
        if not self.mp.poly in self.mp.board.polyominoes:
            # target polyomino combined with poly to its left
            if not self.mp.poly.tiles[(0, 0)].parent == self.mp.tile.parent:
                # target polyomino combined with tile that is not the selected tile
                return True
            # target poly combined with the selected tile. Check if it is in the right place
            combined_poly = self.mp.poly.tiles[(0, 0)].parent
            previous_corner = self.mp.poly.tiles[(0, 0)]
            if not (
                previous_corner.x + self.mp.destination[0] == self.mp.tile.x
                and previous_corner.y + self.mp.destination[1] == self.mp.tile.y
            ):
                # tile is in the wrong place
                return True
            if not (self.poly_size + 1 == combined_poly.size):
                # additional tiles combined with the target polyomino
                return True
            changed = changed - {combined_poly}

        for p in changed:
            if p is not self.mp.poly:
                # uninvolved poly changed
                return True
            if not (self.poly_size + 1 == p.size):
                # additional tiles combined with the target polyomino
                return True
            if not (
                p.position[0] + self.mp.destination[0] == self.mp.tile.x
                and p.position[1] + self.mp.destination[1] == self.mp.tile.y
            ):
                # tile is in the wrong place
                return True

        return False


class TargetUnreachablePruner(Pruner):
    def __init__(self, motion_planner):
        super().__init__()
        self.mp = motion_planner

        # create target polyomino of this construction step and
        self.target_poly = deepcopy(self.mp.poly)
        # add the new tile to the target polyomino
        dest = self.mp.destination
        added_tile = copy(self.mp.tile)
        added_tile.x = self.target_poly.position[0] + dest[0]
        added_tile.y = self.target_poly.position[1] + dest[1]
        self.target_poly.add_tile(added_tile)

        # put in in the correct position relative to the final target shape
        dx = (
            self.mp.target_shape.position[0]
            + self.mp.offset[0]
            - self.target_poly.position[0]
        )
        dy = (
            self.mp.target_shape.position[1]
            + self.mp.offset[1]
            - self.target_poly.position[1]
        )
        self.target_poly.move(dx, dy)

        self._target_area = reachable_set(self.mp.board, self.target_poly)

    def is_prunable(self, changed):
        if not self.mp._stop_condition.is_finished():
            return False
        p = self.mp.poly.tiles[(0, 0)].parent
        return p.position not in self._target_area


class PolyominoLeftAreaPruner(Pruner):
    def __init__(self, motion_planner, area):
        super().__init__()
        self.mp = motion_planner
        self.area = area

    def is_prunable(self, changed):
        p = self.mp.poly.tiles[(0, 0)].parent
        return p.position not in self.area


class TilesGluedOutsideTargetAreaPruner(Pruner):
    def __init__(self):
        super().__init__()
        self.target_area = None

    def setup(self, board: Board, target: Polyomino):
        super().setup(board, target)
        self.target_area = {(t.x, t.y) for t in self.target_shape.get_tiles()}

    def is_prunable(self, changed):
        for p in changed:
            for t in p.get_tiles():
                if (t.x, t.y) not in self.target_area:
                    return True
        return False
