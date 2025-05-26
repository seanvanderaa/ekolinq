// static/js/waste.js
document.addEventListener('DOMContentLoaded', () => {
  // The trigger span
  const trigger = document.getElementById('acceptable-items');
  trigger.style.cursor = 'pointer';

  // The backdrop overlay already in base.html
  const overlay = document.querySelector('.overlay');

  // The hidden items list; make sure you have this in your HTML too:
  // <div id="items-info" style="display: none;">…</div>
  const itemsInfo = document.getElementById('items-info');

  // Create the modal container
  const modal = document.createElement('div');
  modal.classList.add('popup-modal');
  modal.style.display = 'none';
  modal.innerHTML = `
    <div class="popup-content">
      ${itemsInfo.innerHTML}
    </div>
  `;

  // Inject into the page
  document.body.appendChild(modal);

  // Hide overlay initially
  overlay.style.display = 'none';

  // Function to open popup
  function openPopup() {
    overlay.style.display = 'block';
    modal.style.display = 'flex';
  }

  // Function to close popup
  function closePopup() {
    overlay.style.display = 'none';
    modal.style.display = 'none';
  }

  // Wire up events
  trigger.addEventListener('click', openPopup);
  overlay.addEventListener('click', closePopup);
  modal.querySelector('.download-btn').addEventListener('click', closePopup);
});
