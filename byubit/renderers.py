import matplotlib
from matplotlib import pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import tkinter as tk
from tkinter import ttk, StringVar, Misc

from typing import List, Tuple

from byubit.core import BitHistoryRecord, BitHistoryRenderer, draw_record, determine_figure_size


def print_histories(histories: List[Tuple[str, List[BitHistoryRecord]]]):
    for name, history in histories:
        print(name)
        print('-' * len(name))
        for num, record in enumerate(history):
            print(f"{num}: {record.name}")
        print()


class TextRenderer(BitHistoryRenderer):
    def __init__(self, verbose=False):
        self.verbose = verbose

    def render(self, histories: List[Tuple[str, List[BitHistoryRecord]]]):
        if self.verbose:
            print_histories(histories)

        return all(history[-1].error_message is None for _, history in histories)


class LastFrameRenderer(BitHistoryRenderer):
    """Displays the last frame
    Similar to the <=0.1.6 functionality
    """

    def __init__(self, verbose=False, bwmode=False):
        self.verbose = verbose
        self.bwmode = bwmode

    def render(self, histories: List[Tuple[str, List[BitHistoryRecord]]]):
        if self.verbose:
            print_histories(histories)

        for name, history in histories:
            last_record = history[-1]

            fig, axs = plt.subplots(1, 1, figsize=determine_figure_size(last_record.world.shape))
            ax: plt.Axes = fig.gca()

            draw_record(ax, last_record, bwmode=self.bwmode)
            ax.set_title(name, fontsize=14)
            fig.tight_layout()

            plt.show()

        return all(history[-1].error_message is None for _, history in histories)


class AutoSizingGridFrame(tk.Frame):
    """
    A tk Frame that uses grid layout, but automatically resizes to fit its contents
    """
    index = 0

    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, background='', **kwargs)
        Misc.grid_columnconfigure(self, 0, weight=1)
        self.grid_propagate(True)

    def _add_to_grid(self, child):
        # Tells the child what row it is in
        child.grid(row=self.index, column=0, pady=(0, 0), padx=(0, 0))

    def add_to_grid_flex_height(self, child):
        # Adds the child to the grid, and tells the grid to make the child expand
        self._add_to_grid(child)
        Misc.grid_rowconfigure(self, self.index, weight=1)
        self.index += 1

    def add_to_grid_static_height(self, child):
        # Adds the child to the grid, and tells the grid not make the child expand
        self._add_to_grid(child)
        self.index += 1


class MplCanvas(FigureCanvasTkAgg):

    def __init__(self, parent, figsize=(5, 4), dpi=100):
        self.fig = Figure(figsize=figsize, dpi=dpi)
        self.axes = self.fig.add_axes([0, 0, 1, 1])
        super(MplCanvas, self).__init__(self.fig, master=parent)


