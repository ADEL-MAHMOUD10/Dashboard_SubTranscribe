// Toggle password visibility
const togglePassword = document.getElementById('togglePassword');
const passwordInput = document.getElementById('password');

togglePassword.addEventListener('click', () => {
    const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
    passwordInput.setAttribute('type', type);
    togglePassword.innerHTML = type === 'password' 
        ? '<i class="fas fa-eye"></i>' 
        : '<i class="fas fa-eye-slash"></i>';
});

// JavaScript for form validation
document.getElementById('loginForm').addEventListener('submit', function(event) {
    event.preventDefault(); // Prevent form submission

    // Clear previous errors
    document.getElementById('usernameError').innerText = '';
    document.getElementById('passwordError').innerText = '';
    document.getElementById('formMessage').innerText = '';

    // Get form values
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value.trim();
    let isValid = true;

    // Validate username
    if (!username) {
        document.getElementById('usernameError').innerText = 'Username is required.';
        isValid = false;
    }

    // Validate password
    if (!password) {
        document.getElementById('passwordError').innerText = 'Password is required.';
        isValid = false;
    }

    // If form is valid and no flash messages, show success message
    const flashExists = document.querySelector('.alert.alert-danger');
    if (isValid && !flashExists) {
        document.getElementById('formMessage').innerText = 'Login successful!';
        document.getElementById('loginForm').submit(); // Submit form
    }
});

const flashMessage = document.getElementById('flashMessage');
if (flashMessage) {
    setTimeout(() => {
        flashMessage.style.display = 'none';
    }, 1000);
}
