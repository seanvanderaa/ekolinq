document.addEventListener("DOMContentLoaded", function () {
    const toggleButton = document.querySelector('.navbar__toggle');
    const menu = document.getElementById('navbar-menu');
    const icon = toggleButton.querySelector('i');
  
    toggleButton.addEventListener('click', () => {
      const isExpanded = toggleButton.getAttribute('aria-expanded') === 'true';
      toggleButton.setAttribute('aria-expanded', !isExpanded);
      menu.classList.toggle('active');
  
      // Fade out the icon
      icon.style.opacity = 0;
  
      // After a short delay, swap the icon and fade back in
      setTimeout(() => {
        if (menu.classList.contains('active')) {
          icon.classList.remove('bi-list');
          icon.classList.add('bi-x');
        } else {
          icon.classList.remove('bi-x');
          icon.classList.add('bi-list');
        }
        icon.style.opacity = 1;
      }, 150); // Delay roughly half the duration of the transition
    });
  });
  