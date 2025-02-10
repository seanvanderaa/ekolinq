document.addEventListener("DOMContentLoaded", function () {
    // 1) Highlight squares hover logic
    const highlightSquares = document.querySelectorAll('.highlight-square');
  
    highlightSquares.forEach((square) => {
      // The ID of the text container we want to reveal
      const revealId = square.getAttribute('data-reveal-target');
      const revealSquare = document.getElementById(revealId);
  
      if (revealSquare) {
        // Grab the paragraph or child you want to fade in/out
        const revealText = revealSquare.querySelector('.reveal-text');
        if (!revealText) return;
  
        // Hover in => add 'active'
        square.addEventListener('mouseover', function () {
          revealText.classList.add('active');
        });
  
        // Hover out => remove 'active'
        square.addEventListener('mouseout', function () {
          revealText.classList.remove('active');
        });
      }
    });
  
    // 2) Fade-in on scroll logic (Intersection Observer)
    const faders = document.querySelectorAll('.fade-in-section');
    const appearOptions = {
      threshold: 0.15, // Trigger when 15% of the element is visible
    };
  
    const appearOnScroll = new IntersectionObserver((entries, observer) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible'); // Add the .visible class to trigger animation
          observer.unobserve(entry.target);       // Stop observing to prevent re-trigger
        }
      });
    }, appearOptions);
  
    faders.forEach(fader => {
      appearOnScroll.observe(fader);
    });
  
    // 3) Form submission logic
    document.getElementById('request-form-input').addEventListener('submit', async function (event) {
      event.preventDefault(); // Prevent default form submission
  
      const zipcode = document.getElementById('zipcode').value;
  
      // Make an AJAX request to the Flask endpoint
      const response = await fetch(`/verify_zip?zipcode=${zipcode}`);
      const data = await response.json();
  
      if (data.valid) {
        // Redirect to /request_pickup if ZIP code is valid
        window.location.href = `/request_pickup?zipcode=${zipcode}`;
      } else {
        // Display an alert with the invalid reason
        alert(`${data.reason}`);
      }
    });
  });
  