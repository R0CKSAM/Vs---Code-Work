import sys

path = r'D:\MFA\media-reporting-system\backend\app\static\app.js'

# Read preserving EXACT newlines (no translation)
with open(path, 'r', encoding='utf-8', newline='') as f:
    content = f.read()

new_block = (
    "    // Priority 3b: scraped_at as rough time indicator when published_at unavailable\r\n"
    "    if (art.scraped_at) {\r\n"
    "      const scrapedRel = formatClientRelativeTime(art.scraped_at);\r\n"
    "      if (scrapedRel && scrapedRel !== 'Time pending verification') return '~' + scrapedRel;\r\n"
    "    }\r\n"
)

# The line before "// Priority 4" ends with \r\n (CRLF per viewer)
search = "    }\r\n    // Priority 4: Unavailable"
replace = "    }\r\n" + new_block + "    // Priority 4: Unavailable"

if search in content:
    new_content = content.replace(search, replace, 1)
    print("Matched CRLF pattern and replaced.")
else:
    # Try with LF
    search_lf = "    }\n    // Priority 4: Unavailable"
    replace_lf = "    }\n" + new_block.replace('\r\n', '\n') + "    // Priority 4: Unavailable"
    if search_lf in content:
        new_content = content.replace(search_lf, replace_lf, 1)
        print("Matched LF pattern and replaced.")
    else:
        # Debug: show what's around line 113 in the raw content
        idx = content.find("// Priority 4: Unavailable")
        if idx == -1:
            idx = content.find("Time pending verification")
        if idx != -1:
            snippet = repr(content[max(0, idx-30):idx+60])
            print(f"Could not match pattern. Context around target: {snippet}", file=sys.stderr)
        else:
            print("Target text not found at all!", file=sys.stderr)
        sys.exit(1)

if 'scrapedRel' not in new_content:
    print("ERROR: scrapedRel not in patched content", file=sys.stderr)
    sys.exit(1)

with open(path, 'w', encoding='utf-8', newline='') as f:
    f.write(new_content)

print("SUCCESS: app.js patched.")
