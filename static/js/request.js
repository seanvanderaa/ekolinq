document.addEventListener('DOMContentLoaded', function() {
    const overlay = document.getElementById('overlay');
    
    // Add click event to each FAQ item to open the respective popup
    const faqItems = document.querySelectorAll('.faq-item');
    faqItems.forEach(item => {
      item.addEventListener('click', function() {
        const popupId = item.id + '-popup';
        const popup = document.getElementById(popupId);
        if(popup) {
          overlay.style.display = 'block';    // Show overlay
          popup.style.display = 'block';      // Show corresponding popup
        }
      });
    });
    
    // Add click events to close buttons to hide popup and overlay
    const closeButtons = document.querySelectorAll('.popup-close');
    closeButtons.forEach(button => {
      button.addEventListener('click', function() {
        overlay.style.display = 'none';        // Hide overlay
        const popups = document.querySelectorAll('.faq-popup');
        popups.forEach(p => p.style.display = 'none');  // Hide all popups
      });
    });
  });

  const initForm = document.getElementById('init-form-info');

  // Form submission handler
  initForm.addEventListener('submit', async function (event) {
    event.preventDefault();
    // Basic gating validation: if gated is checked, ensure we have what we need
    if (grecaptcha.getResponse().length === 0) {

      alert('Please click the “I’m not a robot” box before continuing.');
      return;
    }

    const zipcode = document.getElementById('zip').value;
    try {
      const response = await fetch(`/verify_zip?zipcode=${zipcode}`);
      const data = await response.json();

      if (data.valid) {
        // If ZIP is valid, submit for real
        initForm.submit(); 
      } else {
        alert(`${data.reason}`);
      }
    } catch (err) {
      console.error(err);
      alert('Error verifying ZIP code. Please try again.');
    }
  });