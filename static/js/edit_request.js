document.addEventListener("DOMContentLoaded", function () {
    const editAddressText = document.getElementById('address-info');
    const editAddressForm = document.getElementById('edit-address-form');
    const editAddressPencil = document.getElementById('edit-address');
    const addressHeader = document.getElementById('address-header');
    const closeUpdate = document.getElementById('cancel-update-address');

    editAddressPencil.addEventListener('click', displayForm);
    closeUpdate.addEventListener('click', displayForm);


    function displayForm() {
      if (editAddressText.style.display === "flex") {
        editAddressText.style.display = "none";
        addressHeader.textContent = `Edit Address`;
        editAddressForm.style.display = "flex";
      }
      else {
        editAddressText.style.display = "flex";
        addressHeader.textContent = `Address`;
        editAddressForm.style.display = "none";
      }
    }

    const cancelRequestInit = document.getElementById('cancel-request-init');
    const cancelRequestWrapper = document.getElementById('cancel-confirm-wrapper');
    const cancelCancelRequest = document.getElementById('cancel-back-btn');

    cancelRequestInit.addEventListener('click', cancelRequest);
    cancelCancelRequest.addEventListener('click', cancelRequest);

    function cancelRequest() {
      if (cancelRequestWrapper.style.display === "flex") {
        cancelRequestWrapper.style.display = "none";
        cancelRequestInit.classList.remove('active');
      }
      else {
        console.log("Here");
        cancelRequestWrapper.style.display = "flex";
        cancelRequestInit.classList.add('active');
      }
    }
    const dateSelectors = document.querySelectorAll('.day-wrapper');
    const submitBtn = document.getElementById('timeframe-submit-btn');
    const submitBtnInfo = document.getElementById('submit-btn-info');
    const chosenDateInput = document.getElementById('chosen_date');
    const chosenTimeInput = document.getElementById('chosen_time');

    // Function to handle time slot click
    function handleClick(event) {
      console.log('Clicked');
      const el = event.currentTarget;

      // If the user clicks an already-active slot, let’s unselect it
      if (el.classList.contains('active')) {
        el.classList.remove('active');
        submitBtn.disabled = true;
        submitBtnInfo.style.display = "none";
        chosenDateInput.value = "";
        chosenTimeInput.value = "";
        return;
      }

      // Otherwise, unselect all timeframe-selectors, then select the clicked one
      dateSelectors.forEach(selector => selector.classList.remove('active'));
      el.classList.add('active');
      
      // Enable the submit button
      submitBtn.disabled = false;
      submitBtnInfo.style.display = "block";

      // Grab the date/time from data attributes
      const dayIso = el.getAttribute('data-date');  // e.g. "2025-01-11"
      const timeRange = "08:00-16:00"; // e.g. "08:00-12:00"

      // Update hidden inputs
      chosenDateInput.value = dayIso;   // "2025-01-11"
      console.log(dayIso);
      chosenTimeInput.value = "08:00-16:00"; // "08:00-12:00"

      // Also update the small text below the button:
      // e.g. "Between 08:00-12:00 on Jan. 11"
      // We can parse the date to something user-friendly, or pass that from Jinja.
      // For simplicity, we’ll just do:
      let dateLabel = el.querySelector('p')?.innerText || '';
      if (!dateLabel) {
        // fallback
        dateLabel = dayIso; 
      }
      submitBtnInfo.textContent = `Between 8am-4pm on ${dateLabel}`;
    }

    // Attach the click event listener to each timeframe selector
    dateSelectors.forEach(selector => {
      selector.addEventListener('click', handleClick);
    });
    const weekSpecElement = document.getElementById('date-selection-scroll');
    if (weekSpecElement) {
      const baseDate = weekSpecElement.getAttribute('data-base-date');   
      const outer = weekSpecElement; 
      const inner = document.getElementById('date-selection-wrapper');
    
      function updateAlignment() {
        if (inner && outer) {
          if (inner.scrollWidth > outer.clientWidth) {
            inner.style.justifyContent = 'flex-start';
          } else {
            inner.style.justifyContent = 'center';
          }
        }
      }
      updateAlignment();
      window.addEventListener('resize', updateAlignment);
    }
    const cancelBtn = document.getElementById("cancel-edit-date");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", function () {
        // 1) Retrieve the POST target URL and the request_id
        const targetUrl = cancelBtn.getAttribute("data-cancel-url"); 
        const requestId = cancelBtn.getAttribute("data-request-id");
    
        // 2) Dynamically create a standalone form
        const form = document.createElement("form");
        form.method = "POST";
        form.action = targetUrl;
    
        // 3) Add hidden input for the request_id
        const hiddenInput = document.createElement("input");
        hiddenInput.type = "hidden";
        hiddenInput.name = "request_id";
        hiddenInput.value = requestId;
        form.appendChild(hiddenInput);
    
        // 4) Append the CSRF token hidden input
        const csrfToken = document.querySelector('[name="csrf_token"]').value;
        const csrfInput = document.createElement("input");
        csrfInput.type = "hidden";
        csrfInput.name = "csrf_token";
        csrfInput.value = csrfToken;
        form.appendChild(csrfInput);
    
        // 5) Append the form to the document and submit it
        document.body.appendChild(form);
        form.submit();
      });
    }

