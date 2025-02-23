document.addEventListener("DOMContentLoaded", function() {
    // Function to toggle display style for a given content element.
    function toggleContent(contentEl, contentWrap, icon) {
      // Get the computed display style
      const currentDisplay = window.getComputedStyle(contentEl).display;
      if (currentDisplay === "none") {
        // Reveal the element. We default to "flex" because that's what you mentioned,
        // but if you need another default, you can change it here.
        contentEl.style.display = "flex";
        contentWrap.style.borderRadius = "10px 10px 0px 0px";
        icon.style.transform = "rotate(180deg)";
      } else {
        contentEl.style.display = "none";
        contentWrap.style.borderRadius = "10px";
        icon.style.transform = "rotate(0deg)";
      }
    }
  
    // Toggle upcoming dates
    const upcomingHeader = document.getElementById("upcoming-dates-header");
    const upcomingContent = document.getElementById("upcoming-dates");
    const upcomingIcon = document.getElementById("upcoming-pickups-icon");
    if (upcomingHeader && upcomingContent) {
      upcomingHeader.addEventListener("click", function() {
        toggleContent(upcomingContent, upcomingHeader, upcomingIcon);
      });
    }
  
    // Toggle past dates
    const pastHeader = document.getElementById("past-pickups-header");
    const pastContent = document.getElementById("past-dates");
    const pastIcon = document.getElementById("past-pickups-icon");
    if (pastHeader && pastContent) {
      pastHeader.addEventListener("click", function() {
        toggleContent(pastContent, pastHeader, pastIcon);
      });
    }
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
  
    // Add event listeners for each input/select element
    filterForm.querySelectorAll('select, input').forEach(el => {
      el.addEventListener('change', updateTable);
    });
  });
