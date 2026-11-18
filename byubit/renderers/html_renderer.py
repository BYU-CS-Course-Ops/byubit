import webbrowser
from pathlib import Path

from tracecode import write_html_view

from ..rendering import BitRenderer


def quote(url):
    # We don't use the built-in quote because:
    # - we do need to escape spaces
    # - but we want to convert \ to / on windows
    # - we want to preserver the : in "C:" on windows
    # and the built-in quote escapes those

    # Fix spaces
    return (
        url
        .replace(' ', '%20')
        .replace('\\', '/')
    )


class HTMLRenderer(BitRenderer):
    def __init__(self):
        self._panel_script = Path(__file__).with_name('bit_panel.js').read_text()

    def render(self, code_file: Path, recordings: dict[str, list[dict]]):
        """Write one Tracecode viewer with a tab for each world run."""
        if not recordings:
            return None
        first_recording = next(iter(recordings.values()))
        view = code_file.with_suffix('.html')
        write_html_view(
            first_recording,
            view,
            panel_title='Bit world',
            panel_script=self._panel_script,
            runs=recordings,
        )
        webbrowser.open(view.resolve().as_uri())
        return view.resolve().as_uri()
