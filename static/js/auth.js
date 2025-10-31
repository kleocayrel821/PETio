// ============================================
// SIGNUP FORM ENHANCEMENTS
// ============================================

document.addEventListener('DOMContentLoaded', function() {
  const signupForm = document.querySelector('.signup-form');

  if (signupForm) {
    // Password Toggle
    const togglePasswordBtns = document.querySelectorAll('.toggle-password');
    togglePasswordBtns.forEach(btn => {
      btn.addEventListener('click', function() {
        const input = this.closest('.input-wrapper').querySelector('input');
        const type = input.type === 'password' ? 'text' : 'password';
        input.type = type;
        const eye = this.querySelector('.eye-icon');
        if (eye) eye.textContent = type === 'password' ? '👁️' : '👁️‍🗨️';
      });
    });

    // Password Strength Checker
    const passwordInput = signupForm.querySelector('input[name="password1"]');
    const strengthBar = document.querySelector('.strength-bar');

    if (passwordInput && strengthBar) {
      passwordInput.addEventListener('input', function() {
        const password = this.value;
        const strength = calculatePasswordStrength(password);

        strengthBar.className = 'strength-bar';

        if (strength.score === 0) {
          strengthBar.style.width = '0%';
        } else if (strength.score <= 2) {
          strengthBar.classList.add('weak');
        } else if (strength.score === 3) {
          strengthBar.classList.add('medium');
        } else {
          strengthBar.classList.add('strong');
        }
      });
    }

    // Password Match Validation
    const confirmPassword = signupForm.querySelector('input[name="password2"]');
    if (confirmPassword && passwordInput) {
      const validateMatch = function() {
        if (confirmPassword.value !== passwordInput.value) {
          confirmPassword.setCustomValidity('Passwords do not match');
        } else {
          confirmPassword.setCustomValidity('');
        }
      };
      confirmPassword.addEventListener('input', validateMatch);
      passwordInput.addEventListener('input', validateMatch);
    }

    // Terms acceptance check
    signupForm.addEventListener('submit', function(e) {
      const termsCheckbox = document.getElementById('terms');
      if (termsCheckbox && !termsCheckbox.checked) {
        e.preventDefault();
        alert('Please accept the Terms of Service and Privacy Policy to continue.');
        termsCheckbox.focus();
      }
    });

    // Real-time Username Validation (placeholder)
    const usernameInput = document.getElementById('username');
    if (usernameInput) {
      let debounceTimer;
      usernameInput.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          validateUsername(this.value);
        }, 500);
      });
    }
  }
});

function calculatePasswordStrength(password) {
  let score = 0;
  if (!password) return { score: 0 };
  if (password.length >= 8) score++;
  if (password.length >= 12) score++;
  if (/[a-z]/.test(password)) score++;
  if (/[A-Z]/.test(password)) score++;
  if (/\d/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;
  return { score: Math.min(score, 4) };
}

function validateUsername(username) {
  if (username.length < 3) {
    return false;
  }
  return true;
}

// ============================================
// PROFILE PAGE ENHANCEMENTS
// ============================================

// Tab Navigation
const profileTabs = document.querySelectorAll('.tab-item');
profileTabs.forEach(tab => {
  tab.addEventListener('click', function(e) {
    e.preventDefault();
    profileTabs.forEach(t => t.classList.remove('active'));
    this.classList.add('active');
    const tabHref = this.getAttribute('href').substring(1);
    loadTabContent(tabHref);
  });
});

function loadTabContent(tabName) {
  // Placeholder: integrate AJAX views for tab content as needed
  console.log('Loading tab:', tabName);
}

// Avatar Upload Preview
const avatarUploadBtn = document.querySelector('.avatar-upload-btn');
if (avatarUploadBtn) {
  avatarUploadBtn.addEventListener('click', function() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.addEventListener('change', function(e) {
      const file = e.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = function(evt) {
          const avatar = document.querySelector('.profile-avatar');
          if (avatar) {
            avatar.src = evt.target.result;
          }
          uploadAvatar(file);
        };
        reader.readAsDataURL(file);
      }
    });
    input.click();
  });
}

function uploadAvatar(file) {
  const formData = new FormData();
  formData.append('avatar', file);
  // Example AJAX endpoint; integrate with existing profile edit view or a dedicated endpoint
  /*
  fetch('/accounts/profile/edit/', {
    method: 'POST',
    body: formData,
    headers: { 'X-CSRFToken': getCookie('csrftoken') }
  }).then(r => r.json()).then(d => console.log('Avatar uploaded:', d));
  */
}

// Follow/Unfollow Button (placeholder wiring)
const followBtn = document.querySelector('[data-action="follow"]');
if (followBtn) {
  followBtn.addEventListener('click', function() {
    const userId = this.dataset.userId;
    const isFollowing = this.classList.contains('following');
    if (isFollowing) {
      unfollowUser(userId);
      this.classList.remove('following');
      this.textContent = '➕ Follow';
    } else {
      followUser(userId);
      this.classList.add('following');
      this.textContent = '✓ Following';
    }
  });
}

function followUser(userId) {
  console.log('Following user:', userId);
  // Optionally: call existing social toggle_follow endpoint
}
function unfollowUser(userId) {
  console.log('Unfollowing user:', userId);
}

// Helper function to get CSRF token
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}