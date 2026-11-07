document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('upload-form');
    const fileInput = document.getElementById('file');
    const button = document.getElementById('upload-button');
    const progress = document.querySelector('.progress');
    const bar = progress.querySelector('.progress-bar');
    const status = document.getElementById('upload-status');
    const failure = document.getElementById('upload-failure');
    try {
        localStorage.removeItem('email');
        localStorage.removeItem('access');
    } catch (_) { /* Storage may be disabled in private browsers. */ }

    function fail(message) {
        failure.textContent = message;
        failure.style.display = 'block';
        progress.style.display = 'none';
        status.textContent = '';
        button.disabled = false;
        fileInput.disabled = false;
    }

    form.addEventListener('submit', function (event) {
        event.preventDefault();
        failure.style.display = 'none';
        const file = fileInput.files[0];
        if (!file) return fail('Choose a ULog file.');
        if (file.size > Number(form.dataset.maxSize)) {
            return fail('The log exceeds the 1 GB file limit.');
        }
        const data = new FormData(form);
        button.disabled = true;
        fileInput.disabled = true;
        progress.style.display = 'flex';
        bar.style.width = '0%';
        bar.textContent = '0%';
        status.textContent = 'Reading file...';

        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/upload');
        xhr.responseType = 'json';
        xhr.upload.addEventListener('progress', function (event) {
            if (!event.lengthComputable) return;
            const percent = Math.round(event.loaded / event.total * 100);
            bar.style.width = percent + '%';
            bar.textContent = percent + '%';
            bar.setAttribute('aria-valuenow', percent);
        });
        xhr.upload.addEventListener('load', function () {
            status.textContent = 'Processing log...';
        });
        xhr.addEventListener('load', function () {
            const result = xhr.response;
            if (xhr.status >= 200 && xhr.status < 300 && result && result.url) {
                window.location.assign(result.url);
            } else {
                fail(result && result.error ? result.error :
                    xhr.status === 413 ? 'The log exceeds the 1 GB file limit.' :
                    'Could not open the log (HTTP ' + xhr.status + '). Try again.');
            }
        });
        xhr.addEventListener('error', function () {
            fail('The local viewer stopped responding. Check that it is running, then retry.');
        });
        xhr.addEventListener('abort', function () { fail('Opening the log was cancelled.'); });
        xhr.send(data);
    });
});

