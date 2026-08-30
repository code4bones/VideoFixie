import unittest

from videofixie.domain.backends import VIDEO2X_BACKEND_SLUG, backend_by_slug, bundled_processing_backends
from videofixie.domain.profiles import bundled_profiles


class ProcessingBackendsTest(unittest.TestCase):
    def test_registry_contains_video2x_backend(self) -> None:
        backends = bundled_processing_backends()

        self.assertEqual(backends[0].slug, VIDEO2X_BACKEND_SLUG)
        self.assertEqual(backend_by_slug(VIDEO2X_BACKEND_SLUG), backends[0])

    def test_bundled_profiles_are_video2x_compatible(self) -> None:
        for profile in bundled_profiles():
            self.assertTrue(profile.supports_backend(VIDEO2X_BACKEND_SLUG))
