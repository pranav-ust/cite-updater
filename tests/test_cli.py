import io

from cite_updater.cli import _Progress


class _FakeStream(io.StringIO):
    def __init__(self, tty: bool):
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def test_progress_non_tty_emits_greppable_lines():
    stream = _FakeStream(tty=False)
    p = _Progress(3, stream=stream)
    p.update(ok=1, suspect=0, unmatched=0)
    p.update(ok=1, suspect=1, unmatched=0)
    p.update(ok=1, suspect=1, unmatched=1)
    lines = stream.getvalue().splitlines()
    assert lines == [
        "PROGRESS 1/3 ok=1 suspect=0 unmatched=0",
        "PROGRESS 2/3 ok=1 suspect=1 unmatched=0",
        "PROGRESS 3/3 ok=1 suspect=1 unmatched=1",
    ]


def test_progress_tty_draws_inplace_bar_and_finishes_with_newline():
    stream = _FakeStream(tty=True)
    p = _Progress(2, stream=stream)
    p.update(ok=1, suspect=0, unmatched=0)
    p.update(ok=2, suspect=0, unmatched=0)
    out = stream.getvalue()
    assert out.startswith("\r[")        # in-place redraw
    assert "1/2" in out and "2/2" in out
    assert out.endswith("\n")           # newline once complete


def test_progress_disabled_writes_nothing():
    stream = _FakeStream(tty=False)
    p = _Progress(5, stream=stream, enabled=False)
    p.update(ok=1, suspect=0, unmatched=0)
    assert stream.getvalue() == ""


def test_progress_empty_input_is_noop():
    stream = _FakeStream(tty=False)
    p = _Progress(0, stream=stream)  # zero entries → disabled, no div-by-zero
    p.update(ok=0, suspect=0, unmatched=0)
    assert stream.getvalue() == ""
