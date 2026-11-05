"""Copy the privacy policy (docs/privacy.html, the single source) into the site.

The site's Content-Security-Policy allows styles only from files on the site, so
the page's inline <style> block and style="" attributes are moved into
public/privacy.css. Run before every deploy:  python3 site/sync-privacy.py
"""
import re
from pathlib import Path

root = Path(__file__).resolve().parent
src = (root.parent / "docs" / "privacy.html").read_text(encoding="utf-8")

css = "\n".join(re.findall(r"<style>(.*?)</style>", src, re.S))
page = re.sub(r"<style>.*?</style>", '<link rel="stylesheet" href="/privacy.css">', src, count=1, flags=re.S)
page = re.sub(r"<style>.*?</style>", "", page, flags=re.S)

inline = []
def lift(m):
    inline.append(m.group(1))
    return f'class="inl{len(inline)}"'
page = re.sub(r'style="([^"]*)"', lift, page)
css += "".join(f"\n.inl{i} {{ {rule} }}" for i, rule in enumerate(inline, 1))

if "<script" in page:
    raise SystemExit("privacy.html has a script; the site's CSP would block it")
(root / "public" / "privacy.html").write_text(page, encoding="utf-8")
(root / "public" / "privacy.css").write_text(css.strip() + "\n", encoding="utf-8")
print(f"synced privacy.html ({len(inline)} inline style(s) lifted)")
