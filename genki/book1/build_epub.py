import html, re, zipfile, mimetypes
from pathlib import Path
from datetime import date

ROOT = Path(__file__).parent
OUT = Path.home() / 'Downloads' / 'Genki I 学习笔记.epub'
USER_COVER = Path('/Users/zeyu/Downloads/cv_book1-74a1d5707f152bde37cf88433da216c1.jpg')
KANA_ROOT = Path('/Users/zeyu/Workspace/blog/obsidian/booknotes/language/japanese/hiragana & katakana')
IMGROOT = ROOT.parents[4] / 'resources' / 'images'
LINK_MAP = {}
IMAGE_MAP = {}

def link_target(page, anchor=None):
    key = page.strip().lower()
    target = LINK_MAP.get(key)
    if not target:
        # Obsidian links often omit the numeric prefix or .md suffix.
        for k, v in LINK_MAP.items():
            if k.removesuffix('.md') == key.removesuffix('.md') or k.endswith(' ' + key):
                target = v; break
    if not target:
        return None
    return target + (f'#{anchor}' if anchor else '')

def clean_inline(s):
    # Preserve inline semantic markup through HTML escaping.
    placeholders = {}
    def hold(value):
        key = f'__EPUBTOKEN{len(placeholders)}__'
        placeholders[key] = value
        return key
    # Obsidian highlight: ==重点==
    s = re.sub(r'==(.+?)==', lambda m: hold(f'<mark>{html.escape(m.group(1), quote=False)}</mark>'), s)
    # Markdown strong emphasis: **粗体**
    s = re.sub(r'\*\*(.+?)\*\*', lambda m: hold(f'<strong>{html.escape(m.group(1), quote=False)}</strong>'), s)
    # Markdown emphasis: *斜体*
    s = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', lambda m: hold(f'<em>{html.escape(m.group(1), quote=False)}</em>'), s)
    # Ruby notation used in these notes: 店\[みせ\] and 幼稚園（ようちえん）.
    # The base is kept conservative (Japanese characters) to avoid consuming prose parentheses.
    s = re.sub(r'([一-龯々ヶ]+)\\?\[([ぁ-んァ-ンー /・]+)\\?\]',
               lambda m: hold(f'<ruby>{html.escape(m.group(1), quote=False)}<rt>{html.escape(m.group(2), quote=False)}</rt></ruby>'), s)
    s = re.sub(r'([一-龯々ヶ]+)\[([ぁ-んァ-ンー /・]+)\]',
               lambda m: hold(f'<ruby>{html.escape(m.group(1), quote=False)}<rt>{html.escape(m.group(2), quote=False)}</rt></ruby>'), s)
    s = re.sub(r'([一-龯々ヶ]+)[（(]([ぁ-んァ-ンー /・]+)[）)]',
               lambda m: hold(f'<ruby>{html.escape(m.group(1), quote=False)}<rt>{html.escape(m.group(2), quote=False)}</rt></ruby>'), s)
    def obs_image(m):
        fname = m.group(1).strip()
        src = IMAGE_MAP.get(fname.lower())
        return hold(f'<img class="note-image" src="{src}" alt="{html.escape(fname, quote=True)}"/>') if src else f'[图片: {html.escape(fname, quote=False)}]'
    s = re.sub(r'!\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', obs_image, s)
    def wiki_link(m):
        target = m.group(1).strip(); label = m.group(2) or target
        if '#' in target:
            page, anchor = target.split('#', 1)
            href = link_target(page, re.sub(r'[^\w\u3040-\u30ff\u4e00-\u9fff -]', '', anchor).strip().replace(' ', '-'))
        else:
            href = link_target(target)
        label_html = html.escape(label, quote=False)
        return hold(f'<a href="{html.escape(href, quote=True)}">{label_html}</a>') if href else label_html
    s = re.sub(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', wiki_link, s)
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1', s)
    s = s.replace('\\[', '[').replace('\\]', ']')
    escaped = html.escape(s, quote=False)
    for key, value in placeholders.items():
        escaped = escaped.replace(key, value)
    return escaped

def english_note(raw, notes, popup=True):
    """Keep English in place; inline translations are the most compatible EPUB format."""
    rendered = clean_inline(raw)
    return rendered

def md_to_xhtml(text, title):
    text = re.sub(r'^---\n.*?\n---\n?', '', text, flags=re.S)
    text = re.sub(r'^<<.*?\n', '', text, flags=re.M)
    lines, out, list_tag, i, notes = text.splitlines(), [], None, 0, []
    # Vocabulary tables are true bilingual lookup tables; keep translations in-cell
    # so Japanese and English remain aligned instead of moving English to footnotes.
    popup_english = 'vocabulary' not in title.lower()
    def close_list():
        nonlocal list_tag
        if list_tag:
            out.append(f'</{list_tag}>'); list_tag = None
    def cells(line):
        return [c.strip() for c in line.strip().strip('|').split('|')]
    def separator(line):
        cs = cells(line)
        return bool(cs) and all(re.fullmatch(r':?-{1,}:?', c.replace(' ', '')) for c in cs)
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            close_list(); i += 1
            continue
        # A Markdown table is a header row followed by a --- separator row.
        if line.strip().startswith('|') and i + 1 < len(lines) and separator(lines[i + 1]):
            close_list()
            header = cells(line)
            header_html=[]
            for c in header:
                # The English column is self-evident from its popup markers.
                label = '' if c.strip().lower() in ('english', '英語', '英文', '英语') else clean_inline(c)
                header_html.append(f'<th>{label}</th>')
            out.append('<table><thead><tr>' + ''.join(header_html) + '</tr></thead><tbody>')
            i += 2
            while i < len(lines) and lines[i].strip().startswith('|'):
                row = cells(lines[i])
                # Pad short rows so malformed source tables still render consistently.
                row += [''] * (len(header) - len(row))
                out.append('<tr>' + ''.join(f'<td>{english_note(c, notes, popup_english)}</td>' for c in row[:len(header)]) + '</tr>')
                i += 1
            out.append('</tbody></table>')
            continue
        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            close_list()
            n=len(m.group(1)); out.append(f'<h{n}>{clean_inline(m.group(2))}</h{n}>'); i += 1; continue
        m = re.match(r'^\s*[-*]\s+(.*)$', line)
        if m:
            if list_tag != 'ul': close_list(); out.append('<ul>'); list_tag='ul'
            out.append(f'<li>{clean_inline(m.group(1))}</li>'); i += 1; continue
        if re.match(r'^\s*\d+[.)]\s+', line):
            content=re.sub(r'^\s*\d+[.)]\s+','',line)
            if list_tag != 'ol': close_list(); out.append('<ol>'); list_tag='ol'
            out.append(f'<li>{clean_inline(content)}</li>'); i += 1; continue
        close_list()
        out.append(f'<p>{clean_inline(line)}</p>')
        i += 1
    close_list()
    if notes:
        out.append('<section class="footnotes">' + ''.join(notes) + '</section>')
    return '\n'.join(out)

def numeric_key(path):
    m = re.match(r'\s*(\d+)', path.stem)
    return (int(m.group(1)) if m else 999, path.stem.lower())

def category_for_path(path):
    if path.parent.name == 'grammar' or path.stem.lower() == '3. basic japanese statements':
        return 'Grammar'
    if 'vocabulary' in path.name.lower():
        return 'Vocabulary'
    return 'Text'

def lesson_for_path(path):
    if KANA_ROOT in path.parents and 'hiragana' in path.parts:
        return 'hiragana'
    if KANA_ROOT in path.parents and 'katakana' in path.parts:
        return 'katakana'
    return next(p.name for p in path.parents if re.match(r'lesson\d+$', p.name))

files=[]
if KANA_ROOT.exists():
    files.extend(sorted((KANA_ROOT / 'hiragana').glob('*.md'), key=numeric_key))
    files.extend(sorted((KANA_ROOT / 'katakana').glob('*.md'), key=numeric_key))
for lesson in sorted(ROOT.glob('lesson*'), key=lambda p:int(re.search(r'\d+',p.name).group())):
    if not lesson.is_dir(): continue
    lesson_files = list(lesson.glob('*.md')) + list(lesson.glob('grammar/*.md'))
    text = sorted([f for f in lesson_files if category_for_path(f) == 'Text'], key=numeric_key)
    vocab = sorted([f for f in lesson_files if category_for_path(f) == 'Vocabulary'], key=numeric_key)
    grammar = sorted([f for f in lesson_files if category_for_path(f) == 'Grammar'], key=numeric_key)
    files.extend(text + vocab + grammar)

# Map Obsidian page titles to generated EPUB chapter files before rendering bodies.
for i, f in enumerate(files):
    href = f'chapter{i:03d}.xhtml'
    LINK_MAP[f.stem.lower()] = href
    LINK_MAP[f.name.lower()] = href

for f in re.findall(r'!\[\[([^\]|]+)', '\n'.join(p.read_text(encoding='utf-8') for p in files)):
    candidates = list(IMGROOT.rglob(f.strip()))
    if candidates:
        IMAGE_MAP[f.strip().lower()] = 'images/' + candidates[0].name

items=[]
for i,f in enumerate(files):
    title=f.stem
    # Text and Vocabulary chapter titles use file-order numbers for Obsidian navigation;
    # omit those numbers in the EPUB正文 while retaining Grammar numbering.
    if category_for_path(f) in ('Text', 'Vocabulary'):
        title = re.sub(r'^\s*\d+\.\s*', '', title)
    body=md_to_xhtml(f.read_text(encoding='utf-8'), title)
    name=f'chapter{i:03d}.xhtml'
    xhtml=f'''<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>{html.escape(title)}</title><link rel="stylesheet" type="text/css" href="style.css"/></head><body><h1>{clean_inline(title)}</h1>{body}</body></html>'''
    items.append((name,title,xhtml))

css='''body{font-family:serif;line-height:1.35;margin:4%;}h1{font-size:1.6em;line-height:1.25;border-bottom:1px solid #bbb;padding-bottom:.25em;margin:0 0 .7em}h2{font-size:1.3em;line-height:1.3;color:#333;margin:1em 0 .45em}h3,h4,h5,h6{line-height:1.3;margin:.9em 0 .4em}p{margin:.4em 0}ul,ol{margin:.4em 0;padding-left:1.6em}li{margin:.12em 0}mark{background:#fff176;padding:0 .12em}ruby{ruby-position:over}rt{font-size:.55em;line-height:1;color:#555}.note-image{display:block;max-width:100%;height:auto;margin:.8em auto}.noteref{text-decoration:none;color:#777;font-size:.8em}.noteref sup{border:1px solid #aaa;border-radius:.25em;padding:.05em .22em}.footnotes{margin-top:2em;border-top:1px solid #bbb;padding-top:.6em;font-size:.9em}.footnotes aside{margin:.2em 0}.backref{text-decoration:none;color:#777;margin-right:.25em}table{border-collapse:collapse;width:100%;margin:.7em 0;font-size:.95em;line-height:1.3}th,td{border:1px solid #aaa;padding:.3em .45em;text-align:left;vertical-align:top}th{background:#eee;font-weight:bold}tbody tr:nth-child(even){background:#f7f7f7}'''
container='<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
manifest=['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>','<item id="css" href="style.css" media-type="text/css"/>']
spine=[]; nav=[]
cover_item = ''
if USER_COVER.exists():
    manifest.append('<item id="cover-image" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>')
    manifest.append('<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>')
    spine.append('<itemref idref="cover"/>')
    cover_item = '<item id="cover-image" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>'
for i,(name,title,xhtml) in enumerate(items):
    manifest.append(f'<item id="c{i}" href="{name}" media-type="application/xhtml+xml"/>'); spine.append(f'<itemref idref="c{i}"/>')
for j, (fname, src) in enumerate(IMAGE_MAP.items()):
    ext = Path(src).suffix.lower(); mime = mimetypes.guess_type(fname)[0] or 'image/png'
    manifest.append(f'<item id="img{j}" href="{src}" media-type="{mime}"/>')

# Build a nested EPUB navigation: Lesson -> Text/Vocabulary/Grammar -> chapters.
groups=[]
for f,(name,title,xhtml) in zip(files,items):
    lesson=lesson_for_path(f)
    category=category_for_path(f)
    if not groups or groups[-1][0] != lesson: groups.append((lesson, {'Text':[], 'Vocabulary':[], 'Grammar':[]}))
    groups[-1][1][category].append((name,title))
nav=[]
for lesson,cats in groups:
    inner=[]
    for cat in ('Text','Vocabulary','Grammar'):
        if cats[cat]:
            entries=[]
            for n,t in cats[cat]:
                display = re.sub(r'^\s*\d+\.\s*', '', t) if cat in ('Text','Vocabulary','Grammar') else t
                entries.append(f'<li><a href="{n}">{html.escape(display)}</a></li>')
            inner.append('<li><span>'+cat+'</span><ol>'+''.join(entries)+'</ol></li>')
    if lesson in ('hiragana', 'katakana'):
        lesson_label = lesson.title()
    else:
        lesson_label = 'Lesson ' + re.search(r'\d+', lesson).group()
    nav.append(f'<li><span>{lesson_label}</span><ol>'+''.join(inner)+'</ol></li>')
navx='''<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>目录</title></head><body><nav epub:type="toc" id="toc"><h1>目录</h1><ol>'''+''.join(nav)+'''</ol></nav></body></html>'''
coverx='''<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>封面</title><style>html,body{margin:0;padding:0;text-align:center;background:#fff}img{max-width:100%;height:100vh;object-fit:contain}</style></head><body><img src="images/cover.jpg" alt="Genki I 封面"/></body></html>'''
opf=f'''<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bookid">genki-notes-{date.today().isoformat()}</dc:identifier><dc:title>Genki I 日语学习笔记</dc:title><dc:language>zh</dc:language><dc:language>ja</dc:language><dc:creator>个人学习笔记</dc:creator><meta property="dcterms:modified">{date.today().isoformat()}T00:00:00Z</meta></metadata><manifest>{''.join(manifest)}</manifest><spine>{''.join(spine)}</spine></package>'''
with zipfile.ZipFile(OUT,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('mimetype','application/epub+zip',compress_type=zipfile.ZIP_STORED)
    z.writestr('META-INF/container.xml',container); z.writestr('OEBPS/style.css',css); z.writestr('OEBPS/nav.xhtml',navx); z.writestr('OEBPS/content.opf',opf)
    if USER_COVER.exists():
        z.writestr('OEBPS/cover.xhtml',coverx); z.write(USER_COVER, 'OEBPS/images/cover.jpg')
    for fname, src in IMAGE_MAP.items():
        source = IMGROOT / fname
        if source.exists(): z.write(source, 'OEBPS/' + src)
    for name,_,xhtml in items: z.writestr('OEBPS/'+name,xhtml)
print(f'Created {OUT} ({len(items)} chapters)')
