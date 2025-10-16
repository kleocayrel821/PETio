// Minimal interaction helpers for Social app
// Relies on window.getCookie from base.html for CSRF

function csrfHeaders() {
  return { 'X-CSRFToken': window.getCookie ? window.getCookie('csrftoken') : '' };
}

function toggleLike(postId, button) {
  try { if (window.setButtonLoading) window.setButtonLoading(button, true); } catch (_) {}
  return fetch(`/social/post/${postId}/like/`, {
    method: 'POST',
    headers: { ...csrfHeaders() },
  })
    .then(r => r.json())
    .then(data => {
      if (!data || typeof data.liked === 'undefined') return;
      // Update button UI if provided
      if (button) {
        const label = data.liked ? 'Liked' : 'Like';
        button.innerHTML = `<i class="fas fa-heart ${data.liked ? 'text-error' : ''}"></i> ${label} (${data.like_count})`;
      }
      return data;
    })
    .finally(() => { try { if (window.setButtonLoading) window.setButtonLoading(button, false); } catch (_) {} });
}

function submitComment(postId, form) {
  const formData = new FormData(form);
  const body = new URLSearchParams();
  for (const [k, v] of formData.entries()) body.append(k, v);
  return fetch(`/social/post/${postId}/comment/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', ...csrfHeaders() },
    body: body.toString(),
  }).then(r => r.json());
}

function toggleFollow(userId, button) {
  try { if (window.setButtonLoading) window.setButtonLoading(button, true); } catch (_) {}
  return fetch(`/social/user/${userId}/follow/`, {
    method: 'POST',
    headers: { ...csrfHeaders() },
  })
    .then(r => r.json())
    .then(data => {
      if (!data || typeof data.following === 'undefined') return;
      if (button) {
        const label = data.following ? 'Following' : 'Follow';
        button.innerHTML = `<i class="fas fa-user-plus"></i> ${label} (${data.follower_count})`;
      }
      return data;
    })
    .finally(() => { try { if (window.setButtonLoading) window.setButtonLoading(button, false); } catch (_) {} });
}

// Make globally accessible for inline templates that may call these
window.toggleLike = toggleLike;
window.submitComment = submitComment;
window.toggleFollow = toggleFollow;