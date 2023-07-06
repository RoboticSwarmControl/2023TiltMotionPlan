import functools
from collections import namedtuple, deque, OrderedDict
from enum import Enum
from copy import deepcopy
import inspect
import numpy as np
from tiltmp.core.gridutil import is_legal_index, direct_neighbors

DEBUGGING = False

# TEMP and GLUEFUNC are not used in this file anymore and remain here for compatibility reasons.
TEMP = 1
GLUEFUNC = {
    "N": 1,
    "E": 1,
    "S": 1,
    "W": 1,
    "A": 1,
    "B": 1,
    "C": 1,
    "D": 1,
    "X": 1,
    "Y": 1,
    "Z": 1,
}

BOARDHEIGHT = 50
BOARDWIDTH = 50
FACTORYMODE = False
COLORCHANGE = False
SINGLESTEP = False


class Direction(Enum):
    N = "N"
    W = "W"
    S = "S"
    E = "E"

    def vector(self):
        if self == Direction.N:
            return 0, -1
        elif self == Direction.W:
            return -1, 0
        elif self == Direction.S:
            return 0, 1
        elif self == Direction.E:
            return 1, 0

    def inverse(self):
        if self == Direction.N:
            return Direction.S
        elif self == Direction.W:
            return Direction.E
        elif self == Direction.S:
            return Direction.N
        elif self == Direction.E:
            return Direction.W

    @staticmethod
    def from_vector(vector):
        if vector == (0, -1):
            return Direction.N
        elif vector == (-1, 0):
            return Direction.W
        elif vector == (0, 1):
            return Direction.S
        elif vector == (1, 0):
            return Direction.E


def neighbor(p, direction):
    if direction == Direction.N:
        return p[0], p[1] - 1
    elif direction == Direction.W:
        return p[0] - 1, p[1]
    elif direction == Direction.S:
        return p[0], p[1] + 1
    elif direction == Direction.E:
        return p[0] + 1, p[1]


# GlueRules define which glues stick to each other.
class GlueRules:
    def __init__(self):
        self._rules = set()

    @property
    def rules(self):
        return self._rules

    def add_rule(self, rule):
        if len(rule) != 2:
            raise ValueError("Rules must be of length 2")
        self._rules.add(tuple(rule))
        # rules are symmetrical
        self._rules.add(tuple(reversed(rule)))

    def remove_rule(self, rule):
        self._rules.remove(tuple(rule))
        self._rules.remove(tuple(reversed(rule)))

    def add_rules(self, rules):
        for rule in rules:
            self.add_rule(rule)

    def sticks(self, glue1, glue2):
        if glue1 is None or glue2 is None:
            return False
        return (glue1, glue2) in self._rules

    def get_unique_rules(self):
        unique_rules = set()
        for rule in self._rules:
            if not reversed(rule) in unique_rules:
                unique_rules.add(rule)
        return unique_rules

    def get_glues(self):
        glues = set()
        for g1, g2 in self._rules:
            glues.update({g1, g2})
        return glues

    def __str__(self):
        return "\n".join(sorted(str(rule) for rule in self.get_unique_rules()))


class ReflexiveGlueRules(GlueRules):
    def sticks(self, glue1, glue2):
        # if glues are equal automatically add a rule that makes them stick.
        if glue1 == glue2 and glue1 is not None:
            self.add_rule((glue1, glue2))
        return super().sticks(glue1, glue2)


# Glues should be integers. 0 is reserved for no glue.
Glues = namedtuple("Glues", ["N", "E", "S", "W"])


# Class for individual tiles. Every tile on a board is part of a Polyomino.
class Tile:
    def __init__(
        self,
        color="#FFFF00",
        position=(0, 0),
        glues=Glues(None, None, None, None),
        is_concrete=False,
    ):
        self.parent = None  # polyomino this tile is in
        self.x = position[0]
        self.y = position[1]
        self.color = color
        self.glues = glues
        # Check for the case that isConcrete might be passed as a String if being read from an xml file
        self.is_concrete = is_concrete is True or is_concrete == "True"

    def set_position(self, x, y):
        self.x = x
        self.y = y


