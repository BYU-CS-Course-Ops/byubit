import matplotlib
from matplotlib import pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import tkinter as tk
from tkinter import ttk, Grid, StringVar

from typing import List

from byubit.core import BitHistoryRenderer


class MplCanvas(FigureCanvasTkAgg):

    def __init__(self, parent, figsize=(10, 20), dpi=100):
        self.fig = Figure(figsize=figsize, dpi=dpi, alpha=0, facecolor='none')
        self.axes = self.fig.add_axes([0, 0, 1, 1])
        self.fig.set_alpha(0)

        super(MplCanvas, self).__init__(self.fig, master=parent)


class AutoGridFrame(tk.Frame):
    index = 0

    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, background='', **kwargs)
        Grid.columnconfigure(self, 0, weight=1)
        self.grid_propagate(True)

    def _add_to_grid(self, child):
        child.grid(row=self.index, column=0, pady=(0, 0))

    def add_to_grid_flex_height(self, child):
        self._add_to_grid(child)
        Grid.rowconfigure(self, self.index, weight=1)
        self.index += 1

    def add_to_grid_static_height(self, child):
        self._add_to_grid(child)
        self.index += 1


class MainWindow(AutoGridFrame):
    histos: List[str]

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.histos = ["World 1", "World 2"]

        # Create the matplotlib FigureCanvas objects,
        # each which defines a single set of axes as self.axes.
        self.canvases = []

        # Add tabs of canvases
        style = ttk.Style(self)
        s = ttk.Style()
        s.configure('TNotebook.Tab', font=('URW Gothic L', '17'))
        style.configure('TNotebook', tabposition='s')

        tabs = ttk.Notebook(master=self, style='TNotebook')
        self.add_to_grid_flex_height(tabs)

        self.top_lines = []

        for index, name in enumerate(self.histos):
            tab = AutoGridFrame(master=tabs)

            label_widget = AutoGridFrame(master=tab)
            tab.add_to_grid_static_height(label_widget)

            # Create messages that we can update
            self.top_lines.append(StringVar())
            self.top_lines[index].set("Hello")

            function_line_label = tk.Label(label_widget,
                                           width=60,
                                           font=("Arial", 17),
                                           padx=25,
                                           textvariable=self.top_lines[index])

            function_line_label.bind('<Configure>',
                                     lambda e: function_line_label.config(wraplength=function_line_label.winfo_width()))
            label_widget.add_to_grid_flex_height(function_line_label)

            tab_grid = AutoGridFrame(master=tab)
            tab.add_to_grid_flex_height(tab_grid)

            canvas = MplCanvas(
                parent=tab_grid,
                figsize=(8.0, 8.0),
                dpi=100,
            )
            tab_grid.add_to_grid_flex_height(canvas.get_tk_widget())

            self.canvases.append(canvas)
            tabs.add(tab, text=f"World {index + 1}: {name}")
            self._display_current_record(index)

    def _update_top_line(self, which: int):
        record = self.histos[which]
        self.top_lines[which].set(f"{record}")
        print(which)

    def _display_current_record(self, which):
        self._display_record(which)

    def _display_record(self, which: int):
        self.canvases[which].axes.clear()  # Clear the canvas.

        self._update_top_line(which)
        draw_record(self.canvases[which].axes)

        # Trigger the canvas to update and redraw.
        self.canvases[which].draw()

    class AnimatedRenderer(BitHistoryRenderer):
        """Displays the world, step-by-step
        The User can pause the animation, or step forward or backward manually
        """

        def __init__(self, verbose=False):
            self.verbose = verbose

        def render(self):
            """
            Run TKinter application
            """
            matplotlib.use("TkAgg")

            root = tk.Tk()
            root.title('CS 110 Bit')

            bit_panel = MainWindow(root)
            bit_panel.pack()

            root.protocol('WM_DELETE_WINDOW', root.quit)
            tk.mainloop()

            return False


def draw_record(ax):
    dims = (10, 10)
    ax.set_aspect('equal')

    # Draw squares
    for y in range(dims[1]):
        for x in range(dims[0]):
            ax.add_patch(plt.Rectangle(
                (x, y),
                20, 20,
                color="white")
            )

    # Draw the "bit"
    ax.scatter(
        1.5,
        1.5,
        c='cyan',
        s=500 if max(dims) < 25 else 300,
        marker=(3, 0, 90)
    )

    ax.get_xaxis().set_label_position('top')
    ax.get_xaxis().set_ticks([])

    ax.set_xlim([0, dims[0]])
    ax.set_ylim([0, dims[1]])
    ax.get_yaxis().set_visible(False)

    # Draw Grid
    grid_style = dict(c='gray', lw=1)
    for x in range(0, dims[0]):
        ax.plot((x, x), [0, dims[1]], **grid_style)
    for y in range(0, dims[1]):
        ax.plot([0, dims[0]], (y, y), **grid_style)


if __name__ == '__main__':
    renderer = MainWindow.AnimatedRenderer(verbose=True)
    renderer.render()
