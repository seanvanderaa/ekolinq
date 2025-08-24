document.addEventListener("DOMContentLoaded", function () {
  const dateSelectors = document.querySelectorAll(".day-wrapper");
  const submitBtn = document.getElementById("timeframe-submit-btn");
  const submitBtnInfo = document.getElementById("submit-btn-info");
  const chosenDateInput = document.getElementById("chosen_date");
  const chosenTimeInput = document.getElementById("chosen_time");
  const form = document.getElementById("timeframe-form");
  const weekSpecElement = document.getElementById("week-specification");
  const baseDate = weekSpecElement?.getAttribute("data-base-date");
  const outer = document.getElementById("date-selection-scroll");
  const inner = document.getElementById("date-selection-wrapper");
  const overlay = document.getElementById("overlay");
  const loadingDiv = document.getElementById("loading-popup");

  // Ensure the button is clickable (even if the HTML still has 'disabled')
  submitBtn.removeAttribute("disabled");

  function showValidationAlert(message) {
    let alertEl = document.getElementById("date-selection-alert");
    if (!alertEl) {
      alertEl = document.createElement("div");
      alertEl.id = "date-selection-alert";
      alertEl.setAttribute("role", "alert");
      alertEl.style.cssText =
        "margin-top:12px;margin-bottom:-12px;color:#b00020;background:#fdecea;border:1px solid #f5c2c7;padding:10px 12px;border-radius:8px;font-weight:500;";
      submitBtn.parentNode.insertBefore(alertEl, submitBtn);
    }
    alertEl.textContent = message;
    alertEl.style.display = "block";
    alertEl.animate(
      [{ opacity: 0 }, { opacity: 1 }, { opacity: 0.4 }, { opacity: 1 }],
      { duration: 600, iterations: 1 }
    );
    if (outer) {
      outer.animate(
        [
          { boxShadow: "0 0 0 0 rgba(220,38,38,0)" },
          { boxShadow: "0 0 0 4px rgba(220,38,38,0.35)" },
          { boxShadow: "0 0 0 0 rgba(220,38,38,0)" }
        ],
        { duration: 900, iterations: 1 }
      );
      outer.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    setTimeout(() => (alertEl.style.display = "none"), 3000);
  }

  function updateAlignment() {
    if (!outer || !inner) return;
    inner.style.justifyContent =
      inner.scrollWidth > outer.clientWidth ? "flex-start" : "center";
  }

  function handleClick(event) {
    const el = event.currentTarget;
    const isActive = el.classList.contains("active");

    document.querySelectorAll(".day-wrapper.active")
      .forEach(n => n.classList.remove("active"));

    if (!isActive) {
      el.classList.add("active");

      const dayIso = el.getAttribute("data-date");
      const timeRange = "08:00-16:00";
      chosenDateInput.value = dayIso;
      chosenTimeInput.value = timeRange;
      const dateLabel = el.querySelector("p")?.innerText || dayIso || "";

      submitBtn.classList.remove("is-disabled"); // visually enabled
      submitBtnInfo.style.display = "block";
      submitBtnInfo.textContent = `Between 8am-4pm on ${dateLabel}`;
    } else {
      el.classList.remove("active");
      chosenDateInput.value = "";
      chosenTimeInput.value = "";
      submitBtn.classList.add("is-disabled"); // visually disabled
      submitBtnInfo.style.display = "none";
      submitBtnInfo.textContent = "";
    }
  }


  dateSelectors.forEach((selector) => selector.addEventListener("click", handleClick));

  if (baseDate && weekSpecElement) weekSpecElement.textContent = baseDate;

  updateAlignment();
  window.addEventListener("resize", updateAlignment);

  // FAQ popups
  const faqItems = document.querySelectorAll(".faq-item");
  faqItems.forEach((item) => {
    item.addEventListener("click", function () {
      const popup = document.getElementById(item.id + "-popup");
      if (popup && overlay) {
        overlay.style.display = "block";
        popup.style.display = "block";
      }
    });
  });
  document.querySelectorAll(".popup-close").forEach((button) => {
    button.addEventListener("click", function () {
      if (overlay) overlay.style.display = "none";
      document.querySelectorAll(".faq-popup").forEach((p) => (p.style.display = "none"));
    });
  });

  // Validate on submit (covers click, Enter key, etc.)
  form.addEventListener("submit", function (e) {
    if (!chosenDateInput.value) {
      e.preventDefault();
      showValidationAlert("Please select one of the available dates.");
      return;
    }

    // show loading
    overlay.style.display = "block";
    loadingDiv.style.display = "block";
  });

});
