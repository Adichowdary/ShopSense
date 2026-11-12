"""
Custom error handlers for ShopSense.
"""

from django.http import HttpRequest, HttpResponse


def handler404(request: HttpRequest, exception=None):
    """Custom 404 error handler."""
    content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Page Not Found - ShopSense</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background: #f5f5f5; }
            .card { background: white; padding: 3rem; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; max-width: 400px; }
            h1 { font-size: 4rem; color: #f59e0b; margin: 0 0 1rem; }
            h2 { color: #1f2937; margin: 0 0 1rem; }
            p { color: #6b7280; margin: 0 0 2rem; }
            .btn { display: inline-block; padding: 0.75rem 1.5rem; background: #4f46e5; color: white; text-decoration: none; border-radius: 8px; margin: 0.5rem; }
            .btn:hover { background: #4338ca; }
            .btn-outline { background: white; color: #4f46e5; border: 2px solid #4f46e5; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>404</h1>
            <h2>Page Not Found</h2>
            <p>Sorry, the page you're looking for doesn't exist or has been moved.</p>
            <a href="/" class="btn">Go to Dashboard</a>
            <a href="/accounts/login/" class="btn btn-outline">Sign In</a>
        </div>
    </body>
    </html>
    """
    return HttpResponse(content, status=404, content_type='text/html')


def handler500(request: HttpRequest):
    """Custom 500 error handler."""
    content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Server Error - ShopSense</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background: #f5f5f5; }
            .card { background: white; padding: 3rem; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; max-width: 400px; }
            h1 { font-size: 4rem; color: #ef4444; margin: 0 0 1rem; }
            h2 { color: #1f2937; margin: 0 0 1rem; }
            p { color: #6b7280; margin: 0 0 2rem; }
            .btn { display: inline-block; padding: 0.75rem 1.5rem; background: #4f46e5; color: white; text-decoration: none; border-radius: 8px; margin: 0.5rem; }
            .btn:hover { background: #4338ca; }
            .btn-outline { background: white; color: #4f46e5; border: 2px solid #4f46e5; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>500</h1>
            <h2>Server Error</h2>
            <p>Something went wrong on our end. Our team has been notified and we're working to fix it.</p>
            <a href="/" class="btn">Try Again</a>
            <a href="/accounts/login/" class="btn" style="background: white; color: #4f46e5; border: 2px solid #4f46e5;">Go Home</a>
        </div>
    </body>
    </html>
    """
    return HttpResponse(content, status=500, content_type='text/html')