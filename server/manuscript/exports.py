"""Small, self-contained DOCX and EPUB packages; publication content only."""
import html
import io
import re
import zipfile
from uuid import UUID

from server.manuscript.word import word_parts

XML = '<?xml version="1.0" encoding="UTF-8"?>'
CSS = 'body{font-family:serif;line-height:1.5;margin:5%;}h1,h2{text-align:left;font-weight:normal;}p{margin:0 0 .5em;text-indent:1.2em;}h1+p,h2+p{text-indent:0;}.scene-break{text-align:center;text-indent:0;margin:1.5em 0;}'


def xml_text(value):
    return html.escape(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]', '\ufffd', value), quote=True)


def paragraphs(text):
    return [part for part in re.split(r'\n\s*\n', text.replace('\r\n', '\n').replace('\r', '\n')) if part.strip()]


def package(parts, mimetype=None):
    target = io.BytesIO()
    with zipfile.ZipFile(target, 'w') as archive:
        if mimetype:
            item = zipfile.ZipInfo('mimetype', date_time=(1980, 1, 1, 0, 0, 0))
            archive.writestr(item, mimetype, compress_type=zipfile.ZIP_STORED)
        for path, text in parts.items():
            item = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, text.encode('utf-8'))
    return target.getvalue()


def export_docx(document):
    return package(word_parts(document, xml_text, paragraphs))


def xhtml(title, body, language):
    return (XML + '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            f'xml:lang="{xml_text(language)}" lang="{xml_text(language)}"><head><title>{xml_text(title)}</title>'
            '<link rel="stylesheet" type="text/css" href="style.css"/></head><body>' + body + '</body></html>')


def chapter_html(chapter, headings):
    body = f'<h1>{xml_text(chapter["title"])}</h1>'
    for index, scene in enumerate(chapter['scenes']):
        if headings:
            body += f'<h2>{xml_text(scene["title"])}</h2>'
        elif index:
            body += '<p class="scene-break">* * *</p>'
        for passage in scene['passages']:
            body += ''.join('<p>' + xml_text(part).replace('\n', '<br/>') + '</p>' for part in paragraphs(passage['text']))
    return body


def export_epub(document):
    language = document['language']
    title = xml_text(document['title'])
    parts = {'META-INF/container.xml': XML + '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
             '<rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
             'EPUB/style.css': CSS,
             'EPUB/title.xhtml': xhtml(document['title'], f'<h1>{title}</h1><p>{xml_text(document["author"])}</p>', language)}
    items, spine, links = [], [], []
    for index, chapter in enumerate(document['chapters'], 1):
        name = f'chapter-{index}'
        parts[f'EPUB/{name}.xhtml'] = xhtml(chapter['title'], chapter_html(chapter, document['scene_headings']), language)
        items.append(f'<item id="{name}" href="{name}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{name}"/>')
        links.append(f'<li><a href="{name}.xhtml">{xml_text(chapter["title"])}</a></li>')
    parts['EPUB/nav.xhtml'] = xhtml('Contents', '<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>'
                                  + ''.join(links) + '</ol></nav>', language)
    modified = document['created_at'][:19] + 'Z'
    parts['EPUB/package.opf'] = (XML + '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="book-id">urn:uuid:{UUID(document["publication_id"])}</dc:identifier><dc:title>{title}</dc:title>'
        f'<dc:language>{xml_text(language)}</dc:language><dc:creator>{xml_text(document["author"])}</dc:creator>'
        f'<meta property="dcterms:modified">{modified}</meta></metadata><manifest>'
        '<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>'
        '<item id="title" href="title.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="css" href="style.css" media-type="text/css"/>' + ''.join(items)
        + '</manifest><spine><itemref idref="title"/><itemref idref="nav"/>' + ''.join(spine) + '</spine></package>')
    return package(parts, 'application/epub+zip')
