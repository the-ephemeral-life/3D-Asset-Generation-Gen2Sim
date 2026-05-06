const themeToggle = document.getElementById('themeToggle');
const resetBtn = document.getElementById('resetBtn');
const body = document.body;
const uploadForm = document.getElementById('uploadForm');
const fileInput = document.getElementById('fileInput');
const dimensionInput = document.getElementById('dimensionInput');
const xInput = document.getElementById('xInput');
const yInput = document.getElementById('yInput');
const zInput = document.getElementById('zInput');
const dropZone = document.getElementById('dropZone');
const preview = document.getElementById('preview');
const placeholder = document.querySelector('.upload-placeholder');
const submitBtn = document.getElementById('submitBtn');
const status = document.getElementById('status');
const downloads = document.getElementById('downloads');
const downloadGrid = document.getElementById('downloadGrid');

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

resetBtn.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to reset the spawning registry? New objects will start spawning at the origin again.')) return;
    
    try {
        const response = await fetch('/api/reset', { method: 'POST' });
        const result = await response.json();
        alert(result.message);
    } catch (err) {
        alert('Failed to reset: ' + err.message);
    }
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

fileInput.addEventListener('change', (e) => {
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
});

// --- Pipeline Execution ---
uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const file = fileInput.files[0];
    const dimension = dimensionInput.value || 1.0;
    const x = xInput.value || 0.0;
    const y = yInput.value || 0.0;
    const z = zInput.value || 0.5;

    if (!file) {
        alert('Please select an image first.');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('dimension', dimension);
    formData.append('x', x);
    formData.append('y', y);
    formData.append('z', z);

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
            
            // Show download links
            if (result.assets && Object.keys(result.assets).length > 0) {
                showDownloadLinks(result.assets);
            }
        } else {
            status.className = 'error';
            status.textContent = `❌ Error: ${result.message}\n${result.error || ''}`;
            if (downloads) downloads.style.display = 'none';
        }
    } catch (err) {
        status.className = 'error';
        status.textContent = `❌ Network Error: ${err.message}`;
        if (downloads) downloads.style.display = 'none';
    } finally {
        setFormState(false);
    }
});

function showDownloadLinks(assets) {
    if (!downloadGrid || !downloads) return;
    downloadGrid.innerHTML = '';
    downloads.style.display = 'block';
    
    const labels = {
        glb: 'GLB Mesh',
        obj: 'Visual OBJ',
        mtl: 'MTL Material',
        collision: 'Collision OBJ',
        urdf: 'URDF Robot',
        texture: 'Texture PNG'
    };

    Object.entries(assets).forEach(([key, url]) => {
        const a = document.createElement('a');
        a.href = url;
        a.download = url.split('/').pop();
        a.className = 'download-link';
        a.innerHTML = `
            <span>${labels[key] || key.toUpperCase()}</span>
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
        `;
        downloadGrid.appendChild(a);
    });
}

function setFormState(isLoading) {
    submitBtn.disabled = isLoading;
    fileInput.disabled = isLoading;
    dimensionInput.disabled = isLoading;
    xInput.disabled = isLoading;
    yInput.disabled = isLoading;
    zInput.disabled = isLoading;
    
    if (isLoading) {
        submitBtn.innerHTML = '<span class="loader"></span> Processing...';
        dropZone.classList.add('disabled');
    } else {
        submitBtn.innerHTML = 'Generate 3D Model';
        dropZone.classList.remove('disabled');
    }
}
