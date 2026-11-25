import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import heygen_avatars


class HeyGenAvatarsTest(unittest.TestCase):
    def test_avatar_iii_support_is_checked_from_the_selected_look(self):
        with patch.object(heygen_avatars.heygen_voice, '_call', return_value={'data': {'id': 'look_1', 'supported_api_engines': ['avatar_iii']}}) as call:
            self.assertTrue(heygen_avatars.supports_avatar_iii('look_1'))
        self.assertEqual(call.call_args.args[0], '/v3/avatars/looks/look_1')
        with patch.object(heygen_avatars.heygen_voice, '_call', return_value={'data': {'id': 'look_1', 'supported_api_engines': ['avatar_iv']}}):
            self.assertFalse(heygen_avatars.supports_avatar_iii('look_1'))

    def test_lists_private_avatar_groups_with_images_and_cursor(self):
        photo = 'https://files.heygen.ai/avatar/preview.jpg?signature=example'
        response = {'data': [
            {'id': 'ag_1', 'name': 'My avatar', 'preview_image_url': photo},
            {'id': 'ag_public', 'name': 'Preset', 'ownership': 'public'},
        ], 'has_more': True, 'next_token': 'next&1'}
        with patch.object(heygen_avatars.heygen_voice, '_call', return_value=response) as call:
            self.assertEqual(heygen_avatars.page(), {'items': [
                {'id': 'ag_1', 'name': 'My avatar', 'preview_image_url': photo},
            ], 'next_token': 'next&1'})
            url = urlsplit(call.call_args.args[0])
        self.assertEqual(url.path, '/v3/avatars')
        self.assertEqual(parse_qs(url.query)['ownership'], ['private'])

    def test_looks_are_scoped_to_the_avatar_and_missing_previews_are_allowed(self):
        response = {'data': [
            {'id': 'lk_1', 'group_id': 'ag_1', 'preview_image_url': 'javascript:example'},
            {'id': 'lk_other', 'group_id': 'ag_other'},
        ], 'has_more': False}
        with patch.object(heygen_avatars.heygen_voice, '_call', return_value=response) as call:
            page = heygen_avatars.page('ag_1', 'next&1')
            url = urlsplit(call.call_args.args[0])
        self.assertEqual(url.path, '/v3/avatars/looks')
        self.assertEqual(parse_qs(url.query), {'ownership': ['private'], 'limit': ['24'],
                                              'group_id': ['ag_1'], 'token': ['next&1']})
        self.assertEqual(page['items'], [{'id': 'lk_1', 'name': '', 'preview_image_url': None}])
        self.assertIsNone(page['next_token'])
