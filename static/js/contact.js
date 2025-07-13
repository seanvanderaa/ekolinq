document.addEventListener('DOMContentLoaded', () => {
    console.log('here');
    const form  = document.getElementById('contactForm');
    const btn   = document.getElementById('contactFormBtn');
    const wrap  = document.getElementById('contact-form-wrapper');
    const done  = document.getElementById('contact-form-confirmation');

    done.style.display = 'none';

    form.addEventListener('submit', onSubmit, { once: true });   // <── only once

    async function onSubmit (e) {
        e.preventDefault();

        const form = e.target;
        const btn  = document.getElementById('contactFormBtn');

        btn.disabled = true;
        btn.textContent = 'Sending…';

        try {
            const res  = await fetch(form.action, {
            method:      'POST',
            credentials: 'same-origin',
            body:        new FormData(form)
            });
            const json = await res.json();

            if (json.valid) {
            document.getElementById('contactForm').style.display = 'none';
            document.getElementById('contact-form-confirmation').style.display = 'flex';
            } else {
                if (json.reason == "The response parameter is missing.") {
                    alert("Please be sure to check the box to prove you're not a robot.");
                }
                else {
                    alert(json.reason);
                }
            }
        } catch (err) {
            console.error(err);
            alert('An error occurred. Please try again.');
        } finally {
            btn.disabled = false;
            btn.textContent = 'Submit';
            /* Optional: if you want the form to be usable again without reload
            remove the “once” lock and reset reCAPTCHA                       */
            // grecaptcha.reset();
            // document.getElementById('contactForm')
            //         .addEventListener('submit', onSubmit, { once: true });
        }
    }

    const newRequestBtn = document.getElementById('new-request-btn');
    if (newRequestBtn) {
        newRequestBtn.addEventListener('click', () => {
            window.location.reload();
        });
    }
});
