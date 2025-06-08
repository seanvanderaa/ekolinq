document.addEventListener("DOMContentLoaded", function () {
    const editAddressText = document.getElementById('address-info');
    const editAddressForm = document.getElementById('edit-address-form');
    const editAddressPencil = document.getElementById('edit-address');
    const addressHeader = document.getElementById('address-header');
    const closeUpdate = document.getElementById('cancel-update-address');
    const loadingDiv = document.getElementById('loading-popup');
    const overlay = document.getElementById('overlay');

    if(editAddressPencil) editAddressPencil.addEventListener('click', displayForm);
    if(closeUpdate) closeUpdate.addEventListener('click', displayForm);


    function displayForm() {
      // Use getComputedStyle to see if the text-div is currently shown or hidden
      const textIsVisible = window
        .getComputedStyle(editAddressText)
        .display !== "none";

      if (textIsVisible) {
        // If the text is visible, hide it and show the form
        editAddressText.style.display = "none";
        addressHeader.textContent = "Edit Address";
        editAddressForm.style.display = "flex";
      } else {
        // Otherwise, show the text and hide the form
        editAddressText.style.display = "flex";
        addressHeader.textContent = "Address";
        editAddressForm.style.display = "none";
      }
    }

    const cancelRequestInit = document.getElementById('cancel-request-init');
    const cancelRequestWrapper = document.getElementById('cancel-confirm-wrapper');
    const cancelCancelRequest = document.getElementById('cancel-back-btn');

    if(cancelRequestInit) cancelRequestInit.addEventListener('click', cancelRequest);
    if(cancelCancelRequest) cancelCancelRequest.addEventListener('click', cancelRequest);

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
        const request_id = document.getElementById('request_id').value;
        window.location.href = `/edit-request?request_id=${encodeURIComponent(request_id)}`;
      });
    }

    const cancelRequestForm = document.getElementById('cancel-request-form');
    if(cancelRequestForm) cancelRequestForm.addEventListener('submit', async function (event) {
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
  const request_date = document.getElementById('request-date')?.getAttribute('data-date');
  const request_time = document.getElementById('request-time')?.getAttribute('data-time');



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
        overlay.style.display = "block";
        loadingDiv.style.display = "block";
        updateAddressForm.submit(); 
      } else {
        alert(`${data.reason}`);
      }
    } catch (err) {
      console.error(err);
      alert('Error verifying ZIP code. Please try again.');
    }
  });

  submitBtn.addEventListener('click', function() {
    overlay.style.display = "block";
    loadingDiv.style.display = "block";
  });
});

