#!/usr/bin/env python
# Copyright (c) 2012 Amazon.com, Inc. or its affiliates.  All Rights Reserved
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish, dis-
# tribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the fol-
# lowing conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABIL-
# ITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
# SHALL THE AUTHOR BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#
from Queue import Queue

import mock
from tests.unit import unittest
from tests.unit import AWSMockServiceTestCase

from boto.glacier.concurrent import ConcurrentUploader, ConcurrentDownloader


class FakeThreadedConcurrentUploader(ConcurrentUploader):
    def _start_upload_threads(self, results_queue, upload_id,
                              worker_queue, filename):
        self.results_queue = results_queue
        self.worker_queue = worker_queue
        self.upload_id = upload_id

    def _wait_for_upload_threads(self, hash_chunks, result_queue, total_parts):
        for i in xrange(total_parts):
            hash_chunks[i] = 'foo'

class FakeThreadedConcurrentDownloader(ConcurrentDownloader):
    def _start_download_threads(self, results_queue, worker_queue):
        self.results_queue = results_queue
        self.worker_queue = worker_queue

    def _wait_for_download_threads(self, filename, result_queue, total_parts):
        pass


class TestConcurrentUploader(unittest.TestCase):

    def setUp(self):
        super(TestConcurrentUploader, self).setUp()
        self.stat_patch = mock.patch('os.stat')
        self.stat_mock = self.stat_patch.start()
        # Give a default value for tests that don't care
        # what the file size is.
        self.stat_mock.return_value.st_size = 1024 * 1024 * 8

    def tearDown(self):
        self.stat_mock = self.stat_patch.start()

    def test_calculate_required_part_size(self):
        self.stat_mock.return_value.st_size = 1024 * 1024 * 8
        uploader = ConcurrentUploader(mock.Mock(), 'vault_name')
        total_parts, part_size = uploader._calculate_required_part_size(
            1024 * 1024 * 8)
        self.assertEqual(total_parts, 2)
        self.assertEqual(part_size, 4 * 1024 * 1024)

    def test_calculate_required_part_size_too_small(self):
        too_small = 1 * 1024 * 1024
        self.stat_mock.return_value.st_size = 1024 * 1024 * 1024
        uploader = ConcurrentUploader(mock.Mock(), 'vault_name',
                                      part_size=too_small)
        total_parts, part_size = uploader._calculate_required_part_size(
            1024 * 1024 * 1024)
        self.assertEqual(total_parts, 256)
        # Part size if 4MB not the passed in 1MB.
        self.assertEqual(part_size, 4 * 1024 * 1024)

    def test_work_queue_is_correctly_populated(self):
        uploader = FakeThreadedConcurrentUploader(mock.MagicMock(),
                                                  'vault_name')
        uploader.upload('foofile')
        q = uploader.worker_queue
        items = [q.get() for i in xrange(q.qsize())]
        self.assertEqual(items[0], (0, 4 * 1024 * 1024))
        self.assertEqual(items[1], (1, 4 * 1024 * 1024))
        # 2 for the parts, 10 for the end sentinels (10 threads).
        self.assertEqual(len(items), 12)

    def test_correct_low_level_api_calls(self):
        api_mock = mock.MagicMock()
        uploader = FakeThreadedConcurrentUploader(api_mock, 'vault_name')
        uploader.upload('foofile')
        # The threads call the upload_part, so we're just verifying the
        # initiate/complete multipart API calls.
        api_mock.initiate_multipart_upload.assert_called_with(
            'vault_name', 4 * 1024 * 1024, None)
        api_mock.complete_multipart_upload.assert_called_with(
            'vault_name', mock.ANY, mock.ANY, 8 * 1024 * 1024)

    def test_downloader_work_queue_is_correctly_populated(self):
        job = mock.MagicMock()
        job.archive_size = 8 * 1024 * 1024
        downloader = FakeThreadedConcurrentDownloader(job)
        downloader.download('foofile')
        q = downloader.worker_queue
        items = [q.get() for i in xrange(q.qsize())]
        self.assertEqual(items[0], (0, 4 * 1024 * 1024))
        self.assertEqual(items[1], (1, 4 * 1024 * 1024))
        # 2 for the parts, 10 for the end sentinels (10 threads).
        self.assertEqual(len(items), 12)


if __name__ == '__main__':
    unittest.main()
