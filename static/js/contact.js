document.addEventListener('DOMContentLoaded', () => {
    const form  = document.getElementById('contactForm');
    const wrap  = document.getElementById('contact-form-wrapper');
    const done  = document.getElementById('contact-form-confirmation');
    const submitBtn = document.getElementById('contactFormBtn');

    done.style.display = 'none';


    async function onSubmit(e) {
        e.preventDefault();
        submitBtn.disabled = true;
        submitBtn.textContent = 'Sending…';
        try {
        const res  = await fetch(form.action, {
            method:      'POST',
            credentials: 'same-origin',
            body:        new FormData(form)
        });
        const json = await res.json();
        if (json.valid) {
            form.style.display = 'none';
            done.style.display = 'flex';
        } else {
            if (window.grecaptcha) grecaptcha.reset();
            if (json.reason == "The response parameter is missing.") {
                alert("Please be sure to check the box to prove you're not a robot.");
            } else {
                alert(json.reason || "Please complete the recaptcha.");
            }
        }
        } catch {
        alert('An error occurred. Please refresh the page and try again.');
        } finally {
        submitBtn.disabled   = false;
        submitBtn.textContent = 'Submit';
        }
    }

    form.addEventListener('submit', onSubmit);

    document.getElementById('new-request-btn').addEventListener('click', () => {
        // 1) reset form fields
        form.reset();
        // 2) reset reCAPTCHA
        if (window.grecaptcha) grecaptcha.reset();
        // 3) toggle back to the form
        form.style.display = 'block';
        done.style.display = 'none';
    });

    window.addEventListener('pageshow', (event) => {
        if (event.persisted) window.location.reload();
    });
});
