const themeToggle = document.getElementById('themeToggle');
const body = document.body;
const uploadForm = document.getElementById('uploadForm');
const fileInput = document.getElementById('fileInput');
const dimensionInput = document.getElementById('dimensionInput');
const dropZone = document.getElementById('dropZone');
const preview = document.getElementById('preview');
const placeholder = document.querySelector('.upload-placeholder');
const submitBtn = document.getElementById('submitBtn');
const status = document.getElementById('status');

// --- Theme Management ---
const savedTheme = localStorage.getItem('theme') || 'light';
body.setAttribute('data-theme', savedTheme);
updateThemeButton(savedTheme);

themeToggle.addEventListener('click', () => {
    const currentTheme = body.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    body.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeButton(newTheme);
});

function updateThemeButton(theme) {
    themeToggle.textContent = theme === 'light' ? '🌙 Dark Mode' : '☀️ Light Mode';
}

// --- Upload Logic ---
dropZone.addEventListener('click', () => {
    if (!submitBtn.disabled) {
        fileInput.click();
    }
});

fileInput.addEventListener('change', handleFileSelect);

function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            preview.src = e.target.result;
            preview.style.display = 'block';
            placeholder.style.display = 'none';
        };
        reader.readAsDataURL(file);
    }
}

// --- Pipeline Execution ---
uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const file = fileInput.files[0];
    const dimension = dimensionInput.value || 1.0;

    if (!file) {
        alert('Please select an image first.');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('dimension', dimension);

    // Update UI for loading (Disable all inputs)
    setFormState(true);
    
    status.style.display = 'block';
    status.className = '';
    status.textContent = `Uploading and running inference at ${dimension}m scale... This may take a minute.`;

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            body: formData
        });
        const result = await response.json();

        if (result.status === 'success') {
            status.className = 'success';
            status.textContent = `✅ ${result.message}`;
        } else {
            status.className = 'error';
            status.textContent = `❌ Error: ${result.message}\n${result.error || ''}`;
        }
    } catch (err) {
        status.className = 'error';
        status.textContent = `❌ Network Error: ${err.message}`;
    } finally {
        setFormState(false);
    }
});

function setFormState(isLoading) {
    submitBtn.disabled = isLoading;
    fileInput.disabled = isLoading;
    dimensionInput.disabled = isLoading;
    
    if (isLoading) {
        submitBtn.innerHTML = '<span class="loader"></span> Processing...';
        dropZone.classList.add('disabled');
    } else {
        submitBtn.innerHTML = 'Generate 3D Model';
        dropZone.classList.remove('disabled');
    }
}
