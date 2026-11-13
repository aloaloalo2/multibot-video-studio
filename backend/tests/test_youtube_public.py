import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import youtube_public as youtube

CHANNEL='UC'+'a'*22
VIDEO='abcdefghijk'

class PublicYouTubeTests(unittest.TestCase):
    def test_current_and_classic_channel_layouts(self):
        data={'items':[{'lockupViewModel':{'contentId':VIDEO,'contentType':'LOCKUP_CONTENT_TYPE_VIDEO','metadata':{'lockupMetadataViewModel':{'metadata':{'contentMetadataViewModel':{'metadataRows':[{'metadataParts':[{'accessibilityLabel':'18 thousand views'},{'accessibilityLabel':'2 weeks ago'}]}]}}}}}}, {'videoRenderer':{'videoId':'12345678901','publishedTimeText':{'simpleText':'3 days ago'}}}]}
        self.assertEqual(youtube.cards(data),[{'id':VIDEO,'age':14},{'id':'12345678901','age':3}])
    def test_exact_watch_metadata_and_channel_identity(self):
        data={'videoDetails':{'videoId':VIDEO,'channelId':CHANNEL,'lengthSeconds':'721','viewCount':'30456','title':'Title'},'microformat':{'playerMicroformatRenderer':{'publishDate':'2026-11-06T12:46:34-08:00'}}}
        with patch.object(youtube,'page',return_value='var ytInitialPlayerResponse = '+json.dumps(data)+';'):
            result=youtube.video(VIDEO,CHANNEL)
            self.assertEqual(result['views'],30456)
            self.assertEqual(result['duration'],721)
            self.assertEqual(result['published_ts'],1793997994)
            with self.assertRaises(ValueError):youtube.video(VIDEO,'UC'+'b'*22)
    def test_missing_date_never_gets_invented(self):
        data={'videoDetails':{'videoId':VIDEO,'channelId':CHANNEL,'lengthSeconds':'5','viewCount':'1'},'microformat':{}}
        with patch.object(youtube,'page',return_value='ytInitialPlayerResponse = '+json.dumps(data)):
            with self.assertRaises(ValueError):youtube.video(VIDEO,CHANNEL)
    def test_public_counts_and_relative_age(self):
        self.assertEqual(youtube.count('8.99M subscribers'),8990000)
        self.assertEqual(youtube.count('1,204 subscribers'),1204)
        self.assertIsNone(youtube.count('Subscribers hidden'))
        self.assertEqual(youtube.age_days('Streamed 2 weeks ago'),14)
        self.assertEqual(youtube.age_days('3 months ago'),90)
    def test_collection_handles_partial_failure_and_hidden_subscribers(self):
        initial={'metadata':{'channelMetadataRenderer':{'externalId':CHANNEL,'title':'C'}},'header':{}}
        with patch.object(youtube,'page',return_value='ytInitialData = '+json.dumps(initial)),patch.object(youtube,'cards',return_value=[{'id':VIDEO,'age':5},{'id':'12345678901','age':6}]),patch.object(youtube,'video',side_effect=[{'id':VIDEO},ValueError('Unavailable')]):
            result=youtube.collect(CHANNEL)
            self.assertEqual(result['videos'],[{'id':VIDEO}])
            self.assertEqual(result['failed_videos'],1)
            self.assertIsNone(result['subscribers'])
    def test_invalid_identity_never_fetches(self):
        with patch.object(youtube,'page') as page,self.assertRaises(Exception):youtube.collect('http://127.0.0.1')
        page.assert_not_called()

    def test_members_only_content_is_an_expected_exclusion(self):
        data={'playabilityStatus':{'status':'UNPLAYABLE','reason':'Available to channel members',
              'errorScreen':{'playerLegacyDesktopYpcOfferRenderer':{'offerId':'sponsors_only_video'}}}}
        with patch.object(youtube,'page',return_value='ytInitialPlayerResponse = '+json.dumps(data)):
            with self.assertRaises(youtube.SkippedVideo):youtube.video(VIDEO,CHANNEL)
        initial={'metadata':{'channelMetadataRenderer':{'externalId':CHANNEL,'title':'C'}}}
        with patch.object(youtube,'page',return_value='ytInitialData = '+json.dumps(initial)),patch.object(youtube,'cards',return_value=[{'id':VIDEO,'age':5}]),patch.object(youtube,'video',side_effect=youtube.SkippedVideo('members only')):
            result=youtube.collect(CHANNEL)
        self.assertEqual(result['failed_videos'],0);self.assertEqual(result['skipped_videos'],1);self.assertEqual(result['videos'],[])

    def test_generic_playback_failure_stays_retryable(self):
        data={'playabilityStatus':{'status':'UNPLAYABLE','reason':"This content isn't available. Try again later."}}
        with patch.object(youtube,'page',return_value='ytInitialPlayerResponse = '+json.dumps(data)):
            with self.assertRaises(ValueError) as error:youtube.video(VIDEO,CHANNEL)
        self.assertNotIsInstance(error.exception,youtube.SkippedVideo)

    def test_partial_retry_reuses_fresh_videos_and_keeps_old_failed_metadata(self):
        import time
        initial={'metadata':{'channelMetadataRenderer':{'externalId':CHANNEL,'title':'C'}}}
        previous={'updated_at':time.time(),'videos':[{'id':VIDEO,'views':4000},
            {'id':'12345678901','views':6000,'fetched_at':0}]}
        with patch.object(youtube,'page',return_value='ytInitialData = '+json.dumps(initial)),patch.object(youtube,'cards',return_value=[{'id':VIDEO,'age':5},{'id':'12345678901','age':6}]),patch.object(youtube,'video',side_effect=ValueError('Temporary failure')) as fetch:
            result=youtube.collect(CHANNEL,previous)
        fetch.assert_called_once_with('12345678901',CHANNEL)
        self.assertEqual(result['videos'],previous['videos']);self.assertEqual(result['failed_video_ids'],['12345678901'])

    def test_failed_pagination_keeps_first_page_and_saved_peers(self):
        initial={'metadata':{'channelMetadataRenderer':{'externalId':CHANNEL,'title':'C'}},'continuationCommand':{'token':'next'}}
        raw='ytcfg.set('+json.dumps({'INNERTUBE_CONTEXT':{'client':{}}})+');ytInitialData = '+json.dumps(initial)
        previous={'updated_at':0,'videos':[{'id':'12345678901','views':6000}]}
        with patch.object(youtube,'page',return_value=raw),patch.object(youtube,'cards',return_value=[{'id':VIDEO,'age':2}]),patch.object(youtube,'continuation',side_effect=RuntimeError('Unavailable')),patch.object(youtube,'video',return_value={'id':VIDEO,'views':9000}):
            result=youtube.collect(CHANNEL,previous)
        self.assertTrue(result['pagination_incomplete']);self.assertEqual({v['id'] for v in result['videos']},{VIDEO,'12345678901'})

    def test_pagination_skips_non_json_config_setters(self):
        initial={'metadata':{'channelMetadataRenderer':{'externalId':CHANNEL,'title':'C'}},'continuationCommand':{'token':'next'}}
        raw="ytcfg.set('EMERGENCY', 'x');ytcfg.set("+json.dumps({'INNERTUBE_CONTEXT':{'client':{'clientName':'WEB'}}})+");var ytInitialData = "+json.dumps(initial)
        with patch.object(youtube,'page',return_value=raw),patch.object(youtube,'cards',side_effect=[[{'id':VIDEO,'age':2}],[{'id':'12345678901','age':95}]]),patch.object(youtube,'continuation',return_value={}) as more,patch.object(youtube,'video',return_value={'id':VIDEO}):
            result=youtube.collect(CHANNEL)
            more.assert_called_once_with('next',{'client':{'clientName':'WEB'}})
            self.assertEqual(len(result['videos']),2)