class MainWindow(AutoSizingGridFrame):
    histories: List[Tuple[str, List[BitHistoryRecord]]]
    cur_pos: List[int]

    def __init__(self, parent, histories, verbose=False, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.histories = histories
        self.cur_pos = [len(history) - 1 for _, history in histories]
        self.verbose = verbose

        has_snapshots = any(
            any(
                event.name.startswith('snapshot')
                for event in history
            )
            for _, history in histories
        )

        # Create the matplotlib FigureCanvas objects,
        # each which defines a single set of axes as self.axes.
        sizes = [determine_figure_size(history[0].world.shape) for _, history in histories]
        size = (max(x for x, _ in sizes), max(y for _, y in sizes))
        self.canvases = []

        # Add tabs of canvases
        style = ttk.Style(self)
        s = ttk.Style()
        s.configure('TNotebook.Tab', font=('URW Gothic L', '17'))
        style.configure('TNotebook', tabposition='s')

        tabs = ttk.Notebook(master=self, style='TNotebook')
        self.add_to_grid_flex_height(tabs)

        self.label_widgets = []

        self.top_line_messages = []
        self.top_lines = []
        self.top_err_messages = []
        self.top_errors = []

        for index, (name, _) in enumerate(histories):
            # A tab for each world
            tab = AutoSizingGridFrame(master=tabs)

            self.label_widgets.append(AutoSizingGridFrame(master=tab))
            tab.add_to_grid_static_height(self.label_widgets[index])

            def add_label_to_widget(str_var_list, label_list, idx, **tk_label_kwargs):
                # Create message that we can update
                str_var_list.append(StringVar())
                str_var_list[index].set("")
                label_list.append(tk.Label(textvariable=str_var_list[idx], **tk_label_kwargs))
                label_list[idx].bind('<Configure>', lambda e: (line := label_list[tabs.index('current')],
                                                               line.config(wraplength=line.winfo_width())))
                self.label_widgets[index].add_to_grid_flex_height(label_list[idx])

            common_props = {
                "master": self.label_widgets[index],
                "width": 60,
                "padx": 100,
                "font": ("Arial", 17),
            }

            # Add top line with function and line number
            add_label_to_widget(self.top_line_messages, self.top_lines, index, **common_props)
            # Add second line with error message
            add_label_to_widget(self.top_err_messages, self.top_errors, index,
                                fg="red", **common_props)

            # Create an auto-sizing frame for the canvas
            bit_image_frame = AutoSizingGridFrame(master=tab)
            tab.add_to_grid_flex_height(bit_image_frame)

            canvas = MplCanvas(
                parent=bit_image_frame,
                figsize=size,
                dpi=100
            )
            bit_image_frame.add_to_grid_flex_height(canvas.get_tk_widget())
            self.canvases.append(canvas)

            tabs.add(tab, text=f"World {index + 1}: {name}")
            self._display_current_record(index)

        # Add buttons
        button_widget = tk.Frame(self)

        # Start
        def start_click():
            which = tabs.index('current')
            self.cur_pos[which] = 0
            self._display_current_record(which)

        start_button = ttk.Button(
            master=button_widget,
            text="<<< First",
            command=start_click,
            padding=0
        )
        start_button.grid(row=2, column=0, sticky="nsew")
        Misc.grid_columnconfigure(button_widget, 0, weight=1)

        # Prev snapshot
        if has_snapshots:
            def prev_snap_click():
                which = tabs.index('current')
                cur_pos = self.cur_pos[which]
                _, tab_histories = self.histories[which]
                snapshots = [
                    pos
                    for pos, event in enumerate(tab_histories[:cur_pos])
                    if event.name.startswith('snapshot')
                ]
                prev_pos = snapshots[-1] if snapshots else 0
                self.cur_pos[which] = prev_pos
                self._display_current_record(which)

            prev_snap_button = ttk.Button(
                master=button_widget,
                text="<< Jump",
                command=prev_snap_click,
                padding=0
            )

            prev_snap_button.grid(row=2, column=1, sticky="nsew")
            Misc.grid_columnconfigure(button_widget, 1, weight=1)

        # Back
        def back_click():
            which = tabs.index('current')
            if self.cur_pos[which] > 0:
                self.cur_pos[which] -= 1
            self._display_current_record(which)

        back_button = ttk.Button(
            master=button_widget,
            text="< Prev",
            command=back_click,
            padding=0
        )
        back_button.grid(row=2, column=2, sticky="nsew")
        Misc.grid_columnconfigure(button_widget, 2, weight=1)

        # Next
        def next_click():
            which = tabs.index("current")
            if self.cur_pos[which] < len(self.histories[which][1]) - 1:
                self.cur_pos[which] += 1
            self._display_current_record(which)

        next_button = ttk.Button(
            master=button_widget,
            text="Next >",
            command=next_click,
            padding=0
        )
        next_button.grid(row=2, column=3, sticky="nsew")
        Misc.grid_columnconfigure(button_widget, 3, weight=1)

        # Next snapshot
        if has_snapshots:
            def next_snap_click():
                which = tabs.index("current")
                cur_pos = self.cur_pos[which]
                _, history = self.histories[which]
                snapshots = [
                    pos + cur_pos + 1
                    for pos, event in enumerate(history[cur_pos + 1:])
                    if event.name.startswith('snapshot')
                ]
                next_pos = snapshots[0] if snapshots else len(history) - 1
                self.cur_pos[which] = next_pos
                self._display_current_record(which)

            next_snap_button = ttk.Button(
                master=button_widget,
                text="Jump >>",
                command=next_snap_click,
                padding=0
            )
            next_snap_button.grid(row=2, column=4, sticky="nsew")
            Misc.grid_columnconfigure(button_widget, 4, weight=1)

        # Last
        def last_click():
            which = tabs.index("current")
            self.cur_pos[which] = len(self.histories[which][1]) - 1
            self._display_current_record(which)

        last_button = ttk.Button(
            master=button_widget,
            text="Last >>>",
            command=last_click,
            padding=0
        )
        last_button.grid(row=2, column=5, sticky="nsew")
        Misc.grid_columnconfigure(button_widget, 5, weight=1)

        button_widget.grid_propagate(True)

        button_widget.grid(row=2, column=0, padx=15, pady=(0, 10), sticky="nsew")

    def _display_current_record(self, which: int):
        self._display_record(which, self.cur_pos[which], self.histories[which][1][self.cur_pos[which]])

    def _display_record(self, which: int, index: int, record: BitHistoryRecord):
        if self.verbose:
            print(f"{index}: {record.name}")

        self.canvases[which].axes.clear()  # Clear the canvas.

        self.top_line_messages[which].set(f"{index}: {record.name} [{record.filename} line {record.line_number}]")
        self.top_err_messages[which].set("" if record.error_message is None else record.error_message)

        draw_record(self.canvases[which].axes, record)

        # Trigger the canvas to update and redraw.
        self.canvases[which].draw()


class AnimatedRenderer(BitHistoryRenderer):
    """Displays the world, step-by-step
    The User can pause the animation, or step forward or backward manually
    """

    def __init__(self, verbose=False):
        self.verbose = verbose

    def render(self, histories: List[Tuple[str, List[BitHistoryRecord]]]):
        """
        Run TKinter application
        """
        matplotlib.use("TkAgg")

        root = tk.Tk()
        root.title('CS 110 Bit')

        bit_panel = MainWindow(root, histories, self.verbose)
        bit_panel.pack()

        root.protocol('WM_DELETE_WINDOW', root.quit)
        tk.mainloop()

        return all(history[-1].error_message is None for _, history in histories)
