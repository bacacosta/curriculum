document.addEventListener('htmx:responseError', (event) => {
  const error = document.getElementById('error');
  let message = 'Could not save your change. Please try again.';
  try {
    const detail = JSON.parse(event.detail.xhr.responseText).detail;
    if (typeof detail === 'string') message = detail;
  } catch (_) {}
  error.textContent = message;
  error.hidden = false;
});
document.addEventListener('htmx:sendError', () => {
  const error = document.getElementById('error');
  error.textContent = 'Unable to reach the server. Please try again.';
  error.hidden = false;
});
document.addEventListener('htmx:afterSwap', () => {
  document.getElementById('error').hidden = true;
});
