import unittest
from model import clean_compose_text, find_links, linkify_markup
from send_test import MAX_TEXT_BYTES
from linkpreview import parse_page


class ComposeTextTests(unittest.TestCase):
    def test_single_line(self):
        self.assertEqual(clean_compose_text('a\nb\r\nc\td'), 'a\nb\nc d')

    def test_cap(self):
        self.assertEqual(len(clean_compose_text('x' * (MAX_TEXT_BYTES + 100))), MAX_TEXT_BYTES)


class LinkTests(unittest.TestCase):
    def test_trailing_punctuation_stays_outside(self):
        self.assertEqual(find_links('see https://youtu.be/abc?t=1.'), [(4, 28, 'https://youtu.be/abc?t=1')])

    def test_bare_www_gets_https(self):
        self.assertEqual(find_links('go to www.example.com/x, ok')[0][2], 'https://www.example.com/x')

    def test_balanced_parentheses_kept(self):
        self.assertEqual(find_links('(http://a.b/(c))')[0][2], 'http://a.b/(c)')

    def test_no_dotless_hosts_or_other_schemes(self):
        self.assertEqual(find_links('http://localhost file:///etc/passwd javascript:alert(1)'), [])

    def test_markup_is_escaped(self):
        self.assertEqual(linkify_markup('<b>&</b> https://x.com/?a=1&b=2'),
                         '&lt;b&gt;&amp;&lt;/b&gt; <a href="https://x.com/?a=1&amp;b=2">https://x.com/?a=1&amp;b=2</a>')

    def test_quotes_cannot_break_out_of_href(self):
        from xml.etree import ElementTree
        markup = linkify_markup('https://x.com/a"onclick=b <i>x</i>')
        tree = ElementTree.fromstring('<r>' + markup + '</r>')  # well-formed: no injected tags
        self.assertEqual([(e.tag, e.attrib) for e in tree], [('a', {'href': 'https://x.com/a'})])
        self.assertEqual(''.join(tree.itertext()), 'https://x.com/a"onclick=b <i>x</i>')


class PreviewParseTests(unittest.TestCase):
    def test_open_graph(self):
        html = ('<html><head><title>Fallback</title><meta property="og:title" content="Me at the zoo">'
                '<meta property="og:image" content="/thumb.jpg"><meta property="og:type" content="video.other">'
                '<meta property="og:site_name" content="YouTube"></head></html>')
        info = parse_page(html, 'https://www.youtube.com/watch?v=x')
        self.assertEqual(info['title'], 'Me at the zoo')
        self.assertEqual(info['image_url'], 'https://www.youtube.com/thumb.jpg')
        self.assertEqual(info['site'], 'YouTube')
        self.assertTrue(info['is_video'])

    def test_title_fallback_and_host(self):
        info = parse_page('<title>  Plain   page </title>', 'https://example.com/a')
        self.assertEqual((info['title'], info['site'], info['image_url'], info['is_video']),
                         ('Plain page', 'example.com', '', False))

    def test_broken_html_does_not_raise(self):
        self.assertIsInstance(parse_page('<meta property="og:title" content="x"><<<', 'https://e.com'), dict)


if __name__ == '__main__':
    unittest.main()