document.getElementById('cancel-request-form').addEventListener('submit', async function (event) {
  event.preventDefault(); // Prevent default form submission

  const request_id = document.getElementById('form-request-id').value;

  const form = event.target;
  const formData = new FormData(form);
  const response = await fetch(form.action, {
    method: "POST",
    body: formData
  });
  const data = await response.json();

  if (data.valid) {
    alert(`${data.reason}`);
    window.location.href = '/'; 
  } else {
    alert(`${data.reason}`);
  }
});

  // Retrieve the raw data directly from the DOM
  const requestDateEl = document.getElementById('request-date');
  const requestTimeEl = document.getElementById('request-time');
  const request_date = requestDateEl.getAttribute('data-date'); // e.g., "2025-01-12"
  const request_time = requestTimeEl.getAttribute('data-time'); // e.g., "08:00-12:00"

  // Format the date
  const formatDate = (dateStr) => {
      const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
      const months = ['Jan.', 'Feb.', 'Mar.', 'Apr.', 'May', 'Jun.', 'Jul.', 'Aug.', 'Sep.', 'Oct.', 'Nov.', 'Dec.'];

      const date = new Date(dateStr);
      const dayName = days[date.getUTCDay()];
      const monthName = months[date.getUTCMonth()];
      const day = date.getUTCDate();

      // Add ordinal suffix for the day
      const ordinal = (n) => n + (["th", "st", "nd", "rd"][(n % 10 > 3 || Math.floor(n % 100 / 10) === 1) ? 0 : n % 10] || "th");
      console.log(`${dayName}, ${monthName} ${ordinal(day)}`);
      return `${dayName}, ${monthName} ${ordinal(day)}`;
  };

  // Format the time
  const formatTime = (timeStr) => {
      const [start, end] = timeStr.split('-').map(t => {
          const [hour, minute] = t.split(':').map(Number);
          const period = hour >= 12 ? 'pm' : 'am';
          const adjustedHour = hour % 12 || 12;
          return `${adjustedHour}:${minute.toString().padStart(2, '0')}${period}`;
      });
      return `${start}-${end}`;
  };

  // Combine formatted date and time
  const formattedDate = formatDate(request_date);
  const formattedTime = formatTime(request_time);

  // Update the content
  document.getElementById('pickup-info').textContent = `${formattedDate} between 8am-4pm`;
  
  const updateAddressForm = document.getElementById('edit-address-form');

  updateAddressForm.addEventListener('submit', async function (event) {
    event.preventDefault();

    const zipcode = document.getElementById('zipcode').value;


    try {
      const response = await fetch(`/verify_zip?zipcode=${zipcode}`);
      const data = await response.json();

      if (data.valid) {
        // If ZIP is valid, submit for real
        updateAddressForm.submit(); 
      } else {
        alert(`${data.reason}`);
      }
    } catch (err) {
      console.error(err);
      alert('Error verifying ZIP code. Please try again.');
    }
  });
});

