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
document.getElementById('contactForm').addEventListener('submit', async function (event) {
  event.preventDefault(); // Prevent default form submission

  const submitBtn = document.getElementById('contactFormBtn');
  const name = document.getElementById('name').value;
  const email = document.getElementById('email').value;
  const message = document.getElementById('message').value;

  submitBtn.style.backgroundColor = "var(--m-blue)";

  // Construct the URL correctly using & to separate parameters
  const url = `/contact-form-entry?name=${encodeURIComponent(name)}&email=${encodeURIComponent(email)}&message=${encodeURIComponent(message)}`;

  const response = await fetch(url);
  const data = await response.json();

  if (data.valid) {
    contactFormWrapper.style.display = 'none';
    contactFormConf.style.display = 'flex';
  } else {
    alert(`${data.reason}`);
  }
});

