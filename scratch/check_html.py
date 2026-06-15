from html.parser import HTMLParser
import sys

class HTMLTagChecker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.errors = []
        
    def handle_starttag(self, tag, attrs):
        # List of self-closing tags
        if tag not in ['img', 'input', 'br', 'hr', 'meta', 'link']:
            self.stack.append((tag, self.getpos()))
            
    def handle_endtag(self, tag):
        if tag in ['img', 'input', 'br', 'hr', 'meta', 'link']:
            return
        if not self.stack:
            self.errors.append(f"Mismatched end tag </{tag}> at line {self.getpos()[0]}")
            return
        expected_tag, pos = self.stack.pop()
        if expected_tag != tag:
            self.errors.append(f"Expected </{expected_tag}> (opened at line {pos[0]}), but got </{tag}> at line {self.getpos()[0]}")
            self.stack.append((expected_tag, pos)) # restore stack

with open("templates/register.html", "r", encoding="utf-8") as f:
    html_content = f.read()

checker = HTMLTagChecker()
checker.feed(html_content)

print("=== HTML TAG STATUS ===")
if checker.errors:
    for err in checker.errors:
        print(err)
else:
    print("All tags are successfully matched and balanced!")

if checker.stack:
    print("\nUnclosed tags remaining on stack:")
    for tag, pos in reversed(checker.stack):
         print(f"<{tag}> opened at line {pos[0]}")
