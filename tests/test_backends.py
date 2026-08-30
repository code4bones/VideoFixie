import unittest

from videofixie.domain.backends import (
    VAPOURSYNTH_BACKEND_SLUG,
    VIDEO2X_BACKEND_SLUG,
    backend_by_slug,
    bundled_processing_backends,
)
from videofixie.domain.profiles import bundled_profiles


class ProcessingBackendsTest(unittest.TestCase):
    def test_registry_contains_video2x_backend(self) -> None:
        backends = bundled_processing_backends()

        self.assertEqual(backends[0].slug, VIDEO2X_BACKEND_SLUG)
        self.assertEqual(backend_by_slug(VIDEO2X_BACKEND_SLUG), backends[0])
        self.assertEqual(backends[1].slug, VAPOURSYNTH_BACKEND_SLUG)
        self.assertEqual(backend_by_slug(VAPOURSYNTH_BACKEND_SLUG), backends[1])

    def test_bundled_profiles_are_video2x_compatible(self) -> None:
        for profile in bundled_profiles()[:3]:
            self.assertTrue(profile.supports_backend(VIDEO2X_BACKEND_SLUG))

    def test_vapoursynth_profiles_are_separate_from_video2x_profiles(self) -> None:
        vapoursynth_profiles = [profile for profile in bundled_profiles() if profile.supports_backend(VAPOURSYNTH_BACKEND_SLUG)]

        self.assertEqual([profile.slug for profile in vapoursynth_profiles], ["vapoursynth-lanczos-x2", "vapoursynth-bicubic-x2"])
        for profile in vapoursynth_profiles:
            self.assertFalse(profile.supports_backend(VIDEO2X_BACKEND_SLUG))
