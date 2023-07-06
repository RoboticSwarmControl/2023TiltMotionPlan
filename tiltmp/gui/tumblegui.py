# GUI for Tumble Tiles Motion Planner
# Tim Wylie
# 2018


import copy
import threading
import tkinter
import tkinter.simpledialog
from tkinter.filedialog import asksaveasfilename
import traceback

from tkinter import *
import tkinter.ttk
import tkinter.filedialog
import tkinter.messagebox
import tkinter.colorchooser
import tkinter.messagebox
import xml.etree.ElementTree as ET
import random
import time
from tkinter import scrolledtext
from tkinter.font import Font

import tiltmp.core.tumbletiles as TT
import tiltmp.gui.tumbleEdit as TE
from tiltmp.core.instance_creation import random_instance
from tiltmp.mp.fixedtilemotionplanner import OriginalBoardGenerator
from tiltmp.mp.heuristic import *

from tiltmp.mp.motionplanner import (
    Instance,
    get_motion_planner,
    OneTileAtATimeMotionPlanner,
    MotionPlanner,
    get_anchoring_motion_planner,
    BFSMotionPlanner,
)
from tiltmp.gui.getFile import getFile, parseFile
from tiltmp.gui.boardgui import redrawCanvas, drawGrid, redrawTumbleTiles, drawPILImage
import os
import sys

# https://pypi.python.org/pypi/pyscreenshot
from tiltmp.core.serialization import read_instance
from tiltmp.mp.rrtmotionplanner import RRTSolver

try:
    PYSCREEN = False
    # imp.find_module('pyscreenshot')
    import pyscreenshot as ImageGrab

    PYSCREEN = True
except ImportError:
    PYSCREEN = False
try:
    IMAGEIO = False
    import imageio as io

    IMAGEIO = True
except ImportError:
    IMAGEIO = False

try:
    PILLOW = False
    import imageio as io

    PILLOW = True
except ImportError:
    PILLOW = False

NEWTILEWINDOW_W = 400

NEWTILEWINDOW_H = 180

LOGFILE = None
LOGFILENAME = "logfile"
TILESIZE = 20
VERSION = "1.0"
LASTLOADEDFILE = ""
LASTLOADEDSCRIPT = ""
RECORDING = False
SCRIPTSEQUENCE = ""

# https://stackoverflow.com/questions/19861689/check-if-modifier-key-is-pressed-in-tkinter
MODS = {
    0x0001: "Shift",
    0x0002: "Caps Lock",
    0x0004: "Control",
    0x0008: "Left-hand Alt",
    0x0010: "Num Lock",
    0x0080: "Right-hand Alt",
    0x0100: "Mouse button 1",
    0x0200: "Mouse button 2",
    0x0400: "Mouse button 3",
}


class SaveSVGDialog(tkinter.Toplevel):
    def __init__(self, parent):
        super().__init__(parent.mainframe)
        self.parent = parent
        self.title("Save SVG")

        self.scale_container = tkinter.Frame(self)
        self.scale_label = tkinter.Label(
            self.scale_container,
            text="SVG scale",
        )
        self.scale_label.pack(side=tkinter.LEFT)
        self.scale_var = IntVar()
        self.scale_var.set(1)
        self.scale = tkinter.Entry(
            self.scale_container, textvariable=self.scale_var, width=5
        )
        self.scale.pack(side=tkinter.RIGHT)
        self.scale_container.pack(padx=5, pady=5)

        self.select_file_container = tkinter.Frame(self)
        self.filename_var = StringVar()
        self.filename_box = tkinter.Entry(
            self.select_file_container,
            state=tkinter.DISABLED,
            textvariable=self.filename_var,
            width=30,
        )
        self.filename_box.pack(side=tkinter.LEFT, padx=5)
        self.select_file_button = tkinter.Button(
            self.select_file_container,
            text="Select",
            command=lambda: self.select_save_file(),
        )
        self.select_file_button.pack(side=tkinter.RIGHT)
        self.select_file_container.pack(padx=5, pady=5)

        self.checkbox_container = tkinter.Frame(self)
        self.border_checkvar = IntVar()
        self.gridlines_checkvar = IntVar()
        self.border_checkbox = tkinter.Checkbutton(
            self.checkbox_container,
            text="Border",
            variable=self.border_checkvar,
            onvalue=1,
            offvalue=0,
        )
        self.border_checkbox.pack(side=tkinter.LEFT)
        self.gridlines_checkbox = tkinter.Checkbutton(
            self.checkbox_container,
            text="Gridlines",
            variable=self.gridlines_checkvar,
            onvalue=1,
            offvalue=0,
        )
        self.gridlines_checkbox.pack(side=tkinter.LEFT)
        self.checkbox_container.pack(padx=5, pady=5)

        self.save_button = Button(
            self.checkbox_container, text="Save", command=lambda: self.save(), width=12
        )
        self.save_button.pack(side=tkinter.RIGHT)

    def save(self):
        try:
            scale = self.scale_var.get()
        except:
            tkinter.messagebox.showerror(
                "Error", "Scale needs to be an integer", parent=self
            )
            return
        try:
            self.parent.board2SVG(
                self.parent.board,
                filename=self.filename_var.get(),
                gridlines=self.gridlines_checkvar.get(),
                border=self.border_checkvar.get(),
                scale=scale,
            )
        except Exception as e:
            tkinter.messagebox.showerror("Something went wrong:", str(e), parent=self)
            return
        self.destroy()

    def select_save_file(self):
        f = asksaveasfilename(parent=self, defaultextension=".svg")
        if not f:
            return
        self.filename_var.set(f)
        self.filename_box.xview_moveto(1)
        self.lift(aboveThis=self.parent.root)


class SequenceToSVGDialog(tkinter.Toplevel):
    def __init__(self, parent):
        super().__init__(parent.mainframe)
        self.parent = parent
        self.title("Sequence to SVGs")

        self.scale_and_prefix_container = tkinter.Frame(self)
        self.scale_label = tkinter.Label(
            self.scale_and_prefix_container, text="SVG scale"
        )
        self.scale_label.pack(side=tkinter.LEFT)
        self.scale_var = IntVar()
        self.scale_var.set(1)
        self.scale = tkinter.Entry(
            self.scale_and_prefix_container, textvariable=self.scale_var, width=5
        )
        self.scale.pack(side=tkinter.LEFT, padx=(0, 20))
        self.prefix_label = tkinter.Label(
            self.scale_and_prefix_container, text="Prefix"
        )
        self.prefix_label.pack(side=tkinter.LEFT)
        self.prefix_var = StringVar()
        self.prefix_var.set("img")
        self.prefix = tkinter.Entry(
            self.scale_and_prefix_container, textvariable=self.prefix_var
        )
        self.prefix.pack(side=tkinter.LEFT)
        self.scale_and_prefix_container.pack(padx=5, pady=5)

        self.sequence_container = tkinter.Frame(self)
        self.sequence_label = tkinter.Label(self.sequence_container, text="Sequence")
        self.sequence_label.pack(side=tkinter.LEFT)
        self.sequence_var = StringVar()
        self.sequence = tkinter.Entry(
            self.sequence_container, textvariable=self.sequence_var, width=30
        )
        self.sequence.pack(side=tkinter.RIGHT)
        self.sequence_container.pack(padx=5, pady=5)

        self.select_directory_container = tkinter.Frame(self)
        self.directory_var = StringVar()
        self.directory_box = tkinter.Entry(
            self.select_directory_container,
            state=tkinter.DISABLED,
            textvariable=self.directory_var,
            width=30,
        )
        self.directory_box.pack(side=tkinter.LEFT, padx=5)
        self.select_file_button = tkinter.Button(
            self.select_directory_container,
            text="Select Directory",
            command=lambda: self.select_directory(),
        )
        self.select_file_button.pack(side=tkinter.RIGHT)
        self.select_directory_container.pack(padx=5, pady=5)

        self.checkbox_container = tkinter.Frame(self)
        self.border_checkvar = IntVar()
        self.gridlines_checkvar = IntVar()
        self.border_checkbox = tkinter.Checkbutton(
            self.checkbox_container,
            text="Border",
            variable=self.border_checkvar,
            onvalue=1,
            offvalue=0,
        )
        self.border_checkbox.pack(side=tkinter.LEFT)
        self.gridlines_checkbox = tkinter.Checkbutton(
            self.checkbox_container,
            text="Gridlines",
            variable=self.gridlines_checkvar,
            onvalue=1,
            offvalue=0,
        )
        self.gridlines_checkbox.pack(side=tkinter.LEFT)
        self.checkbox_container.pack(padx=5, pady=5)

        self.save_button = Button(
            self.checkbox_container, text="Save", command=lambda: self.save(), width=12
        )
        self.save_button.pack(side=tkinter.RIGHT)

    def save(self):
        try:
            sequence = self.parent.parse_sequence(self.sequence_var.get())
        except ValueError:
            tkinter.messagebox.showerror(
                "Error", "Sequence can only contain the characters NESW", parent=self
            )
            return
        try:
            scale = self.scale_var.get()
        except:
            tkinter.messagebox.showerror(
                "Error", "Scale needs to be an integer", parent=self
            )
            return
        try:
            self.parent.sequence_to_svgs(
                sequence,
                self.directory_var.get(),
                gridlines=self.gridlines_checkvar.get(),
                border=self.border_checkvar.get(),
                prefix=self.prefix_var.get(),
                scale=scale,
            )
        except Exception as e:
            tkinter.messagebox.showerror("Something went wrong", str(e), parent=self)
            return
        self.destroy()

    def select_directory(self):
        f = tkinter.filedialog.askdirectory(parent=self)
        if not f:
            return
        self.directory_var.set(f)
        self.directory_box.xview_moveto(1)
        self.lift(aboveThis=self.parent.root)


