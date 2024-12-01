// Toggle Password Visibility
function togglePasswordVisibility(fieldId) {
    const field = document.getElementById(fieldId);
    const toggleIcon = field.parentElement.querySelector('.input-group-text i'); // Correctly locate the icon
    if (field.type === "password") {
        field.type = "text";
        toggleIcon.classList.remove('fa-eye');
        toggleIcon.classList.add('fa-eye-slash');
    } else {
        field.type = "password";
        toggleIcon.classList.remove('fa-eye-slash');
        toggleIcon.classList.add('fa-eye');
    }
}

// Live Validation
function validateField(fieldId, errorId, validationFn, errorMessage) {
    const field = document.getElementById(fieldId);
    const errorField = document.getElementById(errorId);

    field.addEventListener('input', function () {
        if (validationFn(field.value)) {
            errorField.innerText = '';
            field.classList.remove('error-highlight');
        } else {
            errorField.innerText = errorMessage;
            field.classList.add('error-highlight');
        }
    });
}

// Validate Form
function validateForm(fields) {
    let isValid = true;
    fields.forEach(({ fieldId, errorId, validationFn, errorMessage }) => {
        const value = document.getElementById(fieldId).value.trim();
        const errorField = document.getElementById(errorId);
        if (!validationFn(value)) {
            errorField.innerText = errorMessage;
            document.getElementById(fieldId).classList.add('error-highlight');
            isValid = false;
        } else {
            errorField.innerText = '';
            document.getElementById(fieldId).classList.remove('error-highlight');
        }
    });
    return isValid;
}

// Add Event Listeners for Fields
validateField('username', 'usernameError',
    value => value.length >= 3,
    'Username must be at least 3 characters long.'
);

validateField('password', 'passwordError',
    value => value.length >= 6 && /(?=.*[0-9])(?=.*[A-Z])/.test(value),
    'Password must be at least 6 characters long, contain one number, and one uppercase letter.'
);

validateField('confirmPassword', 'confirmPasswordError',
    value => value === document.getElementById('password').value,
    'Passwords do not match.'
);

// Form Submission
document.getElementById('registerForm').addEventListener('submit', function (event) {
    event.preventDefault(); // Prevent default submission

    const fields = [
        { fieldId: 'username', errorId: 'usernameError', validationFn: value => value.length >= 3, errorMessage: 'Username must be at least 3 characters long.' },
        { fieldId: 'password', errorId: 'passwordError', validationFn: value => value.length >= 6 && /(?=.*[0-9])(?=.*[A-Z])/.test(value), errorMessage: 'Password must be at least 6 characters long, contain one number, and one uppercase letter.' },
        { fieldId: 'confirmPassword', errorId: 'confirmPasswordError', validationFn: value => value === document.getElementById('password').value, errorMessage: 'Passwords do not match.' }
    ];

    const isValid = validateForm(fields);

    if (isValid) {
        this.submit(); // Submit the form
    }
});
