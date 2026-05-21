"""
Batch-boost 9 /tools/ pages with "captioning" keyword.
Mirrors the japanese-subtitle-generator.html v1.2.1 edits.
"""
import re
import shutil
from pathlib import Path

TOOLS = Path("tools")
LANGS = ["french", "spanish", "arabic", "german", "portuguese",
         "chinese", "korean", "italian", "hindi"]

CAPT_FAQ_HTML = '''    <div class="faq-item">
      <div class="faq-question">What is {Lang} captioning and how does it differ from subtitling?<span class="faq-icon">+</span></div>
      <div class="faq-answer"><div class="faq-answer-inner">{Lang} captioning includes the spoken dialogue plus non-speech information (sound effects, music cues, speaker identification) and is primarily used for accessibility. {Lang} subtitling typically contains only the spoken dialogue and is used for translation or comprehension support. SubWhisper Pro produces both — generate {lang} captions for accessibility-compliant video, or subtitles for international audiences with the same AI engine.</div></div>
    </div>
'''

def boost(lang):
    f = TOOLS / f"{lang}-subtitle-generator.html"
    bak = TOOLS / f"{lang}-subtitle-generator.html.bak-v121-seo"
    shutil.copy(f, bak)
    txt = f.read_text(encoding="utf-8")
    Lang = lang.capitalize()
    changes = []

    # 1. Title
    old_title = f"<title>{Lang} Subtitle Generator — Translate & Transcribe | SubWhisper Pro</title>"
    new_title = f"<title>{Lang} Subtitle Generator & Captioning Tool — AI-Powered | SubWhisper Pro</title>"
    if old_title in txt:
        txt = txt.replace(old_title, new_title)
        changes.append("title")

    # 2. og:title
    old_og = f'<meta property="og:title" content="{Lang} Subtitle Generator — AI-Powered | SubWhisper Pro">'
    new_og = f'<meta property="og:title" content="{Lang} Subtitle Generator & Captioning — AI-Powered | SubWhisper Pro">'
    if old_og in txt:
        txt = txt.replace(old_og, new_og)
        changes.append("og:title")

    # 3. meta description : insert "and captioning" after "subtitles"
    # pattern: content="Generate accurate XXX subtitles ...
    desc_pattern = re.compile(
        r'(<meta name="description" content="Generate accurate ' + Lang + r' subtitles)( from any video)',
        re.IGNORECASE,
    )
    new_txt, n = desc_pattern.subn(r'\1 and captions\2', txt, count=1)
    if n:
        txt = new_txt
        changes.append("meta-description")
    else:
        # Variant : "Create professional"
        desc_pattern2 = re.compile(
            r'(<meta name="description" content="[^"]*?' + Lang + r' subtitles)',
            re.IGNORECASE,
        )

    # 4. H1 — add "& Captioning Tool"
    old_h1 = f"<h1><em>{Lang} Subtitle Generator</em> — AI-Powered Transcription & Translation</h1>"
    new_h1 = f"<h1><em>{Lang} Subtitle Generator</em> & Captioning Tool — AI-Powered Transcription & Translation</h1>"
    if old_h1 in txt:
        txt = txt.replace(old_h1, new_h1)
        changes.append("h1")

    # 5. FAQ — insert captioning FAQ as the FIRST item in <div class="faq-list">
    faq_marker = '<div class="faq-list">\n    <div class="faq-item">\n      <div class="faq-question">Can SubWhisper Pro translate'
    new_faq = '<div class="faq-list">\n' + CAPT_FAQ_HTML.format(Lang=Lang, lang=lang) + '    <div class="faq-item">\n      <div class="faq-question">Can SubWhisper Pro translate'
    if faq_marker in txt:
        txt = txt.replace(faq_marker, new_faq)
        changes.append("faq")

    f.write_text(txt, encoding="utf-8")
    print(f"[{lang}] changes: {', '.join(changes) if changes else 'NONE'}")

if __name__ == "__main__":
    for lang in LANGS:
        boost(lang)
