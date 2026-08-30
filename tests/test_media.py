import unittest

from videofixie.domain.media import MediaInfo


class MediaInfoTest(unittest.TestCase):
    def test_media_info_from_ffprobe_json_parses_relevant_streams(self) -> None:
        data = {
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 500,
                    "height": 360,
                    "avg_frame_rate": "25/1",
                    "r_frame_rate": "25/1",
                    "duration": "1487.840000",
                    "bit_rate": "385180",
                    "pix_fmt": "yuv420p",
                    "field_order": "progressive",
                    "display_aspect_ratio": "25:18",
                    "nb_frames": "37196",
                },
                {
                    "index": 1,
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "channels": 2,
                    "channel_layout": "stereo",
                    "sample_rate": "44100",
                    "duration": "1487.377415",
                    "bit_rate": "151978",
                    "tags": {"language": "und"},
                },
            ],
            "format": {
                "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                "duration": "1487.840000",
                "size": "100844041",
                "bit_rate": "542230",
            },
        }

        media = MediaInfo.from_ffprobe_json(data, "samples/1.mp4")

        self.assertIsNotNone(media.primary_video)
        assert media.primary_video is not None
        self.assertEqual(media.primary_video.width, 500)
        self.assertEqual(media.primary_video.height, 360)
        self.assertEqual(media.primary_video.fps, 25.0)
        self.assertEqual(media.primary_video.scan_type, "progressive")
        self.assertEqual(media.audio_streams[0].codec_name, "aac")
        self.assertEqual(media.duration_seconds, 1487.84)
