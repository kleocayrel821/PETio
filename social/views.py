from django.shortcuts import render

# Feed and Social Sections
# Each view renders a simple wireframe template for visualization.

def feed(request):
    """Render the social feed wireframe page."""
    return render(request, 'social/feed.html')


def friends(request):
    """Render the friends list wireframe page."""
    return render(request, 'social/friends.html')


# Direct messages feature removed; messaging is now via forum threads and comments.
def messages_view(request):
    """Render the direct messages wireframe page with a chat layout."""
    return render(request, 'social/messages.html')


def notifications(request):
    """Render the notifications wireframe page."""
    return render(request, 'social/notifications.html')


def profile(request):
    """Render the user profile wireframe page."""
    return render(request, 'social/profile.html')


# Forum Sections

def _get_forum_categories():
    """Return a static list of forum categories for wireframing."""
    return [
        'General',
        'Feeding & Nutrition',
        'Health & Vet',
        'Training & Behavior',
        'DIY & Hardware',
        'Marketplace',
        'Events',
    ]


def forum_categories(request):
    """Render the forum categories list wireframe page."""
    context = {
        'categories': _get_forum_categories(),
    }
    return render(request, 'social/forum_categories.html', context)


def forum_threads(request, category_slug):
    """Render the threads list wireframe for a given forum category.

    Args:
        request: Django HttpRequest object.
        category_slug: Slug of the category (e.g., 'feeding-nutrition').
    """
    category_name = category_slug.replace('-', ' ').title()
    context = {
        'category_slug': category_slug,
        'category_name': category_name,
    }
    return render(request, 'social/forum_threads.html', context)


def new_thread(request):
    """Render the new thread creation form wireframe page."""
    context = {
        'categories': _get_forum_categories(),
    }
    return render(request, 'social/new_thread.html', context)


def thread_detail(request, thread_id):
    """Render a thread detail wireframe page with placeholder replies.

    Args:
        request: Django HttpRequest object.
        thread_id: Integer identifier of the thread.
    """
    return render(request, 'social/thread_detail.html', {'thread_id': thread_id})