class Polyomino:
    # creates an empty polyomino with optional starting tiles
    def __init__(self, tiles=()):
        self.position = (float("inf"), float("inf"))
        self.tiles = {}
        self.can_reach = True
        for tile in tiles:
            self.add_tile(tile)

    @property
    def size(self):
        return len(self.tiles)

    def get_tiles(self):
        return self.tiles.values()

    def get_state(self):
        return self.position, tuple(self.tiles.items()), self.can_reach

    @staticmethod
    def restore_from_state(state):
        p = Polyomino()
        p.position = state[0]
        for _, tile in state[1]:
            tile.parent = p
        p.tiles = dict(state[1])
        p.can_reach = state[2]
        return p

    def _recompute_relative_positions(self, new_pos):
        tiles = list(self.tiles.values())
        self.tiles = {}
        for tile in tiles:
            self.tiles[(tile.x - new_pos[0], tile.y - new_pos[1])] = tile

    def add_tile(self, tile):
        if (tile.x, tile.y) < self.position:
            self._recompute_relative_positions((tile.x, tile.y))

        self.position = min((tile.x, tile.y), self.position)
        self.tiles[(tile.x - self.position[0], tile.y - self.position[1])] = tile
        tile.parent = self

    def remove_tile_at(self, x, y):
        relative_x, relative_y = x - self.position[0], y - self.position[1]
        self.tiles.pop(relative_x, relative_y)
        if self.size == 0:
            return False
        if (relative_x, relative_y) == (0, 0):
            dx, dy = min(self.tiles.keys())
            new_position = self.position[0] + dx, self.position[1] + dy
            self._recompute_relative_positions(new_position)
            self.position = new_position

    def join(self, other):
        if other.position < self.position:
            raise ValueError("joining polyomino must have greater position value")
        for tile in other.get_tiles():
            self.add_tile(tile)
            tile.parent = self

    # returns offset, relative coordinates
    def get_shape(self):
        return self.position, self.tiles.keys()

    def remove_tile_at(self, x, y):
        relative_x = x - self.position[0]
        relative_y = y - self.position[1]

        self.tiles.pop((relative_x, relative_y))

    def can_join(self, poly, rules):
        if poly is None:
            return False

        for t in self.get_tiles():
            for pt in poly.get_tiles():
                # pt on left, t on right
                if (
                    t.x - pt.x == 1
                    and t.y == pt.y
                    and rules.sticks(t.glues.W, pt.glues.E)
                ):
                    return True
                # t on left, pt on right
                if (
                    pt.x - t.x == 1
                    and t.y == pt.y
                    and rules.sticks(t.glues.E, pt.glues.W)
                ):
                    return True
                # t on top, pt on bottom
                if (
                    t.x == pt.x
                    and t.y - pt.y == -1
                    and rules.sticks(t.glues.S, pt.glues.N)
                ):
                    return True
                # pt on top, t on bottom
                if (
                    t.x == pt.x
                    and pt.y - t.y == -1
                    and rules.sticks(t.glues.N, pt.glues.S)
                ):
                    return True

    def shape_equals(self, other):
        if self.size != other.size:
            return False
        return set(self.tiles.keys()) == set(other.tiles.keys())

    def move(self, dx, dy):
        for tile in self.get_tiles():
            tile.x += dx
            tile.y += dy
        self.position = (self.position[0] + dx, self.position[1] + dy)

    def __str__(self):
        return (
            "Polyomino at "
            + str(self.position)
            + ", with tiles: "
            + str(self.tiles.keys())
        )