class MsgAbout:
    def __init__(self, parent):
        global VERSION
        self.parent = parent
        self.t = Toplevel(self.parent)
        self.t.resizable(False, False)
        self.t.wm_title("About")
        # self.t.geometry('200x200') #WxH

        self.photo = PhotoImage(file="../Logo/tumble.gif")

        # Return a new PhotoImage based on the same image as this widget but
        # use only every Xth or Yth pixel.
        self.display = self.photo.subsample(3, 3)
        self.label = Label(self.t, image=self.display, width=90, height=80)
        self.label.image = self.display  # keep a reference!
        self.label.pack()

        self.l1 = Label(
            self.t, text="TILT Motion Planner v" + VERSION, font=("", 15)
        ).pack()

        Label(self.t, text="Patrick Blumenberg").pack()
        Label(
            self.t,
            text="Developed for my bachelors thesis.\nBased on the Tumble Tiles software:",
        ).pack()

        def link_callback(url):
            import webbrowser

            webbrowser.open_new(url)

        link1 = Label(
            self.t,
            text="https://github.com/asarg/TumbleTiles",
            fg="blue",
            cursor="hand2",
        )
        link1.pack()
        link1.bind(
            "<Button-1>",
            lambda e: link_callback("https://github.com/asarg/TumbleTiles"),
        )

        Label(self.t, text="For support contact p.blumenberg@tu-bs.de").pack()

        Button(self.t, text="OK", width=10, command=self.t.destroy).pack()

        self.t.focus_set()
        # Make sure events only go to our dialog
        self.t.grab_set()
        # Make sure dialog stays on top of its parent window (if needed)
        self.t.transient(self.parent)
        # Display the window and wait for it to close
        self.t.wait_window(self.t)


class Settings:
    def __init__(self, parent, logging, tumblegui):  # , fun):
        global TILESIZE

        self.tumbleGUI = tumblegui
        self.logging = logging
        # self.function = fun
        self.parent = parent
        self.t = Toplevel(self.parent)
        self.t.resizable(False, False)
        # self.wm_attributes("-disabled", True)
        self.t.wm_title("Board Options")
        # self.toplevel_dialog.transient(self)
        self.t.geometry("180x180")  # wxh

        self.tkTILESIZE = StringVar()
        self.tkTILESIZE.set(str(TILESIZE))
        self.tkBOARDWIDTH = StringVar()
        self.tkBOARDWIDTH.set(str(TT.BOARDWIDTH))
        self.tkBOARDHEIGHT = StringVar()
        self.tkBOARDHEIGHT.set(str(TT.BOARDHEIGHT))
        self.tkTEMP = StringVar()
        self.tkTEMP.set(str(TT.TEMP))

        # tilesize
        self.l1 = Label(self.t, text="Tile Size").grid(
            row=0, column=0, sticky=W, padx=5, pady=5
        )
        self.tilesize_sbx = Spinbox(
            self.t, from_=10, to=100, width=5, increment=5, textvariable=self.tkTILESIZE
        ).grid(row=0, column=1, padx=5, pady=5)
        # board width
        self.l2 = Label(self.t, text="Board Width").grid(
            row=1, column=0, padx=5, pady=5, sticky=W
        )
        self.boardwidth_sbx = Spinbox(
            self.t, from_=10, to=500, width=5, textvariable=self.tkBOARDWIDTH
        ).grid(row=1, column=1, padx=5, pady=5)
        # board height
        self.l3 = Label(self.t, text="Board Height").grid(
            row=2, column=0, padx=5, pady=5, sticky=W
        )
        self.boardheight_sbx = Spinbox(
            self.t, from_=10, to=500, width=5, textvariable=self.tkBOARDHEIGHT
        ).grid(row=2, column=1, padx=5, pady=5)
        # temperature
        self.l4 = Label(self.t, text="Temperature").grid(
            row=3, column=0, padx=5, pady=5, sticky=W
        )
        self.temperature_sbx = Spinbox(
            self.t, from_=1, to=10, width=5, textvariable=self.tkTEMP
        ).grid(row=3, column=1, padx=5, pady=5)
        # buttons
        Button(self.t, text="Cancel", command=self.t.destroy).grid(
            row=4, column=0, padx=5, pady=5
        )
        Button(self.t, text="Apply", command=self.Apply).grid(
            row=4, column=1, padx=5, pady=5
        )

        self.t.focus_set()
        # Make sure events only go to our dialog
        self.t.grab_set()
        # Make sure dialog stays on top of its parent window (if needed)
        self.t.transient(self.parent)
        # Display the window and wait for it to close
        self.t.wait_window(self.t)

    def Apply(self):
        global TILESIZE

        TILESIZE = int(self.tkTILESIZE.get())
        TE.TILESIZE = TILESIZE
        if TT.BOARDWIDTH != int(self.tkBOARDWIDTH.get()):
            self.Log(
                "\nChange BOARDWIDTH from "
                + str(TT.BOARDWIDTH)
                + " to "
                + self.tkBOARDWIDTH.get()
            )
            TT.BOARDWIDTH = int(self.tkBOARDWIDTH.get())
        if TT.BOARDHEIGHT != int(self.tkBOARDHEIGHT.get()):
            self.Log(
                "\nChange BOARDHEIGHT from "
                + str(TT.BOARDHEIGHT)
                + " to "
                + self.tkBOARDHEIGHT.get()
            )
            TT.BOARDHEIGHT = int(self.tkBOARDHEIGHT.get())
        if TT.TEMP != int(self.tkTEMP.get()):
            self.Log("\nChange TEMP from " + str(TT.TEMP) + " to " + self.tkTEMP.get())
            TT.TEMP = int(self.tkTEMP.get())

        self.tumbleGUI.callCanvasRedraw()
        self.t.destroy()

    def Log(self, stlog):
        global LOGFILE
        global LOGFILENAME

        if self.logging:
            LOGFILE = open(LOGFILENAME, "a")
            LOGFILE.write(stlog)
            LOGFILE.close()


class VideoExport:
    def __init__(self, parent, tumblegui):  # , fun):
        global TILESIZE

        self.tumbleGUI = tumblegui
        # self.function = fun
        self.parent = parent

        self.parent = parent
        self.t = Toplevel(self.parent)
        self.t.resizable(False, False)
        # self.wm_attributes("-disabled", True)
        self.t.wm_title("Video Export")
        # self.toplevel_dialog.transient(self)
        self.t.geometry("360x250")

        self.tileRes = StringVar()  # Variable for Tile Resolution
        self.fileName = StringVar()  # Variable for the script file name
        self.videoSpeed = StringVar()  # Variale for the frame rate
        self.lineWidth = StringVar()  # Variable for the width of tile border
        self.exportFileNameText = StringVar()  # Variabe for name of the output file
        self.exportText = (
            StringVar()
        )  # Variable for the text that logs the video output

        # Set default amounts

        self.tileRes.set("100")
        self.videoSpeed.set("3")
        self.lineWidth.set("10")

        # Initiate all Label objects

        self.tileResLabel = Label(self.t, text="Tile Resolution: ")
        self.fileNameLabel = Label(self.t, text="Script File Name: ")
        self.videoSpeedLabel = Label(self.t, text="Frames/Sec: ")
        self.lineWidthLabel = Label(self.t, text="Line Width: ")
        self.exportLabel = Label(self.t, text="", textvariable=self.exportText)
        self.exportFileNameLabel = Label(self.t, text="Output File Name:")

        # Initiate all text field objects

        self.tileResField = Entry(self.t, textvariable=self.tileRes, width=5)
        self.fileNameField = Entry(self.t, textvariable=self.fileName)
        self.videoSpeedField = Entry(self.t, textvariable=self.videoSpeed, width=5)
        self.lineWidthField = Entry(self.t, textvariable=self.lineWidth, width=5)
        self.exportFileNameField = Entry(
            self.t, textvariable=self.exportFileNameText, width=5
        )

        # Horizontal starting points for the labels and the fields

        labelStartX = 60
        fieldStartX = 180

        # Place all the components using x and y coordinates

        self.tileResLabel.place(x=labelStartX, y=20)
        self.tileResField.place(x=fieldStartX, y=20)

        self.lineWidthLabel.place(x=labelStartX, y=40)
        self.lineWidthField.place(x=fieldStartX, y=40)

        self.fileNameLabel.place(x=labelStartX, y=80)
        self.fileNameField.place(x=fieldStartX, y=80, width=130)

        self.exportFileNameLabel.place(x=labelStartX, y=130)
        self.exportFileNameField.place(x=fieldStartX, y=130, width=130)

        self.videoSpeedLabel.place(x=labelStartX, y=60)
        self.videoSpeedField.place(x=fieldStartX, y=60)

        browseButton = Button(self.t, text="Browse", command=self.openFileWindow)
        browseButton.place(x=fieldStartX, y=100, height=20)

        self.exportLabel.place(x=labelStartX, y=155)
        # Create a progres bar to show status of video export

        self.progress_var = DoubleVar()
        self.progress = tkinter.ttk.Progressbar(
            self.t,
            orient=HORIZONTAL,
            variable=self.progress_var,
            length=260,
            mode="determinate",
        )
        self.progress.place(x=50, y=175)

        # Place export button

        exportButton = Button(self.t, text="Export", command=self.export)
        exportButton.place(x=150, y=210)

    def openFileWindow(self):
        fileName = getFile()

        self.fileName.set(fileName)
        # self.fileNameField.delete(0,END)
        # self.fileNameField.insert(0, fileName)

    def export(self):
        # Create a copy of the board to reset to once the recording is done
        boardCopy = copy.deepcopy(self.tumbleGUI._grid)

        # Convert the tile resolution to an INT

        self.tileResInt = int(self.tileRes.get())

        self.createGif()

        # Delete the current board and restore the old board
        del self.tumbleGUI._grid
        self.tumbleGUI._grid = boardCopy

    # This function will load a script (sequence of directions to tumble) and
    # step through it, it will save a temp image in ./Gifs/ and compile these
    # into a gif
    def createGif(self):
        self.progress_var.set(0)  # Set progress bar to 0
        self.exportText.set("")  # Set the export text to blank

        filename = self.fileName.get()  # Get the filename from the text field
        file = open(filename, "r")

        # Calculate duration of each frame from the Framerate text field

        framesPerSec = 1000 / int(self.videoSpeed.get())

        lineWidthInt = int(self.lineWidth.get())

        images = []

        sequence = file.readlines()[0].rstrip("\n")  # Read in the script file

        seqLen = len(sequence)  # total length used for progress bar

        # If Videos folder does not exist, create it
        if not os.path.exists("../../Videos"):
            os.makedirs("../../Videos")

        if self.exportFileNameText.get() == "":  # If no file name was given create one
            x = 0
            y = 0
            z = 0
            while os.path.exists("Videos/%s%s%s.gif" % (x, y, z)):
                z = z + 1
                if z == 10:
                    z = 0
                    y = y + 1
                if y == 10:
                    y = 0
                    x = x + 1

            exportFile = "Videos/%s%s%s.gif" % (x, y, z)
        else:
            exportFile = "Videos/" + self.exportFileNameText.get() + ".gif"

        for x in range(0, len(sequence)):
            self.progress_var.set(float(x) / seqLen * 100)  # Update progress bar
            self.t.update()  # update toplevel window

            self.tumbleGUI.MoveDirection(
                sequence[x], redraw=False
            )  # Move the board in the specified direction

            # Call function to get and image in memory of the current state of the board, passing it the tile resolution and the line width to use
            image = self.tumbleGUI.getImageOfBoard(self.tileResInt, lineWidthInt)

            # Append the returned image to the image array
            images.append(image)

        # Save the image

        images[0].save(
            exportFile,
            save_all=True,
            append_images=images[1:],
            duration=framesPerSec,
            loop=1,
        )

        # Set the export Text
        self.exportText.set("Video saved at " + exportFile)

        # Update the progress bar and update the toplevel to redraw the progress bar

        self.progress_var.set(100)
        self.t.update()


