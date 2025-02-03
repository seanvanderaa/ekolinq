const overlay = document.getElementById('overlay');
const popup = document.getElementById('contactPopup');
const contactForm = document.getElementById('contactForm');
const contactFormWrapper = document.getElementById('contact-form-wrapper');
const contactFormConf = document.getElementById('contact-form-confirmation');

// Function to open the popup (accessible via onClick)
function openContactPopup() {
  overlay.style.display = 'block';
  popup.style.display = 'block';
}

// Function to close the popup and reset form/confirmation state
function closeContactPopup() {
  overlay.style.display = 'none';
  popup.style.display = 'none';

  // Reset the form data
  contactForm.reset();
  // Restore original view: show the form and hide the confirmation
  contactFormWrapper.style.display = 'block';
  contactFormConf.style.display = 'none';
}

// Close the popup if the overlay is clicked
overlay.addEventListener('click', closeContactPopup);

// Handle form submission
contactForm.addEventListener('submit', function(event) {
  event.preventDefault(); // Prevent default form submission

  // Process the form data here (e.g., via AJAX) if desired

  // Hide the form wrapper and show the confirmation message
  contactFormWrapper.style.display = 'none';
  contactFormConf.style.display = 'flex';
});