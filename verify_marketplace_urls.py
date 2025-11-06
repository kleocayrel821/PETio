"""
Verify all marketplace API endpoints are properly wired
"""
import django
import os

# Use the development settings for local verification runs
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings.dev')
django.setup()

from django.urls import get_resolver
from django.urls.resolvers import URLPattern, URLResolver

def get_all_urls(urlpatterns, prefix=''):
    """Recursively get all URL patterns"""
    urls = []
    for pattern in urlpatterns:
        if isinstance(pattern, URLPattern):
            urls.append(prefix + str(pattern.pattern))
        elif isinstance(pattern, URLResolver):
            urls.extend(get_all_urls(pattern.url_patterns, prefix + str(pattern.pattern)))
    return urls

def main():
    resolver = get_resolver()
    all_urls = get_all_urls(resolver.url_patterns)
    
    # Filter marketplace URLs
    marketplace_urls = [url for url in all_urls if 'marketplace' in url or 'api' in url]
    
    print("=" * 80)
    print("MARKETPLACE API ENDPOINTS VERIFICATION")
    print("=" * 80)
    print()
    
    # Expected API endpoints
    expected_endpoints = [
        'api/messages/thread/start/',
        'api/messages/thread/<int:thread_id>/messages/',
        'api/messages/thread/<int:thread_id>/post/',
        'api/listings/<int:listing_id>/reserve/',
        'api/listings/<int:listing_id>/sell/',
        'api/listings/<int:listing_id>/complete/',
        'api/listings/<int:listing_id>/report/',
        'api/requests/<int:listing_id>/create/',
        'api/requests/<int:request_id>/accept/',
        'api/requests/<int:request_id>/reject/',
        'api/requests/<int:request_id>/negotiate/',
        'api/requests/<int:request_id>/cancel/',
        'api/requests/<int:request_id>/meetup/set/',
        'api/requests/<int:request_id>/meetup/confirm/',
        'api/requests/<int:request_id>/complete/',
        'api/categories/',
        'api/listings/',
        'api/threads/',
        'api/messages/',
        'api/transactions/',
        'api/reports/',
    ]
    
    print("Checking expected endpoints:")
    print("-" * 80)
    
    found_count = 0
    missing_count = 0
    
    for endpoint in expected_endpoints:
        # Check if endpoint exists in marketplace URLs
        pattern = endpoint.replace('<int:', '').replace('>', '')
        found = any(pattern in url for url in marketplace_urls)
        
        if found:
            print(f"✅ {endpoint}")
            found_count += 1
        else:
            print(f"❌ {endpoint} - NOT FOUND")
            missing_count += 1
    
    print()
    print("=" * 80)
    print(f"Summary: {found_count} found, {missing_count} missing")
    print("=" * 80)
    
    if missing_count == 0:
        print("✅ All expected endpoints are wired!")
    else:
        print(f"⚠️  {missing_count} endpoint(s) missing. Please check marketplace/urls.py")
    
    print()
    print("All marketplace-related URLs:")
    print("-" * 80)
    for url in sorted(marketplace_urls):
        print(f"  {url}")

if __name__ == '__main__':
    main()