######################################################################


class MotionPlannerLogTextBox(scrolledtext.ScrolledText):
    def __init__(self, parent, messages, height=18, width=1):
        super().__init__(parent, height=height, width=width)
        self["font"] = ("consolas", "12")
        self.tag_configure("bold", font=Font(size=12, weight="bold"))
        self.set_text(messages)
        self.config(state="disabled")
        self.yview(tkinter.END)
        self.pack(side="top", expand=True, fill="x")

    def set_text(self, messages):
        self.config(state="normal")
        self.delete("1.0", END)
        if not messages:
            return
        else:
            for message in messages[:-1]:
                self.add_message(message)
                self.insert(tkinter.END, "------------------------------------------\n")
            self.add_message(messages[-1])
        self.config(state="disabled")

    def add_message(self, message):
        first_line, rest = message.split("\n", 1)
        self.insert(tkinter.END, first_line + "\n", "bold")
        self.insert(tkinter.END, rest + "\n")


class MotionPlannerDialog(tkinter.Toplevel):
    def __init__(self, parent, title, messages, yesno=False):
        tkinter.Toplevel.__init__(self, parent)
        self.title(title)
        self.resizable(False, False)
        self.yes = False

        self.geometry("400x400")

        self.txt = MotionPlannerLogTextBox(self, messages)

        if yesno:
            self.yes_button = tkinter.Button(
                self, text="Yes", command=self.on_yes, width=10
            )
            self.yes_button.pack(side="right", padx=5, pady=5)
            self.no_button = tkinter.Button(
                self, text="No", command=self.on_no, width=10
            )
            self.no_button.pack(side="right", padx=5, pady=5)

        else:
            self.ok_button = tkinter.Button(
                self, text="OK", command=self.on_ok, width=10
            )
            self.ok_button.pack(side="right", padx=5, pady=5)

    def on_yes(self, event=None):
        self.yes = True
        self.destroy()

    def on_no(self, event=None):
        self.yes = False
        self.destroy()

    def on_ok(self, event=None):
        self.destroy()

    def get(self):
        self.wm_deiconify()
        self.wait_window()
        return self.yes


class MotionPlannerFrame(tkinter.Frame):
    def __init__(self, main_gui, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main_gui = main_gui
        self.running_info = Label(
            self,
            text="No motion planner running",
            width=40,
            wraplength=280,
            height=2,
            justify=LEFT,
        )

        self.txt = MotionPlannerLogTextBox(
            self, self.main_gui.motion_planner_log, width=42
        )
        self.txt.pack(side=TOP)
        self.running_info.pack(side=TOP)
        self.stop_button = Button(
            self, text="Stop", width=15, command=self.main_gui.stop_motion_planner
        )
        self.stop_button.pack(side=TOP)
        self.stop_button["state"] = "disabled"

    def update_log(self):
        self.txt.set_text(self.main_gui.motion_planner_log)
        self.txt.yview(tkinter.END)


class StoppableSequenceExecutionThread(threading.Thread):
    def __init__(self, sequence, gui):
        super(StoppableSequenceExecutionThread, self).__init__()
        self.sequence = sequence
        self.gui = gui
        self.stopped = False

    def run(self):
        try:
            for x in self.sequence:
                if self.stopped:
                    break
                time.sleep(self.gui.script_speed_var.get())
                self.gui.MoveDirection(x)
                self.gui.w.update_idletasks()
            self.gui.sequence_execution_thread = None
        except:
            self.gui.sequence_execution_thread = None

    def stop(self):
        self.stopped = True


class StoppableMotionPlannerThread(threading.Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self, motion_planner: MotionPlanner, name, gui):
        super(StoppableMotionPlannerThread, self).__init__()
        self.motion_planner = motion_planner
        self.stopped = False
        self.name = name
        self.gui = gui

    def run(self):
        self.gui.set_active_motion_planner(self.motion_planner, self.name)
        start = time.time()
        try:
            solution = self.motion_planner.solve()
        except Exception:
            tkinter.messagebox.showinfo(
                "Motion Planner Error", str(traceback.format_exc())
            )
            self._exit()
            return
        end = time.time()
        if self.stopped:
            self.gui.motion_planner_log.append(
                self.name
                + " Motion Planner\n"
                + "Search stopped.\nTime used:\t\t\t{:.2f} s".format(end - start)
            )
            self._exit()
            MotionPlannerDialog(
                self.gui.mainframe, "Search stopped", self.gui.motion_planner_log
            )
            return

        elif solution is None:
            self.gui.motion_planner_log.append(
                self.name
                + " Motion Planner\n"
                + "Solution could not be found.\n"
                + "Time used:\t\t\t{:.2f} s".format(end - start)
            )
            self._exit()
            MotionPlannerDialog(
                self.gui.mainframe, "Search finished", self.gui.motion_planner_log
            )
            return

        sequence = "".join(solution)
        self.gui.motion_planner_log.append(
            self.name
            + " Motion Planner\n"
            + "Sequence found\n"
            + sequence
            + "\n\n"
            + "Sequence Length:\t\t\t"
            + str(len(sequence))
            + "\n"
            + "Time used:\t\t\t{:.2f} s".format(end - start)
        )
        self._exit()
        dialog = MotionPlannerDialog(
            self.gui.mainframe, "Run Sequence?", self.gui.motion_planner_log, yesno=True
        )
        if dialog.get():
            self.gui.run_sequence(sequence)

    def _exit(self):
        self.gui.motion_planner_thread = None
        self.gui.motion_planner_finished()

    def stop(self):
        self.stopped = True
        self.motion_planner.stop()
        self.gui.callCanvasRedraw()


class MaxStack(list):
    def __init__(self, max_size):
        super().__init__()
        self.max_size = max_size

    def push(self, element):
        self.append(element)

    def append(self, element):
        super().append(element)
        if super().__len__() > self.max_size:
            super().__delitem__(0)


################################################################
class tumblegui:
    def __init__(self, root):
        global TILESIZE
        self.stateTmpSaves = []
        self.polyTmpSaves = []

        self.maxStates = 255
        self.CurrentState = -1

        # 3 sets of data that the class will keep track of, these are used to sending tiles to the editor or updating the board
        # when tile data is received from the editor
        self.tile_data = None  # the data of the actual tiles on the board
        self.glueFunc = {}  # contains the glue function
        # contains the preview tiles so if the editor needs to be reopened the
        # preview tiles are reserved
        self.prevTileList = []

        self.board = TT.Board(TT.BOARDHEIGHT, TT.BOARDWIDTH)
        self.root = root
        self.root.resizable(True, True)
        self.mainframe = Frame(self.root, bd=0, relief=FLAT)

        self.target_shape = None
        self.target_shape_rectangles = []

        self.motion_planner_thread = None
        self.motion_planner_thread = None
        self.motion_planner_log = []  # list of messages

        self.sequence_execution_thread = None

        self.rrt_nodes = []
        self.rrt_node_iterator = None

        self.last_loaded_file = None

        FACTORYMODE = BooleanVar()
        FACTORYMODE.set(False)

        self.rightFrame = Frame(self.mainframe, width=400, relief=SUNKEN, borderwidth=1)
        self.BoardFrame = Frame(
            self.mainframe,
            borderwidth=1,
            relief=FLAT,
            width=TT.BOARDWIDTH * TILESIZE,
            height=TT.BOARDHEIGHT * TILESIZE,
        )

        # main canvas to draw on
        self.w = Canvas(
            self.BoardFrame,
            width=TT.BOARDWIDTH * TILESIZE,
            height=TT.BOARDHEIGHT * TILESIZE,
            scrollregion=(0, 0, TT.BOARDWIDTH * TILESIZE, TT.BOARDHEIGHT * TILESIZE),
        )

        # mouse
        self.w.bind("<Button-1>", self.callback)
        self.root.bind("<MouseWheel>", self.on_mousewheel)
        # arrow keys
        self.root.bind("<Up>", self.keyPressed)
        self.root.bind("<Right>", self.keyPressed)
        self.root.bind("<Down>", self.keyPressed)
        self.root.bind("<Left>", self.keyPressed)
        self.root.bind("<space>", self.keyPressed)
        self.root.bind("<Escape>", self.keyPressed)
        self.root.bind("<Key>", self.keyPressed)

        self.scrollbarV = Scrollbar(self.BoardFrame)
        self.scrollbarV.pack(side=RIGHT, fill=Y)
        self.w.config(yscrollcommand=self.scrollbarV.set)
        self.scrollbarV.config(command=self.w.yview)

        self.scrollbarH = Scrollbar(self.BoardFrame, orient=HORIZONTAL)
        self.scrollbarH.pack(side=BOTTOM, fill=X)
        self.w.config(xscrollcommand=self.scrollbarH.set)
        self.scrollbarH.config(command=self.w.xview)
        self.w.pack()
        self.rightFrame.pack(side=RIGHT, expand=False)
        self.BoardFrame.pack(side=LEFT, expand=True)

        # menu
        # menu - https://www.tutorialspoint.com/python/tk_menu.htm
        self.menubar = Menu(self.root, relief=RAISED)
        self.filemenu = Menu(self.menubar, tearoff=0)
        self.filemenu.add_command(label="New Board", command=self.newBoard)
        self.filemenu.add_command(
            label="Create SVG", command=lambda: SaveSVGDialog(self)
        )
        # command=lambda: self.board2SVG(self.board))
        self.filemenu.add_command(
            label="Sequence to SVGs", command=lambda: SequenceToSVGDialog(self)
        )
        self.filemenu.add_command(label="Example", command=self.CreateInitial)
        # filemenu.add_command(label="Generate Tiles", command=self.openTileEditDial)
        self.filemenu.add_command(
            label="Load Instance", command=lambda: self.load_instance()
        )
        self.filemenu.add_command(
            label="Reload Last File", command=lambda: self.reload_file()
        )

        self.tkLOG = BooleanVar()
        self.tkLOG.set(False)
        # self.filemenu.add_checkbutton(
        #    label="Log Actions",
        #    onvalue=True,
        #    offvalue=False,
        #    variable=self.tkLOG,
        #    command=self.EnableLogging)

        # if PYSCREEN:
        #    self.filemenu.add_command(label="Picture", command=self.picture)
        # else:
        #    self.filemenu.add_command(
        #        label="Picture",
        #        command=self.picture,
        #        state=DISABLED)

        self.filemenu.add_separator()
        self.filemenu.add_command(label="Exit", command=self.root.quit)

        self.aboutmenu = Menu(self.menubar, tearoff=0)
        self.aboutmenu.add_command(label="About", command=self.about)

        self.tkSTEPVAR = BooleanVar()
        self.tkSTEPVAR.set(False)
        self.tkGLUESTEP = BooleanVar()
        self.tkGLUESTEP.set(False)

        self.tkDRAWGRID = BooleanVar()
        self.tkDRAWGRID.set(False)
        self.tkSHOWLOC = BooleanVar()
        self.tkSHOWLOC.set(False)
        self.tkFACTORYMODE = BooleanVar()
        self.tkFACTORYMODE.set(False)

        self.tkLoopScript = BooleanVar()
        self.tkLoopScript.set(False)

        # This text will change from "Record Script" to "Stop Recording"
        self.recordScriptText = "Record Sequence"
        self.runScriptText = "Run Sequence"

        self.settingsmenu = Menu(self.menubar, tearoff=0)
        self.settingsmenu.add_checkbutton(
            label="Single Step",
            onvalue=True,
            offvalue=False,
            variable=self.tkSTEPVAR,
            command=self.setSingleStep,
        )  # ,command=stepmodel)
        self.settingsmenu.invoke(self.settingsmenu.index("end"))
        self.settingsmenu.add_checkbutton(
            label="Glue on Step", onvalue=True, offvalue=False, variable=self.tkGLUESTEP
        )  # ,state=DISABLED)
        self.settingsmenu.invoke(self.settingsmenu.index("end"))
        self.settingsmenu.add_separator()
        self.settingsmenu.add_command(
            label="Background Color", command=self.changecanvas
        )
        self.settingsmenu.add_checkbutton(
            label="Show Grid",
            onvalue=True,
            offvalue=False,
            variable=self.tkDRAWGRID,
            command=lambda: self.callCanvasRedraw(),
        )
        self.settingsmenu.add_command(label="Grid Color", command=self.changegridcolor)
        self.settingsmenu.add_checkbutton(
            label="Show Locations",
            onvalue=True,
            offvalue=False,
            variable=self.tkSHOWLOC,
            command=lambda: self.callCanvasRedraw(),
        )
        # self.settingsmenu.add_separator()
        # self.settingsmenu.add_command(
        #    label="Board Options",
        #    command=self.changetile)
        # self.settingsmenu.add_checkbutton(
        #     label="Factory Mode",
        #     onvalue=True,
        #     offvalue=False,
        #     variable=self.tkFACTORYMODE,
        #     command=self.setFactoryMode)

        self.motion_planner_menu = Menu(self.menubar, tearoff=0)
        self.motion_planner_menu.add_command(
            label="Run Motion Planner", command=self.run_motion_planner
        )

        heuristic_menu = Menu(self.menubar)
        self.heuristic_var = StringVar(value=next(iter(HEURISTICS.keys())))
        for name in HEURISTICS:
            heuristic_menu.add_radiobutton(
                label=name, value=name, variable=self.heuristic_var
            )
        self.motion_planner_menu.add_cascade(label="Heuristic", menu=heuristic_menu)

        mode_menu = Menu(self.menubar)
        self.mode_var = StringVar(value="Polyomino Construction")
        mode_menu.add_radiobutton(
            label="Polyomino Construction",
            value="Polyomino Construction",
            variable=self.mode_var,
        )
        mode_menu.add_radiobutton(
            label="Anchoring", value="Anchoring", variable=self.mode_var
        )
        self.motion_planner_menu.add_cascade(label="Mode", menu=mode_menu)

        self.motion_planner_menu.add_separator()

        self.motion_planner_menu.add_command(
            label="Run Single Tile Motion Planner",
            command=self.run_one_tile_at_a_time_motion_planner,
        )

        single_tile_heuristic_menu = Menu(self.menubar)
        self.single_tile_heuristic_var = StringVar(
            value=next(iter(SINGLE_TILE_HEURISTICS.keys()))
        )
        for name in SINGLE_TILE_HEURISTICS:
            single_tile_heuristic_menu.add_radiobutton(
                label=name, value=name, variable=self.single_tile_heuristic_var
            )
        self.motion_planner_menu.add_cascade(
            label="Single Tile Heuristic", menu=single_tile_heuristic_menu
        )

        self.motion_planner_menu.add_separator()

        self.motion_planner_menu.add_command(
            label="Run RRT Motion Planner", command=self.run_rrt_motion_planner
        )

        self.motion_planner_menu.add_separator()

        self.motion_planner_menu.add_command(
            label="Stop Motion Planner", command=self.stop_motion_planner
        )

        self.motion_planner_menu.add_command(
            label="Show Log", command=self.show_motion_planner_log
        )

        self.editormenu = Menu(self.menubar, tearoff=0)
        self.editormenu.add_command(label="Open Editor", command=self.editCurrentTiles)

        self.sequence_menu = Menu(self.menubar, tearoff=0)
        self.sequence_menu.add_command(
            label=self.recordScriptText, command=self.record_sequence
        )
        self.sequence_menu.add_command(
            label=self.runScriptText, command=self.enter_sequence
        )
        self.sequence_menu.add_command(
            label="Run from File", command=self.run_sequence_from_file
        )

        self.sequence_menu.add_command(
            label="Stop Execution", command=self.stop_sequence
        )

        self.script_speed_var = DoubleVar()
        self.script_speed_var.set(0.25)
        self.execution_speed_menu = Menu(self.menubar)
        self.execution_speed_menu.add_radiobutton(
            label="No delay", variable=self.script_speed_var, value=0.0
        )
        self.execution_speed_menu.add_radiobutton(
            label="Fast", variable=self.script_speed_var, value=0.1
        )
        self.execution_speed_menu.add_radiobutton(
            label="Normal", variable=self.script_speed_var, value=0.25
        )
        self.execution_speed_menu.add_radiobutton(
            label="Slow", variable=self.script_speed_var, value=0.5
        )
        self.execution_speed_menu.add_radiobutton(
            label="Very Slow", variable=self.script_speed_var, value=1.0
        )
        self.sequence_menu.add_cascade(
            label="Execution Speed", menu=self.execution_speed_menu
        )

        self.menubar.add_cascade(label="File", menu=self.filemenu)
        self.menubar.add_cascade(label="Settings", menu=self.settingsmenu)
        self.menubar.add_cascade(label="Editor", menu=self.editormenu)
        self.menubar.add_cascade(label="Sequence", menu=self.sequence_menu)
        self.menubar.add_cascade(label="Help", menu=self.aboutmenu)
        self.menubar.add_cascade(label="MotionPlanner", menu=self.motion_planner_menu)
        self.root.config(menu=self.menubar)

        self.motion_planner_frame = MotionPlannerFrame(
            self, self.rightFrame, relief=FLAT
        )

        #################################################

        self.motion_planner_frame.pack(side=RIGHT, expand=False)
        self.mainframe.pack()

        toolbarframeheight = 24
        self.w.config(
            width=self.board.cols * TILESIZE, height=self.board.rows * TILESIZE
        )

        self.root.geometry(
            str(self.board.cols * TILESIZE + 300)
            + "x"
            + str(self.board.rows * TILESIZE + toolbarframeheight + 30)
        )

        # other class variables
        self.gridcolor = "#000000"
        self.textcolor = "#000000"

        self.callGridDraw()
        self.CreateInitial()
        self.glue_data = []

        self.previous_boards = MaxStack(50)

    def set_active_motion_planner(self, mp, name):
        self.motion_planner_frame.stop_button["state"] = "normal"
        self.motion_planner_frame.running_info["text"] = (
            name + " motion planner running"
        )

    def motion_planner_finished(self):
        self.motion_planner_frame.stop_button["state"] = "disabled"
        self.motion_planner_frame.running_info["text"] = "No motion planner running"
        self.motion_planner_frame.update_log()

    # Sets the factory mode variable
    def setFactoryMode(self):
        TT.FACTORYMODE = self.tkFACTORYMODE.get()

    # sets the single step variable declared in the tumbletiles.py file
    def setSingleStep(self):
        TT.SINGLESTEP = self.tkSTEPVAR.get()

    def record_sequence(self):
        global RECORDING
        global SCRIPTSEQUENCE

        if not RECORDING:
            RECORDING = True
            SCRIPTSEQUENCE = ""
            self.sequence_menu.entryconfigure(0, label="Stop Recording")
        elif RECORDING:
            self.sequence_menu.entryconfigure(0, label="Record Script")
            filename = tkinter.filedialog.asksaveasfilename()
            file = open(filename, "w+")
            file.write(SCRIPTSEQUENCE)
            file.close()
            RECORDING = False

    def enter_sequence(self):
        sequence = tkinter.simpledialog.askstring("Enter Sequence", "Enter Sequence")
        try:
            sequence = self.parse_sequence(sequence)
        except ValueError:
            tkinter.messagebox.showerror(
                "Error", "Sequence can only contain the characters NESW"
            )
            return
        self.run_sequence(sequence)

    def run_sequence_from_file(self):
        file = tkinter.filedialog.askopenfile(mode="r")
        content = file.read()
        try:
            sequence = self.parse_sequence(content)
        except ValueError:
            tkinter.messagebox.showerror(
                "Error", "Sequence can only contain the characters NESW"
            )
            return
        self.run_sequence(sequence)

    def parse_sequence(self, input_string):
        sequence = input_string.upper().replace(" ", "").replace(",", "")
        sequence = " ".join(sequence.splitlines())
        if any(letter not in ["W", "E", "N", "S"] for letter in sequence):
            raise ValueError(
                "Sequence can only Sequence can only contain the characters NESW"
            )
        return sequence

    # Returns a PIL image object of the board by calling the function in boardgui.py
    def getImageOfBoard(self, tileResInt, lineWidthInt):
        return drawPILImage(
            self.board,
            self.board.cols,
            self.board.rows,
            self.w,
            TILESIZE,
            self.textcolor,
            self.gridcolor,
            self.tkDRAWGRID.get(),
            self.tkSHOWLOC.get(),
            tileRes=tileResInt,
            lineWidth=lineWidthInt,
        )

    # Steps through string in script and tumbles in that direction
    def _run_sequence_threaded(self, sequence):
        for x in sequence:
            time.sleep(self.script_speed_var.get())
            self.MoveDirection(x)
            self.w.update_idletasks()

    def run_sequence(self, sequence):
        if self.sequence_execution_thread is not None:
            return
        self.sequence_execution_thread = StoppableSequenceExecutionThread(
            sequence, self
        )
        self.sequence_execution_thread.start()

    def stop_sequence(self):
        if self.sequence_execution_thread is not None:
            self.sequence_execution_thread.stop()

    def changetile(self):
        global TILESIZE

        Sbox = Settings(self.root, self.tkLOG.get(), self)
        self.resizeBoardAndCanvas()
        self.tkTempText.set(TT.TEMP)

    def resizeBoardAndCanvas(self):
        self.board.cols = TT.BOARDWIDTH
        self.board.rows = TT.BOARDHEIGHT

        self.board.remap_tile_positions()
        toolbarframeheight = 24
        self.root.geometry(
            str(self.board.cols * TILESIZE + 500)
            + "x"
            + str(self.board.rows * TILESIZE + toolbarframeheight + 30)
        )
        self.w.config(
            width=self.board.cols * TILESIZE,
            height=self.board.rows * TILESIZE,
            scrollregion=(0, 0, TT.BOARDWIDTH * TILESIZE, TT.BOARDHEIGHT * TILESIZE),
        )
        self.w.pack()
        # resize window #wxh

        # self.root.geometry(str(self.board.Cols*TILESIZE)+'x'+str(self.board.Rows*TILESIZE+toolbarframeheight))
        # redraw
        self.callCanvasRedraw()

    def generate_original_board(self):
        if (
            not hasattr(self, "obg")
            or self.obg is None
            or self.board is not self.ogb_board
        ):
            try:
                self.obg = OriginalBoardGenerator(self.board)
            except AttributeError:
                return
            self.obg_generator = self.obg.iterate_original_board_positions()
            self.ogb_board = self.board
        try:
            next(self.obg_generator)
        except StopIteration:
            self.board.restore_state(self.obg.original_state)
            self.callCanvasRedraw()
            tkinter.messagebox.showinfo(
                "Reverse Stepper", "Displayed all possible reverse steps"
            )
            self.obg = None
            return
        self.callCanvasRedraw()

    def keyPressed(self, event):
        if event.keysym == "Up":
            self.MoveDirection("N")
        elif event.keysym == "Right":
            self.MoveDirection("E")
        elif event.keysym == "Down":
            self.MoveDirection("S")
        elif event.keysym == "Left":
            self.MoveDirection("W")
        elif event.keysym == "Escape":
            self.stop_sequence()
        elif event.keysym == "BackSpace":
            self.generate_original_board()
        elif event.keysym == "n":
            self.show_next_rrt_node()
        elif event.keysym == "space":

            def clear():
                return os.system("cls")

            clear()
            for x in self.listOfCommands:
                print(x[0], " ", x[1])

        elif event.keysym == "z":
            self.undo()
        elif event.keysym == "minus":
            self.zoom(-1)
        elif event.keysym == "plus":
            self.zoom(1)
        elif event.keysym == "r" and MODS.get(event.state, None) == "Control":
            self.reload_file()
        # print(event.keysym)

    def on_mousewheel(self, event):
        self.zoom(int(event.delta / 120))

    def callback(self, event):
        global TILESIZE

        try:
            # print "clicked at", event.x, event.y
            if (
                event.y <= 2 * TILESIZE
                and event.x > 2 * TILESIZE
                and event.x < TT.BOARDWIDTH * TILESIZE - 2 * TILESIZE
            ):
                self.MoveDirection("N")
            elif (
                event.y >= TT.BOARDHEIGHT * TILESIZE - 2 * TILESIZE
                and event.x > 2 * TILESIZE
                and event.x < TT.BOARDWIDTH * TILESIZE - 2 * TILESIZE
            ):
                self.MoveDirection("S")
            elif (
                event.x >= TT.BOARDWIDTH * TILESIZE - 2 * TILESIZE
                and event.y > 2 * TILESIZE
                and event.y < TT.BOARDHEIGHT * TILESIZE - 2 * TILESIZE
            ):
                self.MoveDirection("E")
            elif (
                event.x <= 2 * TILESIZE
                and event.y > 2 * TILESIZE
                and event.y < TT.BOARDHEIGHT * TILESIZE - 2 * TILESIZE
            ):
                self.MoveDirection("W")

        except BaseException:
            pass

    def closeNewSequenceWindow(self):
        self.addSequenceWindow.destroy()

    def addSequence(self):
        if self.newCommandFile.get() == "No File Selected":
            print("No File Seleceted")
        elif self.newCommandName.get().strip() == "":
            print("No Name Entered")
        else:
            print("There was a file Selected: ", self.newCommandFile.get())
            print("Command Name Entered: ", self.newCommandName.get())

            filename = self.newCommandFile.get()
            file = open(filename, "r")
            script = file.readlines()[0].rstrip("\n")
            sequence = ""
            for x in range(0, len(script)):
                print(script[x], " - ", end=" ")
                sequence = sequence + script[x]
                # self.tg.w.update_idletasks()

            self.listOfCommands.append((self.newCommandName.get().strip(), sequence))

        self.closeNewSequenceWindow()

    def selectSequence(self):
        filename = getFile()
        self.newCommandFile.set(filename)

    def addSequenceWin(self):
        global CURRENTNEWTILECOLOR

        self.addSequenceWindow = Toplevel(self.root)
        self.addSequenceWindow.lift(aboveThis=self.root)
        self.addSequenceWindow.wm_title("Create Sequence")
        self.addSequenceWindow.resizable(False, False)
        self.addSequenceWindow.protocol(
            "WM_DELETE_WINDOW", lambda: self.closeNewSequenceWindow()
        )

        self.prevFrame = Frame(
            self.addSequenceWindow,
            borderwidth=1,
            relief=FLAT,
            width=200,
            height=NEWTILEWINDOW_H - 40,
        )
        self.filename = Label(self.prevFrame, textvariable=self.newCommandFile)
        self.newCommandFile.set("No File Selected")
        self.filename.pack()
        self.prevFrame.pack()

        self.nameFrame = Frame(self.prevFrame, borderwidth=1, relief=FLAT)
        self.nameLabel = Label(self.nameFrame, text="Command Name:")
        self.commandName = Entry(
            self.nameFrame, textvariable=self.newCommandName, width=20
        )

        self.nameLabel.pack(side=LEFT)
        self.commandName.pack(side=RIGHT)
        self.nameFrame.pack(side=TOP)

        # Frame that till hold the two buttons cancel / create
        self.buttonFrame = Frame(
            self.addSequenceWindow,
            borderwidth=1,
            background="#000",
            relief=FLAT,
            width=300,
            height=200,
        )
        self.buttonFrame.pack(side=BOTTOM)

        self.createButton = Button(
            self.buttonFrame,
            text="Create Sequence",
            width=8,
            command=self.addSequence,
            padx=10,
        )
        self.selectScriptButton = Button(
            self.buttonFrame,
            text="Select Script",
            width=8,
            command=self.selectSequence,
            padx=10,
        )
        self.cancelButton = Button(
            self.buttonFrame,
            text="Cancel",
            width=5,
            command=self.closeNewSequenceWindow,
            padx=10,
        )

        self.createButton.pack(side=LEFT)
        self.selectScriptButton.pack(side=LEFT)
        self.cancelButton.pack(side=RIGHT)

        # Makes the new window open over the current editor window

        self.addSequenceWindow.geometry(
            "%dx%d+%d+%d"
            % (
                NEWTILEWINDOW_W,
                NEWTILEWINDOW_H,
                self.root.winfo_x() + self.root.winfo_width() / 2 - NEWTILEWINDOW_W / 2,
                self.root.winfo_y()
                + self.root.winfo_height() / 2
                - NEWTILEWINDOW_H / 2,
            )
        )

    def zoom(self, x):
        global TILESIZE

        if TILESIZE > 5 and x < 0:
            TILESIZE = TILESIZE + x
            self.w.config(
                width=self.board.cols * TILESIZE,
                height=self.board.rows * TILESIZE,
                scrollregion=(
                    0,
                    0,
                    TT.BOARDWIDTH * TILESIZE,
                    TT.BOARDHEIGHT * TILESIZE,
                ),
            )
            self.w.pack()
            self.callCanvasRedraw()
        elif TILESIZE < 35 and x > 0:
            TILESIZE = TILESIZE + x
            self.w.config(
                width=self.board.cols * TILESIZE,
                height=self.board.rows * TILESIZE,
                scrollregion=(
                    0,
                    0,
                    TT.BOARDWIDTH * TILESIZE,
                    TT.BOARDHEIGHT * TILESIZE,
                ),
            )
            self.w.pack()
            self.callCanvasRedraw()

    def SaveStates(self):
        global RECORDING
        global SCRIPTSEQUENCE
        if len(self.stateTmpSaves) == self.maxStates:
            if self.CurrentState == self.maxStates - 1:
                self.stateTmpSaves.pop(0)
                self.stateTmpSaves.append(copy.deepcopy(self.board.polyominoes))
                self.CurrentState = self.maxStates - 1
            else:
                self.ApplyUndo()

                self.stateTmpSaves.append(copy.deepcopy(self.board.polyominoes))
                self.CurrentState = self.CurrentState + 1
        else:
            if self.CurrentState == len(self.stateTmpSaves) - 1:
                self.stateTmpSaves.append(copy.deepcopy(self.board.polyominoes))
                self.CurrentState = self.CurrentState + 1

            else:
                self.ApplyUndo()

                self.stateTmpSaves.append(copy.deepcopy(self.board.polyominoes))
                self.CurrentState = self.CurrentState + 1

    def ApplyUndo(self):
        global RECORDING
        global SCRIPTSEQUENCE
        for x in range(0, len(self.stateTmpSaves) - self.CurrentState - 1):
            print("x :", x)
            self.stateTmpSaves.pop()
            if RECORDING:
                SCRIPTSEQUENCE = SCRIPTSEQUENCE[:-1]

    def undo(self):
        try:
            self.board = self.previous_boards.pop()
            self.callCanvasRedraw()
        except IndexError:
            pass

    # Tumbles the board in a direction, then redraws the Canvas
    def MoveDirection(self, direction, redraw=True):
        global RECORDING
        global SCRIPTSEQUENCE

        if self.motion_planner_thread is not None:
            return

        self.previous_boards.push(copy.deepcopy(self.board))

        if (
            direction != ""
            and self.tkSTEPVAR.get() == False
            and self.tkGLUESTEP.get() == False
        ):
            self.board.tumble(direction)
            self.Log("T" + direction + ", ")

        # normal with glues
        elif (
            direction != ""
            and self.tkSTEPVAR.get() == False
            and self.tkGLUESTEP.get() == True
        ):
            self.board.tumble_glue(direction)
            self.Log("TG" + direction + ", ")

        # single step
        elif direction != "" and self.tkSTEPVAR.get():
            s = True
            s = self.board.step(direction)
            if self.tkGLUESTEP.get():
                self.board.activate_glues()
                self.Log("SG" + direction + ", ")
            else:
                self.Log("S" + direction + ", ")
            if s == False and self.tkGLUESTEP.get() == False:
                self.board.activate_glues()
                self.Log("G, ")
        self.SaveStates()
        if RECORDING:
            SCRIPTSEQUENCE += direction
        if redraw:
            self.callCanvasRedrawTumbleTiles()

    # Uses pyscreenshot to save an image of the canvas
    def picture(self):
        drawPILImage(
            self.board,
            self.board.cols,
            self.board.rows,
            self.w,
            TILESIZE,
            self.textcolor,
            self.gridcolor,
            self.tkDRAWGRID.get(),
            self.tkSHOWLOC.get(),
        )

    def openVideoExportWindow(self):
        videoExport = VideoExport(self.root, self)

    # Opens the GUI file browser
    def loadFile(self):
        global LASTLOADEDFILE
        filename = getFile()
        LASTLOADEDFILE = filename
        self.loadTileSet(filename)

    # Will reload the last loaded file to enable quick testing
    def reload_file(self):
        if self.last_loaded_file:
            self._load_instance(self.last_loaded_file)

    # Gets the board data, preview tile data, and glue data from getFile.py, modifies all thses
    # accordingly, then redraws the canvas
    def loadTileSet(self, filename):
        if filename == "":
            return

        # self.Log("\nLoad "+filename+"\n")
        data = parseFile(filename)

        del self.board

        TT.GLUEFUNC = {}

        self.board = data[0]
        TT.BOARDHEIGHT = self.board.rows
        TT.BOARDWIDTH = self.board.cols

        self.resizeBoardAndCanvas()
        self.callCanvasRedraw()

        # Glue Function
        for label in data[1]:
            TT.GLUEFUNC[label] = int(data[1][label])
            self.glueFunc[label] = TT.GLUEFUNC[label]

        self.prevTileList = data[2]

        # Call the board editor
        self.board.relist_polyominoes()
        # self.openBoardEditDial(self.root, self.board, data[1], self.prevTileList)
        self.CurrentState = -1
        self.stateTmpSaves = []
        self.SaveStates()
        # self.board.SetGrid()

        self.listOfCommands = data[3]
        self.callCanvasRedraw()

    def load_instance(self):
        filename = tkinter.filedialog.askopenfilename(
            filetypes=(("json files", "*.json"), ("all files", "*"))
        )
        self._load_instance(filename)
        self.last_loaded_file = filename

    def _load_instance(self, filename):
        if filename == "":
            return
        instance = read_instance(filename)
        del self.board
        self.board = instance.initial_state
        TT.BOARDHEIGHT = self.board.rows
        TT.BOARDWIDTH = self.board.cols
        self.target_shape = instance.target_shape
        self.resizeBoardAndCanvas()
        self.callCanvasRedraw()

    def callCanvasRedraw(self):
        global TILESIZE
        redrawCanvas(
            self.board,
            self.board.cols,
            self.board.rows,
            self.w,
            TILESIZE,
            self.textcolor,
            self.gridcolor,
            self.tkDRAWGRID.get(),
            self.tkSHOWLOC.get(),
        )
        self.redraw_target_shape()

    def callCanvasRedrawTumbleTiles(self):
        global TILESIZE
        redrawTumbleTiles(
            self.board,
            self.board.cols,
            self.board.rows,
            self.w,
            TILESIZE,
            self.textcolor,
            self.gridcolor,
            self.tkDRAWGRID.get(),
            self.tkSHOWLOC.get(),
        )
        self.redraw_target_shape()

    def callGridDraw(self):
        global TILESIZE
        drawGrid(
            self.board,
            TT.BOARDWIDTH,
            TT.BOARDHEIGHT,
            self.w,
            TILESIZE,
            self.gridcolor,
            self.tkDRAWGRID.get(),
            self.tkSHOWLOC.get(),
        )

    def about(self):
        global VERSION
        MsgAbout(self.root)

    def changecanvas(self):
        try:
            result = tkinter.colorchooser.askcolor(title="Background Color")
            if result[0] is not None:
                self.w.config(background=result[1])
        except BaseException:
            pass

    def changegridcolor(self):
        try:
            result = tkinter.colorchooser.askcolor(title="Grid Color")
            if result[0] is not None:
                self.gridcolor = result[1]
                self.callCanvasRedraw()
        except BaseException:
            pass

    def openBoardEditDial(self, root, board, gluedata, prevTiles):
        TGBox = TE.TileEditorGUI(root, self, board, gluedata, prevTiles)

    # Opens the editor and loads the cuurent tiles from the simulator
    def editCurrentTiles(self):
        global TILESIZE
        self.glueFunc = TT.GLUEFUNC
        TE.TILESIZE = TILESIZE
        TGBox = TE.TileEditorGUI(
            self.root, self, self.board, self.glueFunc, self.prevTileList
        )

    def show_next_rrt_node(self):
        if self.rrt_node_iterator is None:
            self.original_board_state = self.board.get_state()
            self.rrt_node_iterator = iter(self.rrt_nodes)
        try:
            node = next(self.rrt_node_iterator)
        except StopIteration:
            self.board.restore_state(self.original_board_state)
            self.callCanvasRedraw()
            tkinter.messagebox.showinfo("RRT Nodes", "Displayed all RRT Nodes")
            self.rrt_node_iterator = None
            return
        temp = node.config.board
        node.config.board = self.board
        node.config.apply()
        node.config.board = temp
        self.callCanvasRedraw()

    def run_rrt_motion_planner(self):
        if self.target_shape is None:
            return
        if self.motion_planner_thread is not None:
            return
        mp = RRTSolver(Instance(self.board, self.target_shape))
        self.rrt_nodes = mp.nodes
        self.motion_planner_thread = StoppableMotionPlannerThread(mp, "RTT", self)
        self.motion_planner_thread.start()

    def run_one_tile_at_a_time_motion_planner(self):
        if self.target_shape is None:
            return
        if self.motion_planner_thread is not None:
            return
        h_name = self.single_tile_heuristic_var.get()
        heuristic = SINGLE_TILE_HEURISTICS[h_name]
        mp = OneTileAtATimeMotionPlanner(
            Instance(self.board, self.target_shape), single_tile_heuristic=heuristic
        )
        self.motion_planner_thread = StoppableMotionPlannerThread(
            mp, "Single Tile " + h_name, self
        )
        self.motion_planner_thread.start()

    def run_motion_planner(self):
        if self.target_shape is None:
            return
        if self.motion_planner_thread is not None:
            tkinter.messagebox.showinfo(
                title="Tumble Tiles",
                message="Another Motion planner instance is still running.",
            )
            return

        if self.mode_var.get() == "Polyomino Construction":
            heuristic = HEURISTICS[self.heuristic_var.get()]
            mp = get_motion_planner(
                Instance(self.board, self.target_shape), heuristic=heuristic
            )
        elif self.mode_var.get() == "Anchoring":
            mp = get_anchoring_motion_planner(Instance(self.board, self.target_shape))

        self.motion_planner_thread = StoppableMotionPlannerThread(
            mp, self.heuristic_var.get(), self
        )
        self.motion_planner_thread.start()

    def stop_motion_planner(self):
        try:
            self.motion_planner_thread.stop()
        except AttributeError:
            pass

    def show_motion_planner_log(self):
        MotionPlannerDialog(
            self.mainframe, "Motion Planner Log", self.motion_planner_log
        )

    # Turns the list of polyominoes and concrete tiles into a list of tiles including their position
    # this is used to get the tile list that will be paseed to the editor
    def getTileDataFromBoard(self):
        new_tile_data = []

        for p in self.board.polyominoes:
            for t in p.get_tiles():
                ntile = {}
                ntile["label"] = ""
                ntile["location"] = {}
                ntile["location"]["x"] = t.x
                ntile["location"]["y"] = t.y
                ntile["northGlue"] = t.glues[0]
                ntile["eastGlue"] = t.glues[1]
                ntile["southGlue"] = t.glues[2]
                ntile["westGlue"] = t.glues[3]
                ntile["color"] = t.color
                ntile["concrete"] = "False"

                new_tile_data.append(ntile)

        for x, y in self.board.get_concrete_positions():
            ntile = {}
            ntile["label"] = ""
            ntile["location"] = {}
            ntile["location"]["x"] = x
            ntile["location"]["y"] = y
            ntile["northGlue"] = 0
            ntile["eastGlue"] = 0
            ntile["southGlue"] = 0
            ntile["westGlue"] = 0
            ntile["color"] = "#808080"
            ntile["concrete"] = "True"

            new_tile_data.append(ntile)

        return new_tile_data

    # This method will be called wben you want to export the tiles from the
    # editor back to the simulation
    def setTilesFromEditor(
        self, board, glueFunc, prev_tiles, width, height, target_shape
    ):
        TT.BOARDHEIGHT = board.rows
        TT.BOARDWIDTH = board.cols
        self.board = board
        self.board.remap_tile_positions()
        self.target_shape = TT.Polyomino()
        for x, y in target_shape:
            self.target_shape.add_tile(TT.Tile(position=(x, y)))
        self.glueFunc = glueFunc
        TT.GLUEFUNC = self.glueFunc
        self.prevTileList = prev_tiles
        self.board.relist_polyominoes()
        self.resizeBoardAndCanvas()
        self.CurrentState = 0
        self.stateTmpSaves = []
        self.SaveStates()
        self.callCanvasRedraw()

    def parseFile2(self, filename):
        tree = ET.parse(filename)
        treeroot = tree.getroot()

        # default size of board, changes if new board size data is read from
        # the file
        rows = 15
        columns = 15

        boardSizeExits = False
        previewTilesExist = False
        tileDataExists = False

        if tree.find("PreviewTiles") is not None:
            previewTilesExist = True

        if tree.find("BoardSize") is not None:
            boardSizeExists = True

        if tree.find("TileData") is not None:
            tileDataExists = True

        # data = {"size": [],"tileData": []}
        data = {"size": [], "tileData": []}

        if boardSizeExists:
            rows = treeroot[0].attrib["height"]
            columns = treeroot[0].attrib["width"]

        geomerty = [rows, columns]
        # geomerty["rows"] = rows
        # geomerty["columns"] = columns
        data["size"].append(geomerty)
        # if isinstance(geomerty, dict):
        #    print "geomeryu"
        # if isinstance(data["size"], dict):
        #    print "data"

        if tileDataExists:
            tileDataTree = treeroot[3]
            for tile in tileDataTree:
                newTile = {}

                newTile["location"] = {"x": 0, "y": 0}
                newTile["color"] = "#555555"

                if tile.find("Location") is not None:
                    newTile["location"]["x"] = int(tile.find("Location").attrib["x"])
                    newTile["location"]["y"] = int(tile.find("Location").attrib["y"])

                if tile.find("Color") is not None:
                    if tile.find("Concrete").text == "True":
                        newTile["color"] = "#686868"
                    else:
                        newTile["color"] = "#" + tile.find("Color").text

                data["tileData"].append(newTile)
        return data

    def sequence_to_svgs(
        self, sequence, directory, prefix="img", gridlines=False, border=True, scale=1
    ):
        from math import log

        path = os.path.join(directory, prefix)
        suffix_length = math.ceil(log(len(sequence), 10))
        self.board2SVG(
            self.board,
            filename=path + ("0" * suffix_length) + ".svg",
            gridlines=gridlines,
            border=border,
            scale=scale,
        )
        i = 0
        for step in sequence:
            i += 1
            self.MoveDirection(step)
            filename = (path + "{:0" + str(suffix_length) + "d}.svg").format(i)
            self.board2SVG(
                self.board,
                filename=filename,
                gridlines=gridlines,
                border=border,
                scale=scale,
            )

    def board2SVG(
        self, board: Board, filename="test.svg", gridlines=False, border=True, scale=1
    ):
        w = scale * int(board.cols)
        h = scale * int(board.rows)

        f = open(filename, "w")

        f.write(
            '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" baseProfile="full" width="'
            + str(w + 2 * scale)
            + '" height="'
            + str(h + 2 * scale)
            + '">\n'
        )

        f.write(
            """
        <defs>
            <pattern id="diagonalHatch" patternContentUnits="objectBoundingBox" width="0.5" height="1" patternTransform="rotate(45)">
                <line x1="0" y1="0" x2="0" y2="1" stroke="#FF0000" stroke-width="0.3" />
            </pattern>
        </defs>
"""
        )

        if border:
            border = (
                [(0, y) for y in range(board.rows + 1)]
                + [(board.cols + 1, y) for y in range(board.rows + 1)]
                + [(x, 0) for x in range(board.cols + 1)]
                + [(x, board.rows + 1) for x in range(board.cols + 2)]
            )
            c = "#808080"
            for x, y in border:
                x = scale * x
                y = scale * y
                line = (
                    '<rect x="'
                    + str(x)
                    + '" y="'
                    + str(y)
                    + '" width="'
                    + str(scale)
                    + '" height="'
                    + str(scale)
                    + '" fill="'
                    + str(c)
                    + '" stroke="black" stroke-width="'
                    + str(0.05 * scale)
                    + '"/>\n'
                )
                f.write(line)

        # grid lines
        if gridlines:
            for x in range(board.cols):
                for y in range(board.rows):
                    c = "#ffffff"
                    line = (
                        '<rect x="'
                        + str((x + 1) * scale)
                        + '" y="'
                        + str((y + 1) * scale)
                        + '" width="'
                        + str(scale)
                        + '" height="'
                        + str(scale)
                        + '" fill="'
                        + str(c)
                        + '" stroke="black" stroke-width="'
                        + str(0.05 * scale)
                        + '" fill-opacity="0" />\n'
                    )
                    f.write(line)
        # tiles
        for tile in board.get_tiles():
            x = int(tile.x)
            y = int(tile.y)
            c = tile.color
            line = (
                '<rect x="'
                + str((x + 1) * scale)
                + '" y="'
                + str((y + 1) * scale)
                + '" width="'
                + str(scale)
                + '" height="'
                + str(scale)
                + '" fill="'
                + str(c)
                + '" stroke="black" stroke-width="'
                + str(0.05 * scale)
                + '"/>\n'
            )
            f.write(line)

        for x, y in board.get_concrete_positions():
            c = "#808080"
            line = (
                '<rect x="'
                + str((x + 1) * scale)
                + '" y="'
                + str((y + 1) * scale)
                + '" width="'
                + str(scale)
                + '" height="'
                + str(scale)
                + '" fill="'
                + str(c)
                + '" stroke="black" stroke-width="'
                + str(0.05 * scale)
                + '"/>\n'
            )
            f.write(line)

        if self.target_shape is not None:
            for x, y in [(t.x, t.y) for t in self.target_shape.get_tiles()]:
                line = (
                    '<rect x="'
                    + str((x + 1) * scale)
                    + '" y="'
                    + str((y + 1) * scale)
                    + '" width="'
                    + str(scale)
                    + '" height="'
                    + str(scale)
                    + '" stroke="black" stroke-width="0.0" fill-opacity="'
                    + str(0.4)
                    + '" style="stroke: #000000; fill: url(#diagonalHatch);" />\n'
                )
                f.write(line)

        f.write("</svg>")
        f.close()

    def data2SVG(self, data, filename, gridlines=False):
        # the width of one square
        scale = 10

        f = open(filename, "w")
        w = scale * int(data["size"][0][0])
        h = scale * int(data["size"][0][1])
        f.write(
            '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" baseProfile="full" width="'
            + str(w + 2)
            + '" height="'
            + str(h + 2)
            + '">\n'
        )

        # tile the svg with transparant sqares for gridlines
        if gridlines:
            for x in range(w / scale):
                for y in range(h / scale):
                    c = "#ffffff"
                    line = (
                        '<rect x="'
                        + str(x * scale + 1)
                        + '" y="'
                        + str(y * scale + 1)
                        + '" width="'
                        + str(scale)
                        + '" height="'
                        + str(scale)
                        + '" fill="'
                        + str(c)
                        + '" stroke="black" stroke-width="0.5" fill-opacity="0" />\n'
                    )
                    f.write(line)

        # place tiles of file where appropriate
        for tile in data["tileData"]:
            x = scale * int(tile["location"]["x"])
            y = scale * int(tile["location"]["y"])
            c = tile["color"]
            line = (
                '<rect x="'
                + str(x + 1)
                + '" y="'
                + str(y + 1)
                + '" width="'
                + str(scale)
                + '" height="'
                + str(scale)
                + '" fill="'
                + str(c)
                + '" stroke="black" stroke-width="0.5" />\n'
            )
            f.write(line)

        f.write("</svg>")
        f.close()

    def createSvg(self):
        filename = tkinter.filedialog.asksaveasfilename()
        tile_config = ET.Element("TileConfiguration")
        board_size = ET.SubElement(tile_config, "BoardSize")
        glue_func = ET.SubElement(tile_config, "GlueFunction")

        board_size.set("width", str(self.board.cols))
        board_size.set("height", str(self.board.rows))

        # Add all preview tiles to the .xml file if there are any
        p_tiles = ET.SubElement(tile_config, "PreviewTiles")
        if len(self.prevTileList) != 0:
            for td in self.prevTileList:
                print((td.color))
                if td.glues == [] or len(td.glues) == 0:
                    td.glues = [0, 0, 0, 0]

                # Save the tile data exactly as is
                prevTile = ET.SubElement(p_tiles, "PrevTile")

                c = ET.SubElement(prevTile, "Color")
                c.text = str(td.color).replace("#", "")

                ng = ET.SubElement(prevTile, "NorthGlue")

                sg = ET.SubElement(prevTile, "SouthGlue")

                eg = ET.SubElement(prevTile, "EastGlue")

                wg = ET.SubElement(prevTile, "WestGlue")

                if len(td.glues) > 0:
                    ng.text = str(td.glues[0])
                    sg.text = str(td.glues[2])
                    eg.text = str(td.glues[1])
                    wg.text = str(td.glues[3])

                la = ET.SubElement(prevTile, "Label")
                la.text = 0

        tiles = ET.SubElement(tile_config, "TileData")
        # save all tiles on the board to the .xml file
        for p in self.board.polyominoes:
            for tile in p.get_tiles():
                if tile.glues is None or len(tile.glues) == 0:
                    tile.glues = [0, 0, 0, 0]

                t = ET.SubElement(tiles, "Tile")

                loc = ET.SubElement(t, "Location")
                loc.set("x", str(tile.x))
                loc.set("y", str(tile.y))

                c = ET.SubElement(t, "Color")
                c.text = str(str(tile.color).replace("#", ""))

                ng = ET.SubElement(t, "NorthGlue")
                ng.text = str(tile.glues[0])

                sg = ET.SubElement(t, "SouthGlue")
                sg.text = str(tile.glues[2])

                eg = ET.SubElement(t, "EastGlue")
                eg.text = str(tile.glues[1])

                wg = ET.SubElement(t, "WestGlue")
                wg.text = str(tile.glues[3])

                la = ET.SubElement(t, "Label")
                la.text = 0

        for x, y in self.board.get_concrete_positions():
            t = ET.SubElement(tiles, "Tile")

            loc = ET.SubElement(t, "Location")
            loc.set("x", str(x))
            loc.set("y", str(y))

            c = ET.SubElement(t, "Color")
            c.text = "808080"

            ng = ET.SubElement(t, "NorthGlue")
            ng.text = str(0)

            sg = ET.SubElement(t, "SouthGlue")
            sg.text = str(0)

            eg = ET.SubElement(t, "EastGlue")
            eg.text = str(0)

            wg = ET.SubElement(t, "WestGlue")
            wg.text = str(0)

            co = ET.SubElement(t, "Concrete")
            co.text = str(0)

            la = ET.SubElement(t, "Label")
            la.text = str(0)

        # print tile_config
        mydata = ET.tostring(tile_config)
        file = open("../../tt2svg/tmp.xml", "w")
        file.write(mydata)
        file.close()
        self.data2SVG(self.parseFile2("../../tt2svg/tmp.xml"), filename + ".svg")

    def newBoard(self):
        del self.board.polyominoes[:]
        self.board.LookUp = {}

        self.board = TT.Board(TT.BOARDHEIGHT, TT.BOARDWIDTH)

        bh = TT.BOARDHEIGHT
        bw = TT.BOARDWIDTH
        TT.GLUEFUNC = {
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
        self.CurrentState = -1
        self.stateTmpSaves = []
        self.SaveStates()
        self.callCanvasRedraw()

    def CreateInitial(self):
        try:
            self._load_instance("../exampleboards/example.json")
        except FileNotFoundError:
            self.newBoard()

    # Creates the initial configuration that shows then you open the gui
    def CreateInitial2(self):
        self.Log("\nLoad initial\n")
        # flush board
        del self.board.polyominoes[:]
        self.board.LookUp = {}

        self.board = TT.Board(TT.BOARDHEIGHT, TT.BOARDWIDTH)
        bh = TT.BOARDHEIGHT
        bw = TT.BOARDWIDTH
        TT.GLUEFUNC = {
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
        # initial
        # CreateTiles(board)
        colorb = "#000"
        colorl = "#fff"
        colorg = "#686868"
        NumTiles = 10
        for i in range(NumTiles):
            # bottom tiles
            # colorb = str(colorb[0]+chr(ord(colorb[1])+1)+colorb[2:])
            colorb = (
                "#"
                + str(hex(random.randint(0, 16))[2:])
                + str(hex(random.randint(0, 16))[2:])
                + str(hex(random.randint(0, 16))[2:])
            )
            if len(colorb) > 4:
                colorb = colorb[:4]
            t = TT.Tile(
                position=(bh - i - 2, bh - 1),
                glues=TT.Glues("N", "E", "S", "W"),
                color=colorb,
            )
            p = TT.Polyomino(tiles=[t])
            self.board.add(p)
            # left tiles
            # colorl = str(colorl[0]+chr(ord(colorl[1])-1)+colorl[2:])
            colorl = (
                "#"
                + str(hex(random.randint(0, 16))[2:])
                + str(hex(random.randint(0, 16))[2:])
                + str(hex(random.randint(0, 16))[2:])
            )
            if len(colorl) > 4:
                colorl = colorl[:4]

            char = chr(ord("a") + i)
            t = TT.Tile(
                position=(0, bh - i - 2),
                glues=TT.Glues("S", "W", "N", "E"),
                color=colorb,
            )
            p = TT.Polyomino(tiles=[t])

            self.board.add(p)

            # test add a concrete tile

        self.board.add_concrete(5, 13)
        self.board.add_concrete(10, 1)
        self.board.add_concrete(8, 8)
        self.board.add_concrete(1, 10)
        self.board.add_concrete(13, 5)

        self.CurrentState = -1
        self.stateTmpSaves = []
        self.SaveStates()
        # self.board.SetGrid()
        self.callCanvasRedraw()

    def EnableLogging(self):
        global LOGFILE
        global LOGFILENAME
        try:
            if self.tkLOG.get():
                LOGFILENAME = self.tkFileDialog.asksaveasfilename(
                    initialdir="./",
                    title="Select file",
                    filetypes=(("text files", "*.txt"), ("all files", "*.*")),
                )
                if LOGFILENAME != "":
                    LOGFILE = open(LOGFILENAME, "a")
                    LOGFILE.write("Tumble Tiles Log\n")
                    LOGFILE.close()
                else:
                    self.tkLOG.set(False)
            else:
                if not LOGFILE.closed:
                    LOGFILE.close()
        except Exception as e:
            print("Could not log")
            print(e)

    def Log(self, stlog):
        global LOGFILE
        global LOGFILENAME
        if self.tkLOG.get():
            LOGFILE = open(LOGFILENAME, "a")
            LOGFILE.write(stlog)
            LOGFILE.close()

    def drawgrid(self):
        global TILESIZE

        if self.tkDRAWGRID.get():
            for row in range(self.board.rows):
                self.w.create_line(
                    0,
                    row * TILESIZE,
                    TT.BOARDWIDTH * TILESIZE,
                    row * TILESIZE,
                    fill=self.gridcolor,
                    width=0.50,
                )
            for col in range(self.board.cols):
                self.w.create_line(
                    col * TILESIZE,
                    0,
                    col * TILESIZE,
                    TT.BOARDHEIGHT * TILESIZE,
                    fill=self.gridcolor,
                    width=0.50,
                )

        if self.tkSHOWLOC.get():
            for row in range(TT.BOARDHEIGHT):
                for col in range(TT.BOARDWIDTH):
                    self.w.create_text(
                        TILESIZE * (col + 1) - TILESIZE / 2,
                        TILESIZE * (row + 1) - TILESIZE / 2,
                        text="(" + str(row) + "," + str(col) + ")",
                        fill=self.gridcolor,
                        font=("", TILESIZE / 5),
                    )

    def undraw_target_shape(self):
        for rect in self.target_shape_rectangles:
            self.w.delete(rect)
        self.target_shape_rectangles = []

    def redraw_target_shape(self):
        if self.target_shape is None:
            return
        self.undraw_target_shape()
        self.target_shape_rectangles = [
            self.w.create_rectangle(
                TILESIZE * t.x,
                TILESIZE * t.y,
                TILESIZE * (t.x + 1),
                TILESIZE * (t.y + 1),
                outline="Red",
            )
            for t in self.target_shape.tiles.values()
        ]


if __name__ == "__main__":
    random.seed()
    root = Tk()
    root.title("Tumble Tiles Motion Planner")
    # sets the icon
    # sp = os.path.realpath(__file__)
    sp = os.path.dirname(sys.argv[0])
    imgicon = PhotoImage(file=os.path.join(sp, "../../Logo/tumble.gif"))
    root.tk.call("wm", "iconphoto", root._w, imgicon)
    # root.iconbitmap(r'favicon.ico')
    # root.geometry('300x300')
    mainwin = tumblegui(root)

    mainloop()
