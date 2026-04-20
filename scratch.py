import urllib.request

try:
    response = urllib.request.urlopen('http://localhost:8080')
    html = response.read().decode('utf-8')
    print("HTML length:", len(html))
except Exception as e:
    print("Error:", e)
