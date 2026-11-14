"""The YouTube Data API reader with mocked answers: paging, skipped uploads, errors and the fallback."""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import trending_videos
import youtube_api

CID = 'UC' + 'a' * 22


def iso(days):
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - days * 86400))


class YoutubeApiTest(unittest.TestCase):
    def answers(self, resource, secret, **params):
        self.calls.append((resource, params))
        self.assertEqual(secret, 'KEY')
        if resource == 'channels':
            return {'items': [{'snippet': {'title': 'Канал'}, 'statistics': {'subscriberCount': '1200'},
                               'contentDetails': {'relatedPlaylists': {'uploads': 'UU' + 'a' * 22}}}]}
        if resource == 'playlistItems':
            if not params.get('pageToken'):
                return {'items': [{'contentDetails': {'videoId': 'v%09d' % i, 'videoPublishedAt': iso(i)}} for i in range(50)], 'nextPageToken': 'p2'}
            return {'items': [{'contentDetails': {'videoId': 'w%09d' % i, 'videoPublishedAt': iso(60 + i * 5)}} for i in range(20)], 'nextPageToken': 'p3'}
        ids = params['id'].split(',')
        items = []
        for n, identity in enumerate(ids):
            item = {'id': identity, 'snippet': {'title': 'T ' + identity, 'publishedAt': iso(n), 'liveBroadcastContent': 'none'},
                    'contentDetails': {'duration': 'PT2M59S'}, 'statistics': {'viewCount': str(1000 + n)}}
            if identity == ids[0]:
                item['snippet']['liveBroadcastContent'] = 'upcoming'
            items.append(item)
        return {'items': items}

    def test_collects_uploads_of_the_last_hundred_days_in_batches(self):
        self.calls = []
        with patch.object(youtube_api, 'call', side_effect=self.answers):
            result = youtube_api.collect(CID, 'KEY')
        self.assertEqual((result['name'], result['subscribers'], result['source']), ('Канал', 1200, 'youtube-api'))
        self.assertEqual([c[0] for c in self.calls], ['channels', 'playlistItems', 'playlistItems', 'videos', 'videos'])
        # the second page passes 100 days at its ninth upload (60 + 8 * 5): 50 + 8 ids, two of them upcoming
        self.assertEqual(len(result['videos']), 56)
        self.assertEqual(result['skipped_videos'], 2)
        self.assertFalse(result['sample_truncated'])
        self.assertEqual(result['videos'][0]['duration'], 179)

    def test_a_failing_key_falls_back_to_the_public_pages_for_the_whole_refresh(self):
        trending_videos.API_NOTE.clear()
        with patch.object(youtube_api, 'key', return_value='KEY'), \
                patch.object(youtube_api, 'collect', side_effect=youtube_api.ApiError('денний ліміт ключа вичерпано')) as api, \
                patch.object(trending_videos.youtube_public, 'collect', return_value={'source': 'youtube-public'}) as public:
            self.assertEqual(trending_videos.collect(CID)['source'], 'youtube-public')
            self.assertEqual(trending_videos.collect(CID)['source'], 'youtube-public')
        self.assertEqual((api.call_count, public.call_count), (1, 2))
        self.assertIn('ліміт', trending_videos.API_NOTE[0])
        self.assertNotIn('KEY', trending_videos.API_NOTE[0])
        trending_videos.API_NOTE.clear()

    def test_without_a_key_only_the_public_pages_are_read(self):
        with patch.object(youtube_api, 'key', return_value=None), patch.object(youtube_api, 'collect') as api, \
                patch.object(trending_videos.youtube_public, 'collect', return_value={'source': 'youtube-public'}):
            self.assertEqual(trending_videos.collect(CID)['source'], 'youtube-public')
        api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
