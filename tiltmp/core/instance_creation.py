import itertools
import os
import random
from copy import copy

import tiltmp.core.gridcreation as gridcreation
from tiltmp.core.algorithms import reachable_set
from tiltmp.core.serialization import write_instance
from tiltmp.core.tumbletiles import *
from tiltmp.mp.motionplanner import Instance


def random_instance(
    random_board_function,
    board_dimensions,
    target_shape_size,
    leftover_tiles=0,
    glue_number=1,
    fixed_seed_tile=False,
):
    while True:
        try:
            board = random_board_function(board_dimensions)
            target_shape = random_shape(target_shape_size)
            if find_target_shape_position(board, target_shape):
                break
        except Exception as e:
            print(e)

    tiles, rules = create_random_glues(target_shape, glue_number, leftover_tiles)

    if fixed_seed_tile:
        board = FixedSeedTilesBoard(board)
        fixed_seed_tile = random.choice(list(target_shape.get_tiles()))
        for tile in tiles:
            if (
                tile.glues == fixed_seed_tile.glues
                and tile.x == fixed_seed_tile.x
                and tile.y == fixed_seed_tile.y
            ):
                board.add_fixed_tile(tile)
                tiles.remove(tile)
                break

    board.glue_rules = rules
    place_tiles_randomly(board, tiles)
    return Instance(board, target_shape)


def place_tiles_randomly(board, tiles):
    while tiles:
        t = tiles[-1]
        x = np.random.randint(0, board.cols)
        y = np.random.randint(0, board.rows)
        # tile can not be a direct neighbor of another tile
        if board.is_occupied(x, y) or any(
            board.get_tile_at(nx, ny) for nx, ny in direct_neighbors(x, y)
        ):
            continue
        t.x, t.y = x, y
        p = Polyomino(tiles=[t])
        board.add(p)
        tiles.pop()


def find_target_shape_position(board, target_shape, max_attempts=100):
    for _ in range(max_attempts):
        x = np.random.randint(0, board.cols)
        y = np.random.randint(0, board.rows)
        target_shape.position = (x, y)
        for (dx, dy), tile in target_shape.tiles.items():
            tile.x = x + dx
            tile.y = y + dy
        if is_valid_target_shape_position(board, target_shape):
            return True
    return False


def is_valid_target_shape_position(board, target_shape):
    if (
        board.fits(*target_shape.get_shape())
        and len(reachable_set(board, target_shape)) > 1
    ):
        return True
    else:
        return False


def random_shape(size):
    if size <= 0:
        return None
    shape = Polyomino(tiles=[Tile(position=(0, 0))])
    tile_positions = {(0, 0)}
    while shape.size != size:
        t = random.choice(list(shape.get_tiles()))
        direction = random.choice(list(Direction))
        new_tile_position = neighbor((t.x, t.y), direction)
        if new_tile_position not in tile_positions:
            shape.add_tile(Tile(position=new_tile_position))
            tile_positions.add(new_tile_position)
    return shape


def get_shared_edge_glues(tile1, tile2):
    direction_vector = (tile2.x - tile1.x, tile2.y - tile1.y)
    direction = Direction.from_vector(direction_vector)
    glue1 = getattr(tile1.glues, direction.value)
    glue2 = getattr(tile2.glues, direction.inverse().value)
    return glue1, glue2


def create_valid_glue_rules(shape):
    rules = GlueRules()

    positions = {(t.x, t.y): t for t in shape.get_tiles()}
    first_tile = next(iter(shape.get_tiles()))
    came_from = {(first_tile.x, first_tile.y): None}
    selected_edges = []
    queue = list(came_from.keys())
    while queue:
        random.shuffle(queue)
        current = queue.pop()
        if came_from[current] != None:
            selected_edges += [(current, came_from[current])]
        for neighbor in direct_neighbors(*current):
            if neighbor in positions and neighbor not in came_from:
                came_from[neighbor] = current
                queue.append(neighbor)

    for p1, p2 in selected_edges:
        g1, g2 = get_shared_edge_glues(positions[p1], positions[p2])
        rules.add_rule((g1, g2))

    return rules


def create_random_glues(shape, number_glue_types, additional_tiles):
    glues = [chr(65 + n) for n in range(number_glue_types)]

    def rand_glues():
        return Glues(
            random.choice(glues),
            random.choice(glues),
            random.choice(glues),
            random.choice(glues),
        )

    for tile in shape.get_tiles():
        tile.glues = rand_glues()

    all_tiles = [copy(t) for t in shape.get_tiles()]

    for _ in range(additional_tiles):
        all_tiles.append(Tile(glues=rand_glues()))

    rules = create_valid_glue_rules(shape)

    candidates = list(itertools.combinations(glues, r=2))
    needed = int(len(candidates) / 2)

    while len(rules.get_unique_rules()) < needed:
        rules.add_rule(random.choice(candidates))

    return all_tiles, rules


if __name__ == "__main__":
    BOARD_TYPE = ["maze", "cave"]
    TILES = [5, 10, 13, 15]
    SIZE = [40, 80, 120]
    LEFTOVER = [0, 3, 5]
    GLUES = [1, 3, 5]
    PROBLEM = ["fixed", "notfixed"]

    dir = "instances"

    def get_name(instance_type, i):
        name = ""
        for x in instance_type:
            name += str(x) + "_"
        name += str(i) + ".json"
        return name

    files = next(os.walk(dir), (None, None, []))[2]

    for instance_type in itertools.product(
        BOARD_TYPE, TILES, SIZE, LEFTOVER, GLUES, PROBLEM
    ):
        board_type, tiles, size, leftover, glues, fixed = instance_type
        f = (
            gridcreation.random_maze_board
            if board_type == "maze"
            else gridcreation.random_cave_board
        )
        fixed_bool = fixed == "fixed"
        for i in range(1, 6):
            if get_name(instance_type, i) in files:
                continue

            path = os.path.join(dir, get_name(instance_type, i))
            if os.path.isfile(path):
                continue
            print(get_name(instance_type, i))
            instance = random_instance(
                f, (size, size), tiles, leftover, glues, fixed_bool
            )
            write_instance(path, instance)
