from django.http import HttpResponse


def home(request):
    host = request.get_host()
    return HttpResponse(f"""
<!doctype html>
<html>
<head><title>Mad Mallard Platform</title></head>
<body style="font-family: system-ui; max-width: 760px; margin: 4rem auto; line-height: 1.5;">
<h1>Mad Mallard Platform</h1>
<p>Django is running behind Caddy.</p>
<p><strong>Host:</strong> {host}</p>
<p>This is the clean foundation deployment. Multi-business tenancy comes next.</p>
</body>
</html>
""")
