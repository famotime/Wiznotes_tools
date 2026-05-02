// WizNotes Exporter - Shared JS utilities

async function apiFetch(url, options) {
    try {
        const r = await fetch(url, options);
        if (r.status === 401) {
            window.location.href = '/login';
            return null;
        }
        if (!r.ok) {
            const text = await r.text();
            try { return JSON.parse(text); } catch { return null; }
        }
        return await r.json();
    } catch (e) {
        console.error('API error:', e);
        return null;
    }
}

function escHtml(s) {
    if (!s) return '';
    const el = document.createElement('span');
    el.textContent = s;
    return el.innerHTML;
}
