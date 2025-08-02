window.initAutocomplete = function () {
  const addressEl = document.getElementById('address');

  // 2️⃣  Create the widget – keep one “display” field in the mask
  const ac = new google.maps.places.Autocomplete(addressEl, {
    componentRestrictions: { country: "us" },
    types   : ["address"],
    fields  : ["address_components", "name", "place_id"], // name lets Google fill the box
  });

  ac.addListener("place_changed", () => fillForm(ac.getPlace()));
};

// 3️⃣  Map Google component types → your inputs
const MAP = {
  street_number        : { id: "address", cat: "street" },
  route                : { id: "address", cat: "street" },
  locality             : { id: "city"    },
  postal_town          : { id: "city"    }, // UK/SE
  sublocality_level_1  : { id: "city"    }, // e.g. Brooklyn
  administrative_area_level_3: { id: "city" },
  postal_code          : { id: "zip"     },
};

function fillForm(place) {
  if (!place.address_components) return;

  // clear previous values
  ["address","city","zip"].forEach(id => document.getElementById(id).value = "");
  document.getElementById("place_id").value = place.place_id || "";

  place.address_components.forEach(c => {
    c.types.forEach(t => {
      const cfg = MAP[t];
      if (!cfg) return;
      const el  = document.getElementById(cfg.id);
      if (cfg.cat === "street") {
        // concatenate street_number + route
        el.value = [el.value, c.long_name].filter(Boolean).join(" ");
      } else {
        el.value = c.long_name;
      }
    });
  });
}


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

    // reCAPTCHA client-side guard
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

    const loader = document.getElementById('loader');
    loader.style.display = "inline-block";

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
    document
      .querySelectorAll(`.err-${fieldName}`)
      .forEach(el => el.remove());

    const field = document.getElementById(fieldName);
    const div   = document.createElement('div');

    // always wrap the condition in parentheses, and use === for comparison
    if (msg === "The response parameter is missing.") {
      msg = 'Please click the “I’m not a robot” box.';
    }

    // set the message text
    div.textContent = msg;
    div.className   = `user-notice-warn err-${fieldName}`;

    // insert the error and scroll it into view
    field.insertAdjacentElement('afterend', div);
    div.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }




