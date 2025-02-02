document.addEventListener("DOMContentLoaded", function () {
    const editAddressText = document.getElementById('address-info');
    const editAddressForm = document.getElementById('edit-address-form');
    const editAddressPencil = document.getElementById('edit-address');
    const addressHeader = document.getElementById('address-header');



    editAddressPencil.addEventListener('click', displayForm);

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
  document.getElementById('pickup-info').textContent = `${formattedDate} between ${formattedTime}`;
  
  const updateAddressForm = document.getElementById('edit-address-form');

  updateAddressForm.addEventListener('submit', async function (event) {
    event.preventDefault();

    const zipcode = document.getElementById('zip').value;


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