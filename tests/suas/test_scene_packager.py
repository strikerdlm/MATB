import sys, unittest, tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
try:
    import numpy as np
    from scripts import package_suas_scene as packager
except ImportError as error:
    raise unittest.SkipTest(
        "Install requirements-suas-scene.txt for packager checks"
    ) from error


class ScenePackagerTest(unittest.TestCase):
    def test_sparse_source_nodata_remains_transparent(self):
        bands = [np.full((100, 100), 0.15, dtype="float32") for _ in range(3)]
        bands[0][5, 5] = np.nan
        pixels, coverage = packager.masked_rgb(bands)
        self.assertEqual(pixels.shape, (100, 100, 4))
        self.assertEqual(pixels[5, 5, 3], 0)
        self.assertEqual(pixels[6, 6, 3], 255)
        self.assertAlmostEqual(coverage, 99.99)
        bands[0][6, 6] = np.nan
        self.assertIsNone(packager.masked_rgb(bands))

    def test_preparation_failure_is_not_published_and_cleans_only_its_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "test-scene"
            sentinel = root / "keep.txt"
            sentinel.write_text("keep")

            def fail(path, *args):
                path.mkdir(parents=True)
                (path / "partial.json").write_text("{}")
                raise RuntimeError("source failed")

            with patch.object(packager, "build", side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, "source failed"):
                    packager.build_atomic(
                        output, "2026-09-08", None, 4.15, -73.65, "Test", "Meta"
                    )
            self.assertFalse(output.exists())
            self.assertEqual(sentinel.read_text(), "keep")
            self.assertEqual(list((root / ".pending").iterdir()), [])

    def test_preparation_publishes_once_without_replacing_existing(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "test-scene"

            def build(path, *args):
                path.mkdir(parents=True)
                (path / "manifest.json").write_text("{}")

            with patch.object(packager, "build", side_effect=build):
                packager.build_atomic(
                    output, "2026-09-08", None, 4.15, -73.65, "Test", "Meta"
                )
                with self.assertRaisesRegex(RuntimeError, "replace"):
                    packager.build_atomic(
                        output, "2026-09-08", None, 4.15, -73.65, "Test", "Meta"
                    )
            self.assertEqual((output / "manifest.json").read_text(), "{}")


if __name__ == "__main__":
    unittest.main()
