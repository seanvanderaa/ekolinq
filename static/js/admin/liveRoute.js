document.addEventListener('DOMContentLoaded', () => {
    const markCompleteButtons = document.querySelectorAll('.mark-complete');
    const markIncompleteButtons = document.querySelectorAll('.mark-incomplete');
    const markPickupImpossibleButtons = document.querySelectorAll('.mark-pickup-not-possible');

    const csrfToken = document.querySelector('input[name="csrf_token"]').value;

  
    markCompleteButtons.forEach(button => {
      button.addEventListener('click', async function() {
        const pickupId = this.getAttribute('data-pickup-id');
  
        try {
          const formData = new FormData();
          formData.append('pickup_id', pickupId);
          formData.append('csrf_token', csrfToken);

  
          const response = await fetch('/toggle_pickup_status', {
            method: 'POST',
            body: formData
          });
  
          if (!response.ok) {
            alert('Error updating status');
            return;
          }
  
          // At this point we don't really need the JSON data since we're reloading,
          // but here's how you'd parse it if needed:
          // const data = await response.json();
  
          // Simply reload the entire page:
          window.location.reload();
  
        } catch (error) {
          console.error(error);
          alert('Something went wrong');
        }
      });
    });

    markPickupImpossibleButtons.forEach(button => {
      button.addEventListener('click', async function() {
        const pickupId = this.getAttribute('data-pickup-id');
  
        try {
          const formData = new FormData();
          formData.append('pickup_id', pickupId);  
          formData.append('csrf_token', csrfToken);

          const response = await fetch('/mark-pickup-not-possible', {
            method: 'POST',
            body: formData
          });
  
          if (!response.ok) {
            alert('Error updating status');
            return;
          }
  
          // At this point we don't really need the JSON data since we're reloading,
          // but here's how you'd parse it if needed:
          // const data = await response.json();
  
          // Simply reload the entire page:
          window.location.reload();
  
        } catch (error) {
          console.error(error);
          alert('Something went wrong');
        }
      });
    })
    document.getElementById('completed-header')
    .addEventListener('click', function() {
        completedHeader = document.getElementById('completed-header'); 
        completedIcon = document.getElementById('completed-pickups-icon');
        const completedList = document.getElementById('listed-completed-pickups');
        if (completedList.style.display === 'none') {
            completedList.style.display = 'flex';
            completedIcon.style.transform = 'rotate(180deg)';
            completedHeader.style.borderRadius = '10px 10px 0px 0px';
        } else {
            completedList.style.display = 'none';
            completedIcon.style.transform = 'rotate(0deg)';
            completedHeader.style.borderRadius = '10px';
        }
    });
  });