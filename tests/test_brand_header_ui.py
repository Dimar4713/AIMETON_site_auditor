from pathlib import Path


INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def test_brand_logo_and_studio_label_share_one_lockup_row() -> None:
    index = INDEX.read_text(encoding="utf-8")

    brand_start = index.index('<div class="brand">')
    brand_end = index.index('</div>\n      <div id="userIdentity"', brand_start)
    brand = index[brand_start:brand_end]

    assert '<div class="brand-logo">' in brand
    assert '<p class="eyebrow">AIMETON - AI Studio</p>' in brand
    assert '<h1>Бизнес-разведка и AI-возможности</h1>' not in brand

    header_title = index.index('<h1>Бизнес-разведка и AI-возможности</h1>')
    assert header_title > brand_end
