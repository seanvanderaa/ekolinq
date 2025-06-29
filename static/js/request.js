window.initAutocomplete = function () {
  const input = document.getElementById('address');

  const ac = new google.maps.places.Autocomplete(input, {
    types: ['address'],
    componentRestrictions: { country: 'us' },
    fields: ['address_components', 'formatted_address', 'place_id']
  });

  ac.addListener('place_changed', () => {
    const place = ac.getPlace();
    if (!place.address_components) return;

    // clear previous values
    document.getElementById('city').value     = '';
    document.getElementById('zip').value      = '';
    document.getElementById('place_id').value = place.place_id || '';

    // ---- OPTION A: use address_components ----
    let streetNumber = '';
    let route        = '';
    place.address_components.forEach(c => {
      if (c.types.includes('street_number')) {
        streetNumber = c.long_name;
      }
      if (c.types.includes('route')) {
        route = c.long_name;
      }
      switch (c.types[0]) {
        case 'locality':    // city
          document.getElementById('city').value = c.long_name;
          break;
        case 'postal_code': // zip
          document.getElementById('zip').value  = c.long_name;
          break;
      }
    });
    // join number + street name
    const streetOnly = [streetNumber, route].filter(Boolean).join(' ');
    document.getElementById('address').value = streetOnly;


    // ---- OPTION B: use formatted_address.split(',') ----
    // this will grab everything before the first comma
    // const streetOnly = place.formatted_address.split(',')[0];
    // document.getElementById('address').value = streetOnly;
  });
};

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

    const selectedGate = document.getElementById('selected-gate');
    const radios       = document.querySelectorAll('input[name="gated"]');
    const gatedError = document.getElementById('gated-error-info');

    function toggleGateInfo() {
      const yesChosen = document.querySelector('input[name="gated"][value="yes"]').checked;
      selectedGate.style.display = yesChosen ? 'block' : 'none';
      gatedError.style.display = "none";
    }

    radios.forEach(r => r.addEventListener('change', toggleGateInfo));

    // Set the correct state on first load (useful on validation errors)
    toggleGateInfo();
  });

  const initForm   = document.getElementById('init-form-info');
  const csrfToken  = document.querySelector('input[name="csrf_token"]').value;
  let alreadyPosted = false;                      // prevents an endless loop

  ['address', 'city', 'zip'].forEach(id => {
    const el = document.getElementById(id);
    el.addEventListener('input', () => {
      document.getElementById('place_id').value = '';
    });
  });

  const gatedError = document.getElementById('gated-error-info');

  initForm.addEventListener('submit', async function handleSubmit (evt) {
    if (alreadyPosted) return;                    // second call = real submit

    evt.preventDefault();

    if (!document.querySelector('input[name="gated"]:checked')) {
      gatedError.style.display = "block";
      return;
    }
    else {
      gatedError.style.display = "none";
    }

    // 0️⃣ reCAPTCHA client-side guard
    if (grecaptcha.getResponse().length === 0) {
      showFormError('recaptcha', 'Please click the “I’m not a robot” box.');
      return;
    }

    // 1️⃣ ZIP code range check (existing endpoint is fine)
    const zip = document.getElementById('zip').value.trim();
    try {
      const zipRes = await fetch(`/verify_zip?zipcode=${encodeURIComponent(zip)}`);
      const zipData = await zipRes.json();
      if (!zipData.valid) {
        showFormError('zip', zipData.reason);
        return;
      }
    } catch (err) {
      console.error(err);
      showFormError('zip', 'ZIP-code validation failed. Please retry.');
      return;
    }

    // 2️⃣ Address existence check (new POST endpoint)
    const addr   = document.getElementById('address').value.trim();
    const city   = document.getElementById('city').value.trim();
    const placeId = document.getElementById('place_id').value || null;

    const body = JSON.stringify({
      full_addr: `${addr}, ${city}, CA ${zip}`,
      place_id : placeId,
      city     : city,   // ← add both
      zip      : zip
    });

    try {
      const aRes = await fetch('/api/validate_address', {
        method : 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken' : csrfToken,
        },
        body,
      });
      const aData = await aRes.json();
      if (!aData.valid) {
        showFormError('address', aData.message);
        return;
      }
    } catch (err) {
      console.error(err);
      showFormError('address',
        'Address validation service unavailable. Please try again.');
      return;
    }

    // 3️⃣ All good → let the *real* POST go through
    alreadyPosted = true;                         // flip the guard
    initForm.submit();                            // triggers server-side checks
  });

  /* ───────────────────────────────────────────── */
  /* Tiny util to display inline messages          */
  function showFormError(fieldName, msg) {
    // remove any earlier message
    document.querySelectorAll(`.err-${fieldName}`).forEach(el => el.remove());

    const field = document.getElementById(fieldName);
    const div   = document.createElement('div');
    div.textContent = msg;
    div.className   = `user-notice-warn err-${fieldName}`;
    field.insertAdjacentElement('afterend', div);

    // scroll the error into view and focus the field
    div.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }



