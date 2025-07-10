document.addEventListener('DOMContentLoaded', () => {
  const errorButton = document.getElementById('error-back-to-home');
  if (errorButton) {
    errorButton.addEventListener('click', () => {
      window.location.href = '/';
    });
  }
});