"""Office Open XML with semantic styles, chapter breaks and running page numbers."""
XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'


def paragraph(text, escape, style='Normal'):
    lines = text.split('\n')
    runs = '<w:br/>'.join(f'<w:t xml:space="preserve">{escape(line)}</w:t>' for line in lines)
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr><w:r>{runs}</w:r></w:p>'


def styles():
    def style(key, name, size, properties='', run='', base='Normal'):
        return (f'<w:style w:type="paragraph" w:styleId="{key}"><w:name w:val="{name}"/>'
                f'<w:basedOn w:val="{base}"/><w:next w:val="Normal"/><w:pPr>{properties}</w:pPr>'
                f'<w:rPr><w:color w:val="000000"/><w:sz w:val="{size}"/>{run}</w:rPr></w:style>')
    return (XML + f'<w:styles xmlns:w="{W}"><w:docDefaults><w:rPrDefault><w:rPr>'
            '<w:rFonts w:ascii="Georgia" w:hAnsi="Georgia"/><w:color w:val="000000"/><w:sz w:val="24"/>'
            '</w:rPr></w:rPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
            '<w:name w:val="Normal"/><w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/>'
            '<w:widowControl/></w:pPr></w:style>'
            + style('Title', 'Title', 40, '<w:spacing w:before="1000" w:after="360"/><w:keepNext/>')
            + style('Author', 'Author', 26, '<w:spacing w:after="400"/>')
            + style('Heading1', 'heading 1', 32, '<w:pageBreakBefore/><w:keepNext/><w:outlineLvl w:val="0"/><w:spacing w:after="360"/>')
            + style('Heading2', 'heading 2', 26, '<w:keepNext/><w:outlineLvl w:val="1"/><w:spacing w:before="240" w:after="200"/>')
            + style('SceneBreak', 'Scene break', 24, '<w:jc w:val="center"/><w:spacing w:before="160" w:after="160"/>')
            + '</w:styles>')


def word_parts(document, escape, paragraphs):
    body = paragraph(document['title'], escape, 'Title')
    if document['author']:
        body += paragraph(document['author'], escape, 'Author')
    for chapter in document['chapters']:
        body += paragraph(chapter['title'], escape, 'Heading1')
        for index, scene in enumerate(chapter['scenes']):
            if document['scene_headings']:
                body += paragraph(scene['title'], escape, 'Heading2')
            elif index:
                body += paragraph('* * *', escape, 'SceneBreak')
            body += ''.join(paragraph(part, escape) for passage in scene['passages'] for part in paragraphs(passage['text']))
    body += ('<w:sectPr><w:footerReference w:type="default" r:id="footer"/><w:pgSz w:w="12240" w:h="15840"/>'
             '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')
    return {
        '[Content_Types].xml': content_types(),
        '_rels/.rels': XML + f'<Relationships xmlns="{PKG}"><Relationship Id="doc" Type="{R}/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="core" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>',
        'word/document.xml': XML + f'<w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>{body}</w:body></w:document>',
        'word/styles.xml': styles(),
        'word/_rels/document.xml.rels': XML + f'<Relationships xmlns="{PKG}"><Relationship Id="styles" Type="{R}/styles" Target="styles.xml"/>'
            f'<Relationship Id="footer" Type="{R}/footer" Target="footer.xml"/></Relationships>',
        'word/footer.xml': XML + f'<w:ftr xmlns:w="{W}"><w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
            '<w:fldSimple w:instr="PAGE"><w:r><w:t>1</w:t></w:r></w:fldSimple></w:p></w:ftr>',
        'docProps/core.xml': XML + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f'<dc:title>{escape(document["title"])}</dc:title><dc:creator>{escape(document["author"])}</dc:creator></cp:coreProperties>',
    }


def content_types():
    types = {'document': 'document.main', 'styles': 'styles', 'footer': 'footer'}
    return (XML + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            + ''.join(f'<Override PartName="/word/{part}.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml"/>'
                      for part, kind in types.items())
            + '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>')