class Board:
    def __init__(self, rows, cols, glue_rules=ReflexiveGlueRules()):
        # TODO: remove GUI related code from the Board class
        self.rectangles = []
        self.glueText = []

        self.glue_rules = glue_rules
        # self.glue_rules = GlueRules()
        # self.glue_rules.add_rule(("A", "B"))

        self.rows = rows
        self.cols = cols
        # list of polyominoes
        self.polyominoes = []
        self.concrete = np.zeros(shape=(self.rows, self.cols), dtype=bool)

        # dictionary that will be used to find tiles based on their position on the board
        self._tile_at = {}

    def number_of_tiles(self):
        return len(self._tile_at)

    def get_tiles(self):
        return self._tile_at.values()

    def __hash__(self):
        return hash(tuple(sorted((t.x, t.y, t.glues) for t in self._tile_at.values())))

    # returns true iff (x, y) contains concrete or is out of bounds
    def is_blocked(self, x, y):
        return not (0 <= x < self.cols and 0 <= y < self.rows) or self.concrete[x, y]

    # returns true iff (x, y) contains concrete or a polyomino tile
    def is_occupied(self, x, y):
        return self.get_tile_at(x, y) is not None or self.concrete[x, y]

    def get_tile_at(self, x, y):
        return self._tile_at.get((x, y), None)

    def get_concrete_positions(self):
        return np.argwhere(self.concrete == True)

    def remove_tile_or_concrete_at(self, x, y):
        tile = self.get_tile_at(x, y)
        if tile is None:
            if is_legal_index(self.concrete, (x, y)):
                self.concrete[x, y] = 0
            return
        # remove tile from the polyomino that it is in
        tile.parent.remove_tile_at(x, y)
        # if polyomino becomes empty, remove it
        if tile.parent.size == 0:
            self.polyominoes.remove(tile.parent)
        self._tile_at[x, y] = None

    def copy(self, selection=None):
        # TODO: Make this compatible with the new memory layout
        if selection is None:
            return deepcopy(self._tile_at)
        else:
            return deepcopy(
                self.coord_to_tile[
                    selection[0] : selection[1], selection[2] : selection[3]
                ]
            )

    # returns true if the shape defined by the relative coordinates fits in the position
    # ,without colliding with concrete or walls
    def fits(self, position, relative_coordinates):
        x, y = position
        for dx, dy in relative_coordinates:
            if self.is_blocked(x + dx, y + dy):
                return False
        return True

    # Adds a polyomino the the list
    def add(self, p):
        # add tile to the two dimensional array

        for tile in p.get_tiles():
            if self.is_occupied(tile.x, tile.y):
                return False

        for tile in p.get_tiles():
            self._tile_at[(tile.x, tile.y)] = tile
            self.polyominoes.append(p)
        return True

    def add_concrete(self, x, y):
        if self.is_occupied(x, y):
            return False
        else:
            self.concrete[x, y] = True

    # Joins two polyominos, deletes the 2nd redundant polyomino, calls setGrid() to make the character grid
    # accurately represent the new polyominos.
    def combine_polyominoes(self, p1, p2):
        if p1 is p2:
            return

        if p1.position <= p2.position:
            p1.join(p2)
            if p2 in self.polyominoes:
                self.polyominoes.remove(p2)
            return p1
        else:
            p2.join(p1)
            if p1 in self.polyominoes:
                self.polyominoes.remove(p1)
            return p2

    def resize_board(self, w, h):
        new_concrete = np.zeros((h, w), dtype=bool)
        print(h, w)
        new_concrete[
            0 : min(self.concrete.shape[0], h), 0 : min(self.concrete.shape[1], w)
        ] = self.concrete[
            0 : min(self.concrete.shape[0], h), 0 : min(self.concrete.shape[1], w)
        ]
        self.concrete = new_concrete

        print(self.concrete.shape)
        self.rows = h
        self.cols = w
        self.remap_tile_positions()

    def _glueable(self, tile1: Tile, tile2: Tile):
        direction_vector = (tile2.x - tile1.x, tile2.y - tile1.y)
        direction = Direction.from_vector(direction_vector)
        glue1 = getattr(tile1.glues, direction.value)
        glue2 = getattr(tile2.glues, direction.inverse().value)
        if self.glue_rules.sticks(glue1, glue2):
            return True
        return False

    def _find_connected_component_with_glues(self, polyomino):
        active = deque([polyomino])
        connected_component = {polyomino}
        while active:
            p = active.popleft()
            for tile in p.get_tiles():
                for x, y in direct_neighbors(tile.x, tile.y):
                    neighbor_poly = self.get_polyomino_at(x, y)
                    if (
                        neighbor_poly is not None
                        and neighbor_poly is not p
                        and neighbor_poly not in connected_component
                    ):
                        # neighbor polyomino found, check if tiles can be glued together
                        if self._glueable(tile, self._tile_at[(x, y)]):
                            connected_component.add(neighbor_poly)
                            active.append(neighbor_poly)
        return connected_component

    def activate_glues(self):
        remaining = set(self.polyominoes)
        changed = set()
        while remaining:
            polyomino = remaining.pop()
            cc = self._find_connected_component_with_glues(polyomino)
            remaining.difference_update(cc)
            p = functools.reduce(lambda a, b: self.combine_polyominoes(a, b), cc)
            if len(cc) > 1:
                changed.add(p)
        return changed

    def _legal_index(self, x, y):
        return 0 <= x < self.cols or 0 <= y < self.rows

    def _is_concrete(self, x, y):
        try:
            self.concrete[x, y]
        except:
            pass
        return self.concrete[x, y]

    def get_polyomino_at(self, x, y):
        if (x, y) not in self._tile_at.keys():
            return None
        return self._tile_at[(x, y)].parent

    def adjacent_polyominoes_in_direction(self, p, direction):
        adjacent = set()
        for tile in p.get_tiles():
            x, y = neighbor((tile.x, tile.y), direction)
            neighbor_poly = self.get_polyomino_at(x, y)
            if neighbor_poly is not None and neighbor_poly is not p:
                adjacent.add(neighbor_poly)
        return adjacent

    def adjacent_polyominoes(self, p):
        adjacent = set()
        for tile in p.get_tiles():
            for x, y in direct_neighbors(tile.x, tile.y):
                neighbor_poly = self.get_polyomino_at(x, y)
                if neighbor_poly is not None and neighbor_poly is not p:
                    adjacent.add(neighbor_poly)
        return adjacent

    def _recursively_find_blocked_polyominoes(self, p, direction):
        result = {p}
        active = deque([p])
        while active:
            current = active.popleft()
            for neighbor in self.adjacent_polyominoes_in_direction(
                current, direction.inverse()
            ):
                if neighbor not in result:
                    result.add(neighbor)
                    active.append(neighbor)
        return result

    def polyomino_is_blocked(self, p, direction, is_wall):
        for tile in p.get_tiles():
            x, y = neighbor((tile.x, tile.y), direction)
            if is_wall(self, x, y) or self._is_concrete(x, y):
                return True
        return False

    # moves all polyominoes at once
    def _move_polyominoes(self, polyominoes_list, dx, dy):
        # remove current polyomino coordinates from the mapping
        for p in polyominoes_list:
            for tile in p.get_tiles():
                self._tile_at.pop((tile.x, tile.y))
        # set new positions for tiles
        for p in polyominoes_list:
            p.move(dx, dy)
            for tile in p.get_tiles():
                self._tile_at[(tile.x, tile.y)] = tile

    def step(self, direction):
        direction = Direction(direction)
        free_to_move = set(self.polyominoes)

        # defines the condition for a wall depending on the direction
        is_wall = {
            Direction.N: (lambda board, x, y: y < 0),
            Direction.W: (lambda board, x, y: x < 0),
            Direction.S: (lambda board, x, y: y >= board.rows),
            Direction.E: (lambda board, x, y: x >= board.cols),
        }[direction]

        for p in self.polyominoes:
            if p in free_to_move and self.polyomino_is_blocked(p, direction, is_wall):
                blocked = self._recursively_find_blocked_polyominoes(p, direction)
                free_to_move.difference_update(blocked)

        self._move_polyominoes(free_to_move, *direction.vector())

        return free_to_move

    # Removes all tiles from their current polyomino, then puts them each in their own
    # polyomino, and activates glues
    def relist_polyominoes(self):
        tile_list = []
        self._tile_at = {}
        for p in self.polyominoes:
            for tile in p.get_tiles():
                tile_list.append(tile)
            p.tiles = {}
        self.polyominoes = []
        for tile in tile_list:
            poly = Polyomino()
            poly.add_tile(tile)
            self.add(poly)
        self.remap_tile_positions()
        self.activate_glues()

    def load_polyominoes(self, polyominoes):
        self.polyominoes = polyominoes
        self.remap_tile_positions()

    def load_tiles(self, tiles):
        self._tile_at = {}
        self.polyominoes = []
        for position, t in tiles:
            t.x = position[0]
            t.y = position[1]
            self.add(Polyomino(tiles=[t]))
        self.activate_glues()

    def get_state(self):
        return tuple(self._tile_at.items()), tuple(
            p.get_state() for p in self.polyominoes
        )

    def restore_state(self, state):
        self.polyominoes = [Polyomino.restore_from_state(s) for s in state[1]]
        self._tile_at = dict((k, v) for k, v in state[0])
        for (x, y), tile in state[0]:
            tile.x, tile.y = x, y

    def remap_tile_positions(self):
        self._tile_at = {}
        for p in self.polyominoes:
            for tile in p.get_tiles():
                self._tile_at[(tile.x, tile.y)] = tile

    def tumble(self, direction):
        while self.step(direction):
            pass
        self.activate_glues()

    def tumble_glue(self, direction):
        while self.step(direction):
            self.activate_glues()


