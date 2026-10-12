const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const selection = document.getElementById('selection');
const fileSummary = document.getElementById('fileSummary');
const fileList = document.getElementById('fileList');
const clearBtn = document.getElementById('clearBtn');
const processBtn = document.getElementById('processBtn');
const progress = document.getElementById('progress');
const result = document.getElementById('result');
const singleResult = document.getElementById('singleResult');
const originalPreview = document.getElementById('originalPreview');
const resultPreview = document.getElementById('resultPreview');
const downloadBtn = document.getElementById('downloadBtn');
const anotherBtn = document.getElementById('anotherBtn');
const errorBox = document.getElementById('errorBox');

let selectedFiles = [];
let resultBlob = null;
let resultFilename = 'background_removed.png';
let originalObjectUrl = null;
let resultObjectUrl = null;

const allowed = ['image/jpeg', 'image/png', 'image/webp'];
const formatBytes = bytes => bytes < 1024*1024 ? `${(bytes/1024).toFixed(1)} KB` : `${(bytes/1024/1024).toFixed(1)} MB`;

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.remove('hidden');
}
function hideError() { errorBox.classList.add('hidden'); }
function setFiles(files) {
  hideError();
  const valid = [...files].filter(f => allowed.includes(f.type) || /\.(jpe?g|png|webp)$/i.test(f.name));
  if (!valid.length) return showError('Please select JPG, JPEG, PNG or WEBP images.');
  selectedFiles = valid;
  fileSummary.textContent = valid.length === 1 ? valid[0].name : `${valid.length} images selected`;
  fileList.innerHTML = valid.map(f => `<div class="file-row"><span>${escapeHtml(f.name)}</span><span>${formatBytes(f.size)}</span></div>`).join('');
  selection.classList.remove('hidden');
  result.classList.add('hidden');
  processBtn.textContent = valid.length === 1 ? 'Remove Background' : `Remove Backgrounds (${valid.length})`;
}
function escapeHtml(value) { return value.replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
function reset() {
  selectedFiles = [];
  fileInput.value = '';
  selection.classList.add('hidden');
  progress.classList.add('hidden');
  result.classList.add('hidden');
  singleResult.classList.add('hidden');
  hideError();
  if (originalObjectUrl) URL.revokeObjectURL(originalObjectUrl);
  if (resultObjectUrl) URL.revokeObjectURL(resultObjectUrl);
  originalObjectUrl = resultObjectUrl = null;
  resultBlob = null;
}

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });
fileInput.addEventListener('change', () => setFiles(fileInput.files));
['dragenter','dragover'].forEach(evt => dropZone.addEventListener(evt, e => { e.preventDefault(); dropZone.classList.add('dragging'); }));
['dragleave','drop'].forEach(evt => dropZone.addEventListener(evt, e => { e.preventDefault(); dropZone.classList.remove('dragging'); }));
dropZone.addEventListener('drop', e => setFiles(e.dataTransfer.files));
clearBtn.addEventListener('click', reset);
anotherBtn.addEventListener('click', reset);

processBtn.addEventListener('click', async () => {
  if (!selectedFiles.length) return;
  hideError();
  selection.classList.add('hidden');
  result.classList.add('hidden');
  progress.classList.remove('hidden');
  try {
    const form = new FormData();
    if (selectedFiles.length === 1) {
      form.append('file', selectedFiles[0]);
      const response = await fetch('/api/remove', { method: 'POST', body: form });
      if (!response.ok) {
        let msg = 'Processing failed';
        try {
          const errData = await response.json();
          msg = errData.detail || JSON.stringify(errData);
        } catch (_) {
          try { msg = await response.text(); } catch (_) {}
        }
        throw new Error(msg || `Request failed (${response.status})`);
      }
      resultBlob = await response.blob();
      resultFilename = response.headers.get('X-Output-Filename') || `${selectedFiles[0].name.replace(/\.[^.]+$/, '')}_no_bg.png`;
      originalObjectUrl = URL.createObjectURL(selectedFiles[0]);
      resultObjectUrl = URL.createObjectURL(resultBlob);
      originalPreview.src = originalObjectUrl;
      resultPreview.src = resultObjectUrl;
      singleResult.classList.remove('hidden');
      downloadBtn.textContent = 'Download PNG';
    } else {
      selectedFiles.forEach(file => form.append('files', file));
      const response = await fetch('/api/remove-batch', { method: 'POST', body: form });
      if (!response.ok) {
        let msg = 'Batch processing failed';
        try {
          const errData = await response.json();
          msg = errData.detail || JSON.stringify(errData);
        } catch (_) {
          try { msg = await response.text(); } catch (_) {}
        }
        throw new Error(msg || `Batch failed (${response.status})`);
      }
      resultBlob = await response.blob();
      resultFilename = 'background_removed_images.zip';
      singleResult.classList.add('hidden');
      downloadBtn.textContent = 'Download ZIP';
    }
    result.classList.remove('hidden');
  } catch (err) {
    selection.classList.remove('hidden');
    showError(err.message || String(err));
  } finally {
    progress.classList.add('hidden');
  }
});

downloadBtn.addEventListener('click', () => {
  if (!resultBlob) return;
  const url = URL.createObjectURL(resultBlob);
  const a = document.createElement('a');
  a.href = url;
  a.download = resultFilename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
