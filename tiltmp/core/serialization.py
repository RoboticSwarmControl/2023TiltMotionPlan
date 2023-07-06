import json

from tiltmp.mp.motionplanner import Instance
from tiltmp.core.tumbletiles import *
from copy import copy
import numpy as np


class TileEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Tile):
            return self.encode_tile(obj)
        return json.JSONEncoder.default(self, obj)

    @staticmethod
    def encode_tile(tile):
        data = copy(tile.__dict__)
        data.pop("parent")
        return data


def decode_tile(data):
    return Tile(
        position=(data["x"], data["y"]),
        glues=Glues(*data["glues"]),
        color=data["color"],
    )


class PolyominoEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Polyomino):
            return self.encode_polyomino(obj)
        return json.JSONEncoder.default(self, obj)

    @staticmethod
    def encode_polyomino(p):
        return {"tiles": [TileEncoder.encode_tile(t) for t in p.tiles.values()]}


def decode_polyomino(data):
    return Polyomino(tiles=[decode_tile(tile) for tile in data["tiles"]])


class GlueRulesEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, GlueRules):
            return self.encode_rules(obj)
        return json.JSONEncoder.default(self, obj)

    @staticmethod
    def encode_rules(glue_rules):
        return {
            "rules": list(list(rule) for rule in glue_rules.rules),
            "class": type(glue_rules).__name__,
        }


def decode_glue_rules(data):
    if "class" not in data.keys():
        return data
    if data["class"] == ReflexiveGlueRules.__name__:
        rules = ReflexiveGlueRules()
    elif data["class"] == GlueRules.__name__:
        rules = GlueRules()
    else:
        raise ValueError("Unknown GlueRules subclass")
    rules.add_rules(data["rules"])
    return rules


class BoardEncoder(json.JSONEncoder):
    # IDs of polyominoes are not preserved by the serialization method
    def default(self, obj):
        if isinstance(obj, Board):
            return self.encode_board(obj)
        return json.JSONEncoder.default(self, obj)

    @staticmethod
    def encode_board(board):
        data = {
            "width": board.cols,
            "height": board.rows,
            "concrete": board.concrete.tolist(),
            "tiles": [],
            "glueRules": GlueRulesEncoder.encode_rules(board.glue_rules),
        }

        if hasattr(board, "fixed_tiles"):
            data["fixed_tiles"] = [(t.x, t.y) for t in board.fixed_tiles]

        for p in board.polyominoes:
            data["tiles"].extend([TileEncoder.encode_tile(t) for t in p.tiles.values()])
        return data


def decode_board(data):
    board_class = FixedSeedTilesBoard if "fixed_tiles" in data.keys() else Board

    if "height" not in data.keys():
        return data
    board = board_class(
        data["height"], data["width"], glue_rules=decode_glue_rules(data["glueRules"])
    )
    board.concrete = np.array(data["concrete"])
    for tile_data in data["tiles"]:
        board.add(Polyomino(tiles=[decode_tile(tile_data)]))

    if board_class is FixedSeedTilesBoard:
        fixed_tile_positions = {(x, y) for x, y in data["fixed_tiles"]}
        board.fixed_tiles = {
            t for t in board.get_tiles() if (t.x, t.y) in fixed_tile_positions
        }

    board.activate_glues()
    return board


class InstanceEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Instance):
            return self.encode_instance(obj)
        return json.JSONEncoder.default(self, obj)

    @staticmethod
    def encode_instance(instance):
        data = {
            "board": BoardEncoder.encode_board(instance.initial_state),
            "target_shape": PolyominoEncoder.encode_polyomino(instance.target_shape),
        }
        return data


def decode_instance(data):
    if "board" not in data.keys():
        return data
    instance = Instance(
        decode_board(data["board"]), decode_polyomino(data["target_shape"])
    )
    return instance


def write_instance(file, instance):
    with open(file, "w") as f:
        data = InstanceEncoder.encode_instance(instance)
        json.dump(data, f, indent=4)


def read_instance(file):
    with open(file) as f:
        try:
            data = json.load(f)
        except UnicodeDecodeError as e:
            print(file)
            raise e

    instance = decode_instance(data)
    return instance


if __name__ == "__main__":
    b = Board(20, 20)
    b.add_concrete(0, 0)
    b.add(Polyomino(tiles=[Tile(position=(1, 2))]))
    b.add(Polyomino(tiles=[Tile(position=(1, 3))]))
    b.step("N")
    b.activate_glues()
    print([str(p) for p in b.polyominoes])
    json_data = json.dumps(b, cls=BoardEncoder, indent=2)
    b = json.loads(json_data, object_hook=decode_board)
    print([str(p) for p in b.polyominoes])
