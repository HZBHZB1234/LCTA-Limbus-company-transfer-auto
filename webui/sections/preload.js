async function preloadAllSections() {
    const sections = [
        'dashboard', 'translate', 'install', 'download', 'clean', 'fancy',
        'manage', 'config', 'proper', 'about', 'welcome', 'elder',
        'log', 'settings', 'launcher-config', 'cdn', 'test', 'speed'
    ];

    const promises = sections.map(name =>
        fetch(`sections/${name}.html`)
            .then(r => r.text())
            .then(html => {
                const container = document.getElementById(`${name}-section`);
                if (container) container.innerHTML = html;
            })
            .catch(err => console.error(`Failed to load section ${name}:`, err))
    );

    await Promise.all(promises);
}
