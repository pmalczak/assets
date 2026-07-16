import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app_proc.calculate_assets import ASSETS_SNAPSHOT_STEP
from data_step.data_step import DataStep
from data_step.data_step_dependencies import Dependencies
from data_step.data_step_frame import DataStepFrame
from data_step.data_strep_data_types import CACHED, REFRESHED
from data_step.metadata_class import DIGEST, Metadata, MetadataUpdateError
from data_step.metadata_primitives_class import HOME_PATH


def _make_data_steps_tree() -> tuple[Path, Path]:
    """Tworzy izolowany katalog data_steps z plikiem startowym init_steps."""
    root = Path(tempfile.mkdtemp())
    data_steps = root / "data_steps"
    data_steps.mkdir()
    (data_steps / "_metadata.json").write_text("{}", encoding="utf-8")
    start_file = root / "app" / "module.py"
    start_file.parent.mkdir(parents=True)
    start_file.touch()
    return root, start_file


class DataStepFrameTests(unittest.TestCase):
    def test_str_and_accessors(self):
        df = pd.DataFrame({"a": [1, 2]})
        frame = DataStepFrame(status=REFRESHED, data=df, data_set="sample.parquet")
        self.assertEqual(frame.get_status(), REFRESHED)
        self.assertEqual(frame.get_data_file_name(), "sample.parquet")
        self.assertTrue("sample.parquet" in str(frame))
        pd.testing.assert_frame_equal(frame.data_frame(), df)

    def test_get_data_file_name_raises_without_data_set(self):
        frame = DataStepFrame(status=CACHED, data=pd.DataFrame())
        with self.assertRaises(ValueError):
            frame.get_data_file_name()


class DependenciesTests(unittest.TestCase):
    def test_create_update_get(self):
        deps = Dependencies()
        deps.create("product")
        deps.update("product", "source.parquet")
        deps.update("product", "source.parquet")
        self.assertEqual(deps.get("product"), ["source.parquet"])


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_steps = Path(self._tmpdir.name) / "data_steps"
        self.data_steps.mkdir()
        (self.data_steps / "_metadata.json").write_text("{}", encoding="utf-8")
        self.metadata = Metadata(self.data_steps)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_token_roundtrip_for_relative_resource(self):
        token = self.metadata.as_token("01 source/input.parquet")
        path = self.metadata.token_as_path(token)
        self.assertEqual(path, self.data_steps / "01 source/input.parquet")

    def test_update_removes_self_from_dependencies(self):
        token = "out.parquet"
        df = pd.DataFrame({"x": [1]})
        path = self.data_steps / token
        df.to_parquet(path)

        self.metadata.update(DIGEST, token, [token, "other.parquet"], rows=1)

        descriptor = self.metadata.get_items_descriptor(token)
        self.assertEqual(descriptor["dependencies"], ["other.parquet"])

    def test_is_updated_raises_when_metadata_missing(self):
        path = self.data_steps / "missing.parquet"
        pd.DataFrame({"x": [1]}).to_parquet(path)
        with self.assertRaises(MetadataUpdateError):
            self.metadata.is_updated("missing.parquet")

    def test_digest_invalidation_after_file_change(self):
        token = "cached.parquet"
        path = self.data_steps / token
        pd.DataFrame({"x": [1]}).to_parquet(path)
        self.metadata.update(DIGEST, token, [])

        pd.DataFrame({"x": [1, 2]}).to_parquet(path)
        with self.assertRaises(MetadataUpdateError):
            self.metadata.is_updated(token)

    def test_updated_stat_cache_uses_token_keys(self):
        token = "cached.parquet"
        path = self.data_steps / token
        pd.DataFrame({"x": [1]}).to_parquet(path)
        self.metadata.update(DIGEST, token, [])
        self.metadata.is_updated(token)
        self.assertIn(token, self.metadata.updated_stat_cache)

        pd.DataFrame({"x": [9]}).to_parquet(path)
        self.metadata.update(DIGEST, token, [])
        self.assertNotIn(token, self.metadata.updated_stat_cache)


class DataStepIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        root = Path(self._tmpdir.name)
        self.data_steps = root / "data_steps"
        self.data_steps.mkdir()
        (self.data_steps / "_metadata.json").write_text("{}", encoding="utf-8")
        self.start_file = root / "app" / "runner.py"
        self.start_file.parent.mkdir(parents=True)
        self.start_file.touch()
        self.step = DataStep()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_not_initialised_raises(self):
        with self.assertRaises(ReferenceError):
            self.step.obtain("x.parquet", lambda: pd.DataFrame())

    def test_find_data_step_root(self):
        found = self.step.find_data_step_root(self.start_file)
        self.assertEqual(found.resolve(), self.data_steps.resolve())

    def test_init_steps_is_idempotent_for_same_root(self):
        self.step.init_steps(root=self.start_file)
        metadata_ref = self.step.metadata
        self.step.init_steps(root=self.start_file)
        self.assertIs(self.step.metadata, metadata_ref)

    def test_obtain_collects_and_caches_on_second_call(self):
        self.step.init_steps(root=self.start_file)
        calls = {"n": 0}

        def collector(**kwargs):
            calls["n"] += 1
            return pd.DataFrame({"v": [calls["n"]]})

        first = self.step.obtain("01 source/test.parquet", collector)
        second = self.step.obtain("01 source/test.parquet", collector)

        self.assertEqual(first.get_status(), REFRESHED)
        self.assertEqual(second.get_status(), CACHED)
        self.assertEqual(calls["n"], 1)
        pd.testing.assert_frame_equal(first.data_frame(), second.data_frame())

    def test_obtain_dependent_links_source_and_product(self):
        self.step.init_steps(root=self.start_file)
        source = self.data_steps / "01 source" / "raw.csv"
        source.parent.mkdir(parents=True)
        source.write_text("a\n1\n", encoding="utf-8")

        def collector(source_file=None, **kwargs):
            content = source_file.read_text(encoding="utf-8")
            return pd.DataFrame({"raw": [content.strip()]})

        result = self.step.obtain_dependent(
            "02 derived/out.parquet",
            collector,
            source,
        )
        self.assertEqual(result.get_status(), REFRESHED)

        meta = json.loads((self.data_steps / "_metadata.json").read_text(encoding="utf-8"))
        product_key = "02 derived/out.parquet"
        self.assertIn(product_key, meta)
        source_token = self.step.metadata.as_token(str(source))
        self.assertIn(source_token, meta[product_key]["dependencies"])

    def test_force_read_data_triggers_refresh(self):
        self.step.init_steps(root=self.start_file)
        calls = {"n": 0}

        def collector(**kwargs):
            calls["n"] += 1
            return pd.DataFrame({"v": [calls["n"]]})

        self.step.obtain("force.parquet", collector)
        self.step.obtain("force.parquet", collector)
        self.assertEqual(calls["n"], 1)

        self.step.force_read_data()
        refreshed = self.step.obtain("force.parquet", collector)
        self.assertEqual(refreshed.get_status(), REFRESHED)
        self.assertEqual(calls["n"], 2)

    def test_keep_cached_avoids_second_collector_call(self):
        self.step.init_steps(root=self.start_file)
        calls = {"n": 0}

        def collector(**kwargs):
            calls["n"] += 1
            return pd.DataFrame({"v": [calls["n"]]})

        first = self.step.obtain("mem.parquet", collector, keep_cached=True)
        second = self.step.obtain("mem.parquet", collector, keep_cached=True)
        self.assertEqual(first.get_status(), REFRESHED)
        self.assertIs(second, first)
        self.assertEqual(calls["n"], 1)

    def test_read_and_save_featured_parquet(self):
        self.step.init_steps(root=self.start_file)
        df = pd.DataFrame({"a": [1, 2]})
        target = self.data_steps / "io.parquet"
        self.step.save_to_featured_file(df, target)
        loaded = self.step.read_featured_file(target)
        pd.testing.assert_frame_equal(loaded, df)

    def test_get_absolute_file_path_creates_parent_dirs(self):
        self.step.init_steps(root=self.start_file)
        path = self.step.get_absolute_file_path(f"{ASSETS_SNAPSHOT_STEP}/2026-01-01.parquet")
        self.assertTrue(path.parent.is_dir())
        self.assertEqual(path.parent.resolve(), (self.data_steps / ASSETS_SNAPSHOT_STEP).resolve())

    def test_obtain_cleans_metadata_on_collector_failure(self):
        self.step.init_steps(root=self.start_file)

        def failing_collector(**kwargs):
            raise RuntimeError("collect failed")

        with self.assertRaises(RuntimeError):
            self.step.obtain("broken.parquet", failing_collector)

        meta = json.loads((self.data_steps / "_metadata.json").read_text(encoding="utf-8"))
        self.assertNotIn("broken.parquet", meta)

    def test_data_step_frame_as_collector_result_is_unwrapped(self):
        self.step.init_steps(root=self.start_file)

        def collector(**kwargs):
            inner = pd.DataFrame({"x": [1]})
            return DataStepFrame(status=REFRESHED, data=inner, data_set="ignored")

        result = self.step.obtain("wrapped.parquet", collector)
        self.assertIsInstance(result, DataStepFrame)
        self.assertEqual(result.get_status(), REFRESHED)


class MetadataHomePathTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_steps = Path(self._tmpdir.name) / "data_steps"
        self.data_steps.mkdir()
        (self.data_steps / "_metadata.json").write_text("{}", encoding="utf-8")
        self.metadata = Metadata(self.data_steps)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_home_path_token_for_file_outside_data_steps(self):
        external = Path(self.metadata._home) / "data_step_external_test.parquet"
        pd.DataFrame({"x": [1]}).to_parquet(external)
        self.addCleanup(lambda: external.unlink(missing_ok=True))
        token = self.metadata.as_token(str(external))
        self.assertTrue(token.startswith(HOME_PATH))
        self.assertEqual(self.metadata.token_as_path(token), external)


if __name__ == "__main__":
    unittest.main()
