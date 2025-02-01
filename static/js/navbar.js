document.addEventListener("DOMContentLoaded", function () {
    const toggleButton = document.querySelector('.navbar__toggle');
    const menu = document.getElementById('navbar-menu');

    toggleButton.addEventListener('click', () => {
    const isExpanded = toggleButton.getAttribute('aria-expanded') === 'true';
    toggleButton.setAttribute('aria-expanded', !isExpanded);
    menu.classList.toggle('active');
    });
});