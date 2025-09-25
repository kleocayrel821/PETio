from django.shortcuts import render

# Marketplace wireframe views (frontend-only): each view renders a template skeleton for planning.

# Render the marketplace home wireframe
def marketplace_home(request):
    return render(request, "marketplace/home.html")

# Render a single listing detail wireframe
# listing_id: placeholder identifier for navigating to a specific listing page
def listing_detail(request, listing_id):
    return render(request, "marketplace/listing_detail.html", {"listing_id": listing_id})

# Render the create listing wireframe
def create_listing(request):
    return render(request, "marketplace/create_listing.html")

# Render the messages wireframe
def messages(request):
    return render(request, "marketplace/messages.html")

# Render the transactions wireframe
def transactions(request):
    return render(request, "marketplace/transactions.html")

# Render the user dashboard wireframe
def dashboard(request):
    return render(request, "marketplace/dashboard.html")

# Render the admin review wireframe
def admin_review(request):
    return render(request, "marketplace/admin_review.html")
