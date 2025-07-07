document.addEventListener("DOMContentLoaded", function() {
  document.body.addEventListener('click', event => {
    // Did a .btn-close inside a .flash-message get clicked?
    const btn = event.target.closest('.flash-message .btn-close');
    if (!btn) return;

    // Find the flash-message wrapper
    const flash = btn.closest('.flash-message');
    if (!flash) return;

    // Remove the 'show' class to trigger Bootstrap fade‐out (if used)
    flash.classList.remove('show');

    // After fade transition (150ms default), actually remove it from the DOM
    flash.addEventListener('transitionend', () => {
      flash.remove();
    }, { once: true });
  });
  const tableBody  = document.querySelector('#requests-table tbody');

  /* ------------------  delete & view buttons  ------------------ */
  tableBody.addEventListener('click', e => {
    /* ----- view ----- */
    const viewBtn = e.target.closest('.view-request-btn');
    if (viewBtn) {
      window.location.href = `/individual-pickup/${viewBtn.dataset.id}`;
      return;        // don’t fall through
    }
  });

  /* catch the FORM submit, not the button click */
  tableBody.addEventListener('submit', e => {
    if (!e.target.matches('.delete-form')) return;   // some other form

    if (!confirm('Are you sure you want to delete this pickup?')) {
      e.preventDefault();                            // keep the row
    }
  });

  const filterForm = document.getElementById('filter-form');

  // Function to fetch filtered requests and update the table
  function updateTable() {
    const formData = new FormData(filterForm);
    const queryString = new URLSearchParams(formData).toString();
    
    fetch(filterForm.action + '?' + queryString)
      .then(response => response.text())
      .then(html => {
        tableBody.innerHTML = html;
      })
      .catch(error => console.error('Error fetching filtered data:', error));
  }
  
  // Add event listeners for each select and input to trigger updateTable on change
  filterForm.querySelectorAll('select, input').forEach(el => {
    el.addEventListener('change', updateTable);
  });
    
  const cleanForm = document.getElementById('cleanup_form');
  const overlay   = document.getElementById('overlay');

  if (cleanForm && overlay) {
    cleanForm.addEventListener('submit', () => {
      // disable the submit button to prevent double-clicks (optional)
      cleanForm.querySelector('button, input[type="submit"]')?.setAttribute('disabled', 'disabled');

      // reveal the overlay + spinner
      overlay.classList.add('show');
    });
  }
  else {
    console.log("NOPE!");
  }
  
});
