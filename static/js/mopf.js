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
  // Smooth-scroll to the form when the (conditionally visible) button is clicked
  const scrollBtn = document.getElementById('scroll-to-form');
  if (scrollBtn) {
    scrollBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const formEl = document.getElementById('init-form');
      if (!formEl) return;

      // Prefer scrolling the scrollable container (main) if present
      const mainEl = document.querySelector('main');
      if (mainEl) {
        const targetTop = formEl.getBoundingClientRect().top - mainEl.getBoundingClientRect().top + mainEl.scrollTop;
        mainEl.scrollTo({ top: Math.max(0, targetTop), behavior: 'smooth' });
      } else {
        // Fallback: let the browser choose the scroll container
        formEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }

  const initForm   = document.getElementById('init-form-info');
  const csrfToken  = document.querySelector('input[name="csrf_token"]').value;

  ['address', 'city', 'zip'].forEach(id => {
    const el = document.getElementById(id);
    el.addEventListener('input', () => {
      document.getElementById('place_id').value = '';
    });
  });

  const gatedError = document.getElementById('gated-error-info');

  initForm.addEventListener('submit', async function handleSubmit (evt) {
    evt.preventDefault();

    // reCAPTCHA client-side guard
    if (grecaptcha.getResponse().length === 0) {
      showFormError('recaptcha-form', 'Please click the “I’m not a robot” box. Refreshing can resolve most issues.');
      return;
    }

    const loader = document.getElementById('loader');
    loader.style.display = "inline-block";

    // Build FormData from the actual form so WTForms + CSRF + reCAPTCHA validate
    const formData = new FormData(initForm);
    try {
      const response = await fetch(initForm.action || '/mopf-submit', {
        method: 'POST',
        body: formData // Let the browser set multipart/form-data with boundary
      });

      const result = await response.json();

      if (result && result.success === true) {
        // Hide the form and show the success wrapper if present
        initForm.style.display = 'none';
        const successWrapper = document.getElementById('success-wrapper');
        if (successWrapper) {
          successWrapper.style.display = 'flex';
        }
      } else {
        loader.style.display = "none";
        // Try to surface field-specific errors if provided
        if (result && result.errors) {
          Object.entries(result.errors).forEach(([field, msgs]) => {
            const el = document.getElementById(field) || document.getElementById('init-form-info');
            const msgText = Array.isArray(msgs) ? msgs.join(' ') : String(msgs);
            showFormError(el.id, msgText);
          });
        } else {
          showFormError('init-form-info', 'Submission failed. Please try again.');
        }
      }
    } catch (error) {
      loader.style.display = "none";
      showFormError('init-form-info', error.message || 'An error occurred. Please try again.');
    }
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
});



