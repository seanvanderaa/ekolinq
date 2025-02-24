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
      const eventType = ("ontouchstart" in window || navigator.maxTouchPoints) ? "touchstart" : "click";
      upcomingHeader.addEventListener(eventType, function() {
        toggleContent(upcomingContent, upcomingHeader, upcomingIcon);
      });
    }
  
    // Toggle past dates
    const pastHeader = document.getElementById("past-pickups-header");
    const pastContent = document.getElementById("past-dates");
    const pastIcon = document.getElementById("past-pickups-icon");
    if (pastHeader && pastContent) {
      const eventType = ("ontouchstart" in window || navigator.maxTouchPoints) ? "touchstart" : "click";

      pastHeader.addEventListener(eventType, function() {
        toggleContent(pastContent, pastHeader, pastIcon);
      });
    }
  });
