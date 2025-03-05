document.addEventListener("DOMContentLoaded", function () {
    const timeframeSelectors = document.querySelectorAll('.timeframe-selector');
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
      let dateLabel = el.parentNode.querySelector('p')?.innerText || '';
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
    const weekSpecElement = document.getElementById('week-specification');
    const baseDate = weekSpecElement.getAttribute('data-base-date');

    if (baseDate) {
        // Optionally, format the date if needed
        // Assuming base_date_str is already in "Jan. 26" format
        weekSpecElement.textContent = baseDate;
    }
    const outer = document.getElementById('date-selection-scroll');
    const inner = document.getElementById('date-selection-wrapper');

    function updateAlignment() {
      // If content is wider than the outer container, use flex-start
      if (inner.scrollWidth > outer.clientWidth) {
        inner.style.justifyContent = 'flex-start';
      } else {
        // Otherwise, keep it centered
        inner.style.justifyContent = 'center';
      }
    }

    // Check on load
    updateAlignment();

    // And recheck on window resize (or any other event you like)
    window.addEventListener('resize', updateAlignment);
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