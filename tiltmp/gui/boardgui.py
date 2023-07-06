from tkinter import *
from PIL import Image, ImageDraw


def redrawCanvas(
    board,
    boardwidth,
    boardheight,
    canvas,
    tilesize,
    textcolor="#000000",
    gridcolor="#000000",
    b_drawGrid=False,
    b_drawLoc=False,
):
    canvas.delete(ALL)
    drawGrid(
        board,
        boardwidth,
        boardheight,
        canvas,
        tilesize,
        gridcolor,
        b_drawGrid,
        b_drawLoc,
    )

    if hasattr(board, "fixed_tiles"):

        def draw_tile(t):
            if t in board.fixed_tiles:
                board.rectangles.append(
                    canvas.create_rectangle(
                        tilesize * t.x,
                        tilesize * t.y,
                        tilesize * t.x + tilesize,
                        tilesize * t.y + tilesize,
                        fill=t.color,
                        width=2,
                    )
                )
            else:
                board.rectangles.append(
                    canvas.create_rectangle(
                        tilesize * tile.x,
                        tilesize * tile.y,
                        tilesize * tile.x + tilesize,
                        tilesize * tile.y + tilesize,
                        fill=t.color,
                    )
                )

    else:

        def draw_tile(t):
            board.rectangles.append(
                canvas.create_rectangle(
                    tilesize * tile.x,
                    tilesize * tile.y,
                    tilesize * tile.x + tilesize,
                    tilesize * tile.y + tilesize,
                    fill=t.color,
                )
            )

    for p in board.polyominoes:
        for tile in p.get_tiles():
            draw_tile(tile)
            # DRAW THE GLUES
            if tile.glues == [] or tile.glues == None:
                continue

            if tile.glues[0] != "None":
                # north
                board.glueText.append(
                    canvas.create_text(
                        tilesize * tile.x + tilesize // 2,
                        tilesize * tile.y + tilesize // 5,
                        text=tile.glues[0],
                        fill=textcolor,
                        font=("", tilesize // 4),
                    )
                )
            if tile.glues[1] != "None":
                # east
                board.glueText.append(
                    canvas.create_text(
                        tilesize * tile.x + tilesize - tilesize // 5,
                        tilesize * tile.y + tilesize // 2,
                        text=tile.glues[1],
                        fill=textcolor,
                        font=("", tilesize // 4),
                    )
                )
            if tile.glues[2] != "None":
                # south
                board.glueText.append(
                    canvas.create_text(
                        tilesize * tile.x + tilesize // 2,
                        tilesize * tile.y + tilesize - tilesize // 5,
                        text=tile.glues[2],
                        fill=textcolor,
                        font=("", tilesize // 4),
                    )
                )
            if tile.glues[3] != "None":
                # west
                board.glueText.append(
                    canvas.create_text(
                        tilesize * tile.x + tilesize // 5,
                        tilesize * tile.y + tilesize // 2,
                        text=tile.glues[3],
                        fill=textcolor,
                        font=("", tilesize // 4),
                    )
                )

    for x, y in board.get_concrete_positions():
        canvas.create_rectangle(
            tilesize * x,
            tilesize * y,
            tilesize * x + tilesize,
            tilesize * y + tilesize,
            fill="#686868",
        )


def drawPILImage(
    board,
    boardwidth,
    boardheight,
    canvas,
    tilesize,
    textcolor="#000000",
    gridcolor="#000000",
    b_drawGrid=False,
    b_drawLoc=False,
    tileRes=100,
    lineWidth=10,
):
    tileSize = tileRes

    im = Image.new(
        "RGB", (boardwidth * tileSize, boardheight * tileSize), color="#FFFFFF"
    )
    draw = ImageDraw.Draw(im)

    for p in board.polyominoes:
        for tile in p.tiles:
            color = tile.color

            PILDrawTile(draw, tile.x, tile.y, tileSize, color, lineWidth)

    color = "#686868"

    for x, y in board.get_concrete_positions():
        PILDrawTile(draw, x, y, tileSize, color, lineWidth)

    # im.save("test.png", "PNG")
    return im


def PILDrawTile(imageDraw, x, y, tileSize, color, lineWidth):
    imageDraw.rectangle(
        (
            x * tileSize - lineWidth / 2,
            y * tileSize - lineWidth / 2,
            x * tileSize + tileSize + lineWidth / 2,
            y * tileSize + tileSize + lineWidth / 2,
        ),
        fill=0,
        outline=0,
    )
    imageDraw.rectangle(
        (
            x * tileSize + lineWidth / 2,
            y * tileSize + lineWidth / 2,
            x * tileSize + tileSize - lineWidth / 2,
            y * tileSize + tileSize - lineWidth / 2,
        ),
        fill=color,
        outline=0,
    )


def deleteTumbleTiles(
    board,
    boardwidth,
    boardheight,
    canvas,
    tilesize,
    textcolor="#000000",
    gridcolor="#000000",
    b_drawGrid=False,
    b_drawLoc=False,
):
    i = 0
    while i < len(board.rectangles):
        canvas.delete(board.rectangles[i])
        i = i + 1
    i = 0
    while i < len(board.glueText):
        canvas.delete(board.glueText[i])
        i = i + 1


def redrawTumbleTiles(
    board,
    boardwidth,
    boardheight,
    canvas,
    tilesize,
    textcolor="#000000",
    gridcolor="#000000",
    b_drawGrid=False,
    b_drawLoc=False,
):
    i = 0
    while i < len(board.rectangles):
        canvas.delete(board.rectangles[i])
        i = i + 1
    i = 0
    while i < len(board.glueText):
        canvas.delete(board.glueText[i])
        i = i + 1

    if hasattr(board, "fixed_tiles"):

        def draw_tile(t):
            if t in board.fixed_tiles:
                board.rectangles.append(
                    canvas.create_rectangle(
                        tilesize * t.x,
                        tilesize * t.y,
                        tilesize * t.x + tilesize,
                        tilesize * t.y + tilesize,
                        fill=t.color,
                        width=2,
                    )
                )
            else:
                board.rectangles.append(
                    canvas.create_rectangle(
                        tilesize * tile.x,
                        tilesize * tile.y,
                        tilesize * tile.x + tilesize,
                        tilesize * tile.y + tilesize,
                        fill=t.color,
                    )
                )

    else:

        def draw_tile(t):
            board.rectangles.append(
                canvas.create_rectangle(
                    tilesize * tile.x,
                    tilesize * tile.y,
                    tilesize * tile.x + tilesize,
                    tilesize * tile.y + tilesize,
                    fill=t.color,
                )
            )

    board.rectangles = []
    board.glueText = []
    for p in board.polyominoes:
        for tile in p.get_tiles():
            draw_tile(tile)

            # DRAW THE GLUES
            if tile.glues[0] != "None":
                # north
                board.glueText.append(
                    canvas.create_text(
                        tilesize * tile.x + tilesize // 2,
                        tilesize * tile.y + tilesize // 5,
                        text=tile.glues[0],
                        fill=textcolor,
                        font=("", tilesize // 4),
                    )
                )
            if tile.glues[1] != "None":
                # east
                board.glueText.append(
                    canvas.create_text(
                        tilesize * tile.x + tilesize - tilesize // 5,
                        tilesize * tile.y + tilesize // 2,
                        text=tile.glues[1],
                        fill=textcolor,
                        font=("", tilesize // 4),
                    )
                )
            if tile.glues[2] != "None":
                # south
                board.glueText.append(
                    canvas.create_text(
                        tilesize * tile.x + tilesize // 2,
                        tilesize * tile.y + tilesize - tilesize // 5,
                        text=tile.glues[2],
                        fill=textcolor,
                        font=("", tilesize // 4),
                    )
                )
            if tile.glues[3] != "None":
                # west
                board.glueText.append(
                    canvas.create_text(
                        tilesize * tile.x + tilesize // 5,
                        tilesize * tile.y + tilesize // 2,
                        text=tile.glues[3],
                        fill=textcolor,
                        font=("", tilesize // 4),
                    )
                )

    # for c in board.ConcreteTiles:
    #     canvas.create_rectangle(tilesize*c.x, tilesize*c.y, tilesize*c.x + tilesize, tilesize*c.y + tilesize, fill = "#686868")


def drawGrid(
    board,
    boardwidth,
    boardheight,
    canvas,
    tilesize,
    gridcolor="#000000",
    b_drawGrid=False,
    b_drawLoc=False,
):
    if b_drawGrid == True:
        for row in range(board.rows):
            canvas.create_line(
                0,
                row * tilesize,
                boardwidth * tilesize,
                row * tilesize,
                fill=gridcolor,
                width=0.50,
            )
        for col in range(board.cols):
            canvas.create_line(
                col * tilesize,
                0,
                col * tilesize,
                boardheight * tilesize,
                fill=gridcolor,
                width=0.50,
            )

    if b_drawLoc == True:
        for row in range(boardheight):
            for col in range(boardwidth):
                canvas.create_text(
                    tilesize * (col + 1) - tilesize // 2,
                    tilesize * (row + 1) - tilesize // 2,
                    text="(" + str(col) + "," + str(row) + ")",
                    fill=gridcolor,
                    font=("", tilesize // 4),
                )
