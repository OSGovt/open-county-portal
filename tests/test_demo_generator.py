"""The demonstration county generator, at a small scale."""
from __future__ import annotations

import datetime as dt
import io

from PIL import Image
from sqlalchemy import func, select

from portal import cli
from portal.db import images, import_batches, instruments, parties, tx


def test_generate_small_county(client):
    assert cli.main(["demo", "--remove"]) == 0
    try:
        assert cli.main(["demo", "--scale", "3000", "--seed", "3", "--no-banner"]) == 0
        with tx() as conn:
            batch = conn.execute(select(import_batches.c.id).where(import_batches.c.source == "demo-sample-data",
                                                                   import_batches.c.status == "loaded")).scalar_one()
            n = conn.execute(select(func.count()).select_from(instruments)
                             .where(instruments.c.import_batch == batch)).scalar_one()
            assert n == 3000
            latest = conn.execute(select(func.max(instruments.c.recorded_date))
                                  .where(instruments.c.import_batch == batch)).scalar_one()
            assert latest <= dt.date.today()
            assert conn.execute(select(func.count()).select_from(parties)).scalar_one() > 3000
            number = conn.execute(select(instruments.c.instrument_number).where(
                instruments.c.import_batch == batch, instruments.c.status == "public",
                instruments.c.doc_type == "Warranty Deed")).first()[0]
        # The page image is drawn on demand and matches the document.
        r = client.get(f"/records/{number}/pages/1.png")
        assert r.status_code == 200
        assert Image.open(io.BytesIO(r.content)).size == (1275, 1650)
        page = client.get(f"/records/{number}").text
        assert "Utopia County, Nirvana is fictional" in page
        api = client.get(f"/api/v1/instruments/{number}").json()
        assert api["images"][0]["sha256"] is None
        # Same seed, same county.
        assert cli.main(["demo", "--remove"]) == 0
        assert cli.main(["demo", "--scale", "3000", "--seed", "3", "--no-banner"]) == 0
        with tx() as conn:
            again = conn.execute(select(instruments.c.instrument_number).where(
                instruments.c.doc_type == "Warranty Deed", instruments.c.status == "public")
                .order_by(instruments.c.id)).first()[0]
        assert again == number
    finally:
        cli.main(["demo", "--remove"])
        cli.main(["demo"])  # the small sample set other tests expect
