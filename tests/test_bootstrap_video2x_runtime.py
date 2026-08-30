import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_video2x_runtime.py"
SPEC = importlib.util.spec_from_file_location("bootstrap_video2x_runtime", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class BootstrapVideo2XRuntimeTest(unittest.TestCase):
    def test_installs_wrapper_runtime_and_models_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            extracted = root / "squashfs-root"
            binary = extracted / "usr" / "bin" / "video2x"
            model = extracted / "usr" / "share" / "video2x" / "models" / "realcugan" / "models-se" / "up2x-denoise1x.param"
            binary.parent.mkdir(parents=True)
            model.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            model.write_text("fixture\n", encoding="utf-8")

            bootstrap.install_from_extracted_appdir(extracted, root)

            wrapper = root / "bin" / "video2x"
            self.assertTrue(wrapper.exists())
            self.assertTrue(wrapper.stat().st_mode & 0o111)
            self.assertTrue((root / "share" / "video2x" / "usr" / "bin" / "video2x").exists())
            self.assertTrue((root / "share" / "video2x" / "models").is_symlink())
            self.assertTrue(
                (
                    root
                    / "share"
                    / "video2x"
                    / "models"
                    / "realcugan"
                    / "models-se"
                    / "up2x-denoise1x.param"
                ).exists()
            )

    def test_requires_force_for_existing_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            extracted = root / "squashfs-root"
            (extracted / "usr" / "bin").mkdir(parents=True)
            (extracted / "usr" / "bin" / "video2x").write_text("#!/bin/sh\n", encoding="utf-8")
            (extracted / "usr" / "share" / "video2x" / "models").mkdir(parents=True)
            (root / "share" / "video2x").mkdir(parents=True)

            with self.assertRaisesRegex(FileExistsError, "Use --force"):
                bootstrap.install_from_extracted_appdir(extracted, root)
