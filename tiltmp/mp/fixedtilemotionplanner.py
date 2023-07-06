from collections import deque
from copy import copy

from tiltmp.core.tumbletiles import FixedSeedTilesBoard, Direction, Polyomino
import itertools


def combinations(l):
    for length in range(len(l), -1, -1):
        for c in itertools.combinations(l, length):
            yield set(c)


class StackFrame:
    def __init__(self, not_moved, board_state, decided_fixed):
        self.not_moved = not_moved
        self.decided_fixed = decided_fixed
        self.board_state = board_state


class OriginalBoardGenerator:
    def __init__(self, board: FixedSeedTilesBoard):
        self.board = board
        if len(board.fixed_tiles) != 1:
            raise ValueError("Can only handle boards with exactly one fixed tile")
        self.fixed_poly = next(iter(board.fixed_tiles)).parent
        self.original_state = board.get_state()
        self.all_tiles = set(board.get_tiles())

    def iterate_original_board_positions(self):
        for d in Direction:
            for _ in self.reverse_step_direction(d):
                yield

        # iterators = [self.reverse_step_direction(direction) for direction in Direction]
        # while iterators:
        #    for i in reversed(range(len(iterators))):
        #        result = next(iterators[i], None)
        #        if result is True:
        #            yield
        #        elif result is None:
        #            del iterators[i]

    def reverse_step_direction(self, direction):
        stack = deque()
        stack.append(
            StackFrame(
                set(self.board.get_tiles()), self.original_state, self.board.fixed_tiles
            )
        )

        while stack:
            stack_frame = stack.pop()
            rdx, rdy = direction.inverse().vector()

            self.board.restore_state(stack_frame.board_state)
            self.fixed_poly = next(iter(self.board.fixed_tiles)).parent

            must, can = self.must_can_move(stack_frame, direction)
            not_moved = stack_frame.not_moved

            if not must and len(not_moved) != len(self.board.get_tiles()):
                yield True

            if stack_frame.decided_fixed.intersection(must):
                # tile that has been decided to be fixed must move in order to achieve the configuration
                continue

            for tile in must:
                if self.board.is_blocked(tile.x + rdx, tile.y + rdy):
                    # position can not arise from a step in this direction
                    return

            for c in combinations(can):
                self.board.restore_state(stack_frame.board_state)

                moving = must.union(c)
                if not moving:
                    continue
                new_positions = [(tile.x + rdx, tile.y + rdy) for tile in moving]
                for x, y in new_positions:
                    neighbor = self.board.get_tile_at(x, y)
                    if neighbor and neighbor not in moving:
                        continue

                # put all tiles back into their own polyomino (this may inefficient)
                self.board.polyominoes = [
                    Polyomino(tiles=[tile]) for tile in self.all_tiles
                ]

                self.board._move_polyominoes([tile.parent for tile in moving], rdx, rdy)

                self.board.activate_glues()
                self.fixed_poly = next(iter(self.board.fixed_tiles)).parent

                # check for tiles that should move, but that are glued to a fixed polyomino
                if any(tile in moving for tile in self.fixed_poly.get_tiles()):
                    pass
                else:
                    new_not_moved = (not_moved - must) - c
                    decided_fixed = stack_frame.decided_fixed.union(can)
                    stack.append(
                        StackFrame(new_not_moved, self.board.get_state(), decided_fixed)
                    )

    # partitions tiles into tiles that can potentially move, tiles that must move and tiles for which it has not been decided yet.
    def must_can_move(self, stack_frame: StackFrame, direction):
        board = self.board
        dx, dy = direction.vector()
        rdx, rdy = direction.inverse().vector()

        must_move = copy(stack_frame.not_moved)
        must_move.difference_update(tile for tile in self.fixed_poly.get_tiles())
        can_move = set()

        for tile in stack_frame.not_moved:
            if tile.parent == self.fixed_poly:
                continue
            if not board.is_blocked(tile.x + dx, tile.y + dy):
                neighbor = board.get_tile_at(tile.x + dx, tile.y + dy)
                if not neighbor or not neighbor.parent == self.fixed_poly:
                    continue
            must_move.discard(tile)
            temp = tile
            neighbor = board.get_tile_at(tile.x + rdx, tile.y + rdy)
            while neighbor and neighbor.parent != self.fixed_poly:
                must_move.discard(neighbor)
                temp = neighbor
                neighbor = board.get_tile_at(neighbor.x + rdx, neighbor.y + rdy)
            if temp not in stack_frame.decided_fixed and not board.is_blocked(
                temp.x + rdx, temp.y + rdy
            ):
                can_move.add(temp)

        for tile in stack_frame.not_moved.intersection(self.fixed_poly.get_tiles()):
            neighbor = board.get_tile_at(tile.x + rdx, tile.y + rdy)
            if neighbor and neighbor.parent is self.fixed_poly:
                continue
            if tile in board.fixed_tiles:
                continue
            if tile not in stack_frame.decided_fixed and not board.is_blocked(
                tile.x + rdx, tile.y + rdy
            ):
                can_move.add(tile)

        return must_move, can_move