class FixedSeedTilesBoard(Board):
    def __init__(self, *args, **kwargs):
        if isinstance(args[0], Board):
            super().__init__(args[0].rows, args[0].cols)
            self.__dict__ = args[0].__dict__
        else:
            super().__init__(*args, **kwargs)
        self.fixed_tiles = set()

    def add_fixed_tile(self, tile: Tile):
        p = Polyomino(tiles=[tile])
        if not self.add(p):
            return False
        self.fixed_tiles.add(tile)
        return True

    def activate_glues(self):
        sticky_polyominoes = {t.parent for t in self.fixed_tiles}
        changed = set()
        while sticky_polyominoes:
            polyomino = sticky_polyominoes.pop()
            cc = self._find_connected_component_with_glues(polyomino)
            sticky_polyominoes.difference_update(cc)
            p = functools.reduce(lambda a, b: self.combine_polyominoes(a, b), cc)
            if len(cc) > 1:
                changed.add(p)
        return changed

    def step(self, direction):
        direction = Direction(direction)

        fixed_polyominoes = {t.parent for t in self.fixed_tiles}
        free_to_move = set(self.polyominoes)
        free_to_move.difference_update(fixed_polyominoes)

        # defines the condition for a wall depending on the direction
        is_wall = {
            Direction.N: (lambda board, x, y: y < 0),
            Direction.W: (lambda board, x, y: x < 0),
            Direction.S: (lambda board, x, y: y >= board.rows),
            Direction.E: (lambda board, x, y: x >= board.cols),
        }[direction]

        for p in self.polyominoes:
            if (
                p in free_to_move and self.polyomino_is_blocked(p, direction, is_wall)
            ) or p in fixed_polyominoes:
                blocked = self._recursively_find_blocked_polyominoes(p, direction)
                free_to_move.difference_update(blocked)

        self._move_polyominoes(free_to_move, *direction.vector())

        return free_to_move

    def remove_tile_or_concrete_at(self, x, y):
        self.fixed_tiles.discard(self.get_tile_at(x, y))
        super().remove_tile_or_concrete_at(x, y)
