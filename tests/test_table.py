import unittest

from happybase_sql.table import (
    _row_to_key,
    _parse_filter,
    _check_filter,
)


class TableTestCase(unittest.TestCase):

    def test_row_to_key(self):
        """Should return key that is lowercased."""
        self.assertEqual(
            _row_to_key('1111-2222-aaaa-BBBB'),
            '1111-2222-aaaa-bbbb',
        )
        self.assertEqual(
            _row_to_key(1234),
            '1234',
        )

    def test_parse_filter(self):
        """
        Filter string should parse out the correct parameters and set defaults when not present.
        """
        self.assertEqual(
            _parse_filter("SingleColumnValueFilter('e', 'insta', >, 'binary:0', true, FALSE)"),
            {
                'column_family': 'e',
                'column_qualifier': 'insta',
                'comparator': '>',
                'value': '0',
                'filter_if_missing': True,
                'latest_version_only': False,
            },
        )
        self.assertEqual(
            _parse_filter("SingleColumnValueFilter('e', 'insta', >, 'binary:0')"),
            {
                'column_family': 'e',
                'column_qualifier': 'insta',
                'comparator': '>',
                'value': '0',
                'filter_if_missing': False,
                'latest_version_only': True,
            },
        )

    def test_check_filter(self):
        """
        Filters should pass or fail appropriately depending on the value and comparisons.
        """
        # Strings
        self.assertTrue(
            _check_filter(
                {
                    'a:insta': 'jon',
                },
                {
                    'column_family': 'a',
                    'column_qualifier': 'insta',
                    'comparator': '=',
                    'value': 'jon',
                },
            ),
        )
        self.assertTrue(
            _check_filter(
                {
                    'a:insta': 'jon',
                },
                {
                    'column_family': 'a',
                    'column_qualifier': 'insta',
                    'comparator': '!=',
                    'value': 'bob',
                },
            ),
        )

        # Integers
        self.assertTrue(
            _check_filter(
                {
                    'a:count': '5',
                },
                {
                    'column_family': 'a',
                    'column_qualifier': 'count',
                    'comparator': '>=',
                    'value': '4',
                },
            ),
        )
        self.assertFalse(
            _check_filter(
                {
                    'a:count': '111',
                },
                {
                    'column_family': 'a',
                    'column_qualifier': 'count',
                    'comparator': '=',
                    'value': '2222',
                },
            ),
        )

        # Date/time
        self.assertFalse(
            _check_filter(
                {
                    'a:time': '2018-04-04T07:10:49.812255+00:00',
                },
                {
                    'column_family': 'a',
                    'column_qualifier': 'time',
                    'comparator': '<',
                    'value': '2018-04-04T07:10:47.812255+00:00',
                },
            ),
        )
        self.assertTrue(
            _check_filter(
                {
                    'a:time': '2018-04-04T07:10:49.812255+00:00',
                },
                {
                    'column_family': 'a',
                    'column_qualifier': 'time',
                    'comparator': '>=',
                    'value': '2018-04-04T07:10:47.812255+00:00',
                },
            ),
        )
