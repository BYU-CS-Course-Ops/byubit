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
        """Write one tracecode viewer per world and open the first one."""
        views = []
        for name, recording in recordings.items():
            safe_name = ''.join(char if char.isalnum() or char in '-_' else '_' for char in name)
            view = code_file.with_name(f'{code_file.stem}.{safe_name}.html')
            write_html_view(
                recording,
                view,
                panel_title='Bit world',
                panel_script=self._panel_script,
            )
            views.append(view)
        if views:
            webbrowser.open(views[0].resolve().as_uri())
            return views[0].resolve().as_uri()
        return None
