import unittest
from pathlib import Path
from unittest import mock

import internal_logo_sensor as sensor
import wedo_movies_detector as wedo
from multiwindow_logo_experiment import learning_windows
from video_frame_bounds import last_frame_seconds, sample_seconds_within_video


class VideoEndBoundsTests(unittest.TestCase):
    def capture(self, count=100, fps=25):
        capture = mock.Mock()
        capture.get.side_effect = lambda prop: {sensor.cv2.CAP_PROP_FRAME_COUNT: count,
                                               sensor.cv2.CAP_PROP_FPS: fps}[prop]
        capture.read.return_value = (True, "frame")
        return capture

    def test_all_eight_reported_container_tails_are_excluded(self):
        for duration in (9060.02, 6440.015, 7140.021667, 8420.015,
                         6060.02, 8960.006667, 7460.016667, 7580.016667):
            with self.subTest(duration=duration):
                count = int(duration) * 25
                times = sample_seconds_within_video(duration, count, 25, 20)
                self.assertEqual(times[-1], int(duration) - 20)
                self.assertLessEqual(max(times), last_frame_seconds(count, 25))

    def test_exact_video_end_and_partial_frame_times(self):
        self.assertEqual(sample_seconds_within_video(40, 1000, 25, 20), [0, 20])
        self.assertEqual(sample_seconds_within_video(40.02, 1001, 25, 20), [0, 20, 40])
        self.assertEqual(sample_seconds_within_video(.04, 1, 25, 20), [0])

    def test_shared_reader_uses_last_frame_for_container_endpoint(self):
        for second in (3.96, 4.0, 4.021667):
            with self.subTest(second=second):
                capture = self.capture()
                self.assertEqual(sensor.read_frame_at(capture, second), "frame")
                capture.set.assert_called_once_with(sensor.cv2.CAP_PROP_POS_FRAMES, 99)

    def test_interior_seek_and_decode_failure_are_unchanged(self):
        capture = self.capture()
        self.assertEqual(sensor.read_frame_at(capture, 2), "frame")
        capture.set.assert_called_once_with(sensor.cv2.CAP_PROP_POS_MSEC, 2000)
        capture.read.return_value = (False, None)
        self.assertIsNone(sensor.read_frame_at(capture, 2))

    def test_missing_frame_metadata_keeps_normal_decode(self):
        capture = self.capture(count=0, fps=0)
        self.assertEqual(sensor.read_frame_at(capture, 2), "frame")
        capture.set.assert_called_once_with(sensor.cv2.CAP_PROP_POS_MSEC, 2000)

    def test_invalid_timestamps_do_not_seek(self):
        capture = self.capture()
        for second in (-1, float("nan"), float("inf")):
            self.assertIsNone(sensor.read_frame_at(capture, second))
        capture.set.assert_not_called()

    def test_wedo_bumper_does_not_decode_beyond_last_frame(self):
        capture = self.capture(count=100, fps=25)
        capture.isOpened.return_value = True
        with mock.patch.object(wedo.cv2, "VideoCapture", return_value=capture), \
                mock.patch.object(wedo, "_load_logo_mask"), \
                mock.patch.object(wedo, "_bumper_frame_features", return_value={}):
            result = wedo._find_branded_bumper_cut(
                video_path=Path("film.mp4"), fps=25, earliest_seconds=3.96,
                logo_return_seconds=4.02, logo_mask_path=Path("logo.txt"))
        self.assertIsNone(result)
        capture.set.assert_called_once_with(wedo.cv2.CAP_PROP_POS_FRAMES, 99)
        capture.read.assert_called_once()
        capture.release.assert_called_once()

    def test_wedo_bumper_entirely_outside_video_never_seeks(self):
        capture = self.capture(count=100, fps=25)
        with mock.patch.object(wedo.cv2, "VideoCapture", return_value=capture), \
                mock.patch.object(wedo, "_load_logo_mask"):
            result = wedo._find_branded_bumper_cut(
                video_path=Path("film.mp4"), fps=25, earliest_seconds=4,
                logo_return_seconds=4.02, logo_mask_path=Path("logo.txt"))
        self.assertIsNone(result)
        capture.set.assert_not_called()
        capture.read.assert_not_called()

    def test_six_minute_learning_guards_remain_intact(self):
        windows = learning_windows(9060.02)
        self.assertTrue(all(w.start_seconds >= 360 and w.end_seconds <= 9060.02-360 for w in windows))


if __name__ == "__main__":
    unittest.main()
