"""Turn a job description in HTML into plain text. Shared by every source."""
import re
from html.parser import HTMLParser

# Tags that start a new line, so "<p>Remote</p><p>Full time</p>" does not become "RemoteFull time".
_BLOCK_TAGS = {
    "p", "br", "div", "li", "ul", "ol", "tr", "td", "th", "table", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "blockquote", "pre",
}
# Tags whose content is code, not text.
_SKIP_TAGS = {"script", "style"}
# Formatting tags still present after one pass mean the HTML was escaped twice
# (e.g. "&lt;p&gt;Hello&lt;/p&gt;"), which happens in a few real postings.
_LEFTOVER_TAG = re.compile(
    r"</?(?:p|br|div|span|a|li|ul|ol|h[1-6]|strong|b|em|i|u|table|tr|td|th)\b[^>]*>",
    re.IGNORECASE,
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)  # decodes &amp; &nbsp; &#39; ...
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def _strip_once(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    text = "".join(parser.parts)
    lines = (re.sub(r"[^\S\n]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def html_to_text(html: str | None) -> str:
    """Plain text from HTML: no tags, entities decoded, one space between words,
    one line per paragraph or list item. Inline tags such as <b> add nothing, so a
    formatting-only change gives the same text (and the same content_hash, Q3).
    A description escaped twice gets one more pass."""
    if not html:
        return ""
    text = _strip_once(html)
    if _LEFTOVER_TAG.search(text):
        text = _strip_once(text)
    return text