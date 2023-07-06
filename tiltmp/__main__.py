import os
import random
from tkinter import *

from tiltmp.gui.tumblegui import tumblegui
import sys


def main():
    random.seed()
    root = Tk()
    root.title("Tumble Tiles")
    sp = os.path.dirname(sys.argv[0])
    imgicon = PhotoImage(file=os.path.join(sp, "../Logo/tumble.gif"))
    root.tk.call("wm", "iconphoto", root._w, imgicon)
    tumblegui(root)
    mainloop()


if __name__ == "__main__":
    main()
