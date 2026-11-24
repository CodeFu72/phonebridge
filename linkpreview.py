"""On-demand link previews: page title, site and thumbnail.

Nothing is fetched until the user clicks Preview on a link. Only http(s)
URLs are fetched, downloads are size-capped, and nothing is written to disk.
"""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
import urllib.request

PAGE_LIMIT = 1024 * 1024        # read at most 1 MiB of HTML
IMAGE_LIMIT = 4 * 1024 * 1024   # and at most 4 MiB of thumbnail
TIMEOUT = 8
AGENT = 'Mozilla/5.0 (X11; Linux x86_64) PhoneBridge-LinkPreview/1.0'


class _HttpOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlparse(newurl).scheme not in ('http', 'https'):
            raise ValueError('Link redirected somewhere that is not a web page.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_HttpOnlyRedirect())


def _read(url, limit, accept):
    if urlparse(url).scheme not in ('http', 'https'):
        raise ValueError('Only web links can be previewed.')
    request = urllib.request.Request(url, headers={'User-Agent': AGENT, 'Accept': accept,
                                                   'Accept-Language': 'en-US,en;q=0.8'})
    with _opener.open(request, timeout=TIMEOUT) as response:
        data = response.read(limit + 1)
        return response.geturl(), response.headers.get_content_type(), response.headers.get_content_charset(), data[:limit]


class _Meta(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.title, self._in_title = {}, '', False

    def handle_starttag(self, tag, attrs):
        attrs = {k.lower(): (v or '') for k, v in attrs}
        if tag == 'meta':
            key = (attrs.get('property') or attrs.get('name') or '').lower()
            if key and 'content' in attrs and key not in self.meta:
                self.meta[key] = attrs['content'].strip()
        elif tag == 'title':
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and len(self.title) < 300:
            self.title += data


def parse_page(html, base_url):
    """Pull title, description, site name and image URL out of page HTML."""
    parser = _Meta()
    try:
        parser.feed(html)
    except Exception:  # malformed HTML: keep whatever was found
        pass
    meta = parser.meta
    title = meta.get('og:title') or meta.get('twitter:title') or ' '.join(parser.title.split())
    image = meta.get('og:image:secure_url') or meta.get('og:image') or meta.get('twitter:image') or ''
    return {
        'title': title[:200],
        'description': (meta.get('og:description') or meta.get('description') or meta.get('twitter:description') or '')[:300],
        'site': meta.get('og:site_name') or urlparse(base_url).hostname or '',
        'image_url': urljoin(base_url, image) if image else '',
        'is_video': meta.get('og:type', '').startswith('video') or 'og:video' in meta or 'og:video:url' in meta,
    }


def fetch_preview(url):
    """Blocking: call from a worker thread. Returns dict with optional 'image' bytes."""
    final_url, content_type, charset, data = _read(url, PAGE_LIMIT, 'text/html,application/xhtml+xml;q=0.9,image/*;q=0.8')
    if content_type.startswith('image/'):
        return {'title': urlparse(final_url).path.rsplit('/', 1)[-1] or final_url, 'description': '',
                'site': urlparse(final_url).hostname or '', 'image_url': final_url, 'is_video': False,
                'image': data if len(data) < PAGE_LIMIT else None, 'url': final_url}
    if content_type.startswith('video/'):
        return {'title': 'Video file', 'description': 'Open it in your browser to watch.',
                'site': urlparse(final_url).hostname or '', 'image_url': '', 'is_video': True, 'image': None, 'url': final_url}
    html = data.decode(charset or 'utf-8', errors='replace')
    info = parse_page(html, final_url)
    info['url'] = final_url
    info['image'] = None
    if info['image_url']:
        try:
            _, image_type, _, image = _read(info['image_url'], IMAGE_LIMIT, 'image/*')
            if image_type.startswith('image/') and len(image) < IMAGE_LIMIT:
                info['image'] = image
        except Exception:
            info['image'] = None
    return info
