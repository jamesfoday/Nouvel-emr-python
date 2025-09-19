// Basic HTMX helpers: loading indicator + CSRF for POST/PUT/PATCH/DELETE.

(function () {
  // Show a global "loading..." indicator if you want (optional).
  document.addEventListener('htmx:configRequest', function (evt) {
    
    const method = (evt.detail.verb || 'GET').toUpperCase();
    if (['POST','PUT','PATCH','DELETE'].includes(method)) {
      const csrftoken = getCookie('csrftoken');
      if (csrftoken) evt.detail.headers['X-CSRFToken'] = csrftoken;
    }
  });

  document.addEventListener('htmx:beforeRequest', function (evt) {
    toggleGlobalBusy(true);
  });
  document.addEventListener('htmx:afterRequest', function (evt) {
    toggleGlobalBusy(false);
  });
  document.addEventListener('htmx:responseError', function (evt) {
    console.error('HTMX error:', evt.detail);
    alert('Request failed. Please try again.');
  });

  function toggleGlobalBusy(on) {
    var el = document.getElementById('busy-indicator');
    if (!el) return;
    el.style.display = on ? 'inline-block' : 'none';
  }

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return decodeURIComponent(parts.pop().split(';').shift());
  }
})();
