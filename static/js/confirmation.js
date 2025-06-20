document.addEventListener("DOMContentLoaded", function () {
  // Retrieve the raw data directly from the DOM
  const requestDateEl = document.getElementById('request-date');
  const requestTimeEl = document.getElementById('request-time');
  const request_date = requestDateEl.getAttribute('data-date'); // e.g., "2025-01-12"
  const request_time = requestTimeEl.getAttribute('data-time'); // e.g., "08:00-12:00"

  // Format the date
  const formatDate = (dateStr) => {
      const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
      const months = ['Jan.', 'Feb.', 'Mar.', 'Apr.', 'May', 'Jun.', 'Jul.', 'Aug.', 'Sep.', 'Oct.', 'Nov.', 'Dec.'];

      const date = new Date(dateStr);
      const dayName = days[date.getUTCDay()];
      const monthName = months[date.getUTCMonth()];
      const day = date.getUTCDate();

      // Add ordinal suffix for the day
      const ordinal = (n) => n + (["th", "st", "nd", "rd"][(n % 10 > 3 || Math.floor(n % 100 / 10) === 1) ? 0 : n % 10] || "th");
      return `${dayName}, ${monthName} ${ordinal(day)}`;
  };

  // Format the time
  const formatTime = (timeStr) => {
      const [start, end] = timeStr.split('-').map(t => {
          const [hour, minute] = t.split(':').map(Number);
          const period = hour >= 12 ? 'pm' : 'am';
          const adjustedHour = hour % 12 || 12;
          return `${adjustedHour}:${minute.toString().padStart(2, '0')}${period}`;
      });
      return `${start}-${end}`;
  };

  // Combine formatted date and time
  const formattedDate = formatDate(request_date);
  const formattedTime = formatTime(request_time);

  // Update the content
  document.getElementById('pickup-info').textContent = `${formattedDate} between 8am-4pm`;
  

});