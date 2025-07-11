document.addEventListener("DOMContentLoaded", function () {

    const navTextileWaste = document.getElementById('nav-textile-waste');
    if (navTextileWaste) {
      navTextileWaste.addEventListener('click', () => {
        window.location.href = '/textile-waste';
      });
    }

    const aboutUs = document.getElementById('about-us-btn');
    if (aboutUs) {
      aboutUs.addEventListener('click', () => {
        window.location.href = '/about';
      });
    }

    const getInTouch = document.getElementById('get-in-touch');
    if (getInTouch) {
      getInTouch.addEventListener('click', () => {
        // this only runs when you click
        window.location.href = '/contact';
      });
    }
    // Find all highlight squares
    
    const highlightSquares = document.querySelectorAll('.highlight-square');

    highlightSquares.forEach((square) => {
      // The ID of the text container we want to reveal
      const revealId = square.getAttribute('data-reveal-target');
      const revealSquare = document.getElementById(revealId);

      if (revealSquare) {
        // Grab the paragraph (or any child you want to fade in/out)
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
  });

  document.getElementById('request-form-input').addEventListener('submit', async function (event) {
      event.preventDefault(); // Prevent default form submission behavior

      const zipcode = document.getElementById('zipcode').value;

      // Make an AJAX request to the Flask endpoint
      const response = await fetch(`/verify_zip?zipcode=${zipcode}`);
      const data = await response.json();

      if (data.valid) {
          // Redirect to the /request endpoint if the ZIP code is valid
          window.location.href = `/request_pickup?zipcode=${zipcode}`
      } else {
          // Display an alert or popup with the invalid ZIP code reason
          alert(`${data.reason}`);
      }
  });
      navForward = document.getElementById('request-a-pickup');
    navForward.addEventListener('click', function() {
      window.location.href = `/request_init`;
    });