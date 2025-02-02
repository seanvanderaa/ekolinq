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
  const initForm           = document.getElementById('init-form-info');
  const gatedCheckbox      = document.getElementById('gated');
  const gatedPopup         = document.getElementById('gated-popup');
  const gatedOptionsSelect = document.getElementById('gatedOptions');

  // Sections within the gated container
  const gateCodeSection = document.getElementById('gate-code-section');
  const qrCodeSection   = document.getElementById('qr-code-section');
  const noticeSection   = document.getElementById('notice-section');

  // Inputs
  const gateCodeInput = document.getElementById('gateCodeInput');
  const qrCodeInput   = document.getElementById('qrCodeInput');

  // Hidden fields (if needed to pass final gating info)
  const selectedGatedOption = document.getElementById('selectedGatedOption');
  const finalGateCode       = document.getElementById('finalGateCode');
  const finalNotice         = document.getElementById('finalNotice');

  // Toggle the gated-info section on checkbox change
  gatedCheckbox.addEventListener('change', () => {
    if (gatedCheckbox.checked) {
      gatedPopup.style.display = 'block';
    } else {
      gatedPopup.style.display = 'none';
      // Reset gating fields
      gatedOptionsSelect.value = '';
      gateCodeInput.value      = '';
      qrCodeInput.value        = '';
      selectedGatedOption.value= '';
      finalGateCode.value      = '';
      finalNotice.value        = '';
      // Also hide all sub-sections
      gateCodeSection.style.display = 'none';
      qrCodeSection.style.display   = 'none';
      noticeSection.style.display   = 'none';
    }
  });

  // Show/hide relevant sub-section based on dropdown selection
  gatedOptionsSelect.addEventListener('change', function() {
    const val = gatedOptionsSelect.value;
    gateCodeSection.style.display = 'none';
    qrCodeSection.style.display   = 'none';
    noticeSection.style.display   = 'none';

    if (val === 'code') {
      gateCodeSection.style.display = 'block';
    } else if (val === 'qr') {
      qrCodeSection.style.display   = 'flex';
    } else if (val === 'notice') {
      noticeSection.style.display   = 'block';
    }
  });

  // Form submission handler
  initForm.addEventListener('submit', async function (event) {
    // Basic gating validation: if gated is checked, ensure we have what we need
    if (gatedCheckbox.checked) {
      // Must choose one option
      if (!gatedOptionsSelect.value) {
        event.preventDefault();
        alert('Please select a gate access option.');
        return;
      }
      if (gatedOptionsSelect.value === 'code') {
        // Must provide gate code
        if (!gateCodeInput.value.trim()) {
          event.preventDefault();
          alert('Please enter your gate code or uncheck the gated box.');
          return;
        }
      }
      if (gatedOptionsSelect.value === 'qr') {
        // Must upload a file
        if (!qrCodeInput.files || qrCodeInput.files.length === 0) {
          event.preventDefault();
          alert('Please upload a QR code image or uncheck the gated box.');
          return;
        }
        if(qrCodeInput.files[0].size > 5242880) {
          event.preventDefault();
          alert("File is too big. Files must be under 5 megabytes.");
          return;
        }
      }
      // If notice is selected, no additional fields needed

      // Optionally store final gating info into hidden fields
      selectedGatedOption.value = gatedOptionsSelect.value;
      finalGateCode.value       = (gatedOptionsSelect.value === 'code') ? gateCodeInput.value : '';
      finalNotice.value         = (gatedOptionsSelect.value === 'notice') ? 'true' : '';
    } 
    
    // Next, do any other checks you need (e.g. verifying ZIP code)
    event.preventDefault(); // Keep it for the async call below (avoid default submit)

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