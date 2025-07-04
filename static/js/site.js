const overlay = document.getElementById('overlay');
const popup = document.getElementById('contactPopup');
const contactForm = document.getElementById('contactForm');
const contactFormWrapper = document.getElementById('contact-form-wrapper');
const contactFormConf = document.getElementById('contact-form-confirmation');
const submitBtn           = document.getElementById('contactFormBtn');


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
document.getElementById('contactForm').addEventListener('submit', async function (event) {
  event.preventDefault();

  // Disable the button & change text
  submitBtn.disabled = true;
  submitBtn.textContent = 'Sending…';

  // Build a FormData object (includes CSRF & recaptcha response)
  const formData = new FormData(contactForm);

  try {
    const response = await fetch(contactForm.action, {
      method: 'POST',
      credentials: 'same-origin',  // send cookies/CSRF
      body: formData
    });

    // parse JSON
    const data = await response.json();

    if (data.valid) {
      // Hide form, show confirmation
      contactFormWrapper.style.display = 'none';
      contactFormConf.style.display    = 'flex';
    } else {
      // Show server‑side validation error
      if (data.reason == "The response parameter is missing.") {
        alert("Please ensure you fill out the captcha to verify you're not a robot.");
      }
      else {
        alert(data.reason);
      }
    }

  } catch (err) {
    console.error(err);
    alert('An error occurred. Please try again.');
  } finally {
    // Re‑enable button and restore text
    submitBtn.disabled    = false;
    submitBtn.textContent = 'Submit';
  }
});

document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('close-contact-btn');
  if (btn) btn.addEventListener('click', closeContactPopup);
  const btn2 = document.getElementById('close-contact-btn2');
  if (btn2) btn2.addEventListener('click', closeContactPopup);

  const btn3 = document.getElementById('error-open-contact');
  if (btn3) btn3.addEventListener('click', openContactPopup);

  const btn4 = document.getElementById('edit-request-info-open-contact');
  if (btn4) btn4.addEventListener('click', openContactPopup);

  const btn5 = document.getElementById('edit-request-init-open-contact');
  if (btn5) btn5.addEventListener('click', openContactPopup);

  const footerLink = document.getElementById('footer-contact-link');
  if (footerLink) footerLink.addEventListener('click', openContactPopup);

  const errorButton = document.getElementById('error-back-to-home');
  if (errorButton) {
    errorButton.addEventListener('click', () => {
      window.location.href = '/';
    });
  }
});





