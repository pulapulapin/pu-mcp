import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "marketplace" / "agensi" / "submission" / "assets"


def png_dimensions(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    if payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        raise AssertionError(f"not a PNG: {path}")
    return struct.unpack(">II", payload[16:24])


class MarketplaceAssetTests(unittest.TestCase):
    def test_upload_assets_have_expected_dimensions(self):
        self.assertEqual(png_dimensions(ASSETS / "puknowledge-logo.png"), (512, 512))
        for name in (
            "01-recovery-ready.png",
            "02-preview-before-save.png",
            "03-project-isolation.png",
        ):
            self.assertEqual(png_dimensions(ASSETS / name), (1600, 1000))

    def test_editable_sources_use_only_synthetic_identifiers(self):
        source = "\n".join(path.read_text(encoding="utf-8") for path in ASSETS.glob("*.svg"))
        for forbidden in (
            "/Users/",
            "cognitive-manifestation",
            "game-rpg-novel",
            "AI小说",
            "认知显化",
            "pu-dnd",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("acceptance-alpha", source)
        self.assertIn("acceptance-beta", source)


if __name__ == "__main__":
    unittest.main()
