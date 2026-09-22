"""Offline publication of the frozen Book selection, with no workspace metadata."""
from server.manuscript.exports import paragraphs, xml_text

CSS = """
:root { color-scheme: light; font-family: Georgia, 'Times New Roman', serif; color: #25231f; background: #faf8f3; }
* { box-sizing: border-box; }
body { margin: 0; font-size: 1.125rem; line-height: 1.75; overflow-wrap: anywhere; }
.book { max-width: 72ch; margin: 0 auto; padding: 4rem 2rem 6rem; }
.title-page { padding: 3rem 0 4rem; border-bottom: 1px solid #cfc8bb; margin-bottom: 3rem; }
h1, h2, h3 { line-height: 1.25; font-weight: normal; text-wrap: balance; }
h1 { font-size: 2.6em; margin: 0 0 .6em; }
h2 { font-size: 1.8em; margin: 0 0 1.4em; }
h3 { font-size: 1.25em; margin: 2em 0 1em; }
.author { color: #575044; margin: 0; font-size: 1.15em; }
.contents { padding-bottom: 2rem; border-bottom: 1px solid #cfc8bb; }
.contents h2 { font-size: 1.4em; margin-bottom: .75em; }
.contents ol { padding-left: 1.5em; }
.contents li { padding: .25em 0; }
a { color: #68451d; text-underline-offset: .2em; }
a:focus-visible, [tabindex]:focus-visible { outline: 2px solid #68451d; outline-offset: 4px; }
.chapter { margin-top: 4rem; }
.passage { margin: 0 0 .85em; white-space: pre-wrap; }
.scene-break { text-align: center; margin: 2em 0; letter-spacing: .4em; }
@media (max-width: 600px) {
  .book { padding: 1.5rem 1.15rem 3rem; }
  .title-page { padding: 2rem 0; margin-bottom: 2rem; }
  h1 { font-size: 2em; } h2 { font-size: 1.5em; }
  .chapter { margin-top: 3rem; }
}
@media print {
  @page { margin: 20mm; }
  :root { background: white; color: black; }
  body { font-size: 11pt; line-height: 1.5; }
  .book { max-width: none; margin: 0; padding: 0; }
  .title-page { padding: 25mm 0; }
  .chapter { break-before: page; margin-top: 0; }
  h1, h2, h3 { break-after: avoid; }
  p { orphans: 3; widows: 3; }
  a { color: black; text-decoration: none; }
  a:focus-visible, [tabindex]:focus-visible { outline: none; }
}
""".strip()


def chapter_body(chapter, number, headings):
    parts = [f'<section class="chapter" aria-labelledby="chapter-{number}">',
             f'<h2 id="chapter-{number}" tabindex="-1">{xml_text(chapter["title"])}</h2>']
    for index, scene in enumerate(chapter['scenes']):
        if headings:
            parts.append(f'<h3>{xml_text(scene["title"])}</h3>')
        elif index:
            parts.append('<p class="scene-break" aria-label="Scene break">* * *</p>')
        for passage in scene['passages']:
            parts.extend('<p class="passage">' + xml_text(part).replace('\n', '<br>') + '</p>'
                         for part in paragraphs(passage['text']))
    return ''.join(parts) + '</section>'


def export_html(document):
    title, author = xml_text(document['title']), xml_text(document['author'])
    parts = ['<!DOCTYPE html><html lang="' + xml_text(document['language']) + '"><head>',
             '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
             f'<title>{title}</title>']
    if author:
        parts.append(f'<meta name="author" content="{author}">')
    parts.extend([f'<style>{CSS}</style></head><body><main class="book">',
                  f'<header class="title-page"><h1>{title}</h1>'])
    if author:
        parts.append(f'<p class="author">{author}</p>')
    parts.append('</header>')
    if document.get('html_contents', True):
        parts.append('<nav class="contents" aria-labelledby="contents-title"><h2 id="contents-title">Contents</h2><ol>')
        parts.extend(f'<li><a href="#chapter-{number}">{xml_text(chapter["title"])}</a></li>'
                     for number, chapter in enumerate(document['chapters'], 1))
        parts.append('</ol></nav>')
    parts.extend(chapter_body(chapter, number, document['scene_headings'])
                 for number, chapter in enumerate(document['chapters'], 1))
    return (''.join(parts) + '</main></body></html>').encode('utf-8')
