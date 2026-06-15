import urllib.request
from urllib.error import HTTPError

urls = [
    'http://127.0.0.1:5001/',
    'http://127.0.0.1:5001/admin/attendance',
    'http://127.0.0.1:5001/admin/leaves',
    'http://127.0.0.1:5001/teacher/attendance-leaves',
    'http://127.0.0.1:5001/student/attendance-leaves',
    'http://127.0.0.1:5001/student/edit-info'
]

for url in urls:
    try:
        r = urllib.request.urlopen(url)
        print(f"URL: {url} -> Status: {r.getcode()} (Final URL: {r.geturl()})")
    except HTTPError as e:
        print(f"URL: {url} -> Error: {e.code} ({e.reason})")
    except Exception as e:
        print(f"URL: {url} -> Failed: {e}")
