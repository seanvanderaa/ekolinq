document.addEventListener("DOMContentLoaded", function() {
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
});
