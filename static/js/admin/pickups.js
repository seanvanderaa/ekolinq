document.addEventListener("DOMContentLoaded", function() {

  const deleteButtons = document.querySelectorAll('.delete-request-btn');

  deleteButtons.forEach(function (button) {
      button.addEventListener('click', function (event) {
          const confirmed = confirm('Are you sure you want to delete this item?');
          if (!confirmed) {
              event.preventDefault();
          }
      });
  });

  const filterForm = document.getElementById('filter-form');
  const tableBody = document.querySelector('#requests-table tbody');

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
  
  const viewButtons = document.querySelectorAll('#view-request');

  viewButtons.forEach(btn => {
    btn.addEventListener('click', function() {
      // Read the pickup ID from data-attribute
      const pickupId = this.getAttribute('data-attribute');

      // Redirect to /admin/pickups/<id>
      if (pickupId) {
        window.location.href = `/individual-pickup/${pickupId}`;
      } else {
        console.error("No pickup ID found on button.");
      }
    });
  });
});
