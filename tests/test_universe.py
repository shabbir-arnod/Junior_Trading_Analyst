import shutil

import pytest

from analyst.universe import Watchlist


@pytest.fixture
def watchlist_path(tmp_path):
    src = "config/watchlist.yaml"
    dst = tmp_path / "watchlist.yaml"
    shutil.copy(src, dst)
    return dst


def test_load_watchlist(watchlist_path):
    wl = Watchlist.load(watchlist_path)
    assert "NVDA" in wl.groups["core"]
    assert "SMCI" in wl.groups["emerging"]


def test_all_tickers_deduplicated(watchlist_path):
    wl = Watchlist.load(watchlist_path)
    tickers = wl.all_tickers()
    assert len(tickers) == len(set(tickers))


def test_group_filter(watchlist_path):
    wl = Watchlist.load(watchlist_path)
    assert wl.tickers("core") == wl.groups["core"]
    assert wl.tickers("all") == wl.all_tickers()
    with pytest.raises(ValueError):
        wl.tickers("bogus")


def test_add_and_remove_roundtrip(watchlist_path):
    wl = Watchlist.load(watchlist_path)
    assert wl.add("ZZZZ", "emerging") is True
    assert wl.add("ZZZZ", "emerging") is False  # already present
    wl.save()

    reloaded = Watchlist.load(watchlist_path)
    assert "ZZZZ" in reloaded.groups["emerging"]

    assert reloaded.remove("ZZZZ") is True
    assert reloaded.remove("ZZZZ") is False
    reloaded.save()

    final = Watchlist.load(watchlist_path)
    assert "ZZZZ" not in final.all_tickers()


def test_add_invalid_group_raises(watchlist_path):
    wl = Watchlist.load(watchlist_path)
    with pytest.raises(ValueError):
        wl.add("ZZZZ", "bogus")


def test_save_preserves_comments_on_untouched_lines(watchlist_path):
    wl = Watchlist.load(watchlist_path)
    wl.add("ZZZZ", "emerging")
    wl.remove("SMCI")
    wl.save()

    text = watchlist_path.read_text()
    assert "# Nvidia - AI accelerators / GPUs" in text
    assert "# Advanced Micro Devices - AI accelerators / CPUs" in text
    assert "Super Micro Computer" not in text
    assert "- ZZZZ" in text
    assert "- SMCI" not in text
